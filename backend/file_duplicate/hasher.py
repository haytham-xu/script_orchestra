"""
File Duplicate — Hasher
Two-stage hashing: partial MD5 (first 64 KB) then full MD5.
Ordered by filesize DESC so large files (most valuable) are handled first.
"""
import hashlib
import os
from multiprocessing import Pool
from typing import List, Tuple

PARTIAL_READ_BYTES = 64 * 1024  # 64 KB


def _partial_hash_worker(args: Tuple[int, str]) -> Tuple[int, str | None]:
    """Worker: compute partial MD5 of first 64 KB. Returns (file_id, hex_digest | None)."""
    file_id, file_path = args
    try:
        h = hashlib.md5()
        with open(file_path, 'rb') as f:
            h.update(f.read(PARTIAL_READ_BYTES))
        return file_id, h.hexdigest()
    except Exception:
        return file_id, None


def _full_hash_worker(args: Tuple[int, str]) -> Tuple[int, str | None]:
    """Worker: compute full MD5. Returns (file_id, hex_digest | None)."""
    file_id, file_path = args
    try:
        h = hashlib.md5()
        with open(file_path, 'rb') as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return file_id, h.hexdigest()
    except Exception:
        return file_id, None


def compute_partial_hashes(tasks: List[Tuple[int, str]], workers: int = 4,
                            progress_cb=None) -> List[Tuple[int, str | None]]:
    """
    tasks: list of (file_id, file_path) — already filtered to candidates (same-size groups)
    Returns: list of (file_id, partial_hash_or_None)
    """
    results = []
    with Pool(processes=workers) as pool:
        for i, result in enumerate(pool.imap_unordered(_partial_hash_worker, tasks, chunksize=20)):
            results.append(result)
            if progress_cb:
                progress_cb(i + 1, len(tasks))
    return results


def compute_full_hashes(tasks: List[Tuple[int, str]], workers: int = 4,
                        progress_cb=None) -> List[Tuple[int, str | None]]:
    """
    tasks: list of (file_id, file_path) — already filtered (same partial hash groups)
    Returns: list of (file_id, full_hash_or_None)
    """
    results = []
    with Pool(processes=workers) as pool:
        for i, result in enumerate(pool.imap_unordered(_full_hash_worker, tasks, chunksize=10)):
            results.append(result)
            if progress_cb:
                progress_cb(i + 1, len(tasks))
    return results
