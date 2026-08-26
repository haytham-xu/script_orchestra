"""
Global Settings Manager for File-Git
Manages Baidu Cloud credentials and global configuration
"""
import json
import os
from typing import Dict, Optional


class SettingsManager:
    """Manages global file-git settings"""

    SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')
    DEFAULT_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'default_settings.json')

    @staticmethod
    def _load_settings() -> Dict:
        """Load settings from settings.json"""
        if not os.path.exists(SettingsManager.SETTINGS_FILE):
            return SettingsManager._get_default_settings()
        with open(SettingsManager.SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def _save_settings(settings: Dict):
        """Save settings to settings.json"""
        with open(SettingsManager.SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _get_default_settings() -> Dict:
        """Get default settings from JSON file"""
        try:
            with open(SettingsManager.DEFAULT_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading default settings: {e}")
            # Minimal fallback
            return {
                "baidu_cloud": {
                    "app_id": "",
                    "secret_key": "",
                    "app_key": "",
                    "sign_code": "",
                    "expires_in": "",
                    "refresh_token": "",
                    "access_token": ""
                },
                "use_mock_baidu": True,
                "default_password": ""
            }

    @staticmethod
    def get_settings() -> Dict:
        """Get all settings"""
        return SettingsManager._load_settings()

    @staticmethod
    def update_settings(settings: Dict) -> Dict:
        """
        Update settings

        Args:
            settings: Partial or full settings dict

        Returns:
            Updated full settings
        """
        current = SettingsManager._load_settings()

        # Deep merge for nested dicts
        if 'baidu_cloud' in settings:
            current['baidu_cloud'].update(settings['baidu_cloud'])

        if 'use_mock_baidu' in settings:
            current['use_mock_baidu'] = settings['use_mock_baidu']

        if 'default_password' in settings:
            current['default_password'] = settings['default_password']

        SettingsManager._save_settings(current)
        return current

    @staticmethod
    def get_baidu_credentials() -> Dict:
        """Get Baidu Cloud credentials"""
        settings = SettingsManager._load_settings()
        return settings.get('baidu_cloud', {})

    @staticmethod
    def update_baidu_credentials(patch: Dict) -> Dict:
        """Merge a partial patch into the baidu_cloud block and persist.

        Used by the OAuth flow to write access_token / refresh_token /
        expires_in / token_acquired_at without touching other settings.
        """
        current = SettingsManager._load_settings()
        current.setdefault('baidu_cloud', {}).update(patch)
        SettingsManager._save_settings(current)
        return current['baidu_cloud']

    @staticmethod
    def get_baidu_root_prefix() -> str:
        """Restricted Baidu apps can only read/write under /apps/<app>.

        The prefix is stored in baidu_cloud.root_prefix; defaults to
        /apps/sync-assistant (the user's existing app directory).
        """
        creds = SettingsManager.get_baidu_credentials()
        return creds.get('root_prefix') or '/apps/sync-assistant'

    @staticmethod
    def is_mock_enabled() -> bool:
        """Check if mock Baidu Cloud is enabled"""
        settings = SettingsManager._load_settings()
        return settings.get('use_mock_baidu', True)

    @staticmethod
    def get_default_password() -> str:
        """Get default encryption password"""
        settings = SettingsManager._load_settings()
        return settings.get('default_password', '')
