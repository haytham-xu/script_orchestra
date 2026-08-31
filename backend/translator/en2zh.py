"""Translator — en→zh scene (faithful, objective Chinese translation).

Self-contained per DESIGN.md. No back-translation, no learning points — those
belong only to the zh2en scene. Just translate English (or a pasted Slack chat
log) into faithful, objective Chinese, then persist history.

Returns {chinese, history_id}.
"""
from . import copilot_client, repository, settings_manager, websocket_service as ws
from .entity import TranslationHistory

SCENE = "en2zh"


def translate(text: str, model: str = None, job_id: str = None, extra_prompt: str = None) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")

    cfg = settings_manager.get_scene_config(SCENE)
    system = cfg.get("system_prompt", "")
    # One-off instruction for THIS translation only — appended to the saved
    # system prompt, not replacing it.
    extra_prompt = (extra_prompt or "").strip()
    if extra_prompt:
        system = f"{system}\n\n{extra_prompt}".strip()
    # Per-request model override wins over the scene's saved default.
    model = model or cfg.get("model", "auto")

    chinese, usage = copilot_client.ask_with_usage(
        text, system=system, model=model,
        on_delta=lambda c: ws.emit_progress(job_id, SCENE, "translating", delta=c),
    )

    hist = repository.insert_history(TranslationHistory.new_instance(
        SCENE, source_text=text, result_text=chinese,
        model=usage.get("model") or model, usage=usage,
    ))

    ws.emit_progress(job_id, SCENE, "done")
    return {"chinese": chinese, "usage": usage, "history_id": hist.id}
