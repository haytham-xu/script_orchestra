"""Apprentice Soldier — isolated subagent subprocess.

Called by worker.py's dispatch_soldier tool via subprocess.run().
Reads task from env vars, runs a Claude agent, returns output to stdout.
"""
import asyncio
import json
import os
import sys
import traceback
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# ── WriteGate ─────────────────────────────────────────────────

def _parse_scope(scope_str: str) -> list[Path]:
    """Parse comma-separated glob patterns / paths into a list of resolved Paths."""
    if not scope_str.strip():
        return []
    parts = [p.strip() for p in scope_str.split(",") if p.strip()]
    return [Path(p).resolve() for p in parts]


def _path_allowed(file_path: str, allowed: list[Path]) -> bool:
    """Return True if file_path is inside at least one allowed path."""
    target = Path(file_path).resolve()
    for base in allowed:
        if base.is_file():
            if target == base:
                return True
        else:
            # treat as directory prefix
            try:
                target.relative_to(base)
                return True
            except ValueError:
                pass
    return False


def _build_write_gate(allowed_paths: list[Path]):
    """Return a can_use_tool callback that blocks writes outside allowed_paths."""
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext

    async def can_use_tool(
        tool_name: str,
        tool_input: dict,
        ctx: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool_name in ("Write", "Edit", "NotebookEdit"):
            file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            if file_path and not _path_allowed(file_path, allowed_paths):
                return PermissionResultDeny(
                    message=f"[WriteGate] '{file_path}' is outside the allowed scope: "
                            f"{[str(p) for p in allowed_paths]}"
                )
        return PermissionResultAllow()

    return can_use_tool


# ── Main ──────────────────────────────────────────────────────

async def run() -> None:
    prompt = os.environ.get("APPRENTICE_SOLDIER_PROMPT", "")
    scope = os.environ.get("APPRENTICE_SOLDIER_SCOPE", "")
    model = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6"

    if not prompt:
        print(json.dumps({"error": "APPRENTICE_SOLDIER_PROMPT not set"}))
        sys.exit(1)

    try:
        from claude_agent_sdk import (
            ClaudeSDKClient, ClaudeAgentOptions,
            AssistantMessage, ResultMessage, TextBlock,
        )
    except ImportError as e:
        print(json.dumps({"error": f"claude_agent_sdk not available: {e}"}))
        sys.exit(1)

    allowed_paths = _parse_scope(scope)
    scope_note = f"\nAllowed write scope: {scope}" if scope else ""
    system_prompt = f"""You are a Soldier — an isolated code execution agent.
You execute a specific coding task given to you by the Commander.
Complete the task precisely, then output a brief summary of what you did.{scope_note}
"""

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
        max_turns=30,
        model=model,
        can_use_tool=_build_write_gate(allowed_paths) if allowed_paths else None,
    )

    result_text = ""
    async with ClaudeSDKClient(options=options) as agent:
        await agent.query(prompt)
        async for msg in agent.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in (msg.content or []):
                    if isinstance(block, TextBlock):
                        result_text += block.text
            elif isinstance(msg, ResultMessage):
                break

    print(result_text or "(done)")


def main() -> None:
    try:
        asyncio.run(run())
    except Exception as e:
        tb = traceback.format_exc()
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        print(tb, file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
