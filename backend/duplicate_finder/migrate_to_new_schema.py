"""
Migration script: Old schema → New schema (DATABASE_SCHEMA.md)

Changes:
1. image_hashes: Add id (AUTOINCREMENT), status, remove mtime
2. whitelist: Change to image_id FK
3. Drop scan_cache, phash_neighbors
4. Create phash_similarities table
"""
import sqlite3
from pathlib import Path

CACHE_DB = Path(__file__).parent / 'phash_cache.db'


def migrate():
    print(f"[Migration] Migrating database: {CACHE_DB}")

    if not CACHE_DB.exists():
        print(f"[Migration] Database not found, skipping migration")
        return

    conn = sqlite3.connect(CACHE_DB, check_same_thread=False)
    cursor = conn.cursor()

    # Check if already migrated
    cursor.execute("PRAGMA table_info(image_hashes)")
    columns = {col[1] for col in cursor.fetchall()}

    if 'id' in columns and 'status' in columns:
        print("[Migration] Already migrated, skipping")
        conn.close()
        return

    print("[Migration] Starting migration...")

    # Step 1: Create new image_hashes table
    print("[Migration] Step 1: Recreating image_hashes table...")
    cursor.execute('''
        CREATE TABLE image_hashes_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filesize INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            phash TEXT NOT NULL,
            resolution TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            UNIQUE (filename, filesize, file_path)
        )
    ''')

    # Migrate data
    cursor.execute('''
        INSERT INTO image_hashes_new (filename, filesize, file_path, phash, resolution, status)
        SELECT filename, filesize, file_path, phash, resolution, 'pending'
        FROM image_hashes
    ''')

    cursor.execute('DROP TABLE image_hashes')
    cursor.execute('ALTER TABLE image_hashes_new RENAME TO image_hashes')

    # Create indexes
    cursor.execute('CREATE INDEX idx_phash ON image_hashes(phash)')
    cursor.execute('CREATE INDEX idx_filename_filesize ON image_hashes(filename, filesize)')
    cursor.execute('CREATE INDEX idx_status ON image_hashes(status)')

    print(f"[Migration] Migrated {cursor.rowcount} image records")

    # Step 2: Recreate whitelist table
    print("[Migration] Step 2: Recreating whitelist table...")

    # Get old whitelist data
    cursor.execute('SELECT filename, filesize, added_time, note FROM whitelist')
    old_whitelist = cursor.fetchall()

    cursor.execute('DROP TABLE whitelist')

    cursor.execute('''
        CREATE TABLE whitelist (
            image_id INTEGER PRIMARY KEY,
            added_time REAL NOT NULL,
            note TEXT,
            FOREIGN KEY (image_id) REFERENCES image_hashes(id) ON DELETE CASCADE
        )
    ''')

    # Migrate whitelist (match by filename + filesize)
    migrated_count = 0
    for filename, filesize, added_time, note in old_whitelist:
        cursor.execute('''
            SELECT id FROM image_hashes
            WHERE filename = ? AND filesize = ?
        ''', (filename, filesize))
        row = cursor.fetchone()
        if row:
            image_id = row[0]
            cursor.execute('''
                INSERT OR IGNORE INTO whitelist (image_id, added_time, note)
                VALUES (?, ?, ?)
            ''', (image_id, added_time, note))
            migrated_count += 1

    print(f"[Migration] Migrated {migrated_count}/{len(old_whitelist)} whitelist records")

    # Step 3: Drop old tables
    print("[Migration] Step 3: Dropping old tables...")
    cursor.execute('DROP TABLE IF EXISTS scan_cache')
    cursor.execute('DROP TABLE IF EXISTS phash_neighbors')
    print("[Migration] Dropped scan_cache, phash_neighbors")

    # Step 4: Create phash_similarities table
    print("[Migration] Step 4: Creating phash_similarities table...")
    cursor.execute('''
        CREATE TABLE phash_similarities (
            image_id_a INTEGER NOT NULL,
            image_id_b INTEGER NOT NULL,
            threshold INTEGER NOT NULL,
            distance INTEGER NOT NULL,
            PRIMARY KEY (image_id_a, image_id_b, threshold),
            CHECK (image_id_a < image_id_b),
            FOREIGN KEY (image_id_a) REFERENCES image_hashes(id) ON DELETE CASCADE,
            FOREIGN KEY (image_id_b) REFERENCES image_hashes(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('CREATE INDEX idx_image_id_a_threshold ON phash_similarities(image_id_a, threshold)')
    cursor.execute('CREATE INDEX idx_image_id_b_threshold ON phash_similarities(image_id_b, threshold)')
    cursor.execute('CREATE INDEX idx_threshold ON phash_similarities(threshold)')

    # Step 5: Create view
    print("[Migration] Step 5: Creating phash_similarities_view...")
    cursor.execute('''
        CREATE VIEW phash_similarities_view AS
        SELECT image_id_a as image_id, image_id_b as neighbor_id, threshold, distance
        FROM phash_similarities
        UNION ALL
        SELECT image_id_b as image_id, image_id_a as neighbor_id, threshold, distance
        FROM phash_similarities
    ''')

    conn.commit()
    conn.close()

    print("[Migration] ✅ Migration completed successfully")
    print("[Migration] Note: phash_similarities table is empty, run 'Refresh & Build' to populate")


if __name__ == '__main__':
    migrate()
