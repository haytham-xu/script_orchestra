"""
IndexService — local & cloud file index management (REQUIREMENTS §3.9).

Responsibilities:
    * Scan a repo's local files → produce local_index.json
    * Load / save local_index.json and cloud_index.json (on disk mirrors)
    * cloud_index.json is stored *decrypted* on the local mirror; the
      upload/download layer handles encryption transparently
    * Compute (added / modified / deleted) between local and cloud

The index key is ``md5(middle_path)``; entries carry ``size`` for
change detection (REQUIREMENTS §3.10). For ENCRYPTED repos the entry
also carries ``encoded_path`` (hmac16-encoded) so the sync layer can
locate the file on the cloud.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TypedDict

from ..crypto import (
    AesGcmDecryptStream,
    AesGcmEncryptStream,
    encode_middle_path,
)


CLOUD_INDEX_FILENAME = "cloud_index.json"


class IndexEntry(TypedDict, total=False):
    middle_path: str    # POSIX-style, relative to repo root
    encoded_path: str   # ENCRYPTED repo: hmac16-encoded; ORIGINAL: same as middle_path
    size: int


@dataclass
class DiffResult:
    """Result of comparing two indexes."""
    added: List[IndexEntry] = field(default_factory=list)      # in A, not in B
    deleted: List[IndexEntry] = field(default_factory=list)    # in B, not in A
    modified: List[IndexEntry] = field(default_factory=list)   # in both, size differs


def _hash_middle_path(middle_path: str) -> str:
    return hashlib.md5(middle_path.encode("utf-8")).hexdigest()


def _normalize_middle_path(p: str) -> str:
    return p.replace("\\", "/").lstrip("/")


class IndexService:
    """Static helpers; no instance state."""

    # ---- local scan ---------------------------------------------------

    @staticmethod
    def scan_local_files(
        local_root: str,
        key: Optional[bytes] = None,
    ) -> Dict[str, IndexEntry]:
        """Walk ``local_root``, produce ``{path_hash: IndexEntry}``.

        Skips any directory or file whose name starts with '.', so the
        ``.fgit/`` internal folder is naturally excluded.

        If ``key`` is provided (ENCRYPTED repo), each entry also carries
        the hmac16-encoded ``encoded_path``.
        """
        index: Dict[str, IndexEntry] = {}
        for cur_dir, dirnames, filenames in os.walk(local_root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for filename in filenames:
                if filename.startswith("."):
                    continue
                full = os.path.join(cur_dir, filename)
                rel = os.path.relpath(full, local_root)
                middle_path = _normalize_middle_path(rel)
                try:
                    size = os.path.getsize(full)
                except OSError as exc:
                    print(f"[IndexService] cannot stat {full}: {exc}")
                    continue
                entry: IndexEntry = {
                    "middle_path": middle_path,
                    "size": size,
                }
                if key is not None:
                    entry["encoded_path"] = encode_middle_path(key, middle_path)
                else:
                    entry["encoded_path"] = middle_path
                index[_hash_middle_path(middle_path)] = entry
        return index

    # ---- local_index.json read/write ---------------------------------

    @staticmethod
    def load_local_index(repo_root: str) -> Dict[str, IndexEntry]:
        path = os.path.join(repo_root, ".fgit", "local_index.json")
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_local_index(repo_root: str, index: Dict[str, IndexEntry]) -> None:
        path = os.path.join(repo_root, ".fgit", "local_index.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    # ---- cloud_index.json read/write (local mirror) ------------------

    @staticmethod
    def load_cloud_index(repo_root: str) -> Dict[str, IndexEntry]:
        path = os.path.join(repo_root, ".fgit", "cloud_index.json")
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_cloud_index(repo_root: str, index: Dict[str, IndexEntry]) -> None:
        path = os.path.join(repo_root, ".fgit", "cloud_index.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    # ---- cloud_index (de)serialization for transport -----------------
    # ENCRYPTED repos: the JSON is AES-GCM encrypted with the repo key
    # before upload, and decrypted after download. ORIGINAL repos ship
    # the JSON verbatim. (REQUIREMENTS §3.9)

    @staticmethod
    def serialize_cloud_index_for_upload(
        index: Dict[str, IndexEntry],
        key: Optional[bytes] = None,
    ) -> bytes:
        raw = json.dumps(index, ensure_ascii=False).encode("utf-8")
        if key is None:
            return raw
        # Encrypt with the same stream format the sync layer uses
        enc = AesGcmEncryptStream(io.BytesIO(raw), key)
        return enc.read()

    @staticmethod
    def deserialize_cloud_index_after_download(
        payload: bytes,
        key: Optional[bytes] = None,
    ) -> Dict[str, IndexEntry]:
        if key is None:
            return json.loads(payload.decode("utf-8"))
        dec = AesGcmDecryptStream(io.BytesIO(payload), key)
        raw = dec.read()
        return json.loads(raw.decode("utf-8"))

    # ---- diff --------------------------------------------------------

    @staticmethod
    def diff(
        a: Dict[str, IndexEntry],
        b: Dict[str, IndexEntry],
    ) -> DiffResult:
        """Compute ``a`` vs ``b``.

        Convention:
            * added    = in ``a`` but not ``b``
            * deleted  = in ``b`` but not ``a``
            * modified = in both, size differs (entry from ``a`` is returned)
        """
        result = DiffResult()
        for h, entry in a.items():
            if h not in b:
                result.added.append(entry)
            elif entry.get("size") != b[h].get("size"):
                result.modified.append(entry)
        for h, entry in b.items():
            if h not in a:
                result.deleted.append(entry)
        return result
