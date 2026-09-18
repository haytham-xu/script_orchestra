"""
Settings database service for Roadmap
"""
import sqlite3
from .settings_models import RoadmapSettings
from shared.db import get_conn


class SettingsDatabase:
    """SQLite database for roadmap settings"""

    def __init__(self):
        self.init_db()

    def init_db(self):
        """Initialize database tables"""
        conn = get_conn()
        cursor = conn.cursor()

        # Create settings table (single row)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS roadmap_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                in_progress_timeout_hours REAL NOT NULL DEFAULT 4.0,
                done_auto_remove_days INTEGER DEFAULT NULL
            )
        ''')

        # Insert default settings if not exists
        cursor.execute('SELECT COUNT(*) FROM roadmap_settings WHERE id = 1')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO roadmap_settings (id, in_progress_timeout_hours, done_auto_remove_days)
                VALUES (1, 4.0, NULL)
            ''')

        conn.commit()
        conn.close()

    def get_settings(self) -> RoadmapSettings:
        """Get settings"""
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT in_progress_timeout_hours, done_auto_remove_days
            FROM roadmap_settings
            WHERE id = 1
        ''')

        row = cursor.fetchone()
        conn.close()

        if row:
            return RoadmapSettings(
                in_progress_timeout_hours=row[0],
                done_auto_remove_days=row[1]
            )
        else:
            # Return defaults if not found
            return RoadmapSettings()

    def update_settings(self, settings: RoadmapSettings) -> RoadmapSettings:
        """Update settings"""
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE roadmap_settings
            SET in_progress_timeout_hours = ?,
                done_auto_remove_days = ?
            WHERE id = 1
        ''', (
            settings.in_progress_timeout_hours,
            settings.done_auto_remove_days
        ))

        conn.commit()
        conn.close()

        return settings


# Global database instance
settings_db = SettingsDatabase()
