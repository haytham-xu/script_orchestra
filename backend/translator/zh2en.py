"""Translator — zh→en scene (Slack-style translation + back-translation +
English learning points).

This scene is intentionally self-contained (DESIGN.md: the two scenes do not
share business abstractions). Back-translation and learning-point extraction
belong ONLY to this scene and are hardcoded here, not exposed as generic toggles.

Flow:
  1. Translate the user's Chinese / mixed source into Slack-style English,
     using the user-authored system prompt for this scene.
  2. Back-translate that English into Chinese so the user can sanity-check it.
  3. Ask the model to extract English learning points from the user's ORIGINAL
     text — spelling errors, awkward / non-idiomatic phrasing — plus a
     comparison of "what you wrote" vs. the idiomatic version. Each point:
     {original, suggestion, explanation}. Shaped for a future memory-card.
  4. Persist history + learning points.

Returns {english, back_translation, learning_points[], history_id}.
"""
import json
import concurrent.futures
from typing import List

from . import repository, settings_manager, websocket_service as ws
from .entity import TranslationHistory, LearningPoint

SCENE = "zh2en"

# Fixed instruction appended to the user's prompt to force machine-parseable
# learning points. The user's system_prompt governs *translation style*; this
# governs the learning-point *format* only.
_LP_INSTRUCTION = (
    "You are an English writing coach. The user wrote the text below (Chinese, "
    "English, or mixed) and it was translated to idiomatic English. Extract a "
    "list of concrete English learning points from the USER'S ORIGINAL text and "
    "from the gap between what they wrote and the idiomatic version: spelling "
    "mistakes, awkward or non-native phrasing, and better word choices. "
    "Respond with ONLY a JSON object of the form "
    '{"points": [{"original": "...", "suggestion": "...", "explanation": "..."}]} '
    "where `original` is what the user wrote and `suggestion` is a more idiomatic "
    "way to say it (both in English). Write `explanation` (the short why / what-rule) "
    "in Simplified Chinese, except keep any English words or grammatical terms you "
    "need to quote in English. If there is "
    "nothing worth noting, return {\"points\": []}. No prose outside the JSON."
)


def _extract_json_object(text: str):
    """Find and parse the first balanced top-level {...} JSON object in text.
    (Same tolerance as knowledge_vault.ai_client — models wrap JSON in fences
    or prose.)"""
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


def _parse_learning_points(raw: str) -> List[dict]:
    obj = _extract_json_object(raw) or {}
    pts = obj.get("points") if isinstance(obj, dict) else None
    out = []
    if isinstance(pts, list):
        for p in pts:
            if not isinstance(p, dict):
                continue
            original = (p.get("original") or "").strip()
            if not original:
                continue
            out.append({
                "original": original,
                "suggestion": (p.get("suggestion") or "").strip(),
                "explanation": (p.get("explanation") or "").strip(),
            })
    return out


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
    # A one-off instruction for THIS translation only — appended to (not
    # replacing) the saved system prompt. Affects the main translation's style;
    # back-translation and learning-point extraction keep their fixed prompts.
    extra_prompt = (extra_prompt or "").strip()
    if extra_prompt:
        system = f"{system}\n\n{extra_prompt}".strip()
    # Per-request model override wins over the scene's saved default.
    # For Ollama, fall back to the global ollama_model setting when no model specified.
    if provider == "ollama":
        default_model = settings_manager.load_settings().get("ollama_model", "qwen2.5:14b")
    else:
        default_model = "auto"
    model = model or cfg.get("model", default_model) or default_model

    usage = ai_client._empty_usage()

    # 1) Slack-style English translation — streamed live via on_delta.
    english, u1 = ai_client.ask_with_usage(
        text, system=system, model=model,
        on_delta=lambda c: ws.emit_progress(job_id, SCENE, "translating", delta=c),
    )
    usage = ai_client.add_usage(usage, u1)

    # 2+3) Back-translation and learning-point extraction are independent of
    # each other (back needs english; learning points need original text only).
    # Run them in parallel to cut wall-clock time roughly in half.
    ws.emit_progress(job_id, SCENE, "back_translating")

    back_prompt = (
        "Translate the following English text back into natural Chinese. "
        "Respond with only the Chinese translation, no extra commentary.\n\n"
        f"{english}"
    )
    pref = (cfg.get("learning_prompt") or "").strip()
    lp_instruction = f"{_LP_INSTRUCTION}\n\nUser preference for these learning points: {pref}" if pref else _LP_INSTRUCTION
    lp_prompt = f"{lp_instruction}\n\nUSER'S ORIGINAL TEXT:\n{text}"

    def _do_back():
        try:
            return ai_client.ask_with_usage(back_prompt, model=model)
        except Exception:
            return "", ai_client._empty_usage()

    def _do_lp():
        try:
            return ai_client.ask_with_usage(lp_prompt, model=model)
        except Exception:
            return "", ai_client._empty_usage()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f_back = pool.submit(_do_back)
        f_lp = pool.submit(_do_lp)
        back_translation, u2 = f_back.result()
        lp_raw, u3 = f_lp.result()

    usage = ai_client.add_usage(ai_client.add_usage(usage, u2), u3)
    learning_points: List[dict] = _parse_learning_points(lp_raw)

    # 4) Persist history + learning points.
    hist = repository.insert_history(TranslationHistory.new_instance(
        SCENE, source_text=text, result_text=english,
        back_translation=back_translation, model=usage.get("model") or model,
        usage=usage,
    ))
    saved_points = repository.insert_learning_points(
        hist.id,
        [LearningPoint.new_instance(hist.id, p["original"], p["suggestion"], p["explanation"])
         for p in learning_points],
    )

    ws.emit_progress(job_id, SCENE, "done")
    return {
        "english": english,
        "back_translation": back_translation,
        "learning_points": [p.to_dict() for p in saved_points],
        "usage": usage,
        "history_id": hist.id,
    }
