"""Translator — GitHub Copilot client (shared by both scenes).

Wraps the GitHub Copilot Python SDK (`github-copilot-sdk`, import `copilot`).
Authentication uses the locally logged-in Copilot credentials: we read the
OAuth token for the Copilot-bound account from ~/.config/github-copilot/apps.json
and hand it to the SDK as `github_token`. The account is NOT hardcoded — set it
via the TRANSLATOR_COPILOT_ACCOUNT env var (empty = use whichever account
apps.json contains). No token is hardcoded or committed. This mirrors
knowledge_vault depending on the `claude` CLI: both drive a locally-
authenticated CLI runtime.

Two things make this work on a locked-down/slow network (see DESIGN.md §1 and
the project memory `translator-copilot-cli-download`):
  - COPILOT_CLI_PATH points the SDK at a CLI binary installed via npm
    (`@github/copilot`, from the npm registry), so the SDK does NOT try to
    download a ~99MB CLI from github.com on first use.
  - github_token is taken from apps.json (a `ghu_` OAuth token for the
    configured account), so the fresh CLI runtime is authenticated without an
    interactive `copilot login` browser/device flow.

The SDK is async and Flask is sync, so every public function here is synchronous
and drives the async SDK on a private event loop in a dedicated thread (same
approach as knowledge_vault.ai_client, adapted for asyncio). Each call currently
spins up a fresh client+session (simple and robust); if startup overhead proves
costly we can pool a long-lived client later (see DESIGN.md §3).

On any SDK/auth failure we raise a readable RuntimeError; the controller turns
that into a 502 with a clear "Copilot auth failed" hint.
"""
import os
import json
import asyncio
import threading
from typing import List, Optional

# The Copilot-bound account. Auth is only valid as this identity (DESIGN.md §1).
# Configure via env; empty means "use whichever account apps.json holds".
COPILOT_ACCOUNT = os.environ.get("TRANSLATOR_COPILOT_ACCOUNT", "")
_APPS_JSON = os.path.expanduser("~/.config/github-copilot/apps.json")

# Model default; a request may override per-scene (settings model).
DEFAULT_MODEL = os.environ.get("TRANSLATOR_MODEL", "auto")

# How long to wait for a single model reply (seconds). The SDK's own
# send_and_wait default is 60s; translations can be a touch longer.
_REPLY_TIMEOUT = int(os.environ.get("TRANSLATOR_REPLY_TIMEOUT", "120"))
# Guard the whole client lifecycle (start + session + reply + stop) so a hung
# runtime can never wedge a Flask worker forever.
_CALL_TIMEOUT = int(os.environ.get("TRANSLATOR_CALL_TIMEOUT", "180"))


class CopilotAuthError(RuntimeError):
    """Raised when the SDK cannot authenticate (wrong/absent Copilot login)."""


class CopilotUnavailableError(RuntimeError):
    """Raised when the SDK/runtime is not usable (not installed, download
    incomplete, runtime failed to start)."""


def _load_github_token() -> Optional[str]:
    """Read the Copilot OAuth token for COPILOT_ACCOUNT from apps.json.

    Precedence of token type: ghu_ (Copilot CLI app) > gho_ (gh app) >
    github_pat_ (fine-grained PAT). Classic ghp_ is NOT supported by the SDK,
    so it's skipped. An explicit COPILOT_GITHUB_TOKEN / GH_TOKEN env var wins
    over apps.json (matches the CLI's own precedence). Returns None if nothing
    usable is found — the SDK then falls back to any logged-in CLI credential.
    """
    for env_key in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(env_key)
        if v and not v.startswith("ghp_"):
            return v
    try:
        with open(_APPS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    candidates = [
        v["oauth_token"] for v in data.values()
        if isinstance(v, dict)
        and (not COPILOT_ACCOUNT or v.get("user") == COPILOT_ACCOUNT)
        and isinstance(v.get("oauth_token"), str)
    ]
    for prefix in ("ghu_", "gho_", "github_pat_"):
        for tok in candidates:
            if tok.startswith(prefix):
                return tok
    return None


def _resolve_cli_path() -> Optional[str]:
    """Point the SDK at an already-installed CLI binary so it never tries to
    download the ~99MB CLI from github.com. Honors COPILOT_CLI_PATH; otherwise
    falls back to the npm-installed location under ~/.copilot-cli-npm/copilot.
    Returns None if neither exists (SDK then uses its own cache/download path).
    """
    explicit = os.environ.get("COPILOT_CLI_PATH")
    if explicit and os.path.exists(explicit):
        return explicit
    npm_default = os.path.expanduser("~/.copilot-cli-npm/copilot")
    if os.path.exists(npm_default):
        return npm_default
    return None


def _empty_usage() -> dict:
    return {
        "model": "",
        "credits": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }


def _usage_from_events(events) -> dict:
    """Aggregate ASSISTANT_USAGE session events into a flat usage dict.

    Each ASSISTANT_USAGE event's to_dict() carries `model`, `cacheReadTokens`,
    `cacheWriteTokens`, and `copilotUsage.{totalNanoAiu, tokenDetails[]}` where
    tokenDetails entries are {tokenType, tokenCount}. credits = sum of
    totalNanoAiu / 1e9. Defensive: any missing field contributes 0.
    """
    usage = _empty_usage()
    for e in events or []:
        etype = str(getattr(e, "type", "") or "")
        if not etype.endswith("ASSISTANT_USAGE"):
            continue
        try:
            d = e.to_dict().get("data", {}) or {}
        except Exception:
            continue
        if d.get("model") and not usage["model"]:
            usage["model"] = d.get("model")
        usage["cache_read_tokens"] += int(d.get("cacheReadTokens") or 0)
        usage["cache_write_tokens"] += int(d.get("cacheWriteTokens") or 0)
        cu = d.get("copilotUsage") or {}
        try:
            usage["credits"] += float(cu.get("totalNanoAiu") or 0) / 1e9
        except (TypeError, ValueError):
            pass
        for td in (cu.get("tokenDetails") or []):
            ttype = td.get("tokenType")
            cnt = int(td.get("tokenCount") or 0)
            if ttype == "input":
                usage["input_tokens"] += cnt
            elif ttype == "output":
                usage["output_tokens"] += cnt
    usage["credits"] = round(usage["credits"], 4)
    return usage


def add_usage(a: dict, b: dict) -> dict:
    """Sum two usage dicts (model taken from the first non-empty)."""
    out = _empty_usage()
    out["model"] = a.get("model") or b.get("model") or ""
    for k in ("credits", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
        out[k] = (a.get(k) or 0) + (b.get(k) or 0)
    out["credits"] = round(out["credits"], 4)
    return out


def _extract_text(resp) -> str:
    """Pull assistant text out of a SessionEvent. Its `.data` is an
    AssistantMessageData with a `.content: str`; be defensive about shape since
    the SDK is pre-1.0-ish and may evolve."""
    if resp is None:
        return ""
    data = getattr(resp, "data", None)
    for obj in (data, resp):
        if obj is None:
            continue
        content = getattr(obj, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        text = getattr(obj, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _classify(exc: Exception) -> RuntimeError:
    """Map an SDK exception onto a readable, categorized error."""
    msg = f"{type(exc).__name__}: {exc}"
    low = msg.lower()
    if any(k in low for k in ("auth", "unauthorized", "401", "403", "login", "credential", "token")):
        return CopilotAuthError(
            "Copilot authentication failed. Ensure you are logged in as the "
            f"Copilot-bound account (see TRANSLATOR_COPILOT_ACCOUNT). Detail: {msg}"
        )
    if any(k in low for k in ("download", "runtime", "not found", "no such file", "connect", "spawn")):
        return CopilotUnavailableError(
            "Copilot runtime unavailable (CLI binary missing/incomplete or "
            f"runtime failed to start). Detail: {msg}"
        )
    return RuntimeError(f"Copilot call failed: {msg}")


async def _ask_async(prompt: str, system: str, model: str, on_delta=None) -> tuple:
    # Imported lazily so importing this module never blocks on the SDK (whose
    # CopilotClient() constructor can trigger a large CLI download on first use).
    from copilot import CopilotClient
    from copilot.session import PermissionHandler

    # Point the SDK at the pre-installed CLI so its constructor never downloads.
    cli = _resolve_cli_path()
    if cli:
        os.environ.setdefault("COPILOT_CLI_PATH", cli)

    events = []  # collect ASSISTANT_USAGE (and everything else) for usage accounting

    def _on_event(e):
        events.append(e)
        # Fire incremental text chunks for live streaming. deltaContent is the
        # per-chunk text on ASSISTANT_MESSAGE_DELTA events (verified via probe).
        if on_delta is not None and str(getattr(e, "type", "") or "").endswith("ASSISTANT_MESSAGE_DELTA"):
            try:
                chunk = (e.to_dict().get("data") or {}).get("deltaContent")
                if chunk:
                    on_delta(chunk)
            except Exception:
                pass  # never let a progress callback break the translation

    client = CopilotClient(log_level="warning", github_token=_load_github_token())
    await client.start()
    try:
        session = await client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model=model or DEFAULT_MODEL,
            streaming=True,          # emit ASSISTANT_MESSAGE_DELTA chunks as they arrive
            on_event=_on_event,
            # A translator never needs tools; keep the turn a pure completion.
            system_message={"mode": "replace", "content": system} if system else None,
        )
        resp = await session.send_and_wait(prompt, timeout=float(_REPLY_TIMEOUT))
        return _extract_text(resp), _usage_from_events(events)
    finally:
        try:
            await client.stop()
        except Exception:
            pass


async def _list_models_async() -> List[dict]:
    from copilot import CopilotClient
    cli = _resolve_cli_path()
    if cli:
        os.environ.setdefault("COPILOT_CLI_PATH", cli)
    client = CopilotClient(log_level="warning", github_token=_load_github_token())
    await client.start()
    try:
        models = await client.list_models()
        out = []
        for m in (models or []):
            mid = getattr(m, "id", None) or getattr(m, "name", None)
            if mid:
                out.append({"id": mid, "name": getattr(m, "name", mid)})
        return out
    finally:
        try:
            await client.stop()
        except Exception:
            pass


def _run(coro, timeout: int):
    """Run an async coroutine to completion on a private event loop in a
    dedicated thread, then tear the loop down. Safe from a sync Flask worker."""
    result = {}

    def worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result["value"] = loop.run_until_complete(
                asyncio.wait_for(coro, timeout=timeout)
            )
        except Exception as e:  # noqa: BLE001 — captured and re-raised on caller thread
            result["error"] = e
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    # Give the worker a little slack beyond the inner asyncio timeout so the
    # inner TimeoutError surfaces as our classified error, not a bare join gap.
    t.join(timeout + 15)
    if t.is_alive():
        raise CopilotUnavailableError(
            f"Copilot call did not return within {timeout}s (runtime may be "
            "downloading the CLI binary or is unresponsive)."
        )
    if "error" in result:
        err = result["error"]
        if isinstance(err, asyncio.TimeoutError):
            raise CopilotUnavailableError(f"Copilot call timed out after {timeout}s")
        raise _classify(err)
    return result.get("value")


# ---- public sync API --------------------------------------------------

def ask_with_usage(prompt: str, *, system: str = "", model: str = DEFAULT_MODEL,
                   on_delta=None) -> tuple:
    """Send one prompt to Copilot; return (text, usage).

    usage is a flat dict: {model, credits, input_tokens, output_tokens,
    cache_read_tokens, cache_write_tokens}. If `on_delta` is given, it's called
    with each incremental text chunk as the reply streams in (called on the
    SDK's event thread — keep it lightweight, e.g. a socket emit). Raises
    CopilotAuthError / CopilotUnavailableError / RuntimeError on failure.
    """
    text, usage = _run(_ask_async(prompt, system, model, on_delta), _CALL_TIMEOUT)
    if not text:
        raise RuntimeError("Copilot returned an empty response.")
    return text, usage


def ask(prompt: str, *, system: str = "", model: str = DEFAULT_MODEL) -> str:
    """Send one prompt to Copilot and return the assistant's text (usage discarded)."""
    text, _usage = ask_with_usage(prompt, system=system, model=model)
    return text


def list_models() -> List[dict]:
    """Return available models as [{id, name}]. Empty list on soft failure."""
    try:
        return _run(_list_models_async(), 60) or []
    except Exception:
        return []
