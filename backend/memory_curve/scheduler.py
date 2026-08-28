"""Memory Curve — SM-2 (simplified) spaced-repetition scheduler.

Applies a review rating to a card and updates its interval / ease / due_date.
Ratings: again | hard | good | easy.
"""
from datetime import date, timedelta

from .entity import Card

MIN_EASE = 1.3
MAX_EASE = 3.0
VALID_RATINGS = ("again", "hard", "good", "easy")


def apply_review(card: Card, rating: str) -> Card:
    if rating not in VALID_RATINGS:
        raise ValueError(f"rating must be one of {VALID_RATINGS}")

    ease = card.ease or 2.5
    interval = card.interval or 0.0
    reps = card.reps or 0

    if rating == "again":
        reps = 0
        interval = 0  # due again today (relearn)
        ease = max(MIN_EASE, ease - 0.20)
    elif rating == "hard":
        interval = max(1, interval * 1.2) if interval else 1
        ease = max(MIN_EASE, ease - 0.15)
        reps += 1
    elif rating == "good":
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = interval * ease
        reps += 1
    elif rating == "easy":
        if reps == 0:
            interval = 4
        else:
            interval = interval * ease * 1.3
        ease = min(MAX_EASE, ease + 0.15)
        reps += 1

    card.ease = round(ease, 3)
    card.interval = round(interval, 2)
    card.reps = reps
    today = date.today()
    card.due_date = (today + timedelta(days=round(interval))).isoformat()
    card.last_reviewed = today.isoformat()
    return card
