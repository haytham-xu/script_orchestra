import os
from . import repository


def _strip_keywords(name: str, keywords: list) -> str:
    result = name
    for kw in keywords:
        result = result.replace(kw, '')
    return result.strip().strip(' _-')


def _resolve_name(parent_dir: str, new_name: str, exclude_path: str) -> str:
    """Return a name that does not collide with existing siblings (excluding the source folder)."""
    candidate = new_name
    n = 1
    while True:
        target = os.path.join(parent_dir, candidate)
        if not os.path.exists(target) or target == exclude_path:
            return candidate
        candidate = f"{new_name}_{n}"
        n += 1


def get_keywords() -> list:
    return repository.get_all()


def add_keyword(kw: str) -> bool:
    kw = kw.strip()
    if not kw:
        return False
    return repository.add(kw)


def delete_keyword(kw: str):
    repository.delete(kw)


def import_keywords(text: str) -> int:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return repository.import_bulk(lines)


def preview_clean(root_path: str) -> list:
    """
    Walk root_path one level deep (direct children only).
    Returns list of dicts for folders whose name changes after keyword stripping.
    """
    keywords = repository.get_all()
    if not keywords or not os.path.isdir(root_path):
        return []

    items = []
    # Collect names first so conflict check is aware of all siblings
    try:
        entries = [e for e in os.scandir(root_path) if e.is_dir()]
    except PermissionError:
        return []

    seen_resolved = {}  # new_name -> count, to detect multi-conflict within the batch

    for entry in entries:
        old_name = entry.name
        new_name = _strip_keywords(old_name, keywords)

        if new_name == old_name or not new_name:
            continue

        conflict = os.path.exists(os.path.join(root_path, new_name)) and \
                   os.path.join(root_path, new_name) != entry.path

        # Also check if another item in this same batch resolves to the same name
        base_conflict = conflict or (new_name in seen_resolved)

        if base_conflict:
            # Find a free suffix considering both disk and current batch
            n = 1
            resolved = new_name
            while True:
                candidate = f"{new_name}_{n}" if n > 1 else new_name
                # check within batch
                if candidate not in seen_resolved:
                    # check on disk
                    target = os.path.join(root_path, candidate)
                    if not os.path.exists(target) or target == entry.path:
                        resolved = candidate
                        break
                n += 1
        else:
            resolved = new_name

        seen_resolved[resolved] = True

        items.append({
            'old_name': old_name,
            'new_name': new_name,
            'conflict': base_conflict,
            'resolved': resolved,
        })

    return items


def apply_clean(root_path: str) -> dict:
    """Rename folders on disk. Returns {renamed, skipped, errors}."""
    keywords = repository.get_all()
    if not keywords or not os.path.isdir(root_path):
        return {'renamed': 0, 'skipped': 0, 'errors': []}

    # Use os.walk bottom-up so nested folders rename before parents
    renamed = 0
    skipped = 0
    errors = []

    # Only top-level children (one level) for now — consistent with preview
    try:
        entries = sorted([e for e in os.scandir(root_path) if e.is_dir()], key=lambda e: e.name)
    except PermissionError as ex:
        return {'renamed': 0, 'skipped': 0, 'errors': [str(ex)]}

    for entry in entries:
        old_name = entry.name
        new_name = _strip_keywords(old_name, keywords)

        if new_name == old_name or not new_name:
            skipped += 1
            continue

        resolved = _resolve_name(root_path, new_name, entry.path)
        target_path = os.path.join(root_path, resolved)

        try:
            os.rename(entry.path, target_path)
            renamed += 1
        except Exception as ex:
            errors.append({'folder': old_name, 'error': str(ex)})

    return {'renamed': renamed, 'skipped': skipped, 'errors': errors}
