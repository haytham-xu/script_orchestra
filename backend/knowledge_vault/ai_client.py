"""Knowledge Vault — Claude client via the Claude CLI (one-shot --print mode).

Authenticates through the locally logged-in Claude CLI (no ANTHROPIC_API_KEY),
same as poc03. We invoke the CLI directly in one-shot `--print` mode rather than
via claude_agent_sdk's stream-json protocol: the installed CLI (2.x) and the old
SDK (0.1.x) disagree on that protocol, which fails under a subprocess spawn.
One-shot mode is exactly the call we verified works. Kept independent of the
assistant module so the two tools stay decoupled.
"""
import os
import json
import shutil
import subprocess
from typing import Optional

MODEL = os.environ.get("KV_MODEL", "<model>")

# Default to the local proxy when the environment doesn't set one (e.g. under
# pm2, which doesn't inherit the interactive shell's env). The CLI reads
# ANTHROPIC_BASE_URL from the environment. Mirrors assistant/config.py.
_DEFAULT_BASE_URL = "<your-anthropic-base-url>"


def _cli_path() -> str:
    return os.environ.get("KV_CLAUDE_CLI") or shutil.which("claude") or "claude"


def _run_query(prompt: str, timeout: int = 120) -> str:
    """Run a one-shot prompt through the Claude CLI and return its text output."""
    env = dict(os.environ)
    env.setdefault("ANTHROPIC_BASE_URL", _DEFAULT_BASE_URL)
    try:
        proc = subprocess.run(
            [_cli_path(), "--print", "--model", MODEL, prompt],
            capture_output=True, text=True, timeout=timeout, env=env,
            stdin=subprocess.DEVNULL,   # never block waiting on a tty
        )
    except subprocess.TimeoutExpired:
        # subprocess.run already terminated the child on timeout.
        raise RuntimeError(f"claude CLI timed out after {timeout}s")
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude CLI exited {proc.returncode}: {(proc.stderr or proc.stdout or '').strip()[:400]}")
    return (proc.stdout or "").strip()


def ask_text(prompt: str, max_tokens: int = 1024, timeout: int = 120) -> str:
    # max_tokens kept for signature compatibility; the CLI manages limits.
    return _run_query(prompt, timeout=timeout)


def ask_json(prompt: str, max_tokens: int = 1024, timeout: int = 120) -> Optional[dict]:
    """Send a prompt expecting a JSON object back. Returns parsed dict or None.

    The CLI's --print output may wrap JSON in ```fences``` or add prose, so we
    extract the first balanced {...} block rather than trusting exact framing.
    """
    text = _run_query(prompt, timeout=timeout)
    obj = _extract_json_object(text)
    if obj is not None:
        return obj
    # Fallback: strip a leading ```json fence and try the whole thing.
    if text.startswith("```"):
        inner = text.split("```", 2)
        if len(inner) >= 2:
            body = inner[1]
            if body.startswith("json"):
                body = body[4:]
            try:
                return json.loads(body.strip())
            except json.JSONDecodeError:
                pass
    return None


def _extract_json_object(text: str) -> Optional[dict]:
    """Find and parse the first balanced top-level {...} JSON object in text."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None
