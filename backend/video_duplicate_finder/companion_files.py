"""
Video Duplicate Finder — Companion File Operations.

When a video is deleted or moved, its sidecar files (.srt subtitle, .nfo
metadata, .jpg cover image, etc.) must travel with it. This module
implements pure-OS-level companion handling — it never touches the
duplicate-detection database.

DECOUPLED: this module must not import from duplicate_finder.

See DECISION D-07 for the rationale: companion files are NOT modeled in
`video_hashes` because they aren't candidates for deduplication. Their
sole purpose is to be carried along with the parent video file.

Companion-matching rule (intentionally simple, file-stem-based):
    given video /dir/movie.mkv and extensions [.srt, .nfo, .jpg]
    matching candidates: /dir/movie.srt, /dir/movie.nfo, /dir/movie.jpg
    (only the ones that actually exist on disk are returned)
"""
import os
import shutil
from typing import Dict, List, Optional


def _ensure_dot_prefix(ext: str) -> str:
    """Normalize '.srt' / 'srt' / '.SRT' → '.srt'."""
    if not ext:
        return ''
    ext = ext.lower()
    if not ext.startswith('.'):
        ext = '.' + ext
    return ext


def find_companion_files(video_path: str, extensions: List[str]) -> List[str]:
    """
    Find sidecar files in the same directory as `video_path` whose stem
    matches the video's stem.

    Example:
        video_path = '/movies/Inception.mkv'
        extensions = ['.srt', '.ass', '.nfo', '.jpg']
        → ['/movies/Inception.srt', '/movies/Inception.nfo']   # if those exist

    Case-sensitivity:
        - Extension matching is case-insensitive (.SRT == .srt).
        - Stem matching IS case-sensitive (so 'Inception.mkv' will NOT
          pair with 'inception.srt' on case-sensitive filesystems).
          On Windows/macOS that's effectively case-insensitive anyway.

    The video file itself is never returned (the stem matches but the ext
    is the video's, not a companion ext).
    """
    if not video_path or not extensions:
        return []

    dirname = os.path.dirname(os.path.abspath(video_path))
    basename = os.path.basename(video_path)
    stem, _ = os.path.splitext(basename)

    norm_exts = {_ensure_dot_prefix(e) for e in extensions if e}
    if not norm_exts:
        return []

    found: List[str] = []
    for ext in norm_exts:
        candidate = os.path.join(dirname, stem + ext)
        if os.path.isfile(candidate):
            found.append(candidate)
    return found


def _resolve_collision(dest_path: str) -> str:
    """
    If `dest_path` exists, append `_1`, `_2`, ... before the extension until
    a free name is found. Same strategy as duplicate_finder's delete flow.

    Caller must ensure parent directory exists.
    """
    if not os.path.exists(dest_path):
        return dest_path
    stem, ext = os.path.splitext(dest_path)
    n = 1
    while True:
        candidate = f"{stem}_{n}{ext}"
        if not os.path.exists(candidate):
            return candidate
        n += 1


def move_with_companions(video_path: str,
                         dest_video_path: str,
                         extensions: List[str]) -> Dict:
    """
    Move a video file to `dest_video_path`, taking companion files with it.

    The video itself is moved to exactly `dest_video_path` (with collision
    handling — `_N` suffix appended if needed). Companions are renamed to
    match the video's NEW stem, preserving their own extension. Example:

        video:     /src/Inception.mkv → /trash/Inception.mkv
        companion: /src/Inception.srt → /trash/Inception.srt
        companion: /src/Inception.nfo → /trash/Inception.nfo

    If the video's basename CHANGED on destination (e.g. /src/movie.mkv →
    /dst/film.mkv), companions also get the new stem:
        /src/movie.srt → /dst/film.srt

    Returns:
        {
            'video_moved_to': str,           # final destination of the video
            'companions_moved': List[dict],  # [{'src': ..., 'dst': ...}, ...]
            'errors': List[str],             # non-fatal errors (companion failures)
        }

    Raises:
        FileNotFoundError if the source video doesn't exist.
        OSError if the video move itself fails (companions only log errors).
    """
    src_video = os.path.abspath(video_path)
    if not os.path.isfile(src_video):
        raise FileNotFoundError(f"Source video not found: {src_video}")

    # Collect companions BEFORE moving the video (so paths still resolve)
    companions = find_companion_files(src_video, extensions)

    # Move video
    dest_dir = os.path.dirname(os.path.abspath(dest_video_path))
    os.makedirs(dest_dir, exist_ok=True)
    final_video_dest = _resolve_collision(os.path.abspath(dest_video_path))
    shutil.move(src_video, final_video_dest)

    # Derive new stem from the (possibly collision-resolved) final destination
    new_stem, _ = os.path.splitext(os.path.basename(final_video_dest))

    moved: List[Dict[str, str]] = []
    errors: List[str] = []
    for src_companion in companions:
        try:
            _, comp_ext = os.path.splitext(src_companion)
            comp_dest = os.path.join(dest_dir, new_stem + comp_ext)
            comp_dest = _resolve_collision(comp_dest)
            shutil.move(src_companion, comp_dest)
            moved.append({'src': src_companion, 'dst': comp_dest})
        except Exception as e:
            errors.append(f"failed to move companion {src_companion}: {e}")

    return {
        'video_moved_to': final_video_dest,
        'companions_moved': moved,
        'errors': errors,
    }


def rename_companions_in_place(old_video_path: str,
                               new_video_path: str,
                               extensions: List[str]) -> Dict:
    """
    Rename companion files when a video is renamed IN-PLACE (same directory)
    or moved to a different file with new stem.

    Used by the /replace flow: the kept video gets renamed to the anchor's
    basename; its sidecars must follow the rename.

    NOTE: This does NOT move the video itself. Call this AFTER moving/renaming
    the video file, passing both old and new paths.

    Args:
        old_video_path: pre-rename absolute video path (companions are looked
                        up from THIS path's stem/dir)
        new_video_path: post-rename absolute video path (companions are
                        renamed to match THIS path's stem/dir)
        extensions: list of companion extensions

    Returns the same shape as `move_with_companions` (minus `video_moved_to`).
    """
    old_dir = os.path.dirname(os.path.abspath(old_video_path))
    old_stem, _ = os.path.splitext(os.path.basename(old_video_path))
    new_dir = os.path.dirname(os.path.abspath(new_video_path))
    new_stem, _ = os.path.splitext(os.path.basename(new_video_path))

    moved: List[Dict[str, str]] = []
    errors: List[str] = []

    norm_exts = {_ensure_dot_prefix(e) for e in extensions if e}
    for ext in norm_exts:
        src_companion = os.path.join(old_dir, old_stem + ext)
        if not os.path.isfile(src_companion):
            continue
        try:
            os.makedirs(new_dir, exist_ok=True)
            dest_companion = os.path.join(new_dir, new_stem + ext)
            dest_companion = _resolve_collision(dest_companion)
            shutil.move(src_companion, dest_companion)
            moved.append({'src': src_companion, 'dst': dest_companion})
        except Exception as e:
            errors.append(f"failed to rename companion {src_companion}: {e}")

    return {
        'companions_moved': moved,
        'errors': errors,
    }
