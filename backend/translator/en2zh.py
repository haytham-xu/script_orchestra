"""Translator — en→zh scene (faithful, objective Chinese translation).

Self-contained per DESIGN.md. No back-translation, no learning points — those
belong only to the zh2en scene. Just translate English (or a pasted Slack chat
log) into faithful, objective Chinese, then persist history.

Returns {chinese, history_id}.
"""
from . import repository, settings_manager, websocket_service as ws
from .entity import TranslationHistory

SCENE = "en2zh"


def translate(text: str, model: str = None, job_id: str = None, extra_prompt: str = None) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")

    cfg = settings_manager.get_scene_config(SCENE)
    system = cfg.get("system_prompt", "")

    provider = cfg.get("provider", "copilot")
    if provider == "ollama":
        from . import ollama_client as ai_client  # noqa: PLC0415
    else:
        from . import copilot_client as ai_client  # noqa: PLC0415

    if provider == "ollama":
        default_model = settings_manager.load_settings().get("ollama_model", "qwen2.5:14b")
    else:
        default_model = "auto"
    model = model or cfg.get("model", default_model) or default_model

    # One-off instruction for THIS translation only — appended to the saved
    # system prompt, not replacing it.
    extra_prompt = (extra_prompt or "").strip()
    if extra_prompt:
        system = f"{system}\n\n{extra_prompt}".strip()

    chinese, usage = ai_client.ask_with_usage(
        text, system=system, model=model,
        on_delta=lambda c: ws.emit_progress(job_id, SCENE, "translating", delta=c),
    )

    hist = repository.insert_history(TranslationHistory.new_instance(
        SCENE, source_text=text, result_text=chinese,
        model=usage.get("model") or model, usage=usage,
    ))

    ws.emit_progress(job_id, SCENE, "done")
    return {"chinese": chinese, "usage": usage, "history_id": hist.id}
