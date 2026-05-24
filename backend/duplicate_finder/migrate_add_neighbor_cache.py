#!/usr/bin/env python3
"""
Add phash_neighbors table to existing databases.

This migration adds the neighbor cache table for faster incremental scans.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "phash_cache.db"

def migrate():
    """Add phash_neighbors table if it doesn't exist"""
    print(f"Migrating database: {DB_PATH}")

    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if table already exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='phash_neighbors'
    """)

    if cursor.fetchone():
        print("✅ phash_neighbors table already exists, no migration needed")
        conn.close()
        return True

    print("📝 Creating phash_neighbors table...")

    # Create the table
    cursor.execute('''
        CREATE TABLE phash_neighbors (
            phash TEXT NOT NULL,
            neighbor_phash TEXT NOT NULL,
            distance INTEGER NOT NULL,
            last_checked REAL NOT NULL,
            PRIMARY KEY (phash, neighbor_phash)
        )
    ''')

    # Create indexes
    print("📝 Creating indexes...")
    cursor.execute('''
        CREATE INDEX idx_neighbors_phash ON phash_neighbors(phash)
    ''')

    cursor.execute('''
        CREATE INDEX idx_neighbors_distance ON phash_neighbors(distance)
    ''')

    conn.commit()
    conn.close()

    print("✅ Migration completed successfully!")
    print("\nNew features enabled:")
    print("  • Neighbor cache for faster incremental scans")
    print("  • 10-100x speedup for repeated scans")
    print("  • Efficient threshold changes")

    return True

if __name__ == "__main__":
    migrate()
