#!/usr/bin/env python3
"""
Restore Cypress Config Snapshots

Usage:
    python backend/cypress_support/restore_config.py [tool_name]
    python backend/cypress_support/restore_config.py --all
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cypress_support.config_manager import ConfigManager


def main():
    config_manager = ConfigManager()

    if len(sys.argv) < 2:
        # Check for unrestored snapshots
        result = config_manager.check_all_snapshots()
        if result['count'] == 0:
            print("✅ No unrestored snapshots found")
            return

        print(f"⚠️  Found {result['count']} unrestored snapshot(s):")
        for snap in result['unrestored']:
            print(f"   - {snap['tool']}: {snap['snapshot_time']}")

        print("\nUsage:")
        print("  python restore_config.py <tool_name>   # Restore specific tool")
        print("  python restore_config.py --all         # Restore all")
        return

    arg = sys.argv[1]

    if arg == '--all':
        # Restore all
        result = config_manager.restore_all_snapshots()
        print(f"✅ Restored {result['count']} config(s):")
        for item in result['restored']:
            status = '✅' if item['success'] else '❌'
            print(f"   {status} {item['tool']}")
    else:
        # Restore specific tool
        tool = arg
        result = config_manager.restore_snapshot(tool)
        if 'error' in result:
            print(f"❌ Error: {result['error']}")
            sys.exit(1)
        else:
            print(f"✅ Config restored for {tool}")
            print(f"   Restored from: {result['restored_from']}")


if __name__ == "__main__":
    main()
