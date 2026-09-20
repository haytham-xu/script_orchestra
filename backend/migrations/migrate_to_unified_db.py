"""
Migrate all per-tool SQLite databases into the single unified DB.

Workflow (four phases, run in order by default):
  1. backup   — copy target DB to a timestamped .bak file
  2. migrate  — copy rows from each source .db into the unified DB
  3. verify   — compare row counts: source vs destination
  4. report   — print a full report including which old .db files can be deleted

Usage:
    cd backend
    python migrations/migrate_to_unified_db.py [options]

Options:
    --dry-run       Print what would be done; write nothing
    --backup-only   Only run phase 1 (backup)
    --verify-only   Only run phases 3+4 (verify + report); no backup, no copy
    --no-backup     Skip backup (not recommended)
    --report-only   Only print the deletion report for old .db files

Exit codes:
    0  success (or dry-run)
    1  one or more row-count mismatches detected
    2  backup failed
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).parent.parent
TARGET_DB = Path(os.environ.get("DB_PATH", str(BACKEND_DIR / "data" / "script_orchestra.db")))

# ---------------------------------------------------------------------------
# Migration manifest
# Each entry: (source_db_path, old_table_name, new_table_name)
# ---------------------------------------------------------------------------

MIGRATIONS = [
    # memory_curve
    (BACKEND_DIR / "memory_curve/memory_curve.db",          "card",                         "memory_curve_card"),

    # assistant
    (BACKEND_DIR / "assistant/assistant.db",                "conversations",                "assistant_conversations"),
    (BACKEND_DIR / "assistant/assistant.db",                "messages",                     "assistant_messages"),
    (BACKEND_DIR / "assistant/assistant.db",                "attachments",                  "assistant_attachments"),
    (BACKEND_DIR / "assistant/assistant.db",                "kb_sources",                   "assistant_kb_sources"),
    (BACKEND_DIR / "assistant/assistant.db",                "kb_documents",                 "assistant_kb_documents"),
    (BACKEND_DIR / "assistant/assistant.db",                "kb_chunks",                    "assistant_kb_chunks"),

    # apprentice
    (BACKEND_DIR / "apprentice/apprentice.db",              "task",                         "apprentice_task"),
    (BACKEND_DIR / "apprentice/apprentice.db",              "memory_short",                 "apprentice_memory_short"),
    (BACKEND_DIR / "apprentice/apprentice.db",              "memory_long",                  "apprentice_memory_long"),
    (BACKEND_DIR / "apprentice/apprentice.db",              "human_message",                "apprentice_human_message"),
    (BACKEND_DIR / "apprentice/apprentice.db",              "integration_event",            "apprentice_integration_event"),
    (BACKEND_DIR / "apprentice/apprentice.db",              "red_line",                     "apprentice_red_line"),

    # file_pipeline
    (BACKEND_DIR / "file_pipeline/file_pipeline.db",        "tool",                         "file_pipeline_tool"),
    (BACKEND_DIR / "file_pipeline/file_pipeline.db",        "pipeline",                     "file_pipeline_pipeline"),

    # file_git
    (BACKEND_DIR / "file_git/file_git.db",                  "repos",                        "file_git_repos"),

    # roadmap
    (BACKEND_DIR / "roadmap/tasks.db",                      "tasks",                        "roadmap_tasks"),
    (BACKEND_DIR / "roadmap/tasks.db",                      "settings",                     "roadmap_settings"),

    # file_tracker
    (BACKEND_DIR / "file_tracker/file_tracker.db",          "tracked_file",                 "file_tracker_tracked_file"),

    # clean_keyword
    (BACKEND_DIR / "clean_keyword/clean_keyword.db",        "keyword",                      "clean_keyword_keyword"),

    # translator
    (BACKEND_DIR / "translator/translator.db",              "translation_history",          "translator_translation_history"),
    (BACKEND_DIR / "translator/translator.db",              "learning_point",               "translator_learning_point"),

    # claude_bridge
    (BACKEND_DIR / "claude_bridge/claude_bridge.db",        "messages",                     "claude_bridge_messages"),

    # knowledge_vault
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db",    "raw_fragment",                 "knowledge_vault_raw_fragment"),
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db",    "fragment_vector",              "knowledge_vault_fragment_vector"),
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db",    "label",                        "knowledge_vault_label"),
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db",    "fragment_label",               "knowledge_vault_fragment_label"),
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db",    "fragment_group",               "knowledge_vault_fragment_group"),
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db",    "fragment_group_member",        "knowledge_vault_fragment_group_member"),

    # manga_viewer
    (BACKEND_DIR / "manga_viewer/queues.db",                "read_queue",                   "manga_viewer_read_queue"),
    (BACKEND_DIR / "manga_viewer/queues.db",                "snooze_queue",                 "manga_viewer_snooze_queue"),

    # browser_agent
    (BACKEND_DIR / "browser_agent/browser_agent.db",        "browser_tab",                  "browser_agent_browser_tab"),
    (BACKEND_DIR / "browser_agent/browser_agent.db",        "archived_tab",                 "browser_agent_archived_tab"),
    (BACKEND_DIR / "browser_agent/browser_agent.db",        "tab_label",                    "browser_agent_tab_label"),
    (BACKEND_DIR / "browser_agent/browser_agent.db",        "archived_tab_label",           "browser_agent_archived_tab_label"),
    (BACKEND_DIR / "browser_agent/browser_agent.db",        "tab_archive_batch",            "browser_agent_tab_archive_batch"),
    (BACKEND_DIR / "browser_agent/browser_agent.db",        "tab_archive_vector",           "browser_agent_tab_archive_vector"),

    # duplicate_finder
    (BACKEND_DIR / "duplicate_finder/phash_cache.db",       "image_hashes",                 "duplicate_finder_image_hashes"),
    (BACKEND_DIR / "duplicate_finder/phash_cache.db",       "whitelist",                    "duplicate_finder_whitelist"),
    (BACKEND_DIR / "duplicate_finder/phash_cache.db",       "whitelist_groups",             "duplicate_finder_whitelist_groups"),
    (BACKEND_DIR / "duplicate_finder/phash_cache.db",       "whitelist_group_members",      "duplicate_finder_whitelist_group_members"),
    (BACKEND_DIR / "duplicate_finder/phash_cache.db",       "phash_similarities",           "duplicate_finder_phash_similarities"),

    # video_duplicate_finder
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_hashes",            "video_duplicate_finder_video_hashes"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_similarities",      "video_duplicate_finder_video_similarities"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "duplicate_video_groups",  "video_duplicate_finder_duplicate_video_groups"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_group_stats",       "video_duplicate_finder_video_group_stats"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_whitelist",         "video_duplicate_finder_video_whitelist"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_whitelist_groups",  "video_duplicate_finder_video_whitelist_groups"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_whitelist_group_members", "video_duplicate_finder_video_whitelist_group_members"),
]

# Unique source DB paths (derived from MIGRATIONS, in order of first appearance)
def _source_dbs() -> list[Path]:
    seen: set[Path] = set()
    result = []
    for path, _, _ in MIGRATIONS:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


# ---------------------------------------------------------------------------
# Phase 1: Backup
# ---------------------------------------------------------------------------

def phase_backup(dry_run: bool) -> Path | None:
    """Copy TARGET_DB to a timestamped .bak file. Returns backup path or None."""
    if not TARGET_DB.exists():
        print("[backup] Target DB does not exist yet — nothing to back up.")
        return None

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = TARGET_DB.with_name(f"{TARGET_DB.name}.bak-{ts}")

    size_mb = TARGET_DB.stat().st_size / 1024 / 1024
    if dry_run:
        print(f"[backup] DRY-RUN: would copy {TARGET_DB.name} ({size_mb:.1f} MB) -> {bak.name}")
        return bak

    try:
        shutil.copy2(TARGET_DB, bak)
        bak_size = bak.stat().st_size
        if bak_size != TARGET_DB.stat().st_size:
            print(f"[backup] ERROR: size mismatch after copy ({bak_size} vs {TARGET_DB.stat().st_size})")
            sys.exit(2)
        print(f"[backup] OK: {bak.name} ({size_mb:.1f} MB)")
        return bak
    except Exception as e:
        print(f"[backup] ERROR: {e}")
        sys.exit(2)


# ---------------------------------------------------------------------------
# Phase 2: Migrate
# ---------------------------------------------------------------------------

def _get_tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _get_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def phase_migrate(dry_run: bool) -> list[dict]:
    """
    Copy rows from each source .db into TARGET_DB.
    Returns list of result dicts for the report.
    """
    TARGET_DB.parent.mkdir(parents=True, exist_ok=True)

    if not dry_run:
        dst_conn = sqlite3.connect(TARGET_DB)
        dst_conn.execute("PRAGMA journal_mode=WAL")
        dst_conn.execute("PRAGMA foreign_keys=OFF")
    else:
        dst_conn = None

    results: list[dict] = []
    prev_src: Path | None = None

    for src_path, src_table, dst_table in MIGRATIONS:
        if src_path != prev_src:
            print(f"\n--- {src_path.relative_to(BACKEND_DIR)} ---")
            prev_src = src_path

        if not src_path.exists():
            results.append({"src_db": src_path, "src_table": src_table, "dst_table": dst_table,
                             "src_rows": 0, "dst_rows": 0, "status": "SRC_MISSING"})
            print(f"  SKIP {src_table}: source DB not found")
            continue

        src_conn = sqlite3.connect(src_path)
        src_tables = _get_tables(src_conn)

        if src_table not in src_tables:
            src_conn.close()
            results.append({"src_db": src_path, "src_table": src_table, "dst_table": dst_table,
                             "src_rows": 0, "dst_rows": 0, "status": "TABLE_MISSING"})
            print(f"  SKIP {src_table}: table not found in source DB")
            continue

        src_rows = src_conn.execute(f"SELECT COUNT(*) FROM {src_table}").fetchone()[0]

        if dry_run:
            src_conn.close()
            results.append({"src_db": src_path, "src_table": src_table, "dst_table": dst_table,
                             "src_rows": src_rows, "dst_rows": src_rows, "status": "DRY_RUN"})
            print(f"  DRY-RUN {src_table} -> {dst_table}: {src_rows} rows")
            continue

        # Check destination
        dst_tables = _get_tables(dst_conn)
        if dst_table in dst_tables:
            dst_existing = dst_conn.execute(f"SELECT COUNT(*) FROM {dst_table}").fetchone()[0]
            if dst_existing > 0:
                src_conn.close()
                results.append({"src_db": src_path, "src_table": src_table, "dst_table": dst_table,
                                 "src_rows": src_rows, "dst_rows": dst_existing, "status": "ALREADY_DONE"})
                print(f"  SKIP {src_table} -> {dst_table}: dest already has {dst_existing} rows")
                continue

        if src_rows == 0:
            src_conn.close()
            results.append({"src_db": src_path, "src_table": src_table, "dst_table": dst_table,
                             "src_rows": 0, "dst_rows": 0, "status": "SRC_EMPTY"})
            print(f"  SKIP {src_table}: source is empty")
            continue

        # Build CREATE TABLE in dst using source schema, renamed
        schema_row = src_conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (src_table,)
        ).fetchone()
        if not schema_row or not schema_row[0]:
            src_conn.close()
            results.append({"src_db": src_path, "src_table": src_table, "dst_table": dst_table,
                             "src_rows": src_rows, "dst_rows": 0, "status": "SCHEMA_ERROR"})
            print(f"  ERROR {src_table}: could not read schema")
            continue

        create_sql = schema_row[0]
        # Replace table name in CREATE statement (unquoted, double-quoted, with/without IF NOT EXISTS)
        new_create = create_sql
        for variant in (
            f'CREATE TABLE IF NOT EXISTS "{src_table}"',
            f'CREATE TABLE "{src_table}"',
            f"CREATE TABLE IF NOT EXISTS {src_table}",
            f"CREATE TABLE {src_table}",
        ):
            if variant in new_create:
                new_create = new_create.replace(variant, f"CREATE TABLE IF NOT EXISTS {dst_table}", 1)
                break

        dst_conn.execute(new_create)

        cols = _get_columns(src_conn, src_table)
        col_list = ", ".join(cols)
        placeholders = ", ".join("?" * len(cols))
        rows = src_conn.execute(f"SELECT {col_list} FROM {src_table}").fetchall()
        dst_conn.executemany(
            f"INSERT OR IGNORE INTO {dst_table} ({col_list}) VALUES ({placeholders})", rows
        )
        dst_conn.commit()

        dst_rows = dst_conn.execute(f"SELECT COUNT(*) FROM {dst_table}").fetchone()[0]
        status = "OK" if dst_rows == src_rows else "MISMATCH"
        src_conn.close()

        results.append({"src_db": src_path, "src_table": src_table, "dst_table": dst_table,
                         "src_rows": src_rows, "dst_rows": dst_rows, "status": status})
        print(f"  {'OK' if status == 'OK' else 'MISMATCH!'} {src_table} -> {dst_table}: {src_rows} rows")

    if dst_conn:
        dst_conn.execute("PRAGMA foreign_keys=ON")
        dst_conn.close()

    return results


# ---------------------------------------------------------------------------
# Phase 3: Verify
# ---------------------------------------------------------------------------

def phase_verify(results: list[dict]) -> bool:
    """Check row counts. Returns True if all migrated tables match."""
    if not TARGET_DB.exists():
        print("[verify] Target DB not found — nothing to verify.")
        return False

    dst_conn = sqlite3.connect(TARGET_DB)
    all_ok = True

    print("\n[verify] Row count check:")
    for r in results:
        if r["status"] in ("SRC_MISSING", "TABLE_MISSING", "SRC_EMPTY", "DRY_RUN"):
            continue
        dst_actual = 0
        if r["dst_table"] in _get_tables(dst_conn):
            dst_actual = dst_conn.execute(f"SELECT COUNT(*) FROM {r['dst_table']}").fetchone()[0]
        match = dst_actual == r["src_rows"]
        if not match:
            all_ok = False
        mark = "OK" if match else "MISMATCH"
        print(f"  [{mark}] {r['dst_table']}: src={r['src_rows']} dst={dst_actual}")

    dst_conn.close()
    return all_ok


# ---------------------------------------------------------------------------
# Phase 4: Report
# ---------------------------------------------------------------------------

def phase_report(results: list[dict], backup_path: Path | None, dry_run: bool):
    """Print full migration report including old DB files that can be deleted."""
    print("\n" + "=" * 70)
    print("MIGRATION REPORT")
    print("=" * 70)

    print(f"\nTarget DB : {TARGET_DB}")
    if backup_path:
        print(f"Backup    : {backup_path}")
    if TARGET_DB.exists():
        size_mb = TARGET_DB.stat().st_size / 1024 / 1024
        print(f"DB size   : {size_mb:.1f} MB")

    # Summary table
    print("\n--- Table migration summary ---")
    col_w = max((len(r["dst_table"]) for r in results), default=20)
    header = f"  {'Destination table':<{col_w}}  {'Src rows':>9}  {'Dst rows':>9}  Status"
    print(header)
    print("  " + "-" * (len(header) - 2))

    mismatches = 0
    for r in results:
        status = r["status"]
        mark = {
            "OK": "OK",
            "ALREADY_DONE": "done",
            "DRY_RUN": "dry",
            "SRC_MISSING": "skip-no-src",
            "TABLE_MISSING": "skip-no-tbl",
            "SRC_EMPTY": "skip-empty",
            "MISMATCH": "MISMATCH!",
            "SCHEMA_ERROR": "ERROR",
        }.get(status, status)
        if status == "MISMATCH":
            mismatches += 1
        print(f"  {r['dst_table']:<{col_w}}  {r['src_rows']:>9}  {r['dst_rows']:>9}  {mark}")

    # Old DB files to delete
    print("\n--- Old .db files that can be deleted after verification ---")
    source_dbs = _source_dbs()

    can_delete: list[Path] = []
    cannot_delete: list[tuple[Path, str]] = []

    for src_path in source_dbs:
        if not src_path.exists():
            continue
        # Check that all tables from this source were successfully migrated
        src_results = [r for r in results if r["src_db"] == src_path]
        migrated = [r for r in src_results if r["status"] in ("OK", "ALREADY_DONE", "SRC_EMPTY", "DRY_RUN")]
        failed = [r for r in src_results if r["status"] in ("MISMATCH", "SCHEMA_ERROR")]
        if failed:
            cannot_delete.append((src_path, f"{len(failed)} table(s) with errors"))
        elif len(migrated) == len(src_results) and src_results:
            can_delete.append(src_path)
        else:
            cannot_delete.append((src_path, "not all tables processed"))

    if can_delete:
        print("\n  Safe to delete (all tables migrated successfully):")
        for p in can_delete:
            size_kb = p.stat().st_size // 1024
            rel = p.relative_to(BACKEND_DIR)
            print(f"    rm backend/{rel}   ({size_kb} KB)")
        if not dry_run:
            print("\n  To delete all at once:")
            paths_str = " \\\n    ".join(f"backend/{p.relative_to(BACKEND_DIR)}" for p in can_delete)
            print(f"    cd <repo-root> && rm \\\n    {paths_str}")
    else:
        print("\n  None ready for deletion yet (run migration first).")

    if cannot_delete:
        print("\n  NOT safe to delete (errors or not fully migrated):")
        for p, reason in cannot_delete:
            rel = p.relative_to(BACKEND_DIR)
            print(f"    backend/{rel}  — {reason}")

    # Final verdict
    print("\n--- Result ---")
    if dry_run:
        print("  DRY-RUN complete. No data was written.")
    elif mismatches:
        print(f"  FAILED: {mismatches} table(s) have row-count mismatches.")
        print("  Do NOT delete source DBs until mismatches are resolved.")
    else:
        print("  All migrated tables verified OK.")
        if can_delete:
            print(f"  {len(can_delete)} source DB file(s) are safe to delete (see list above).")
    print("=" * 70)

    return mismatches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Migrate per-tool SQLite DBs into the unified script_orchestra.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run",      action="store_true", help="Show what would be done; write nothing")
    parser.add_argument("--backup-only",  action="store_true", help="Only run backup phase")
    parser.add_argument("--verify-only",  action="store_true", help="Only run verify + report (reads current state)")
    parser.add_argument("--no-backup",    action="store_true", help="Skip backup (not recommended)")
    parser.add_argument("--report-only",  action="store_true", help="Print deletion report only")
    args = parser.parse_args()

    # --- report-only ---
    if args.report_only:
        # Build results from current DB state without migrating
        results = []
        dst_conn = sqlite3.connect(TARGET_DB) if TARGET_DB.exists() else None
        dst_tables = _get_tables(dst_conn) if dst_conn else set()
        for src_path, src_table, dst_table in MIGRATIONS:
            src_rows = 0
            dst_rows = 0
            status = "SRC_MISSING"
            if src_path.exists():
                sc = sqlite3.connect(src_path)
                st = _get_tables(sc)
                if src_table in st:
                    src_rows = sc.execute(f"SELECT COUNT(*) FROM {src_table}").fetchone()[0]
                    status = "SRC_EMPTY" if src_rows == 0 else "TABLE_MISSING"
                    if dst_table in dst_tables:
                        dst_rows = dst_conn.execute(f"SELECT COUNT(*) FROM {dst_table}").fetchone()[0]
                        status = "OK" if dst_rows == src_rows else ("ALREADY_DONE" if dst_rows > 0 else "TABLE_MISSING")
                else:
                    status = "TABLE_MISSING"
                sc.close()
            results.append({"src_db": src_path, "src_table": src_table, "dst_table": dst_table,
                             "src_rows": src_rows, "dst_rows": dst_rows, "status": status})
        if dst_conn:
            dst_conn.close()
        phase_report(results, None, dry_run=False)
        return

    # --- verify-only ---
    if args.verify_only:
        # Rebuild results from live DB counts
        results = []
        dst_conn = sqlite3.connect(TARGET_DB) if TARGET_DB.exists() else None
        dst_tables = _get_tables(dst_conn) if dst_conn else set()
        for src_path, src_table, dst_table in MIGRATIONS:
            src_rows, dst_rows, status = 0, 0, "SRC_MISSING"
            if src_path.exists():
                sc = sqlite3.connect(src_path)
                if src_table in _get_tables(sc):
                    src_rows = sc.execute(f"SELECT COUNT(*) FROM {src_table}").fetchone()[0]
                    if dst_table in dst_tables:
                        dst_rows = dst_conn.execute(f"SELECT COUNT(*) FROM {dst_table}").fetchone()[0]
                        status = "OK" if dst_rows == src_rows else ("ALREADY_DONE" if dst_rows > 0 else "MISMATCH")
                    else:
                        status = "TABLE_MISSING"
                else:
                    status = "TABLE_MISSING"
                sc.close()
            results.append({"src_db": src_path, "src_table": src_table, "dst_table": dst_table,
                             "src_rows": src_rows, "dst_rows": dst_rows, "status": status})
        if dst_conn:
            dst_conn.close()
        all_ok = phase_verify(results)
        mismatches = phase_report(results, None, dry_run=False)
        sys.exit(0 if all_ok else 1)

    # --- backup-only ---
    if args.backup_only:
        phase_backup(dry_run=False)
        return

    # --- full run ---
    print(f"Target DB : {TARGET_DB}")
    print(f"Dry-run   : {args.dry_run}")

    # Phase 1: Backup
    backup_path = None
    if not args.no_backup and not args.dry_run:
        backup_path = phase_backup(dry_run=False)
    elif args.dry_run:
        backup_path = phase_backup(dry_run=True)

    # Phase 2: Migrate
    print("\n[migrate] Copying tables...")
    results = phase_migrate(dry_run=args.dry_run)

    # Phase 3: Verify
    if not args.dry_run:
        phase_verify(results)

    # Phase 4: Report
    mismatches = phase_report(results, backup_path, dry_run=args.dry_run)

    sys.exit(0 if mismatches == 0 else 1)


if __name__ == "__main__":
    main()
