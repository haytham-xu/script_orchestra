"""Knowledge Vault — Claude client via claude_agent_sdk.

Uses claude_agent_sdk (the Claude Code SDK), which authenticates through the
locally logged-in Claude CLI — no ANTHROPIC_API_KEY needed. This mirrors poc03's
approach and works with the local proxy (ANTHROPIC_BASE_URL). Kept independent
of the assistant module so the two tools stay decoupled.
"""
import os
import json
import asyncio
from typing import Optional

MODEL = os.environ.get("KV_MODEL", "<model>")


def _run_query(prompt: str) -> str:
    """Run a one-shot query through claude_agent_sdk and return the text reply.

    claude_agent_sdk is async-only; we drive it on a private event loop so the
    Flask (sync) request thread can call ask_json/ask_text directly.
    """
    from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

    async def _go() -> str:
        parts = []
        options = ClaudeAgentOptions(model=MODEL)
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
        return "".join(parts).strip()

    # A background-thread request has no running loop; make our own.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_go())
    finally:
        loop.close()


def ask_text(prompt: str, max_tokens: int = 1024) -> str:
    # max_tokens kept for signature compatibility; the CLI manages limits.
    return _run_query(prompt)


def ask_json(prompt: str, max_tokens: int = 1024) -> Optional[dict]:
    """Send a prompt expecting a JSON object back. Returns parsed dict or None."""
    text = _run_query(prompt)
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
