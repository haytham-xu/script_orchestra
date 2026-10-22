"""Web Terminal — window entity."""
import time
from dataclasses import dataclass


@dataclass
class TerminalWindow:
    window_id: str
    title: str
    cwd: str
    created_at: float
    last_active: float

    def to_dict(self) -> dict:
        return {
            'window_id': self.window_id,
            'title': self.title,
            'cwd': self.cwd,
            'created_at': self.created_at,
            'last_active': self.last_active,
        }

    @staticmethod
    def from_row(row) -> 'TerminalWindow':
        return TerminalWindow(
            window_id=row['window_id'],
            title=row['title'],
            cwd=row['cwd'],
            created_at=row['created_at'],
            last_active=row['last_active'],
        )
