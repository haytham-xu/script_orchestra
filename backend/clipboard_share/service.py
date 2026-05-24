"""
Clipboard Share Service

Business logic for clipboard sharing functionality.
"""
from datetime import datetime
from typing import List, Dict, Optional
from .config import MAX_HISTORY_SIZE, MAX_CONTENT_LENGTH


class ClipboardService:
    """Service for managing clipboard content"""

    def __init__(self):
        # In-memory storage for clipboard history
        # In production, could use Redis or database
        self._history: List[Dict] = []
        self._current_id = 0

    def add_content(self, content: str, source: str = "web") -> Dict:
        """
        Add new clipboard content

        Args:
            content: The clipboard text content
            source: Source of the content (web, mac, windows)

        Returns:
            Dict with the created clipboard item
        """
        if not content:
            raise ValueError("Content cannot be empty")

        if len(content) > MAX_CONTENT_LENGTH:
            raise ValueError(f"Content too large (max {MAX_CONTENT_LENGTH} bytes)")

        self._current_id += 1

        item = {
            "id": self._current_id,
            "content": content,
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "length": len(content)
        }

        # Add to beginning of history
        self._history.insert(0, item)

        # Keep only MAX_HISTORY_SIZE items
        if len(self._history) > MAX_HISTORY_SIZE:
            self._history = self._history[:MAX_HISTORY_SIZE]

        return item

    def get_latest(self) -> Optional[Dict]:
        """Get the most recent clipboard content"""
        return self._history[0] if self._history else None

    def get_history(self, limit: int = 20) -> List[Dict]:
        """
        Get clipboard history

        Args:
            limit: Maximum number of items to return

        Returns:
            List of clipboard items
        """
        return self._history[:limit]

    def get_by_id(self, item_id: int) -> Optional[Dict]:
        """Get clipboard item by ID"""
        for item in self._history:
            if item["id"] == item_id:
                return item
        return None

    def clear_history(self) -> int:
        """Clear all history and return count of items cleared"""
        count = len(self._history)
        self._history.clear()
        return count


# Singleton instance
_service_instance = None

def get_service() -> ClipboardService:
    """Get or create the clipboard service singleton"""
    global _service_instance
    if _service_instance is None:
        _service_instance = ClipboardService()
    return _service_instance
