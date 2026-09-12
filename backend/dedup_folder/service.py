"""Dedup Folder — three deduplication strategies for folders and files."""

import os
import re
import filecmp
import shutil


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ensure_trash(trash_path: str) -> None:
    os.makedirs(trash_path, exist_ok=True)


def _move_to_trash(src: str, trash_path: str) -> str:
    """Move src into trash_path, resolving name collisions with _N suffix."""
    name = os.path.basename(src)
    dest = os.path.join(trash_path, name)
    n = 1
    while os.path.exists(dest):
        base, ext = os.path.splitext(name)
        dest = os.path.join(trash_path, f"{base}_{n}{ext}")
        n += 1
    shutil.move(src, dest)
    return dest


# ---------------------------------------------------------------------------
# Strategy 1: Cross-Dir Dedup
# Folders present in both source and duplicate dirs; move identical ones to trash
# ---------------------------------------------------------------------------

def _dirs_identical(d1: str, d2: str) -> bool:
    cmp = filecmp.dircmp(d1, d2)
    if cmp.left_only or cmp.right_only or cmp.diff_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(d1, d2, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    for sub in cmp.common_dirs:
        if not _dirs_identical(os.path.join(d1, sub), os.path.join(d2, sub)):
            return False
    return True


def cross_dir_preview(source_path: str, duplicate_path: str) -> dict:
    source_names = {e.name for e in os.scandir(source_path) if e.is_dir()}
    dup_names = {e.name for e in os.scandir(duplicate_path) if e.is_dir()}
    common = source_names & dup_names
    items = []
    for name in sorted(common):
        s = os.path.join(source_path, name)
        d = os.path.join(duplicate_path, name)
        identical = _dirs_identical(s, d)
        items.append({'name': name, 'identical': identical})
    eligible = sum(1 for i in items if i['identical'])
    return {'total': len(items), 'eligible': eligible, 'items': items}


def cross_dir_apply(source_path: str, duplicate_path: str, trash_path: str) -> dict:
    _ensure_trash(trash_path)
    preview = cross_dir_preview(source_path, duplicate_path)
    moved, errors = [], []
    for item in preview['items']:
        if not item['identical']:
            continue
        src = os.path.join(duplicate_path, item['name'])
        try:
            dest = _move_to_trash(src, trash_path)
            moved.append({'name': item['name'], 'dest': dest})
        except Exception as e:
            errors.append({'name': item['name'], 'error': str(e)})
    return {'moved': len(moved), 'errors': len(errors), 'items': moved + errors}


# ---------------------------------------------------------------------------
# Strategy 2: Name Pattern Dedup
# Finds "XXX 2", "XXX_2", "XXX copy", "XXX (2)" etc. in a single directory
# ---------------------------------------------------------------------------

_PATTERN_SUFFIXES = re.compile(
    r'^(.+?)(\s*[\s_\-](?:copy|\d+)|\s*\(\d+\)|\s*copy\s*\d*)$',
    re.IGNORECASE,
)


def _base_name(folder_name: str) -> str | None:
    m = _PATTERN_SUFFIXES.match(folder_name)
    return m.group(1).strip() if m else None


def name_pattern_preview(source_path: str) -> dict:
    all_dirs = {e.name for e in os.scandir(source_path) if e.is_dir()}
    suspects: dict[str, list[str]] = {}
    for name in sorted(all_dirs):
        base = _base_name(name)
        if base and base in all_dirs:
            suspects.setdefault(base, []).append(name)
    items = []
    for base, copies in suspects.items():
        for c in copies:
            items.append({'name': c, 'original': base})
    return {'total': len(items), 'items': items}


def name_pattern_apply(source_path: str, trash_path: str) -> dict:
    _ensure_trash(trash_path)
    preview = name_pattern_preview(source_path)
    moved, errors = [], []
    for item in preview['items']:
        src = os.path.join(source_path, item['name'])
        if not os.path.exists(src):
            continue
        try:
            dest = _move_to_trash(src, trash_path)
            moved.append({'name': item['name'], 'original': item['original'], 'dest': dest})
        except Exception as e:
            errors.append({'name': item['name'], 'error': str(e)})
    return {'moved': len(moved), 'errors': len(errors), 'items': moved + errors}


# ---------------------------------------------------------------------------
# Strategy 3: macOS File Dedup
# Files matching "name (1).ext", "name copy.ext", "name 2.ext" etc.
# ---------------------------------------------------------------------------

_MACOS_SUFFIXES = [' (1)', ' (2)', ' (3)', ' (4)', ' (5)', ' copy', ' copy 2', ' 2', ' _2', ' (1) 2']


def _macos_original(filename: str, suffix: str) -> str | None:
    name, ext = os.path.splitext(filename)
    if name.endswith(suffix):
        return name[: -len(suffix)] + ext
    return None


def macos_file_preview(source_path: str) -> dict:
    all_files = [e.name for e in os.scandir(source_path) if e.is_file()]
    file_set = set(all_files)
    items = []
    seen = set()
    for fname in sorted(all_files):
        if fname in seen:
            continue
        for suffix in _MACOS_SUFFIXES:
            original = _macos_original(fname, suffix)
            if original and original in file_set:
                src_size = os.path.getsize(os.path.join(source_path, fname))
                orig_size = os.path.getsize(os.path.join(source_path, original))
                same_size = src_size == orig_size
                items.append({
                    'name': fname,
                    'original': original,
                    'same_size': same_size,
                    'size_kb': round(src_size / 1024, 1),
                })
                seen.add(fname)
                break
    return {'total': len(items), 'items': items}


def macos_file_apply(source_path: str, trash_path: str | None, delete_directly: bool = False) -> dict:
    preview = macos_file_preview(source_path)
    if not delete_directly and trash_path:
        _ensure_trash(trash_path)
    removed, errors = [], []
    for item in preview['items']:
        path = os.path.join(source_path, item['name'])
        if not os.path.exists(path):
            continue
        try:
            if delete_directly:
                os.remove(path)
                removed.append({'name': item['name'], 'action': 'deleted'})
            else:
                dest = _move_to_trash(path, trash_path)
                removed.append({'name': item['name'], 'action': 'moved', 'dest': dest})
        except Exception as e:
            errors.append({'name': item['name'], 'error': str(e)})
    return {'removed': len(removed), 'errors': len(errors), 'items': removed + errors}
