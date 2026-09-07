"""
SyncFilterService — 3-mode selective-sync configuration.

Storage format (.fgit/sync_filter.json):
    { "decisions": { "photos": "local-only", "docs": "synced" } }

Modes:
  local-only   — never push or pull; stays on local disk only
  remote-only  — never pull; exists in cloud only (local copy is a conflict)
  synced       — bidirectional; push uploads, pull downloads (default)

Cascade rules:
  - Set a mode on a folder → all children inherit it (existing child
    decisions that are now redundant are pruned).
  - A child can only override with a MORE RESTRICTIVE mode:
      synced → remote-only   (OK: narrowing from bidirectional to cloud-only)
      synced → local-only    (FORBIDDEN: would mean local dominates a synced parent)
      local-only → anything  (FORBIDDEN: local-only is terminal)
      remote-only → synced   (FORBIDDEN: widening is not allowed)
      remote-only → local-only (FORBIDDEN: crossing from one extreme to the other)
  - Only remote-only can appear under synced.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Literal, Optional

from .index_service import IndexService

SYNC_FILTER_FILENAME = "sync_filter.json"
SyncMode = Literal['local-only', 'remote-only', 'synced']
_VALID_MODES = {'local-only', 'remote-only', 'synced'}


def _path(repo_root: str) -> str:
    return os.path.join(repo_root, ".fgit", SYNC_FILTER_FILENAME)


def load(repo_root: str) -> dict:
    p = _path(repo_root)
    if not os.path.exists(p):
        return {"decisions": {}}
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Migrate old binary format if present
    if "checked_prefixes" in data or "unchecked_overrides" in data:
        decisions: Dict[str, str] = {}
        for pref in data.get("checked_prefixes", []):
            decisions[_norm(pref)] = "synced"
        for pref in data.get("unchecked_overrides", []):
            decisions[_norm(pref)] = "local-only"
        return {"decisions": decisions}
    data.setdefault("decisions", {})
    return data


def save(repo_root: str, data: dict) -> None:
    p = _path(repo_root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _norm(p: str) -> str:
    return (p or "").replace("\\", "/").strip("/")


def _under(prefix: str, middle_path: str) -> bool:
    """True if middle_path equals prefix or is nested under it."""
    if prefix == "":
        return True
    return middle_path == prefix or middle_path.startswith(prefix + "/")


def get_mode(filt: dict, middle_path: str) -> str:
    """Longest-prefix-match over decisions dict. Default = 'synced'."""
    mp = _norm(middle_path)
    decisions: Dict[str, str] = filt.get("decisions", {})
    best_len = -1
    result = "synced"
    for prefix, mode in decisions.items():
        pn = _norm(prefix)
        if _under(pn, mp):
            ln = len(pn)
            if ln > best_len:
                best_len, result = ln, mode
    return result


def get_status(filt: dict, middle_path: str, in_local: bool, in_remote: bool) -> str:
    """Derive human-readable status from mode + existence."""
    mode = get_mode(filt, middle_path)
    if mode == "local-only":
        return "local-only · not pushed"
    if mode == "remote-only":
        if in_local and in_remote:
            return "conflict — local copy should not exist"
        return "remote-only · not pulled"
    # synced
    if in_local and in_remote:
        return "synced"
    if in_remote and not in_local:
        return "pending pull"
    if in_local and not in_remote:
        return "pending push"
    return "unknown"


def validate_mode_change(filt: dict, middle_path: str, new_mode: str) -> Optional[str]:
    """Return error string if the mode change is invalid, else None."""
    mp = _norm(middle_path)

    # Root-level paths have no parent constraint — any mode is valid.
    if "/" not in mp:
        if new_mode not in _VALID_MODES:
            return f"Unknown mode: {new_mode}"
        return None

    parent_mode = _get_parent_mode(filt, mp)

    if new_mode == "synced":
        if parent_mode in ("local-only", "remote-only"):
            return f"Cannot set synced under a {parent_mode} parent"
    elif new_mode == "local-only":
        if parent_mode == "remote-only":
            return "Cannot set local-only under a remote-only parent"
    elif new_mode == "remote-only":
        if parent_mode == "local-only":
            return "Cannot set remote-only under a local-only parent"
    else:
        return f"Unknown mode: {new_mode}"
    return None


def _get_parent_mode(filt: dict, mp: str) -> str:
    """Find the effective mode of the nearest ancestor."""
    parts = mp.split("/")
    # Walk from the most-specific parent upward
    for i in range(len(parts) - 1, 0, -1):
        parent_path = "/".join(parts[:i])
        decisions = filt.get("decisions", {})
        if parent_path in decisions:
            return decisions[parent_path]
    # No explicit parent — check the root-level default
    decisions = filt.get("decisions", {})
    if "" in decisions:
        return decisions[""]
    return "synced"  # system default


def set_mode(filt: dict, middle_path: str, mode: str) -> None:
    """Set mode for middle_path and cascade (remove now-overridden children)."""
    mp = _norm(middle_path)
    decisions: Dict[str, str] = filt.setdefault("decisions", {})
    # Remove child decisions that are now overridden
    to_remove = [p for p in list(decisions.keys()) if _under(mp, _norm(p)) and _norm(p) != mp]
    for p in to_remove:
        del decisions[p]
    decisions[mp] = mode


# ---- tree derivation (lazy, from local index + cloud index) ----------

def _both_indexes(repo_root: str):
    local = IndexService.scan_local_files(repo_root, key=None)
    cloud = IndexService.load_cloud_index(repo_root)
    return local, cloud


def _entries(index: dict) -> List[str]:
    return [_norm(e.get("middle_path", "")) for e in index.values()]


def list_children(repo_root: str, parent: str = "") -> List[dict]:
    """Return direct children (one level) under parent middle-path.

    Each child: { name, path, is_dir, in_local, in_remote, mode, status, can_set }
    """
    parent = _norm(parent)
    local, cloud = _both_indexes(repo_root)
    filt = load(repo_root)

    local_paths = _entries(local)
    cloud_paths = _entries(cloud)

    def direct_children(paths: List[str]) -> Dict[str, bool]:
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
        in_remote = name in cld_children
        mode = get_mode(filt, child_path)
        status = get_status(filt, child_path, in_local, in_remote)
        is_dir = loc_children.get(name, False) or cld_children.get(name, False)

        # Determine which modes are allowed as overrides for this child
        can_set = _allowed_overrides(filt, child_path, in_local, in_remote)

        result.append({
            "name": name,
            "path": child_path,
            "is_dir": is_dir,
            "in_local": in_local,
            "in_remote": in_remote,
            "mode": mode,
            "status": status,
            "can_set": can_set,
        })
    return result


def _allowed_overrides(filt: dict, mp: str, in_local: bool, in_remote: bool) -> List[str]:
    """Modes the user is allowed to explicitly set for this path.

    remote-only is only offered when the remote already has a copy — setting
    it on a local-only new file makes no sense (there's nothing on the remote
    to 'stay remote').
    """
    if "/" not in mp:
        # Root-level: no parent constraint, all modes allowed
        allowed = ["synced", "local-only"]
        if in_remote:
            allowed.append("remote-only")
        return allowed

    parent_mode = _get_parent_mode(filt, mp)
    if parent_mode in ("local-only", "remote-only"):
        return []  # locked by parent
    # parent is synced
    allowed = ["synced"]
    if in_remote:
        allowed.append("remote-only")
    return allowed


def refresh_defaults(repo_root: str) -> dict:
    """Ensure new local top-level folders default to synced.

    Folders with no decision yet are given 'synced' (local default).
    Remote-only folders are left without a decision (system default = synced,
    but they show as 'pending pull' since they're not local).
    """
    filt = load(repo_root)
    local, _cloud = _both_indexes(repo_root)
    decisions = filt.setdefault("decisions", {})

    top_local: set = set()
    for mp in _entries(local):
        if mp:
            top_local.add(mp.split("/", 1)[0])

    changed = False
    for folder in sorted(top_local):
        # Only add default if the folder has no decision and no parent decision
        if folder not in decisions:
            parent_mode = _get_parent_mode(filt, folder)
            if parent_mode == "synced":
                # Inherits synced naturally — no need to write an explicit decision
                pass
            # else: locked by parent mode; don't add
            _ = parent_mode  # suppress unused warning

    if changed:
        save(repo_root, filt)
    return filt


def folder_has_remote_backup(repo_root: str, middle_prefix: str) -> bool:
    """True if cloud index has any file under middle_prefix."""
    prefix = _norm(middle_prefix)
    _local, cloud = _both_indexes(repo_root)
    for mp in _entries(cloud):
        if _under(prefix, mp):
            return True
    return False
