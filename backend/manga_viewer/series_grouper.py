"""
Series Grouper — scan flat directories and group folder names that belong to the
same manga series (different volumes/chapters).

Normalisation pipeline (applied before grouping):
  1. Strip leading bracketed tags: [xxx] / 【xxx】 / (xxx)
  2. Collapse whitespace
  3. Strip trailing volume/chapter markers:
       - Arabic digits:      "Title 3", "Title Vol.3", "Title v3", "Title #3"
       - Chinese numerals:   "Title 第三集", "Title 第3话"
       - Season/arc labels:  "Title Season 2", "Title Arc III"
       - Episode subtitles:  "Title 3 - Subtitle" (strip subtitle after dash)
  4. Lower-case + strip
"""

import os
import re
import shutil
import unicodedata
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from natsort import natsorted


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

_BRACKET_PREFIX = re.compile(
    r'^(?:\[[^\]]*\]|【[^】]*】|\([^)]*\))\s*',
    re.UNICODE,
)

_CJK_EPISODE_CHARS = r'[集话話章卷巻部回期册冊篇]'

_VOLUME_SUFFIX = re.compile(
    # Must be preceded by at least one non-whitespace non-digit character so we
    # never consume the entire name (e.g. a one-word title like "xxxxx 1").
    r'(?<=\S)'
    r'(?<!\d)'          # not preceded by a digit (avoids eating "Title123")
    r'[\s_\-\.]*'
    r'(?:'
    # Chinese ordinal: 第N集/话/章/卷…  or  集N / 话N …
    r'第\s*[0-9零一二三四五六七八九十百千]+\s*' + _CJK_EPISODE_CHARS + r'?'
    r'|' + _CJK_EPISODE_CHARS + r'\s*[0-9零一二三四五六七八九十百千]+'
    # Season / Arc / Part label (English)
    r'|(?:season|arc|part|vol(?:ume)?|ep(?:isode)?|chapter|ch|v)\s*\.?\s*[0-9ivxlcdm]+'
    # Plain number or roman numeral — only when preceded by a space/separator
    r'|(?<=[\s_\-\.])\s*#?\s*[0-9ivxlcdm]+'
    r')'
    # optional subtitle after dash/colon/em-dash following the episode marker
    r'(?:\s*[-:—–]\s*.+)?'
    r'$',
    re.IGNORECASE | re.UNICODE,
)

_TRAILING_DASH_SUBTITLE = re.compile(
    r'\s*[-:—–]\s*.+$',
    re.UNICODE,
)

_MULTI_SPACE = re.compile(r'\s+')
_NUM_RE = re.compile(r'[0-9]+')
_CJK_NUM_RE = re.compile(r'[零一二三四五六七八九十]+')
_CJK_DIGIT_MAP = {
    '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
}


def _cjk_to_int(s: str) -> Optional[int]:
    """Convert a CJK numeral string (up to 99) to int, or None if unsupported."""
    if not s:
        return None
    if s == '十':
        return 10
    if len(s) == 1:
        return _CJK_DIGIT_MAP.get(s)
    if s.startswith('十') and len(s) == 2:
        v = _CJK_DIGIT_MAP.get(s[1])
        return 10 + v if v is not None else None
    if s.endswith('十') and len(s) == 2:
        v = _CJK_DIGIT_MAP.get(s[0])
        return v * 10 if v is not None else None
    if len(s) == 3 and s[1] == '十':
        a, b = _CJK_DIGIT_MAP.get(s[0]), _CJK_DIGIT_MAP.get(s[2])
        return a * 10 + b if a is not None and b is not None else None
    return None


def _find_nums(text: str) -> list[tuple[int, str, int, int]]:
    """Return all numbers in *text* as (int_value, display_str, start, end).

    Arabic digits are tried first.  If none found, CJK numerals are used and
    converted to Arabic strings so the generated suggestion always uses Arabic.
    """
    hits = [(int(m.group(0)), m.group(0), m.start(), m.end())
            for m in _NUM_RE.finditer(text)]
    if hits:
        return hits
    out = []
    for m in _CJK_NUM_RE.finditer(text):
        v = _cjk_to_int(m.group(0))
        if v is not None:
            out.append((v, str(v), m.start(), m.end()))
    return out


def _extract_bracket_prefix(name: str) -> str:
    """Extract all consecutive leading bracket segments as one string (including
    the trailing whitespace that follows them), e.g. '[3D][tag] ' from
    '[3D][tag] Title 第1話'."""
    s = name
    result = ''
    while True:
        m = _BRACKET_PREFIX.match(s)
        if not m:
            break
        result += m.group(0)
        s = s[m.end():]
    return result


def _strip_brackets(name: str) -> str:
    """Strip any number of leading bracketed segments."""
    prev = None
    while prev != name:
        prev = name
        name = _BRACKET_PREFIX.sub('', name).strip()
    return name


def _strip_volume_suffix(s: str) -> str:
    """Iteratively remove volume/chapter suffixes (same logic as normalize_name,
    but without lowercasing so casing is preserved for display)."""
    prev = None
    while prev != s:
        prev = s
        m = _VOLUME_SUFFIX.search(s)
        if m:
            s = s[:m.start()].strip()
    s = _TRAILING_DASH_SUBTITLE.sub('', s).strip()
    return s


def _extract_suffix_parts(raw: str):
    """Return (before_num, num_str, after_num) for the volume suffix in *raw*, or None."""
    no_bracket = _strip_brackets(raw).strip()
    base = _strip_volume_suffix(no_bracket)
    if not base or base == no_bracket:
        return None
    suffix = no_bracket[len(base):]
    m = _NUM_RE.search(suffix)
    if not m:
        return None
    return suffix[:m.start()], m.group(0), suffix[m.end():]


def _generate_suggestions(display_name: str, raws: list[str]) -> list[str]:
    """Return alternative name suggestions for a series group.

    Generates a range-notation suggestion when all member folder names share
    the same text *before* their first volume/chapter number.  Numbers are
    collected from every suffix (including range-format like "1-40"), and
    the global min/max are used to build the suggestion.

    Examples:
      [3D]秘密 1-40, 46-47, 49-49  →  [3D]秘密 1-49
      XXX 02-subtitle, 03-sub, 04  →  XXX 02-04
      [YYY]xxxx 第1话, 第2话        →  [YYY]xxxx 第1-2话  (unit preserved)
    """
    befores: list[str] = []
    afters: list[str] = []
    all_nums: list[tuple[int, str]] = []

    for raw in raws:
        no_bracket = _strip_brackets(raw).strip()
        base = _strip_volume_suffix(no_bracket)
        if not base or base == no_bracket:
            return []
        suffix = no_bracket[len(base):]
        nums = _find_nums(suffix)
        if not nums:
            return []
        first = nums[0]
        befores.append(suffix[:first[2]])
        afters.append(suffix[first[3]:] if len(nums) == 1 else '')
        for v, s, _, _ in nums:
            all_nums.append((v, s))

    if not all_nums:
        return []
    if len(set(befores)) != 1:
        return []
    before = befores[0]
    after = afters[0] if len(set(afters)) == 1 else ''

    min_num = min(all_nums, key=lambda x: x[0])
    max_num = max(all_nums, key=lambda x: x[0])
    if min_num[0] == max_num[0]:
        return []

    return [f"{display_name}{before}{min_num[1]}-{max_num[1]}{after}"]


def normalize_name(name: str) -> str:
    """Return a canonical series key for *name* (a folder basename)."""
    s = name.strip()
    s = _strip_brackets(s)
    # Try to remove volume/chapter suffix iteratively (some names have multiple)
    prev = None
    while prev != s:
        prev = s
        m = _VOLUME_SUFFIX.search(s)
        if m:
            s = s[:m.start()].strip()
    # If only a subtitle remains after a dash, strip it too
    s = _TRAILING_DASH_SUBTITLE.sub('', s).strip()
    # Re-strip brackets that may now be trailing (e.g. name ends with "[tag]")
    s = _strip_brackets(s)
    s = _MULTI_SPACE.sub(' ', s).strip().lower()
    return s


# ---------------------------------------------------------------------------
# Scan + group
# ---------------------------------------------------------------------------

@dataclass
class SeriesGroup:
    key: str                        # normalised key
    display_name: str               # the most common raw name (heuristic)
    folders: list[str] = field(default_factory=list)   # abs paths
    suggestions: list[str] = field(default_factory=list)  # alternative name chips


def _longest_common_prefix(names: list[str]) -> str:
    """Return the longest common prefix of *names*, stripped of trailing separators."""
    if not names:
        return ""
    prefix = os.path.commonprefix(names)
    # Strip trailing separators / spaces so the name looks clean
    return prefix.rstrip(" _-–—:.").strip()


def scan_and_group(
    scan_paths: list[str],
    min_group_size: int = 2,
    whitelist: Optional[dict] = None,
) -> list[SeriesGroup]:
    """
    Scan each path (one level only), collect folder names, normalise, group.

    Returns only groups where at least *min_group_size* distinct folders share
    the same normalised key.  Singletons (unique series with only one folder)
    are excluded.  Groups whose key appears in *whitelist* are also excluded.
    """
    whitelist = whitelist or {}

    # key → list of abs paths
    buckets: dict[str, list[str]] = {}
    # key → list of raw basenames (to pick display_name)
    raw_names: dict[str, list[str]] = {}

    for scan_path in scan_paths:
        root = Path(scan_path)
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            basename = entry.name
            key = normalize_name(basename)
            if not key:
                continue
            buckets.setdefault(key, []).append(str(entry))
            raw_names.setdefault(key, []).append(basename)

    groups: list[SeriesGroup] = []
    for key, paths in buckets.items():
        if len(paths) < min_group_size:
            continue
        if key in whitelist:
            continue
        raws = raw_names[key]
        # If all raws share the same leading bracket prefix, keep it in the
        # display name (e.g. "[YYY]xxxx" instead of just "xxxx").
        bracket_prefixes = {_extract_bracket_prefix(r) for r in raws}
        common_bracket = next(iter(bracket_prefixes)) if len(bracket_prefixes) == 1 else ''

        # Strip brackets then volume suffixes before computing LCP, so we get
        # "xxxx" instead of "xxxx 第" as the base name.
        clean = [_strip_volume_suffix(_strip_brackets(r).strip()) for r in raws]
        base = _longest_common_prefix(clean) or min(clean, key=len)
        display = (common_bracket + base) if common_bracket else base
        suggestions = _generate_suggestions(display, raws)
        groups.append(SeriesGroup(key=key, display_name=display, folders=natsorted(paths),
                                  suggestions=suggestions))

    # Sort groups by display_name for stable UI ordering
    groups.sort(key=lambda g: g.display_name.lower())
    return groups


# ---------------------------------------------------------------------------
# Move / execute
# ---------------------------------------------------------------------------

def execute_grouping(
    groups: list[dict],
    output_path: str,
    dry_run: bool = False,
) -> dict:
    """
    Move folders into <output_path>/<series_folder_name>/.

    *groups* is a list of dicts (from the API request):
        {
          "key": str,
          "target_name": str,   # the folder name to create under output_path
          "folders": [str, ...]  # abs paths to move
        }

    Returns {"moved": int, "errors": [str]}.
    """
    out = Path(output_path)
    moved = 0
    errors: list[str] = []

    for g in groups:
        target_name = (g.get("target_name") or g.get("key") or "").strip()
        if not target_name:
            errors.append(f"Group missing target_name: {g}")
            continue
        dest_dir = out / target_name
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        for src_str in g.get("folders", []):
            src = Path(src_str)
            if not src.exists():
                errors.append(f"Source not found: {src_str}")
                continue
            dest = dest_dir / src.name
            if dest.exists():
                base = src.name
                counter = 2
                while dest.exists():
                    dest = dest_dir / f"{base}_{counter}"
                    counter += 1
            try:
                if not dry_run:
                    shutil.move(str(src), str(dest))
                moved += 1
            except Exception as e:
                errors.append(f"Failed to move {src_str} → {dest}: {e}")

    return {"moved": moved, "errors": errors}
