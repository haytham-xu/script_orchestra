"""Image compression service — shrink JPG/PNG files to a target size."""

import os
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png'}


def _file_size_kb(path: str) -> float:
    return round(os.path.getsize(path) / 1024, 1)


def _compress_jpg(input_path: str, output_path: str, target_kb: float) -> bool:
    """Returns True if file was actually compressed (not just copied)."""
    target_bytes = int(target_kb * 1024)
    if os.path.getsize(input_path) <= target_bytes:
        with Image.open(input_path) as img:
            img.save(output_path, format='JPEG')
        return False
    quality = 90
    with Image.open(input_path) as img:
        while quality > 5:
            img.save(output_path, format='JPEG', quality=quality)
            if os.path.getsize(output_path) <= target_bytes:
                break
            quality -= 5
    return True


def _compress_png(input_path: str, output_path: str, target_kb: float) -> bool:
    target_bytes = int(target_kb * 1024)
    if os.path.getsize(input_path) <= target_bytes:
        with Image.open(input_path) as img:
            img.save(output_path, format='PNG')
        return False
    quality = 85
    with Image.open(input_path) as img:
        while quality >= 10:
            img.save(output_path, format='PNG', optimize=True, quality=quality)
            if os.path.getsize(output_path) <= target_bytes:
                break
            quality -= 10
    return True


def _resolve_output_path(input_path: str, output_dir: str | None, overwrite: bool) -> str:
    if overwrite:
        return input_path
    fname = os.path.basename(input_path)
    name, ext = os.path.splitext(fname)
    dest_dir = output_dir if output_dir else os.path.dirname(input_path)
    return os.path.join(dest_dir, name + '_compressed' + ext)


def scan_images(root_path: str) -> list:
    """Scan root_path for image files (top-level only if file, recursive if dir)."""
    root_path = root_path.strip()
    if os.path.isfile(root_path):
        ext = os.path.splitext(root_path)[1].lower()
        if ext in SUPPORTED_EXTS:
            return [root_path]
        return []
    if not os.path.isdir(root_path):
        return []
    results = []
    for entry in os.scandir(root_path):
        if entry.is_file():
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in SUPPORTED_EXTS:
                results.append(entry.path)
    return sorted(results)


def preview(root_path: str, target_kb: float) -> dict:
    files = scan_images(root_path)
    items = []
    total_before = 0.0
    eligible = 0
    for f in files:
        size_kb = _file_size_kb(f)
        total_before += size_kb
        needs = size_kb > target_kb
        if needs:
            eligible += 1
        items.append({
            'path': f,
            'name': os.path.basename(f),
            'size_kb': size_kb,
            'needs_compress': needs,
        })
    return {
        'total': len(items),
        'eligible': eligible,
        'total_size_kb': round(total_before, 1),
        'items': items,
    }


def apply_compress(root_path: str, target_kb: float, overwrite: bool, output_dir: str | None) -> dict:
    files = scan_images(root_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    results = []
    total_saved = 0.0

    for f in files:
        before_kb = _file_size_kb(f)
        if before_kb <= target_kb:
            results.append({'name': os.path.basename(f), 'before_kb': before_kb, 'after_kb': before_kb, 'skipped': True, 'error': None})
            continue
        out_path = _resolve_output_path(f, output_dir, overwrite)
        ext = os.path.splitext(f)[1].lower()
        try:
            if ext in ('.jpg', '.jpeg'):
                _compress_jpg(f, out_path, target_kb)
            else:
                _compress_png(f, out_path, target_kb)
            after_kb = _file_size_kb(out_path)
            saved = round(before_kb - after_kb, 1)
            total_saved += saved
            results.append({'name': os.path.basename(f), 'before_kb': before_kb, 'after_kb': after_kb, 'skipped': False, 'error': None})
        except Exception as e:
            results.append({'name': os.path.basename(f), 'before_kb': before_kb, 'after_kb': None, 'skipped': False, 'error': str(e)})

    compressed = sum(1 for r in results if not r['skipped'] and not r['error'])
    errors = sum(1 for r in results if r['error'])
    return {
        'total': len(results),
        'compressed': compressed,
        'skipped': len(results) - compressed - errors,
        'errors': errors,
        'total_saved_kb': round(total_saved, 1),
        'results': results,
    }
