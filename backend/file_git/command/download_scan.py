"""
Download Scan — pre-stage preview for Manual Download.

Read-only diff that lists entries which exist on the cloud (cloud_index)
but are missing locally ("remote exists, local missing"). Produces a flat
``.fgit/pending_download.json`` the UI browses as a lazy tree.

No lock is taken: this is a preview. It reads the LOCAL cloud_index mirror
(the same source the home-page sync view uses) plus a fresh local scan, so
it needs no network call.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..crypto import encode_middle_path
from ..service import IndexService
from .context import build_context

PENDING_DOWNLOAD_FILENAME = "pending_download.json"


@dataclass
class DownloadScanResult:
    ok: bool
    message: str = ""
    count: int = 0
    total_size: int = 0


def command_download_scan(repo_id: str) -> DownloadScanResult:
    """Compute the remote-only set and persist it to pending_download.json."""
    ctx = build_context(repo_id)

    cloud_index = IndexService.load_cloud_index(ctx.repo_root)
    local_index = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)

    # added = present in cloud, absent locally.
    added = IndexService.diff(cloud_index, local_index).added

    entries: List[dict] = [
        {
            "middle_path": e["middle_path"],
            "encoded_path": e.get("encoded_path", e["middle_path"]),
            "size": int(e.get("size") or 0),
        }
        for e in added
    ]
    total_size = sum(e["size"] for e in entries)

    pending_path = os.path.join(ctx.repo_root, ".fgit", PENDING_DOWNLOAD_FILENAME)
    os.makedirs(os.path.dirname(pending_path), exist_ok=True)
    with open(pending_path, "w", encoding="utf-8") as f:
        json.dump({
            "scanned_at": time.time(),
            "count": len(entries),
            "total_size": total_size,
            "entries": entries,
        }, f, ensure_ascii=False)

    return DownloadScanResult(
        ok=True,
        message=f"Found {len(entries)} remote-only item(s).",
        count=len(entries),
        total_size=total_size,
    )


def download_scan_children(repo_id: str, path: str = "") -> List[dict]:
    """Return the DIRECT children under ``path`` from the last scan.

    Each node: ``{name, path, is_dir, size, encoded_path}``.
      * file  → the entry's own encoded_path + size
      * dir   → encoded_path = encode_middle_path(key, dir_path); size = sum of
                all descendant sizes under it

    Returns ``[]`` if no scan has been run yet.
    """
    ctx = build_context(repo_id)
    pending_path = os.path.join(ctx.repo_root, ".fgit", PENDING_DOWNLOAD_FILENAME)
    if not os.path.isfile(pending_path):
        return []

    with open(pending_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries: List[dict] = data.get("entries", [])

    prefix = path.rstrip("/") + "/" if path else ""

    # Aggregate direct children.
    dir_size: Dict[str, int] = {}
    file_node: Dict[str, dict] = {}
    for e in entries:
        mp = e["middle_path"]
        if prefix and not mp.startswith(prefix):
            continue
        rest = mp[len(prefix):]
        if not rest:
            continue
        head, _, tail = rest.partition("/")
        child_path = f"{prefix}{head}"
        if tail:
            # descendant → head is a directory
            dir_size[child_path] = dir_size.get(child_path, 0) + int(e.get("size") or 0)
        else:
            # direct file
            file_node[child_path] = {
                "name": head,
                "path": child_path,
                "is_dir": False,
                "size": int(e.get("size") or 0),
                "encoded_path": e.get("encoded_path", mp),
            }

    nodes: List[dict] = []
    for child_path, size in dir_size.items():
        name = child_path.rsplit("/", 1)[-1]
        if ctx.key is not None:
            encoded = encode_middle_path(ctx.key, child_path)
        else:
            encoded = child_path
        nodes.append({
            "name": name,
            "path": child_path,
            "is_dir": True,
            "size": size,
            "encoded_path": encoded,
        })
    nodes.extend(file_node.values())

    # Dirs first, then alphabetical.
    nodes.sort(key=lambda n: (not n["is_dir"], n["name"].lower()))
    return nodes
