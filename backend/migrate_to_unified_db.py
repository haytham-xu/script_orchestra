"""
Migrate all per-tool SQLite databases into the single unified DB.

Usage:
    cd backend
    python migrate_to_unified_db.py [--dry-run] [--verify-only]

What this script does:
1. Opens each existing per-tool .db file
2. For every table it finds, computes the new prefixed name
3. Copies all rows into backend/data/script_orchestra.db (the unified DB)
4. Prints a row-count verification summary

Safety:
- Reads existing data only; never modifies the source .db files
- Skips tables that already have data in the destination (idempotent)
- Use --dry-run to see what would be copied without making changes
- Use --verify-only to only print row counts (no copying)
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent

# Mapping: (source_db_path, old_table_name) -> new_table_name
# For tables that already match the new name (previously migrated), they map to themselves.
MIGRATIONS = [
    # memory_curve
    (BACKEND_DIR / "memory_curve/memory_curve.db", "card", "memory_curve_card"),

    # assistant
    (BACKEND_DIR / "assistant/assistant.db", "conversations", "assistant_conversations"),
    (BACKEND_DIR / "assistant/assistant.db", "messages", "assistant_messages"),
    (BACKEND_DIR / "assistant/assistant.db", "attachments", "assistant_attachments"),
    (BACKEND_DIR / "assistant/assistant.db", "kb_sources", "assistant_kb_sources"),
    (BACKEND_DIR / "assistant/assistant.db", "kb_documents", "assistant_kb_documents"),
    (BACKEND_DIR / "assistant/assistant.db", "kb_chunks", "assistant_kb_chunks"),

    # apprentice
    (BACKEND_DIR / "apprentice/apprentice.db", "task", "apprentice_task"),
    (BACKEND_DIR / "apprentice/apprentice.db", "memory_short", "apprentice_memory_short"),
    (BACKEND_DIR / "apprentice/apprentice.db", "memory_long", "apprentice_memory_long"),
    (BACKEND_DIR / "apprentice/apprentice.db", "human_message", "apprentice_human_message"),
    (BACKEND_DIR / "apprentice/apprentice.db", "integration_event", "apprentice_integration_event"),
    (BACKEND_DIR / "apprentice/apprentice.db", "red_line", "apprentice_red_line"),

    # file_pipeline
    (BACKEND_DIR / "file_pipeline/file_pipeline.db", "tool", "file_pipeline_tool"),
    (BACKEND_DIR / "file_pipeline/file_pipeline.db", "pipeline", "file_pipeline_pipeline"),

    # file_git
    (BACKEND_DIR / "file_git/file_git.db", "repos", "file_git_repos"),

    # roadmap
    (BACKEND_DIR / "roadmap/tasks.db", "tasks", "roadmap_tasks"),
    (BACKEND_DIR / "roadmap/tasks.db", "settings", "roadmap_settings"),

    # file_tracker
    (BACKEND_DIR / "file_tracker/file_tracker.db", "tracked_file", "file_tracker_tracked_file"),

    # clean_keyword
    (BACKEND_DIR / "clean_keyword/clean_keyword.db", "keyword", "clean_keyword_keyword"),

    # translator
    (BACKEND_DIR / "translator/translator.db", "translation_history", "translator_translation_history"),
    (BACKEND_DIR / "translator/translator.db", "learning_point", "translator_learning_point"),

    # claude_bridge
    (BACKEND_DIR / "claude_bridge/claude_bridge.db", "messages", "claude_bridge_messages"),

    # knowledge_vault
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db", "raw_fragment", "knowledge_vault_raw_fragment"),
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db", "fragment_vector", "knowledge_vault_fragment_vector"),
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db", "label", "knowledge_vault_label"),
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db", "fragment_label", "knowledge_vault_fragment_label"),
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db", "fragment_group", "knowledge_vault_fragment_group"),
    (BACKEND_DIR / "knowledge_vault/knowledge_vault.db", "fragment_group_member", "knowledge_vault_fragment_group_member"),

    # manga_viewer
    (BACKEND_DIR / "manga_viewer/queues.db", "read_queue", "manga_viewer_read_queue"),
    (BACKEND_DIR / "manga_viewer/queues.db", "snooze_queue", "manga_viewer_snooze_queue"),

    # browser_agent
    (BACKEND_DIR / "browser_agent/browser_agent.db", "browser_tab", "browser_agent_browser_tab"),
    (BACKEND_DIR / "browser_agent/browser_agent.db", "archived_tab", "browser_agent_archived_tab"),
    (BACKEND_DIR / "browser_agent/browser_agent.db", "tab_label", "browser_agent_tab_label"),
    (BACKEND_DIR / "browser_agent/browser_agent.db", "archived_tab_label", "browser_agent_archived_tab_label"),
    (BACKEND_DIR / "browser_agent/browser_agent.db", "tab_archive_batch", "browser_agent_tab_archive_batch"),
    (BACKEND_DIR / "browser_agent/browser_agent.db", "tab_archive_vector", "browser_agent_tab_archive_vector"),

    # duplicate_finder (phash_cache.db)
    (BACKEND_DIR / "duplicate_finder/phash_cache.db", "image_hashes", "duplicate_finder_image_hashes"),
    (BACKEND_DIR / "duplicate_finder/phash_cache.db", "whitelist", "duplicate_finder_whitelist"),
    (BACKEND_DIR / "duplicate_finder/phash_cache.db", "whitelist_groups", "duplicate_finder_whitelist_groups"),
    (BACKEND_DIR / "duplicate_finder/phash_cache.db", "whitelist_group_members", "duplicate_finder_whitelist_group_members"),
    (BACKEND_DIR / "duplicate_finder/phash_cache.db", "phash_similarities", "duplicate_finder_phash_similarities"),

    # video_duplicate_finder
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_hashes", "video_duplicate_finder_video_hashes"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_similarities", "video_duplicate_finder_video_similarities"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "duplicate_video_groups", "video_duplicate_finder_duplicate_video_groups"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_group_stats", "video_duplicate_finder_video_group_stats"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_whitelist", "video_duplicate_finder_video_whitelist"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_whitelist_groups", "video_duplicate_finder_video_whitelist_groups"),
    (BACKEND_DIR / "video_duplicate_finder/video_hash_cache.db", "video_whitelist_group_members", "video_duplicate_finder_video_whitelist_group_members"),
]

TARGET_DB = Path(os.environ.get("DB_PATH", BACKEND_DIR / "data/script_orchestra.db"))


def _get_tables(conn) -> set:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def _get_columns(conn, table: str):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def _copy_table(src_conn, dst_conn, src_table: str, dst_table: str, dry_run: bool) -> tuple[int, int]:
    """
    Copy rows from src_table in src_conn to dst_table in dst_conn.
    Returns (src_rows, inserted_rows).
    Skips if dst_table already has data.
    """
    # Get source row count
    src_rows = src_conn.execute(f"SELECT COUNT(*) FROM {src_table}").fetchone()[0]

    # Check if destination already has data
    dst_tables = _get_tables(dst_conn)
    if dst_table in dst_tables:
        dst_rows = dst_conn.execute(f"SELECT COUNT(*) FROM {dst_table}").fetchone()[0]
        if dst_rows > 0:
            print(f"  SKIP {src_table} -> {dst_table}: destination already has {dst_rows} rows")
            return src_rows, 0

    if src_rows == 0:
        print(f"  SKIP {src_table} -> {dst_table}: source is empty")
        return 0, 0

    if dry_run:
        print(f"  DRY-RUN {src_table} -> {dst_table}: would copy {src_rows} rows")
        return src_rows, src_rows

    # Get schema from source to create table in destination if needed
    schema_row = src_conn.execute(
        f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (src_table,)
    ).fetchone()
    if not schema_row or not schema_row[0]:
        print(f"  ERROR: could not get schema for {src_table}")
        return src_rows, 0

    # Rewrite CREATE TABLE statement with new table name
    create_sql = schema_row[0]
    new_create_sql = create_sql.replace(
        f"CREATE TABLE {src_table}",
        f"CREATE TABLE IF NOT EXISTS {dst_table}",
        1
    ).replace(
        f"CREATE TABLE IF NOT EXISTS {src_table}",
        f"CREATE TABLE IF NOT EXISTS {dst_table}",
        1
    )

    dst_conn.execute(new_create_sql)

    # Copy data
    cols = _get_columns(src_conn, src_table)
    col_list = ", ".join(cols)
    placeholders = ", ".join("?" * len(cols))

    rows = src_conn.execute(f"SELECT {col_list} FROM {src_table}").fetchall()
    dst_conn.executemany(
        f"INSERT OR IGNORE INTO {dst_table} ({col_list}) VALUES ({placeholders})",
        rows
    )
    dst_conn.commit()

    inserted = dst_conn.execute(f"SELECT COUNT(*) FROM {dst_table}").fetchone()[0]
    print(f"  COPY {src_table} -> {dst_table}: {src_rows} source rows, {inserted} in dest")
    return src_rows, inserted


def main():
    parser = argparse.ArgumentParser(description="Migrate per-tool DBs to unified DB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing")
    parser.add_argument("--verify-only", action="store_true", help="Only verify row counts")
    args = parser.parse_args()

    if args.verify_only:
        print(f"\n=== Row count verification: {TARGET_DB} ===")
        if not TARGET_DB.exists():
            print("Target DB does not exist yet.")
            return
        dst_conn = sqlite3.connect(TARGET_DB)
        tables = sorted(_get_tables(dst_conn))
        total = 0
        for t in tables:
            n = dst_conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n}")
            total += n
        print(f"\nTotal rows across {len(tables)} tables: {total}")
        dst_conn.close()
        return

    TARGET_DB.parent.mkdir(parents=True, exist_ok=True)

    if not args.dry_run:
        dst_conn = sqlite3.connect(TARGET_DB)
        dst_conn.execute("PRAGMA journal_mode=WAL")
        dst_conn.execute("PRAGMA foreign_keys=OFF")  # FK off during bulk copy
    else:
        dst_conn = None

    results = []
    prev_src = None

    for src_path, src_table, dst_table in MIGRATIONS:
        if not src_path.exists():
            print(f"\nSKIP {src_path.name}: file not found")
            continue

        if src_path != prev_src:
            print(f"\n--- {src_path.relative_to(BACKEND_DIR)} ---")
            prev_src = src_path

        src_conn = sqlite3.connect(src_path)
        src_tables = _get_tables(src_conn)

        if src_table not in src_tables:
            print(f"  SKIP {src_table}: table not in source DB")
            src_conn.close()
            continue

        if args.dry_run:
            src_rows = src_conn.execute(f"SELECT COUNT(*) FROM {src_table}").fetchone()[0]
            print(f"  DRY-RUN {src_table} -> {dst_table}: {src_rows} rows")
            results.append((dst_table, src_rows, src_rows))
        else:
            src_rows, inserted = _copy_table(src_conn, dst_conn, src_table, dst_table, dry_run=False)
            results.append((dst_table, src_rows, inserted))

        src_conn.close()

    if dst_conn:
        dst_conn.execute("PRAGMA foreign_keys=ON")
        dst_conn.close()

    print("\n=== Summary ===")
    total_src = sum(r[1] for r in results)
    total_dst = sum(r[2] for r in results)
    for dst_table, src, dst in results:
        status = "OK" if src == dst or dst == 0 else f"MISMATCH ({src} src vs {dst} dst)"
        print(f"  {dst_table}: {src} -> {dst} [{status}]")
    print(f"\nTotal: {total_src} source rows, {total_dst} rows in unified DB")

    if not args.dry_run:
        print(f"\nUnified DB: {TARGET_DB}")
        print("Run with --verify-only to recheck counts at any time.")


if __name__ == "__main__":
    main()
