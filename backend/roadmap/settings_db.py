"""
Settings database service for Roadmap
"""
import sqlite3
import os
from .settings_models import RoadmapSettings


class SettingsDatabase:
    """SQLite database for roadmap settings"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create settings table (single row)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                in_progress_timeout_hours REAL NOT NULL DEFAULT 4.0,
                done_auto_remove_days INTEGER DEFAULT NULL
            )
        ''')

        # Insert default settings if not exists
        cursor.execute('SELECT COUNT(*) FROM settings WHERE id = 1')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO settings (id, in_progress_timeout_hours, done_auto_remove_days)
                VALUES (1, 4.0, NULL)
            ''')

        conn.commit()
        conn.close()

    def get_settings(self) -> RoadmapSettings:
        """Get settings"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT in_progress_timeout_hours, done_auto_remove_days
            FROM settings
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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE settings
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
_db_path = os.path.join(os.path.dirname(__file__), 'tasks.db')
settings_db = SettingsDatabase(_db_path)
