"""
Settings models for Roadmap
"""
from typing import Optional


class RoadmapSettings:
    """Roadmap settings model"""
    def __init__(
        self,
        in_progress_timeout_hours: float = 4.0,
        done_auto_remove_days: Optional[int] = None
    ):
        self.in_progress_timeout_hours = in_progress_timeout_hours
        self.done_auto_remove_days = done_auto_remove_days

    def to_dict(self):
        """Convert to dict for JSON serialization"""
        return {
            "inProgressTimeoutHours": self.in_progress_timeout_hours,
            "doneAutoRemoveDays": self.done_auto_remove_days
        }

    @staticmethod
    def from_dict(data: dict) -> 'RoadmapSettings':
        """Create Settings from dict"""
        return RoadmapSettings(
            in_progress_timeout_hours=data.get("inProgressTimeoutHours", 4.0),
            done_auto_remove_days=data.get("doneAutoRemoveDays", None)
        )
