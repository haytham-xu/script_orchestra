"""Memory Curve — card entity (spaced-repetition flashcard)."""
from datetime import datetime, date


class Card:
    def __init__(self, id, front, back="", deck="", created_at=None,
                 updated_at=None, interval=0.0, ease=2.5, reps=0,
                 due_date=None, last_reviewed=None, suspended=0):
        self.id = id
        self.front = front              # qa: question; single: the content
        self.back = back                # qa: answer; single: empty
        self.deck = deck
        self.created_at = created_at
        self.updated_at = updated_at
        # SM-2 scheduling state
        self.interval = interval        # days
        self.ease = ease
        self.reps = reps
        self.due_date = due_date        # ISO date string YYYY-MM-DD
        self.last_reviewed = last_reviewed
        self.suspended = suspended

    @classmethod
    def new_instance(cls, front, back="", deck=""):
        today = date.today().isoformat()
        now = datetime.now().isoformat()
        return cls(None, front, back, deck, created_at=now, updated_at=now,
                   interval=0.0, ease=2.5, reps=0, due_date=today,
                   last_reviewed=None, suspended=0)

    def to_dict(self):
        return {
            "id": self.id,
            "front": self.front,
            "back": self.back,
            "deck": self.deck,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "interval": self.interval,
            "ease": self.ease,
            "reps": self.reps,
            "due_date": self.due_date,
            "last_reviewed": self.last_reviewed,
            "suspended": self.suspended,
        }

    @staticmethod
    def from_row(row):
        return Card(row[0], row[1], row[2], row[3], row[4], row[5],
                    row[6], row[7], row[8], row[9], row[10], row[11])
