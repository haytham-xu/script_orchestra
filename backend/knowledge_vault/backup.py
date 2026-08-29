"""Knowledge Vault — lightweight DB backup.

After a write, snapshot the SQLite file into .backups/ (timestamped, keeping the
most recent N). Cheap insurance against accidental deletion/corruption — the raw
layer is the source of truth, so we never want to lose it.
"""
import os
import shutil
import glob

from . import settings_manager

_KEEP = 10  # how many timestamped snapshots to retain


def _backup_dir() -> str:
    d = os.path.join(os.path.dirname(settings_manager.get_db_path()), ".backups")
    os.makedirs(d, exist_ok=True)
    return d


def snapshot(tag: str = "") -> str:
    """Copy the current db into .backups/ with a timestamped name. Returns the
    backup path, or '' if there's nothing to back up."""
    db = settings_manager.get_db_path()
    if not os.path.exists(db):
        return ""
    # Timestamp from file mtime (Date.now is fine here — plain module, not a workflow).
    import time
    ts = time.strftime("%Y%m%d_%H%M%S")
    name = f"knowledge_vault_{ts}{('_' + tag) if tag else ''}.db"
    dest = os.path.join(_backup_dir(), name)
    try:
        shutil.copy2(db, dest)
    except OSError as exc:
        print(f"[knowledge_vault] backup failed: {exc}")
        return ""
    _prune()
    return dest


def _prune() -> None:
    backups = sorted(glob.glob(os.path.join(_backup_dir(), "knowledge_vault_*.db")))
    for old in backups[:-_KEEP]:
        try:
            os.remove(old)
        except OSError:
            pass


def list_backups() -> list:
    return sorted(glob.glob(os.path.join(_backup_dir(), "knowledge_vault_*.db")), reverse=True)
