#!/usr/bin/env python3
"""
Migrate scan_cache table from old schema to new schema.

Old schema: id, threshold, file_list_hash, scan_timestamp, total_files, duplicate_count
New schema: file_list_hash, threshold, scan_result, scan_time, file_count (PRIMARY KEY)

This migration:
1. Renames the old table to scan_cache_old
2. Creates the new table with correct schema
3. Drops the old table (no data migration since scan results need to be re-run)
"""
import sqlite3
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent / "phash_cache.db"

def migrate():
    """Perform the migration"""
    print(f"Migrating database: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if old table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='scan_cache'
    """)

    if not cursor.fetchone():
        print("❌ scan_cache table does not exist")
        conn.close()
        return

    # Check current schema
    cursor.execute("PRAGMA table_info(scan_cache)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Current columns: {columns}")

    # Check if migration is needed
    if 'scan_result' in columns:
        print("✅ Table already has new schema, no migration needed")
        conn.close()
        return

    print("🔄 Migration needed: old schema detected")

    # Step 1: Rename old table
    print("  Step 1: Renaming old table to scan_cache_old...")
    cursor.execute("ALTER TABLE scan_cache RENAME TO scan_cache_old")

    # Step 2: Create new table with correct schema
    print("  Step 2: Creating new scan_cache table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scan_cache (
            file_list_hash TEXT NOT NULL,
            threshold INTEGER NOT NULL,
            scan_result TEXT NOT NULL,
            scan_time REAL NOT NULL,
            file_count INTEGER NOT NULL,
            PRIMARY KEY (file_list_hash, threshold)
        )
    ''')

    # Step 3: Drop old table (data is stale anyway)
    print("  Step 3: Dropping old table (old data is not compatible)...")
    cursor.execute("DROP TABLE scan_cache_old")

    conn.commit()
    conn.close()

    print("✅ Migration completed successfully!")
    print("ℹ️  Old scan cache data was discarded (incompatible format)")
    print("ℹ️  New scans will be cached with full duplicate group results")

if __name__ == "__main__":
    migrate()
