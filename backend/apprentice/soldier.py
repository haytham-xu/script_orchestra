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


async def run() -> None:
    prompt = os.environ.get("APPRENTICE_SOLDIER_PROMPT", "")
    scope = os.environ.get("APPRENTICE_SOLDIER_SCOPE", "")
    model = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6"
    task_id = os.environ.get("APPRENTICE_TASK_ID", "?")

    if not prompt:
        print(json.dumps({"error": "APPRENTICE_SOLDIER_PROMPT not set"}))
        sys.exit(1)

    try:
        from claude_agent_sdk import (
            ClaudeSDKClient, ClaudeAgentOptions,
            AssistantMessage, ResultMessage, TextBlock,
        )
        from claude_agent_sdk.types import PermissionResultAllow
    except ImportError as e:
        print(json.dumps({"error": f"claude_agent_sdk not available: {e}"}))
        sys.exit(1)

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
