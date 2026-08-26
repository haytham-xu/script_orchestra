"""
SyncFilterService — selective-sync configuration (tree-shaped).

The user's core need: local disk is small, so after pushing to the cloud
they don't want to keep files locally — only pull specific folders back on
demand. The sync filter is a *static* decision config: checking/unchecking a
folder declares intent but does nothing until the next push/pull.

Design:
  * The config stores only the DECISIONS, not the whole tree:
      - checked_prefixes:      middle-path prefixes that ARE synced
      - unchecked_overrides:   more-specific prefixes carved back OUT
    A path is synced iff its longest-matching prefix is a checked one
    (an unchecked override wins when more specific). This gives parent→child
    cascade for free and stays tiny for huge trees.
  * The tree itself is derived on demand from cloud_index + local_index
    (both are on-disk mirrors — no network). Remote freshness is the job of
    the separate "rebuild cloud index" action.
  * All middle-paths are relative to the repo's remote_path (== repo root),
    POSIX style. root_prefix is a cloud-API concern and never appears here.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from .index_service import IndexService, IndexEntry

SYNC_FILTER_FILENAME = "sync_filter.json"


def _path(repo_root: str) -> str:
    return os.path.join(repo_root, ".fgit", SYNC_FILTER_FILENAME)


def load(repo_root: str) -> dict:
    p = _path(repo_root)
    if not os.path.exists(p):
        return {"checked_prefixes": [], "unchecked_overrides": []}
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("checked_prefixes", [])
    data.setdefault("unchecked_overrides", [])
    return data


def save(repo_root: str, data: dict) -> None:
    with open(_path(repo_root), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _norm(p: str) -> str:
    return (p or "").replace("\\", "/").strip("/")


def _under(prefix: str, middle_path: str) -> bool:
    """True if middle_path == prefix or is nested under prefix."""
    if prefix == "":
        return True
    return middle_path == prefix or middle_path.startswith(prefix + "/")


def is_synced(filt: dict, middle_path: str) -> bool:
    """Longest-matching-prefix decision, unchecked override wins when more specific."""
    mp = _norm(middle_path)
    best_len = -1
    decision = False  # default: not synced unless a checked prefix covers it
    for pref in filt.get("checked_prefixes", []):
        pn = _norm(pref)
        if _under(pn, mp) and len(pn) > best_len:
            best_len, decision = len(pn), True
    for pref in filt.get("unchecked_overrides", []):
        pn = _norm(pref)
        if _under(pn, mp) and len(pn) >= best_len:
            # >= so a same-or-more-specific unchecked override beats checked
            best_len, decision = len(pn), False
    return decision


# ---- tree derivation (lazy, from local index + cloud index) ----------

def _both_indexes(repo_root: str):
    # Local side is scanned live (not read from local_index.json) so the tree
    # reflects the current working directory even before the first push/pull.
    local = IndexService.scan_local_files(repo_root, key=None)
    cloud = IndexService.load_cloud_index(repo_root)
    return local, cloud


def _entries(index: Dict[str, IndexEntry]) -> List[str]:
    return [_norm(e.get("middle_path", "")) for e in index.values()]


def list_children(repo_root: str, parent: str = "") -> List[dict]:
    """Return the direct children (one level) under ``parent`` middle-path.

    Merges local + cloud index. Each child:
      { name, path, is_dir, kind: local-only|remote-only|both, synced, checked }
    - synced: does the cloud have any file under this child's path
    - checked: current sync-filter decision for this child's path
    """
    parent = _norm(parent)
    local, cloud = _both_indexes(repo_root)
    filt = load(repo_root)

    local_paths = _entries(local)
    cloud_paths = _entries(cloud)

    def direct_children(paths: List[str]) -> Dict[str, bool]:
        # name -> is_dir (True if the child has deeper segments)
        out: Dict[str, bool] = {}
        prefix = parent + "/" if parent else ""
        for mp in paths:
            if parent and not mp.startswith(prefix):
                continue
            rest = mp[len(prefix):] if prefix else mp
            if not rest:
                continue
            head = rest.split("/", 1)
            name = head[0]
            is_dir = len(head) > 1
            out[name] = out.get(name, False) or is_dir
        return out

    loc_children = direct_children(local_paths)
    cld_children = direct_children(cloud_paths)

    names = sorted(set(loc_children) | set(cld_children))
    result: List[dict] = []
    for name in names:
        child_path = f"{parent}/{name}" if parent else name
        in_local = name in loc_children
        in_cloud = name in cld_children
        is_dir = loc_children.get(name, False) or cld_children.get(name, False)
        kind = ("both" if in_local and in_cloud
                else "local-only" if in_local else "remote-only")
        result.append({
            "name": name,
            "path": child_path,
            "is_dir": is_dir,
            "kind": kind,
            "synced": in_cloud,                 # remote has it (any file under it)
            "checked": is_synced(filt, child_path),
        })
    return result


def refresh_defaults(repo_root: str) -> dict:
    """Ensure new local top-level folders default to checked.

    Called on user "refresh". Uses only local + cloud index (no network).
    A local top-level folder that has no explicit decision yet is added to
    checked_prefixes (default: local = synced). Remote-only folders are left
    unchecked (absent from checked_prefixes).
    """
    filt = load(repo_root)
    local, _cloud = _both_indexes(repo_root)
    checked = set(_norm(p) for p in filt.get("checked_prefixes", []))
    unchecked = set(_norm(p) for p in filt.get("unchecked_overrides", []))

    top_local = set()
    for mp in _entries(local):
        if mp:
            top_local.add(mp.split("/", 1)[0])

    for folder in sorted(top_local):
        # only add default if the folder has no decision at all yet
        has_decision = any(_under(c, folder) or _under(folder, c) for c in checked | unchecked)
        if not has_decision:
            checked.add(folder)

    filt["checked_prefixes"] = sorted(checked)
    filt["unchecked_overrides"] = sorted(unchecked)
    save(repo_root, filt)
    return filt


def folder_has_remote_backup(repo_root: str, middle_prefix: str) -> bool:
    """True if the cloud index has any file under ``middle_prefix`` (safety check)."""
    prefix = _norm(middle_prefix)
    _local, cloud = _both_indexes(repo_root)
    for mp in _entries(cloud):
        if _under(prefix, mp):
            return True
    return False


def unsynced_local_files(repo_root: str) -> List[dict]:
    """Local files whose middle_path is currently NOT synced (checked=false).

    Used by pull to move now-excluded files to the unsynced buffer. Works at
    file granularity so both top-level and nested un-checks are handled.
    Returns [{middle_path, has_remote_backup}].
    """
    local, cloud = _both_indexes(repo_root)
    filt = load(repo_root)
    cloud_paths = set(_entries(cloud))
    out: List[dict] = []
    for mp in _entries(local):
        if mp and not is_synced(filt, mp):
            out.append({
                "middle_path": mp,
                "has_remote_backup": mp in cloud_paths,
            })
    return out
