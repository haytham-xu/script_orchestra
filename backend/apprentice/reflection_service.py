"""Apprentice — self-reflection (自省) service.

Triggered after the user submits feedback on a completed task.
Gives Apprentice its own decision log + user feedback and asks it to
audit its reasoning — producing a richer lesson than distillation alone.
"""
import json
import os
import shutil
import subprocess

from . import repository, settings_manager


def _build_decision_log(task_id: int) -> str:
    events = repository.list_task_events(task_id)
    lines = []
    for e in events:
        et = e.event_type
        if et not in ("commander_text", "commander_tool_use", "soldier_start", "soldier_done"):
            continue
        try:
            payload = json.loads(e.payload)
        except Exception:
            continue
        if et == "commander_text":
            text = (payload.get("text") or "").strip()
            if text:
                lines.append(f"[Reasoning] {text}")
        elif et == "commander_tool_use":
            tool = payload.get("tool_name", "")
            preview = payload.get("input_preview", "")
            lines.append(f"[Tool call] {tool}({preview[:300]})")
        elif et == "soldier_start":
            preview = payload.get("prompt_preview", "")
            lines.append(f"[Soldier dispatched] {preview[:300]}")
        elif et == "soldier_done":
            status = payload.get("status", "")
            preview = payload.get("output_preview", "") or payload.get("error", "")
            lines.append(f"[Soldier result] status={status} | {preview[:200]}")
    return "\n".join(lines) if lines else "(no decision log available)"


def trigger_reflection(short_memory_id: int) -> None:
    """Run self-reflection for a short-memory entry that has user feedback.

    Stores the reflection in apprentice_reflection and appends a summary
    addendum to the short-memory raw_log so distillation picks it up.
    """
    entry = repository.get_short_memory_by_id(short_memory_id)
    if entry is None:
        return

    task = repository.get_task(entry.task_id)
    if task is None:
        return

    settings = settings_manager.load_settings()
    model = (settings.get("distillation_model") or "claude-sonnet-4-6").strip()

    decision_log = _build_decision_log(entry.task_id)
    score_str = str(entry.user_score) if entry.user_score is not None else "not rated"
    note_str = entry.user_note or "(no note provided)"

    prompt = f"""You are Apprentice — an autonomous developer agent. You just completed a task and received feedback from the user. Your job now is to reflect honestly on your own decision-making.

## The task you completed
Title: {task.title}
Description:
{task.description}

## What you wrote about what you did (your narrative)
{entry.raw_log}

## Your actual decisions (from the event log)
{decision_log}

## User feedback
Score: {score_str}/5
Note: "{note_str}"

## Your task: self-reflection

Answer these three questions honestly and specifically. Do not be vague or defensive.

### 1. What I decided and why
For each key decision you made during this task, describe the reasoning you used at the time. Be specific — "I read the task description which said X, so I did Y" or "I assumed Z without verifying it."

### 2. Where the feedback points
For each criticism raised by the user (or implied by a low score), trace it back: which specific decision caused it? What was the reasoning — or lack of reasoning — that led to that decision? Was information available to you at the time that could have led to a better outcome, and did you use it?

### 3. What I will do differently
For each gap identified above, state a concrete behavioral rule for future tasks. Not "I will be more careful" but a specific trigger-action rule: "When [situation], I will [specific action] before [proceeding]."

Be honest. The goal is not to justify your decisions but to understand them well enough to improve."""

    cli = shutil.which("claude") or "claude"
    result = subprocess.run(
        [cli, "--print", "--model", model, prompt],
        capture_output=True, text=True, timeout=240,
        stdin=subprocess.DEVNULL, env=dict(os.environ),
    )
    if result.returncode != 0 or not (result.stdout or "").strip():
        raise RuntimeError(
            f"Reflection failed (exit {result.returncode}): "
            f"{(result.stderr or result.stdout or '').strip()[:400]}"
        )

    reflection_text = result.stdout.strip()

    # Check if a reflection already exists before appending to raw_log.
    # upsert_reflection is idempotent (updates in-place), but append_to_short_memory_log
    # concatenates unconditionally — skip the append on re-runs to avoid duplicate blocks.
    already_exists = repository.get_reflection(short_memory_id) is not None

    # Store full reflection
    repository.upsert_reflection(short_memory_id, entry.task_id, reflection_text)

    # Extract just the "What I will do differently" section as addendum to raw_log
    # so distillation sees the concrete rules, not just the original narrative
    if not already_exists:
        addendum = _extract_action_rules(reflection_text)
        repository.append_to_short_memory_log(short_memory_id, addendum)


def _extract_action_rules(reflection_text: str) -> str:
    """Extract the 'What I will do differently' section, or fall back to full text."""
    marker = "### 3. What I will do differently"
    idx = reflection_text.find(marker)
    if idx != -1:
        return reflection_text[idx + len(marker):].strip()
    # Fallback: use last third of the text
    lines = reflection_text.strip().splitlines()
    return "\n".join(lines[len(lines) * 2 // 3:]).strip() or reflection_text[:600]
