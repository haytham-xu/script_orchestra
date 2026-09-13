"""Apprentice — three-layer memory service."""
import os
import shutil
import subprocess
from typing import Optional

from . import repository, settings_manager


def get_long_memory_text() -> str:
    entry = repository.get_long_memory()
    return entry.content if entry else ""


def append_short_memory(task_id: int, narrative: str) -> None:
    repository.append_short_memory(task_id, narrative)


def trigger_distillation() -> str:
    """Distil undistilled short-term entries into long-term memory.

    Returns the new long-term memory text, or raises on failure.
    """
    undistilled = repository.get_undistilled_short_memory()
    if not undistilled:
        current = get_long_memory_text()
        return current

    settings = settings_manager.load_settings()
    model = (settings.get("distillation_model") or "claude-sonnet-4-6").strip()

    current_long = get_long_memory_text()
    narratives_text = "\n\n---\n\n".join(
        f"Task {e.task_id} (score: {e.user_score or 'N/A'}):\n{e.raw_log}"
        for e in undistilled
    )

    prompt = f"""You are an autonomous developer agent reviewing your recent experiences.

Recent task experiences:
{narratives_text}

Your current long-term memory (your accumulated principles):
{current_long or '(empty — you are just starting)'}

Update your long-term memory to incorporate lessons learned from these experiences.
- Write in first person
- Be concise and principled, not a list of events
- Preserve existing principles unless clearly contradicted
- Add new principles you have genuinely learned
- Weight experiences marked with high user scores (4-5) more heavily
- Return ONLY the updated long-term memory text, nothing else"""

    cli = shutil.which("claude") or "claude"
    result = subprocess.run(
        [cli, "--print", "--model", model, prompt],
        capture_output=True, text=True, timeout=180,
        stdin=subprocess.DEVNULL, env=dict(os.environ),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Distillation failed (exit {result.returncode}): "
            f"{(result.stderr or result.stdout or '').strip()[:400]}"
        )

    new_text = (result.stdout or "").strip()
    if not new_text:
        raise RuntimeError("Distillation returned empty text")

    repository.upsert_long_memory(new_text)
    repository.mark_distilled([e.id for e in undistilled])
    return new_text


def should_auto_distill() -> bool:
    settings = settings_manager.load_settings()
    threshold = int(settings.get("distillation_threshold") or 10)
    undistilled = repository.get_undistilled_short_memory()
    return len(undistilled) >= threshold
