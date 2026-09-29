"""Translator — Ollama local model client.

Drop-in replacement for copilot_client: exposes the same public API so zh2en
and en2zh can swap providers without changing any other logic.

Public API (identical signatures to copilot_client):
  ask_with_usage(prompt, *, system, model, on_delta) -> (str, dict)
  ask(prompt, *, system, model) -> str
  list_models() -> List[dict]

Calls Ollama's /api/generate endpoint with stream=True (NDJSON). Each line's
"response" field is forwarded to on_delta for live streaming; the final line
carries prompt_eval_count / eval_count for token accounting.

Configure via environment:
  OLLAMA_BASE_URL  — defaults to http://localhost:11434
"""
import json
import os
from typing import List, Optional

import requests

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_TIMEOUT_CONNECT = 5   # seconds to establish connection
_TIMEOUT_READ = 120    # seconds per streaming read


class OllamaUnavailableError(RuntimeError):
    """Raised when the Ollama server is unreachable or returns an error."""


def _empty_usage() -> dict:
    return {
        "model": "",
        "credits": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }


def add_usage(a: dict, b: dict) -> dict:
    """Sum two usage dicts (mirrors copilot_client.add_usage)."""
    out = _empty_usage()
    out["model"] = a.get("model") or b.get("model") or ""
    for k in ("credits", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
        out[k] = (a.get(k) or 0) + (b.get(k) or 0)
    out["credits"] = round(out["credits"], 4)
    return out


def ask_with_usage(prompt: str, *, system: str = "", model: str = "qwen2.5:14b",
                   on_delta=None) -> tuple:
    """Send one prompt to Ollama; return (text, usage).

    usage matches the copilot_client shape: credits is always 0 for Ollama;
    input_tokens / output_tokens come from Ollama's prompt_eval_count /
    eval_count fields on the final streamed line.

    For models that support thinking (e.g. qwen3), thinking is disabled via
    Ollama's options.think=false. Translation does not benefit from reasoning
    chains and the overhead is significant (~3x slower, ~3x more tokens).
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"think": False},
    }
    if system:
        payload["system"] = system

    url = f"{OLLAMA_BASE_URL}/api/generate"
    try:
        resp = requests.post(
            url, json=payload,
            stream=True,
            timeout=(_TIMEOUT_CONNECT, _TIMEOUT_READ),
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise OllamaUnavailableError(
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
            "Make sure `ollama serve` is running. Detail: " + str(e)
        ) from e
    except requests.exceptions.HTTPError as e:
        raise OllamaUnavailableError(f"Ollama returned HTTP error: {e}") from e
    except requests.exceptions.Timeout as e:
        raise OllamaUnavailableError(f"Ollama request timed out: {e}") from e

    chunks: list[str] = []
    final_line: dict = {}
    try:
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            try:
                data = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            chunk = data.get("response") or ""
            if chunk:
                chunks.append(chunk)
                if on_delta is not None:
                    try:
                        on_delta(chunk)
                    except Exception:
                        pass
            if data.get("done"):
                final_line = data
                break
    except requests.exceptions.ChunkedEncodingError as e:
        raise OllamaUnavailableError(f"Ollama stream interrupted: {e}") from e

    text = "".join(chunks).strip()
    if not text:
        raise OllamaUnavailableError("Ollama returned an empty response.")

    usage = _empty_usage()
    usage["model"] = final_line.get("model") or model
    usage["input_tokens"] = int(final_line.get("prompt_eval_count") or 0)
    usage["output_tokens"] = int(final_line.get("eval_count") or 0)
    return text, usage


def ask(prompt: str, *, system: str = "", model: str = "qwen2.5:14b") -> str:
    """Send one prompt to Ollama and return the assistant's text (usage discarded)."""
    text, _ = ask_with_usage(prompt, system=system, model=model)
    return text


def list_models() -> List[dict]:
    """Return locally available Ollama models as [{id, name}]. Empty list on failure."""
    try:
        resp = requests.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=(_TIMEOUT_CONNECT, 10),
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {"id": m["name"], "name": m["name"]}
            for m in (data.get("models") or [])
            if m.get("name")
        ]
    except Exception:
        return []
