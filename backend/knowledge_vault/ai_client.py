"""Knowledge Vault — Claude client (independent of the assistant module).

Uses the same env contract (ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL) but does
not import assistant, so the two tools stay decoupled.
"""
import json
import os
from typing import Optional

_client = None
MODEL = os.environ.get("KV_MODEL", "<model>")


def get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic
        kwargs = {}
        base = os.environ.get("ANTHROPIC_BASE_URL")
        key = os.environ.get("ANTHROPIC_API_KEY")
        if base:
            kwargs["base_url"] = base
        if key:
            kwargs["api_key"] = key
        _client = Anthropic(**kwargs)
    return _client


def ask_json(prompt: str, max_tokens: int = 1024) -> Optional[dict]:
    """Send a prompt expecting a JSON object back. Returns parsed dict or None."""
    resp = get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
    text = text.strip()
    # Tolerate ```json fences.
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def ask_text(prompt: str, max_tokens: int = 1024) -> str:
    resp = get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in resp.content
                   if getattr(block, "type", "") == "text").strip()
