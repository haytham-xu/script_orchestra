"""
Configuration Manager for Cypress Tests

Handles saving/restoring tool configurations for isolated testing.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional


class ConfigManager:
    """Manages configuration snapshots for Cypress testing"""

    # Tool configuration mapping
    TOOL_CONFIG_MAP = {
        'photo_classifier': {
            'settings_path': 'photo_classifier/user_settings.json',
            'snapshot_name': '.cypress_snapshot.json'
        },
        'manga_viewer': {
            'settings_path': 'manga_viewer/manga_viewer_settings.json',
            'snapshot_name': '.cypress_snapshot.json'
        },
        'duplicate_finder': {
            'settings_path': 'duplicate_finder/settings.json',
            'snapshot_name': '.cypress_snapshot.json'
        }
    }

    def __init__(self):
        self.backend_dir = Path(__file__).parent.parent

    def _get_paths(self, tool: str) -> Dict[str, Path]:
        """Get file paths for a tool"""
        if tool not in self.TOOL_CONFIG_MAP:
            raise ValueError(f"Unknown tool: {tool}. Valid tools: {list(self.TOOL_CONFIG_MAP.keys())}")

        config = self.TOOL_CONFIG_MAP[tool]
        settings_path = self.backend_dir / config['settings_path']
        snapshot_path = settings_path.parent / config['snapshot_name']

        return {
            'settings': settings_path,
            'snapshot': snapshot_path
        }

    def save_snapshot(self, tool: str) -> Dict:
        """Save current configuration as snapshot"""
        paths = self._get_paths(tool)

        if not paths['settings'].exists():
            raise FileNotFoundError(f"Settings file not found: {paths['settings']}")

        # Read current settings
        with open(paths['settings'], 'r', encoding='utf-8') as f:
            current_config = json.load(f)

        # Save snapshot
        snapshot_data = {
            'timestamp': datetime.now().isoformat(),
            'tool': tool,
            'config': current_config
        }

        with open(paths['snapshot'], 'w', encoding='utf-8') as f:
            json.dump(snapshot_data, f, ensure_ascii=False, indent=2)

        return {
            'snapshot_path': str(paths['snapshot'].absolute()),
            'snapshot_created': True,
            'timestamp': snapshot_data['timestamp']
        }

    def set_test_config(self, tool: str, test_config: Dict) -> Dict:
        """Set test configuration (overwrites current settings)"""
        paths = self._get_paths(tool)

        # Write test config to settings file
        with open(paths['settings'], 'w', encoding='utf-8') as f:
            json.dump(test_config, f, ensure_ascii=False, indent=2)

        return {
            'config_updated': True,
            'settings_path': str(paths['settings'].absolute())
        }

    def restore_snapshot(self, tool: str) -> Dict:
        """Restore configuration from snapshot"""
        paths = self._get_paths(tool)

        if not paths['snapshot'].exists():
            return {
                'error': f"No snapshot found for {tool}",
                'snapshot_path': str(paths['snapshot'].absolute())
            }

        # Read snapshot
        with open(paths['snapshot'], 'r', encoding='utf-8') as f:
            snapshot_data = json.load(f)

        # Restore config
        with open(paths['settings'], 'w', encoding='utf-8') as f:
            json.dump(snapshot_data['config'], f, ensure_ascii=False, indent=2)

        # Delete snapshot
        os.remove(paths['snapshot'])

        return {
            'config_restored': True,
            'snapshot_deleted': True,
            'restored_from': snapshot_data['timestamp']
        }

    def check_snapshot(self, tool: str) -> Dict:
        """Check if snapshot exists for a tool"""
        paths = self._get_paths(tool)

        if not paths['snapshot'].exists():
            return {
                'has_snapshot': False,
                'tool': tool
            }

        # Read snapshot info
        with open(paths['snapshot'], 'r', encoding='utf-8') as f:
            snapshot_data = json.load(f)

        return {
            'has_snapshot': True,
            'tool': tool,
            'snapshot_path': str(paths['snapshot'].absolute()),
            'snapshot_time': snapshot_data['timestamp']
        }

    def check_all_snapshots(self) -> Dict:
        """Check for unrestored snapshots across all tools"""
        unrestored = []

        for tool in self.TOOL_CONFIG_MAP.keys():
            check_result = self.check_snapshot(tool)
            if check_result['has_snapshot']:
                unrestored.append({
                    'tool': tool,
                    'snapshot_path': check_result['snapshot_path'],
                    'snapshot_time': check_result['snapshot_time']
                })

        return {
            'unrestored': unrestored,
            'count': len(unrestored)
        }

    def restore_all_snapshots(self) -> Dict:
        """Restore all unrestored snapshots"""
        results = []

        for tool in self.TOOL_CONFIG_MAP.keys():
            check = self.check_snapshot(tool)
            if check['has_snapshot']:
                result = self.restore_snapshot(tool)
                results.append({
                    'tool': tool,
                    'success': result.get('config_restored', False)
                })

        return {
            'restored': results,
            'count': len(results)
        }
