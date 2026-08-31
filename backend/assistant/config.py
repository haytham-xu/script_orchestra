"""
Assistant Config

Reads Anthropic base URL / API key from env, mirroring poc03's convention.
Model IDs and defaults are declared here so the rest of the module never
hard-codes strings.
"""
import os
from pathlib import Path

# Anthropic API — read from the environment (no baked-in default).
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Model IDs are NOT hardcoded here — they are user-configured and persisted
# (see settings_manager). Code refers to tier *names* (router/simple/medium/hard)
# and resolves the real id from settings at call time.
from . import settings_manager


def router_model() -> str:
    """Tiny model for complexity classification + summarization."""
    return settings_manager.model_for("router")


def complexity_model(complexity: str) -> str:
    """Resolve a complexity tier (simple/medium/hard) to its configured model id."""
    return settings_manager.model_for(complexity if complexity in ("simple", "medium", "hard") else "simple")


# UI selector values. "auto" lets the router decide; the tier names map to the
# same-named settings slots (resolved via complexity_model / model_for).
MODEL_ALIASES = ("auto", "simple", "medium", "hard")

# Default behaviour when the user hasn't picked one
DEFAULT_MODEL_ALIAS = "auto"

# Generation limits
MAX_OUTPUT_TOKENS = 4096
ROUTER_MAX_TOKENS = 32   # classifier only needs a couple of tokens
ROUTER_TIMEOUT_SECONDS = 8

# Conversation defaults
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful, concise assistant. "
    "Answer in the same language the user writes in. "
    "When code is involved, use fenced code blocks with language tags."
)
MAX_HISTORY_MESSAGES = 40   # how many past turns to feed back into the model

# Context summarization: when a conversation grows past this many
# messages, oldest turns get compressed into a rolling summary that
# lives in `conversations.summary`. Only the most recent
# `KEEP_RECENT_MESSAGES` are sent verbatim; the summary covers the rest.
SUMMARIZATION_TRIGGER = 30
KEEP_RECENT_MESSAGES = 12
SUMMARIZER_MAX_TOKENS = 1024

# SQLite path (co-located with this module, like duplicate_finder)
DB_PATH = Path(__file__).resolve().parent / "assistant.db"

# Where uploaded attachment bytes live. One file per attachment, named by
# content hash so identical uploads dedupe automatically.
MEDIA_DIR = Path(__file__).resolve().parent / "media"

# Upload limits
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024   # 20 MB per file
MAX_ATTACHMENTS_PER_MESSAGE = 8

# Mime types we treat as vision inputs. Everything else that Anthropic
# accepts as `document` (PDFs) goes through the document code path. Plain
# text and small text-like docs get inlined into the prompt.
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
DOCUMENT_MIME_TYPES = {"application/pdf"}
TEXT_MIME_PREFIXES = ("text/",)
MAX_TEXT_INLINE_BYTES = 200 * 1024   # 200 KB — bigger texts get truncated
