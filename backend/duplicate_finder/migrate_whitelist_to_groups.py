#!/usr/bin/env python3
"""
Migrate whitelist table to group-based schema (Cross-Platform Compatible)

Supports three legacy schemas:
1. Version 1: PRIMARY KEY (filename, filesize) - File metadata-based
2. Version 2: image_id INTEGER PRIMARY KEY - File-level whitelist
3. Version 3: Already using group-based schema
"""
import sqlite3
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from duplicate_finder.settings_manager import settings_manager


def detect_whitelist_schema_version(cursor):
    """
    Detect current whitelist table schema version
    Returns: 'VERSION_1_FILENAME', 'VERSION_2_IMAGE_ID', 'VERSION_3_GROUPS', 'NO_TABLE', 'UNKNOWN'
    """
    # Check if whitelist table exists
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='whitelist'")
    result = cursor.fetchone()

    if not result:
        return 'NO_TABLE'

    # Check if groups tables already exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='whitelist_groups'")
    if cursor.fetchone():
        return 'VERSION_3_GROUPS'

    # Analyze whitelist table structure
    cursor.execute("PRAGMA table_info(whitelist)")
    columns = {col[1] for col in cursor.fetchall()}

    if 'image_id' in columns:
        return 'VERSION_2_IMAGE_ID'
    elif 'filename' in columns and 'filesize' in columns:
        return 'VERSION_1_FILENAME'
    else:
        return 'UNKNOWN'


def create_group_schema(cursor):
    """Create group-based whitelist schema"""
    print("🔨 Creating whitelist_groups table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS whitelist_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            added_time REAL NOT NULL
        )
    ''')

    print("🔨 Creating whitelist_group_members table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS whitelist_group_members (
            group_id INTEGER NOT NULL,
            image_id INTEGER NOT NULL,
            FOREIGN KEY (group_id) REFERENCES whitelist_groups(id) ON DELETE CASCADE,
            FOREIGN KEY (image_id) REFERENCES image_hashes(id) ON DELETE CASCADE,
            PRIMARY KEY (group_id, image_id)
        )
    ''')

    print("🔨 Creating indexes...")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_whitelist_group_members_group ON whitelist_group_members(group_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_whitelist_group_members_image ON whitelist_group_members(image_id)')


def migrate():
    """Compatible database migration for all schema versions"""
    # Get database path from settings
    db_path = settings_manager.get_phash_db_path()
    if not db_path or not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return False

    print(f"📁 Database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. Detect current schema version
        version = detect_whitelist_schema_version(cursor)
        print(f"📋 Detected whitelist schema: {version}")

        # 2. Execute different migration strategies based on version
        if version == 'VERSION_3_GROUPS':
            print("✅ Already using group-based whitelist schema, no migration needed")
            return True

        elif version == 'NO_TABLE':
            print("ℹ️  No whitelist table found, creating new schema...")
            # Create new schema directly
            create_group_schema(cursor)
            conn.commit()
            print("✅ Group schema created")
            return True

        elif version == 'VERSION_1_FILENAME':
            print("⚠️  Version 1 detected (filename+filesize schema)")
            print("   📝 Note: Cannot convert to groups automatically")
            print("      Reason: Old data is file-level, new schema is group-level")
            print("      Old whitelist entries use different semantics:")
            print("        - Old: 'whitelist this FILE'")
            print("        - New: 'whitelist this GROUP COMBINATION'")
            print("   🗑️  Dropping old whitelist table...")
            cursor.execute('DROP TABLE IF EXISTS whitelist')
            create_group_schema(cursor)
            conn.commit()
            print("✅ Migration complete")
            print("   ℹ️  You can re-create whitelist entries in the new UI")
            return True

        elif version == 'VERSION_2_IMAGE_ID':
            print("⚠️  Version 2 detected (image_id schema)")
            print("   📝 Note: Cannot convert to groups automatically")
            print("      Reason: Old data is file-level, new schema is group-level")
            print("      Old whitelist entries use different semantics:")
            print("        - Old: 'whitelist this FILE'")
            print("        - New: 'whitelist this GROUP COMBINATION'")
            print("   🗑️  Dropping old whitelist table...")
            cursor.execute('DROP TABLE IF EXISTS whitelist')
            create_group_schema(cursor)
            conn.commit()
            print("✅ Migration complete")
            print("   ℹ️  You can re-create whitelist entries in the new UI")
            return True

        else:
            print(f"❌ Unknown whitelist schema: {version}")
            print("   Cannot proceed with migration")
            print("   Please report this issue with your database schema")
            return False

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    print("=" * 70)
    print("Whitelist Table Migration Script (Cross-Platform Compatible)")
    print("=" * 70)
    print("\nThis script will migrate whitelist table to group-based schema:")
    print("  📦 OLD: Individual file whitelist")
    print("      - Version 1: (filename, filesize) composite key")
    print("      - Version 2: image_id primary key")
    print("  ✨ NEW: Group-based whitelist")
    print("      - whitelist_groups: group metadata")
    print("      - whitelist_group_members: group members with CASCADE delete")
    print("\n⚠️  IMPORTANT:")
    print("   Old whitelist data CANNOT be automatically converted!")
    print("\n   Why?")
    print("   - Old whitelist: 'Don't show THIS FILE in results'")
    print("   - New whitelist: 'Don't show THIS FILE COMBINATION in results'")
    print("   - These are fundamentally different concepts")
    print("\n   What happens?")
    print("   - Old whitelist table will be dropped")
    print("   - New group-based tables will be created")
    print("   - You can re-create whitelist entries using the new UI")
    print("\n✅ This script is cross-platform compatible:")
    print("   - Auto-detects schema version (3 versions supported)")
    print("   - Works on Windows, Mac, and Linux")
    print("   - Idempotent: safe to run multiple times")
    print("\n" + "=" * 70)

    response = input("\nProceed with migration? (yes/no): ").strip().lower()
    if response != 'yes':
        print("❌ Migration cancelled")
        sys.exit(0)

    print("\n🚀 Starting migration...\n")
    success = migrate()

    if success:
        print("\n🎉 All done!")
        print("   ✅ New group-based whitelist schema is ready")
        print("   📌 Next steps:")
        print("      1. Start the application")
        print("      2. Run Phase 3 to find duplicate groups")
        print("      3. Click 'Add to Whitelist' on groups you want to exempt")
        sys.exit(0)
    else:
        print("\n❌ Migration failed")
        print("   Please check the error messages above")
        sys.exit(1)
