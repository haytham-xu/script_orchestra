"""Translator — entities.

Two persisted layers, both scene-scoped:
  - TranslationHistory: one row per translation (zh2en or en2zh), the source
    text and its result. zh2en also stores the back-translation. Each row also
    stores `usage` — the aggregated Copilot usage for that translation (AI
    credits + token counts + the model actually used).
  - LearningPoint: AI-extracted English learning notes, only produced by the
    zh2en scene, each linked to its history row. Fields (original / suggestion
    / explanation) are shaped to map cleanly onto a future memory-card
    (memory_curve) front/back, but that integration is not built yet.
"""
import json
from datetime import datetime


class TranslationHistory:
    """One translation record. scene distinguishes 'zh2en' from 'en2zh'."""

    def __init__(self, id, scene, source_text, result_text,
                 back_translation="", model="", created_at=None, usage=None):
        self.id = id
        self.scene = scene                    # 'zh2en' | 'en2zh'
        self.source_text = source_text        # what the user typed
        self.result_text = result_text        # zh2en=english / en2zh=chinese
        self.back_translation = back_translation  # zh2en only
        self.model = model
        self.created_at = created_at
        self.usage = usage or {}              # aggregated Copilot usage for this row
        self.learning_points = []             # populated on load (zh2en only)

    @classmethod
    def new_instance(cls, scene, source_text, result_text,
                     back_translation="", model="", usage=None):
        return cls(None, scene, source_text, result_text,
                   back_translation, model, created_at=datetime.now().isoformat(),
                   usage=usage or {})

    def to_dict(self):
        return {
            "id": self.id,
            "scene": self.scene,
            "source_text": self.source_text,
            "result_text": self.result_text,
            "back_translation": self.back_translation,
            "model": self.model,
            "created_at": self.created_at,
            "usage": self.usage,
            "learning_points": [lp.to_dict() for lp in self.learning_points],
        }

    @staticmethod
    def from_row(r):
        # r: id, scene, source_text, result_text, back_translation, model, created_at, usage_json
        usage = {}
        if len(r) > 7 and r[7]:
            try:
                usage = json.loads(r[7])
            except (ValueError, TypeError):
                usage = {}
        return TranslationHistory(r[0], r[1], r[2], r[3], r[4], r[5], r[6], usage=usage)


class LearningPoint:
    """An English learning note derived from the user's zh2en source text.

    original    — what the user wrote (spelling error / awkward / non-idiomatic)
    suggestion  — a more idiomatic way to say it
    explanation — short why / what rule
    Linked to a TranslationHistory row via history_id.
    """

    def __init__(self, id, history_id, original, suggestion="",
                 explanation="", created_at=None):
        self.id = id
        self.history_id = history_id
        self.original = original
        self.suggestion = suggestion
        self.explanation = explanation
        self.created_at = created_at

    @classmethod
    def new_instance(cls, history_id, original, suggestion="", explanation=""):
        return cls(None, history_id, original, suggestion, explanation,
                   created_at=datetime.now().isoformat())

    def to_dict(self):
        return {
            "id": self.id,
            "history_id": self.history_id,
            "original": self.original,
            "suggestion": self.suggestion,
            "explanation": self.explanation,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_row(r):
        # r: id, history_id, original, suggestion, explanation, created_at
        return LearningPoint(r[0], r[1], r[2], r[3], r[4], r[5])
