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
import unicodedata
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


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


def _strip_brackets(name: str) -> str:
    """Strip any number of leading bracketed segments."""
    prev = None
    while prev != name:
        prev = name
        name = _BRACKET_PREFIX.sub('', name).strip()
    return name


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


def scan_and_group(
    scan_paths: list[str],
    min_group_size: int = 2,
) -> list[SeriesGroup]:
    """
    Scan each path (one level only), collect folder names, normalise, group.

    Returns only groups where at least *min_group_size* distinct folders share
    the same normalised key.  Singletons (unique series with only one folder)
    are excluded.
    """
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
        # Pick display_name: shortest raw name (usually the series title without episode)
        raws = raw_names[key]
        display = min(raws, key=len)
        groups.append(SeriesGroup(key=key, display_name=display, folders=sorted(paths)))

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
                errors.append(f"Destination already exists, skipping: {dest}")
                continue
            try:
                if not dry_run:
                    src.rename(dest)
                moved += 1
            except Exception as e:
                errors.append(f"Failed to move {src_str} → {dest}: {e}")

    return {"moved": moved, "errors": errors}
