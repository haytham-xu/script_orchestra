"""Apprentice worker — subprocess entry point.

Called as: python worker.py <task_id>

Runs the Commander agent loop. Commander has no fixed stages —
it self-plans based on the task description and its own long-term memory.
"""
import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Annotated

sys.stdout.reconfigure(line_buffering=True)

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from apprentice import repository, settings_manager, memory_service  # noqa: E402
from apprentice.integration_service import (  # noqa: E402
    get_pr_status, get_pr_review_comments,
    get_build_result, get_build_console,
)


def emit(event_type: str, data: dict) -> None:
    print(json.dumps({"event": event_type, **data}), flush=True)


def _text(s: str) -> dict:
    return {"content": [{"type": "text", "text": s}]}


# ── Commander system prompt ──────────────────────────────────

_SYSTEM_TEMPLATE = """\
You are Apprentice — an autonomous developer agent.

## Red lines (never violate — these are absolute boundaries)
{red_lines}

## Your long-term memory (accumulated experience and principles)
{long_memory}

## Current task
Title: {task_title}
Description:
{task_description}

Target repository: {repo_path}

## How to work
- You decide your own steps. There are no fixed stages.
- Think through the task, plan your approach, then execute.
- Use dispatch_soldier to delegate code changes to an isolated subagent.
- Use query_github / query_jenkins to check external feedback on your work.
- Use check_human_messages periodically — the user may have sent guidance.
- Use post_checkpoint when you need the user's approval before a risky step.
- When finished, call write_short_memory with a narrative of what happened and what you learned.
- End your final response with [DONE] when the task is complete, or [HALTED] if you must stop.
"""


def _build_system_prompt(task_id: int) -> str:
    task = repository.get_task(task_id)
    red_lines = repository.list_red_lines()
    long_memory = memory_service.get_long_memory_text()

    if red_lines:
        red_lines_text = "\n".join(f"- {r.rule}" for r in red_lines)
    else:
        red_lines_text = "(none configured — use good judgment)"

    if not long_memory:
        long_memory = "(no experience yet — you are just starting)"

    return _SYSTEM_TEMPLATE.format(
        red_lines=red_lines_text,
        long_memory=long_memory,
        task_title=task.title,
        task_description=task.description,
        repo_path=task.repo_path,
    )


# ── Worker main ──────────────────────────────────────────────

async def run(task_id: int) -> None:
    emit("system", {"content": f"Apprentice worker starting for task {task_id}"})

    settings = settings_manager.load_settings()
    task = repository.get_task(task_id)
    if task is None:
        emit("done", {"status": "failed", "reason": f"task {task_id} not found"})
        return

    commander_model = settings.get("commander_model") or "claude-opus-4-5"
    soldier_model = settings.get("soldier_model") or "claude-sonnet-4-6"
    max_turns = int(settings.get("commander_max_turns") or 50)
    max_cost_usd = float(settings.get("max_cost_usd") or 0)

    try:
        from claude_agent_sdk import (
            ClaudeSDKClient, ClaudeAgentOptions,
            AssistantMessage, ResultMessage, TextBlock, ToolUseBlock,
            tool, create_sdk_mcp_server,
        )
    except ImportError as e:
        emit("done", {"status": "failed", "reason": f"claude_agent_sdk not available: {e}"})
        return

    system_prompt = _build_system_prompt(task_id)
    emit("system", {"content": f"Commander model: {commander_model}"})
    emit("system", {"content": f"Soldier model:   {soldier_model}"})

    # ── MCP tools ────────────────────────────────────────────

    soldier_seq = [0]
    turns_since_soldier = [0]
    cumulative_cost = [0.0]

    @tool(
        "dispatch_soldier",
        "Dispatch an isolated Soldier subagent to execute code work in the repository.",
        {
            "prompt": Annotated[str, "Detailed instructions for the Soldier."],
            "scope": Annotated[str, "Comma-separated file/dir patterns the Soldier may write (empty = unrestricted)."],
        },
    )
    async def dispatch_soldier(args: dict) -> dict:
        prompt = args["prompt"]
        scope = args.get("scope", "")
        soldier_seq[0] += 1
        seq = soldier_seq[0]
        emit("soldier_start", {"seq": seq, "prompt_preview": prompt[:200]})
        turns_since_soldier[0] = 0

        env = dict(os.environ)
        env["APPRENTICE_SOLDIER_PROMPT"] = prompt
        env["APPRENTICE_SOLDIER_SCOPE"] = scope
        env["ANTHROPIC_MODEL"] = soldier_model
        env["APPRENTICE_TASK_ID"] = str(task_id)

        soldier_script = Path(__file__).parent / "soldier.py"
        import subprocess as sp
        result = sp.run(
            [sys.executable, "-u", str(soldier_script)],
            capture_output=True, text=True, timeout=600,
            stdin=sp.DEVNULL, env=env,
        )
        output = (result.stdout or "").strip()
        if result.returncode != 0:
            error = (result.stderr or "").strip()[-500:]
            emit("soldier_done", {"seq": seq, "status": "failed", "error": error})
            return _text(f"[Soldier {seq} FAILED] {error}")
        emit("soldier_done", {"seq": seq, "status": "done", "output_preview": output[:300]})
        return _text(output or f"[Soldier {seq} completed with no output]")

    @tool("read_long_memory", "Read your accumulated long-term memory (distilled principles).", {})
    async def read_long_memory(args: dict) -> dict:
        return _text(memory_service.get_long_memory_text() or "(empty)")

    @tool("read_red_lines", "Read the red lines (absolute boundaries you must never cross).", {})
    async def read_red_lines(args: dict) -> dict:
        lines = repository.list_red_lines()
        if not lines:
            return _text("(none configured)")
        return _text("\n".join(f"- {r.rule}" for r in lines))

    @tool("check_human_messages", "Check for unread messages from the user in the human channel.", {})
    async def check_human_messages(args: dict) -> dict:
        msgs = repository.get_unread_user_messages(task_id)
        if not msgs:
            return _text("(no new messages)")
        repository.mark_messages_read([m.id for m in msgs])
        parts = [f"[{m.created_at}] {m.content}" for m in msgs]
        return _text("\n".join(parts))

    @tool(
        "post_checkpoint",
        "Post a checkpoint message to the user and wait for their response before continuing. Use before risky steps.",
        {"message": Annotated[str, "What you are asking or about to do."]},
    )
    async def post_checkpoint(args: dict) -> dict:
        message = args["message"]
        repository.post_human_message(task_id, "cmd_to_user", message)
        emit("checkpoint", {"content": message})
        for _ in range(600):
            await asyncio.sleep(1)
            new_msgs = repository.get_unread_user_messages(task_id)
            if new_msgs:
                repository.mark_messages_read([m.id for m in new_msgs])
                return _text("\n".join(m.content for m in new_msgs))
        return _text("(no response received within 10 minutes — continuing)")

    @tool(
        "write_short_memory",
        "Write a narrative of this task to short-term memory for future learning. Call when the task is complete.",
        {"narrative": Annotated[str, "Your narrative of the task experience, written in first person."]},
    )
    async def write_short_memory(args: dict) -> dict:
        narrative = args["narrative"]
        memory_service.append_short_memory(task_id, narrative)
        emit("memory_written", {"preview": narrative[:200]})
        return _text("Memory written.")

    @tool(
        "query_github",
        "Query GitHub for a pull request's status and review comments.",
        {
            "repo_full_name": Annotated[str, "e.g. 'owner/repo'"],
            "pr_number": Annotated[int, "PR number"],
        },
    )
    async def query_github(args: dict) -> dict:
        try:
            status = get_pr_status(args["repo_full_name"], int(args["pr_number"]))
            comments = get_pr_review_comments(args["repo_full_name"], int(args["pr_number"]))
            return _text(json.dumps({"pr": status, "review_comments": comments}, indent=2))
        except Exception as e:
            return _text(f"[GitHub error] {e}")

    @tool(
        "query_jenkins",
        "Query Jenkins for a build result and console log excerpt.",
        {
            "job_name": Annotated[str, "Jenkins job name"],
            "build_number": Annotated[int, "Build number"],
        },
    )
    async def query_jenkins(args: dict) -> dict:
        try:
            result = get_build_result(args["job_name"], int(args["build_number"]))
            console = get_build_console(args["job_name"], int(args["build_number"]))
            return _text(json.dumps({"build": result, "console_tail": console}, indent=2))
        except Exception as e:
            return _text(f"[Jenkins error] {e}")

    # ── MCP server ───────────────────────────────────────────

    supervisor_server = create_sdk_mcp_server(
        name="apprentice",
        version="1.0.0",
        tools=[
            dispatch_soldier, read_long_memory, read_red_lines,
            check_human_messages, post_checkpoint, write_short_memory,
            query_github, query_jenkins,
        ],
    )

    commander_options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        mcp_servers={"apprentice": supervisor_server},
        allowed_tools=["Read", "Glob", "Grep",
                       "mcp__apprentice__dispatch_soldier",
                       "mcp__apprentice__read_long_memory",
                       "mcp__apprentice__read_red_lines",
                       "mcp__apprentice__check_human_messages",
                       "mcp__apprentice__post_checkpoint",
                       "mcp__apprentice__write_short_memory",
                       "mcp__apprentice__query_github",
                       "mcp__apprentice__query_jenkins"],
        permission_mode="acceptEdits",
        cwd=task.repo_path,
        max_turns=max_turns,
        model=commander_model,
    )

    # ── Commander loop ───────────────────────────────────────

    current_prompt = (
        "Start working on the task. Plan your approach, then execute step by step. "
        "Check your red lines and long-term memory first. "
        "When done, write your experience to memory and emit [DONE]."
    )
    turn = 0
    HEARTBEAT_STALE_TURNS = 10

    async with ClaudeSDKClient(options=commander_options) as commander:
        emit("system", {"content": "Commander session opened."})

        while True:
            turn += 1
            emit("commander_turn_start", {"turn_no": turn})
            turns_since_soldier[0] += 1

            t0 = time.time()
            await commander.query(current_prompt)

            full_text = ""
            subtype = "unknown"
            cost = 0.0

            async for msg in commander.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in (msg.content or []):
                        if isinstance(block, TextBlock):
                            emit("commander_text", {"turn_no": turn, "text": block.text})
                            full_text += block.text
                        elif isinstance(block, ToolUseBlock):
                            emit("commander_tool_use", {
                                "turn_no": turn,
                                "tool_name": block.name,
                                "input_preview": str(block.input)[:200],
                            })
                elif isinstance(msg, ResultMessage):
                    subtype = msg.subtype
                    cost = msg.total_cost_usd or 0.0
                    break

            duration = time.time() - t0
            emit("commander_turn_end", {
                "turn_no": turn, "subtype": subtype,
                "cost_usd": cost, "duration_s": round(duration, 1),
            })
            cumulative_cost[0] += cost

            # ── [DONE] ────────────────────────────────────────
            if "[DONE]" in full_text:
                emit("system", {"content": "[DONE] received — task complete."})
                emit("done", {"status": "completed"})
                return

            # ── [HALTED] ──────────────────────────────────────
            if "[HALTED]" in full_text:
                emit("system", {"content": "[HALTED] received — stopping."})
                emit("done", {"status": "failed", "reason": "commander_halted"})
                return

            # ── max_turns ─────────────────────────────────────
            if subtype == "error_max_turns":
                emit("system", {"content": "Commander hit max_turns limit."})
                emit("done", {"status": "failed", "reason": "max_turns"})
                return

            # ── cost cap ──────────────────────────────────────
            if max_cost_usd > 0 and cumulative_cost[0] >= max_cost_usd:
                emit("system", {"content": f"Cost cap ${max_cost_usd:.2f} reached (${cumulative_cost[0]:.2f})."})
                emit("done", {"status": "failed", "reason": "cost_cap"})
                return

            # ── heartbeat ─────────────────────────────────────
            if turns_since_soldier[0] >= HEARTBEAT_STALE_TURNS:
                emit("system", {"content": f"Heartbeat: {turns_since_soldier[0]} turns with no Soldier dispatch."})
                emit("done", {"status": "failed", "reason": "heartbeat_stale"})
                return

            current_prompt = "Continue."


def main() -> None:
    if len(sys.argv) < 2:
        emit("done", {"status": "failed", "reason": "usage: worker.py <task_id>"})
        sys.exit(2)
    task_id = int(sys.argv[1])
    try:
        asyncio.run(run(task_id))
    except Exception as e:
        tb = traceback.format_exc()
        emit("done", {"status": "failed", "reason": f"{type(e).__name__}: {e}"})
        print(tb, file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    main()
