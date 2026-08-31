"""
Rolling conversation summarization.

When a conversation grows past `SUMMARIZATION_TRIGGER` messages, the
oldest turns are compressed into a summary stored in
`conversations.summary`. The `summary_up_to_id` column tracks which
message ID is the boundary — anything with a smaller ID is considered
"covered" by the summary and only shows up as summary text.

The summary is *incremental*: when more turns pile up, we ask Haiku to
extend the existing summary rather than rewriting from scratch, so cost
scales with new content rather than total history length.
"""
import logging
import sqlite3
from typing import List, Optional, Tuple

from . import db
from .config import (
    KEEP_RECENT_MESSAGES,
    SUMMARIZATION_TRIGGER,
    SUMMARIZER_MAX_TOKENS,
)

logger = logging.getLogger("assistant.summarizer")


_SUMMARIZER_SYSTEM = (
    "You compress chat history for a conversational assistant. Your only "
    "output is a concise summary that preserves the user's goals, key "
    "facts they've established, decisions made, and any outstanding tasks. "
    "Keep it factual, bullet-point when helpful, and short — aim for 200 "
    "words unless the content genuinely needs more. Do NOT introduce new "
    "opinions, do NOT address the user in second person, and do NOT wrap "
    "the summary in commentary. If a previous summary is provided, "
    "extend it rather than replacing it wholesale."
)


def _format_msgs(msgs: List[dict]) -> str:
    lines = []
    for m in msgs:
        role = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{role}: {m['content']}")
    return "\n\n".join(lines)


def maybe_summarize(conv_id: str) -> Optional[str]:
    """
    Idempotent trigger. Runs the summarizer only if the conversation has
    grown past the threshold and there's meaningful new content since
    the last summary boundary. Returns the resulting summary string, or
    None if nothing was done.
    """
    from .service import get_client   # local import to break cycles
    from .config import router_model

    conv = db.get_conversation(conv_id)
    if conv is None:
        return None

    msgs = db.list_messages(conv_id)
    if len(msgs) < SUMMARIZATION_TRIGGER:
        return None

    boundary = conv.get("summary_up_to_id") or 0
    # Messages that are older than what the current summary already covers.
    to_summarize = [m for m in msgs if m["id"] > boundary][:-KEEP_RECENT_MESSAGES]
    if not to_summarize:
        return None

    prior_summary = conv.get("summary") or ""
    context = _format_msgs(to_summarize)

    prompt = (
        (f"Previous summary:\n{prior_summary}\n\n" if prior_summary else "")
        + f"New chat turns to incorporate:\n{context}"
    )

    try:
        resp = get_client().messages.create(
            model=router_model(),   # the small router/summarizer model (from settings)
            max_tokens=SUMMARIZER_MAX_TOKENS,
            system=_SUMMARIZER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[summarizer] Claude call failed: {exc}")
        return None

    text = "".join(
        block.text for block in resp.content
        if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        return None

    new_boundary = to_summarize[-1]["id"]
    db.set_conversation_summary(conv_id, text, new_boundary)
    logger.info(
        f"[summarizer] updated conv {conv_id}: boundary→{new_boundary}, "
        f"compressed {len(to_summarize)} messages, summary length {len(text)}"
    )
    return text
