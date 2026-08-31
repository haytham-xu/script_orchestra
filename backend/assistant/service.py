"""
Assistant Service

Two things:
  1. `classify_complexity` — a very short Haiku call that labels the user
     prompt as `simple` / `medium` / `hard`. That label maps to Haiku /
     Sonnet / Opus for the real answer.
  2. `chat` — non-streaming Claude call that turns a conversation + a new
     user message into an assistant reply, persists both messages, and
     returns the reply along with usage / routing metadata.

The `anthropic` SDK reads base_url and api_key from env when we construct
the client with explicit args, so tests / scripts can override at runtime.
"""
import logging
from typing import Dict, List, Optional, Tuple

from anthropic import Anthropic

from . import attachments, db

try:
    from . import summarizer as _summarizer
except Exception:  # noqa: BLE001
    _summarizer = None


def _post_message_hooks(conv_id: str) -> None:
    """Fire-and-forget maintenance after a successful assistant reply."""
    if _summarizer is not None:
        try:
            _summarizer.maybe_summarize(conv_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[assistant] post-hook summarize failed: {exc}")
from .config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    DEFAULT_MODEL_ALIAS,
    DEFAULT_SYSTEM_PROMPT,
    MAX_HISTORY_MESSAGES,
    MAX_OUTPUT_TOKENS,
    MODEL_ALIASES,
    ROUTER_MAX_TOKENS,
    ROUTER_TIMEOUT_SECONDS,
    router_model,
    complexity_model,
)

logger = logging.getLogger("assistant.service")

_CLASSIFIER_SYSTEM = (
    "You are a fast prompt-difficulty classifier for a chat assistant. "
    "Given the user's latest message (and optional short history), output "
    "EXACTLY one of these lowercase tokens with no other text:\n"
    "  simple — small talk, greetings, one-line factual questions, "
    "     trivial rewrites.\n"
    "  medium — questions that need a short explanation, code snippets, "
    "     multi-step reasoning of moderate depth.\n"
    "  hard — deep analysis, long-form writing, non-trivial code design, "
    "     careful multi-step logic, proofs, unusual/ambiguous requests.\n"
    "Answer with only the token, nothing else."
)


_client_singleton: Optional[Anthropic] = None


def get_client() -> Anthropic:
    """Return a shared Anthropic client bound to env-configured base_url/key."""
    global _client_singleton
    if _client_singleton is None:
        kwargs = {}
        if ANTHROPIC_BASE_URL:
            kwargs["base_url"] = ANTHROPIC_BASE_URL
        if ANTHROPIC_API_KEY:
            kwargs["api_key"] = ANTHROPIC_API_KEY
        _client_singleton = Anthropic(**kwargs)
    return _client_singleton


# ── Complexity classifier ─────────────────────────────────

def classify_complexity(user_message: str,
                        history: Optional[List[Dict]] = None) -> str:
    """
    Return one of 'simple' | 'medium' | 'hard'. Never raises; on any
    failure we fall back to 'medium' so the user still gets a good answer.
    """
    if not user_message.strip():
        return "simple"

    excerpt_history = ""
    if history:
        tail = history[-4:]
        excerpt_history = "\n\nRecent turns (for context, most recent last):\n" + "\n".join(
            f"[{m['role']}] {m['content'][:200]}" for m in tail
        )

    prompt = f"User message:\n{user_message}{excerpt_history}"

    try:
        resp = get_client().messages.create(
            model=router_model(),
            max_tokens=ROUTER_MAX_TOKENS,
            system=_CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            timeout=ROUTER_TIMEOUT_SECONDS,
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        ).strip().lower()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[assistant] classifier failed, defaulting to medium: {exc}")
        return "medium"

    for label in ("simple", "medium", "hard"):
        if label in text:
            return label
    logger.warning(f"[assistant] unrecognized classifier output: {text!r}, defaulting to medium")
    return "medium"


def resolve_model(model_alias: str, user_message: str,
                  history: Optional[List[Dict]] = None
                  ) -> Tuple[str, Optional[str]]:
    """
    Given the conversation's alias ('auto' / 'simple' / 'medium' / 'hard'),
    return (concrete_model_id, complexity_label_or_None). Concrete ids come
    from user settings (no hardcoded model names).
    """
    alias = (model_alias or DEFAULT_MODEL_ALIAS).lower()
    if alias not in MODEL_ALIASES:
        alias = DEFAULT_MODEL_ALIAS

    if alias != "auto":
        # a specific tier was forced
        return complexity_model(alias), None

    complexity = classify_complexity(user_message, history)
    return complexity_model(complexity), complexity


# ── Chat ──────────────────────────────────────────────────

def _build_context_messages(conv_id: str) -> List[Dict]:
    """
    Fetch the tail of the conversation shaped for the Anthropic API.
    For user messages with attachments, expands them into content blocks
    (text + image/document/text blocks). Assistant messages are always
    plain text. If a conversation has a rolling summary, only messages
    with id > summary_up_to_id are sent verbatim.
    """
    conv = db.get_conversation(conv_id)
    boundary = (conv or {}).get("summary_up_to_id") or 0

    all_msgs = db.list_messages(conv_id)
    if boundary:
        tail = [m for m in all_msgs if m["id"] > boundary]
    else:
        tail = all_msgs
    tail = tail[-MAX_HISTORY_MESSAGES:]

    context: List[Dict] = []
    for msg in tail:
        if msg["role"] == "assistant":
            context.append({"role": "assistant", "content": msg["content"]})
            continue

        rows = db.list_attachments_for_message(msg["id"])
        if not rows:
            context.append({"role": "user", "content": msg["content"]})
            continue

        att_blocks, warnings = attachments.as_content_blocks(rows)
        user_text = msg["content"]
        if warnings:
            user_text = user_text + "\n\n" + "\n".join(warnings)
        # Anthropic puts non-text blocks BEFORE the text prompt so the
        # model reads the attached material first.
        content_blocks: List[Dict] = list(att_blocks)
        if user_text:
            content_blocks.append({"type": "text", "text": user_text})
        context.append({"role": "user", "content": content_blocks})

    return context


def _validate_attachments(conv_id: str,
                          attachment_ids: Optional[List[str]]) -> List[Dict]:
    if not attachment_ids:
        return []
    return attachments.lookup_and_check_ownership(attachment_ids, conv_id)


def _effective_system_prompt(conv: Dict, user_query: str) -> Tuple[str, List[Dict]]:
    """
    Build the system prompt that goes to Claude. If this conversation has
    knowledge-base retrieval enabled AND at least one source exists, we
    embed the user's query, fetch the top-K relevant chunks, and append
    them as a context block below the user's own system prompt. If a
    rolling summary exists, we prepend it so the model has continuity
    even after older turns are dropped from the raw message array.

    Returns (system_prompt, retrieved_hits). Hits are also surfaced back
    to callers so the UI can show which snippets were used.
    """
    base = conv["system_prompt"] or DEFAULT_SYSTEM_PROMPT

    # Rolling summary of older turns, if any.
    summary = conv.get("summary")
    if summary:
        base = (
            base
            + "\n\n[Conversation summary so far, from turns older than the "
            + "recent messages you'll see]:\n"
            + summary
        )

    if not conv.get("kb_enabled"):
        return base, []

    # Import here to avoid making sentence-transformers a hard dependency
    # for people who never enable KB.
    try:
        from .knowledge import service as kb
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[assistant] KB module unavailable: {exc}")
        return base, []

    try:
        hits = kb.retrieve(user_query)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[assistant] KB retrieve failed: {exc}")
        return base, []

    if not hits:
        return base, []

    context_block = kb.format_context_block(hits)
    return base + "\n\n" + context_block, hits


def send_message(conv_id: str, user_content: str,
                 attachment_ids: Optional[List[str]] = None) -> Dict:
    """
    Persist the user message, call Claude once, persist and return the
    assistant reply along with routing / usage metadata.
    """
    # Attachments-only messages are legal: user might drop a screenshot
    # with no text. Fall back to a marker string in DB for clarity.
    if not user_content.strip() and not attachment_ids:
        raise ValueError("Message content cannot be empty")

    conv = db.get_conversation(conv_id)
    if conv is None:
        raise LookupError(f"Conversation not found: {conv_id}")

    att_rows = _validate_attachments(conv_id, attachment_ids)

    # Prior context BEFORE we insert this new user message, so the classifier
    # sees the last few turns without the current message duplicated in.
    prior_history = db.recent_messages_for_context(conv_id, MAX_HISTORY_MESSAGES)

    stored_text = user_content.strip() or f"[{len(att_rows)} attachment(s)]"
    user_msg = db.add_message(conv_id, "user", stored_text)
    if attachment_ids:
        db.attach_to_message(attachment_ids, user_msg["id"])

    model, complexity = resolve_model(
        conv["model_alias"], user_content, prior_history
    )

    context_messages = _build_context_messages(conv_id)
    system_prompt, kb_hits = _effective_system_prompt(conv, user_content)

    resp = get_client().messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=system_prompt,
        messages=context_messages,
    )

    reply_text = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    )
    usage = getattr(resp, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None

    assistant_msg = db.add_message(
        conv_id,
        "assistant",
        reply_text,
        model=model,
        complexity=complexity,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    _post_message_hooks(conv_id)

    return {
        "message": assistant_msg,
        "model": model,
        "complexity": complexity,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "kb_hits": kb_hits,
    }


def stream_message(conv_id: str, user_content: str,
                   attachment_ids: Optional[List[str]] = None):
    """
    Streaming variant of `send_message`. Yields dicts describing events:

      {"type": "start",  "model": ..., "complexity": ...}
      {"type": "delta",  "text": "…"}                    (repeated)
      {"type": "done",   "message": {...}, "model": ...,
                          "complexity": ..., "input_tokens": ...,
                          "output_tokens": ...}
      {"type": "error",  "message": "…"}                 (on failure)
    """
    if not user_content.strip() and not attachment_ids:
        yield {"type": "error", "message": "Message content cannot be empty"}
        return

    conv = db.get_conversation(conv_id)
    if conv is None:
        yield {"type": "error", "message": f"Conversation not found: {conv_id}"}
        return

    try:
        att_rows = _validate_attachments(conv_id, attachment_ids)

        prior_history = db.recent_messages_for_context(conv_id, MAX_HISTORY_MESSAGES)
        stored_text = user_content.strip() or f"[{len(att_rows)} attachment(s)]"
        user_msg = db.add_message(conv_id, "user", stored_text)
        if attachment_ids:
            db.attach_to_message(attachment_ids, user_msg["id"])

        model, complexity = resolve_model(
            conv["model_alias"], user_content, prior_history
        )
        context_messages = _build_context_messages(conv_id)
        system_prompt, kb_hits = _effective_system_prompt(conv, user_content)

        yield {
            "type": "start",
            "model": model,
            "complexity": complexity,
            "kb_hits": kb_hits,
        }

        collected: List[str] = []
        input_tokens = None
        output_tokens = None
        stream_error: Optional[str] = None

        try:
            with get_client().messages.stream(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system_prompt,
                messages=context_messages,
            ) as stream:
                for chunk in stream.text_stream:
                    if chunk:
                        collected.append(chunk)
                        yield {"type": "delta", "text": chunk}

                final = stream.get_final_message()
                usage = getattr(final, "usage", None)
                input_tokens = getattr(usage, "input_tokens", None) if usage else None
                output_tokens = getattr(usage, "output_tokens", None) if usage else None
        except Exception as exc:  # noqa: BLE001
            logger.exception("[assistant] stream mid-flight failure")
            stream_error = str(exc)

        reply_text = "".join(collected)

        # Persist whatever we managed to collect — even a partial reply is
        # more useful than nothing, and it means the retry button can pick
        # up from a coherent state.
        if reply_text:
            assistant_msg = db.add_message(
                conv_id,
                "assistant",
                reply_text + ("\n\n[stream interrupted]" if stream_error else ""),
                model=model,
                complexity=complexity,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        else:
            assistant_msg = None

        if stream_error:
            yield {
                "type": "error",
                "message": stream_error,
                "partial_message": assistant_msg,
            }
            return

        _post_message_hooks(conv_id)

        yield {
            "type": "done",
            "message": assistant_msg,
            "model": model,
            "complexity": complexity,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("[assistant] stream_message failed")
        yield {"type": "error", "message": str(exc)}


def stream_regenerate(conv_id: str):
    """
    Regenerate a fresh assistant reply for the current tail of the
    conversation. Unlike stream_message this does NOT insert a new user
    message — it assumes the caller already prepared the state (e.g.
    edit-and-truncate). If the last message is an assistant reply, it
    gets deleted first so the new one takes its place.
    """
    conv = db.get_conversation(conv_id)
    if conv is None:
        yield {"type": "error", "message": f"Conversation not found: {conv_id}"}
        return

    try:
        # If the last message is an assistant reply we treat this as a
        # "redo the last answer" call: drop it before regenerating so
        # the DB doesn't accumulate stale replies.
        all_msgs = db.list_messages(conv_id)
        if not all_msgs:
            yield {"type": "error", "message": "Conversation is empty"}
            return
        last = all_msgs[-1]
        if last["role"] == "assistant":
            import sqlite3 as _sqlite3
            with _sqlite3.connect(str(db.DB_PATH)) as _c:
                _c.execute("DELETE FROM messages WHERE id = ?", (last["id"],))
            all_msgs = all_msgs[:-1]
            if not all_msgs:
                yield {"type": "error", "message": "Nothing left after cleanup"}
                return
            last = all_msgs[-1]
        if last["role"] != "user":
            yield {"type": "error",
                   "message": "Last message must be a user message"}
            return

        user_content = last["content"]
        prior_history = [
            {"role": m["role"], "content": m["content"]}
            for m in all_msgs[:-1]
        ]
        model, complexity = resolve_model(
            conv["model_alias"], user_content, prior_history
        )
        context_messages = _build_context_messages(conv_id)
        system_prompt, kb_hits = _effective_system_prompt(conv, user_content)

        yield {
            "type": "start",
            "model": model,
            "complexity": complexity,
            "kb_hits": kb_hits,
        }

        collected: List[str] = []
        input_tokens = None
        output_tokens = None

        with get_client().messages.stream(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system_prompt,
            messages=context_messages,
        ) as stream:
            for chunk in stream.text_stream:
                if chunk:
                    collected.append(chunk)
                    yield {"type": "delta", "text": chunk}
            final = stream.get_final_message()
            usage = getattr(final, "usage", None)
            input_tokens = getattr(usage, "input_tokens", None) if usage else None
            output_tokens = getattr(usage, "output_tokens", None) if usage else None

        reply_text = "".join(collected)
        assistant_msg = db.add_message(
            conv_id, "assistant", reply_text,
            model=model, complexity=complexity,
            input_tokens=input_tokens, output_tokens=output_tokens,
        )
        _post_message_hooks(conv_id)
        yield {
            "type": "done",
            "message": assistant_msg,
            "model": model,
            "complexity": complexity,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("[assistant] stream_regenerate failed")
        yield {"type": "error", "message": str(exc)}
