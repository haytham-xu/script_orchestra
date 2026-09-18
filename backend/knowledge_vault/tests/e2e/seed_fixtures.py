"""
Seed or clear the canonical 10-fragment E2E test dataset for Knowledge Vault.

Usage:
    python3 seed_fixtures.py --seed     # insert the 10 fixtures (idempotent)
    python3 seed_fixtures.py --clear    # delete all fixtures by tag

The 10 fixtures encode the full 8-column x 10-row view-matrix:
  non-archived: Example-Top Group (/), Example-L1-1, Example-L1-2,
                Example-L2-1, Example-ungroup (null)
  archived:     Archive-Example-Top Group (/), Archive-Example-L1-1,
                Archive-Example-L1-2, Archive-Example-L2-1,
                Archive-Example-ungroup (null)

All fixtures carry note="__kv_e2e_fixture__" so --clear can target them
without touching real data.  Named groups (l1-1, l1-2, l2-1) must already
exist in the database before running --seed.
"""

import argparse
import sys
import os

# Resolve backend/ on the path regardless of where the script is invoked from
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from knowledge_vault import repository
from knowledge_vault.entity import RawFragment

_TAG = "__kv_e2e_fixture__"
ROOT_GROUP_ID = 1


def _make(header: str, group_id, archived: bool) -> int:
    frag = RawFragment.new_instance(
        blocks=[{"type": "text", "body": header}],
        note=_TAG,
        raw_text=header,
        kind="note",
        header=header,
    )
    repository.insert_fragment(frag)
    if archived:
        repository.archive_fragment(frag.id)
    if group_id is not None:
        existing = repository.get_group_members(group_id)
        repository.set_group_members(group_id, existing + [frag.id])
    return frag.id


def seed():
    repository.init_db()

    # Check idempotency
    all_frags = repository.get_fragments(include_archived=True)
    existing_headers = {f.header for f in all_frags if f.note == _TAG}
    if existing_headers:
        print(f"Fixtures already present ({len(existing_headers)} found), skipping.")
        return

    groups = {g.name: g.id for g in repository.get_groups()}
    missing = [n for n in ("l1-1", "l1-2", "l2-1") if n not in groups]
    if missing:
        print(f"ERROR: required groups not found: {missing}. Create them first.", file=sys.stderr)
        sys.exit(1)

    ids = []
    ids.append(_make("Example-Top Group",         ROOT_GROUP_ID,       False))
    ids.append(_make("Example-L1-1",              groups["l1-1"],      False))
    ids.append(_make("Example-L1-2",              groups["l1-2"],      False))
    ids.append(_make("Example-L2-1",              groups["l2-1"],      False))
    ids.append(_make("Example-ungroup",           None,                False))
    ids.append(_make("Archive-Example-Top Group", ROOT_GROUP_ID,       True))
    ids.append(_make("Archive-Example-L1-1",      groups["l1-1"],      True))
    ids.append(_make("Archive-Example-L1-2",      groups["l1-2"],      True))
    ids.append(_make("Archive-Example-L2-1",      groups["l2-1"],      True))
    ids.append(_make("Archive-Example-ungroup",   None,                True))

    print(f"Seeded {len(ids)} fixtures: {ids}")


def clear():
    repository.init_db()
    all_frags = repository.get_fragments(include_archived=True)
    deleted = []
    for f in all_frags:
        if f.note == _TAG:
            repository.delete_fragment(f.id)
            deleted.append(f.id)
    print(f"Cleared {len(deleted)} fixtures: {deleted}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KV E2E fixture management")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", action="store_true", help="Insert the 10 canonical test fixtures")
    group.add_argument("--clear", action="store_true", help="Delete all tagged test fixtures")
    args = parser.parse_args()

    if args.seed:
        seed()
    else:
        clear()
