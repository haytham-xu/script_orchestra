"""Claude Bridge — per-session agent runner.

Each AgentSession owns a daemon thread running a private asyncio event loop and
a long-lived ClaudeSDKClient. Because Flask-SocketIO runs in threading mode here
(no eventlet/gevent — see app.py), socketio.emit() is safe to call directly from
these background threads, so the async<->sync bridge is just:

  socketio thread  --run_coroutine_threadsafe-->  agent loop  --emit-->  clients

Streaming: the loop consumes client.receive_messages() forever and pushes each
serialized message to the broadcaster.

Approvals: a PreToolUse hook (matcher "*") gates every tool call. Read-only
tools are auto-allowed in the hook; write/exec tools await a Future created on
the agent loop, which the socketio thread resolves via call_soon_threadsafe when
the phone responds. (The older can_use_tool callback does not reliably fire in
headless SDK sessions — CLI allow-rules shadow it — so we use the hook, which is
the SDK-blessed way to gate every call. Verified against SDK 0.2.148.)
"""
import asyncio
import os
import threading
import uuid
from typing import Callable, Optional

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    HookMatcher,
    AssistantMessage,
    UserMessage,
    SystemMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolResultBlock,
)

from . import config


def _permission_summary(tool_name: str, tool_input: dict) -> str:
    """A compact one-liner describing what a tool call will do, for the approval UI."""
    ti = tool_input or {}
    if tool_name == "Bash":
        return (ti.get("command") or "").strip()[:200]
    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return f"→ {ti.get('file_path') or ti.get('notebook_path') or '?'}"
    if tool_name == "Read":
        return f"read {ti.get('file_path', '?')}"
    return tool_name


def _serialize_block(block) -> Optional[dict]:
    if isinstance(block, TextBlock):
        return {"type": "assistant_text", "text": block.text}
    if isinstance(block, ThinkingBlock):
        return {"type": "thinking", "thinking": block.thinking}
    if isinstance(block, ToolUseBlock):
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    if isinstance(block, ToolResultBlock):
        content = block.content
        # content may be str or a list of content blocks; stringify defensively.
        if not isinstance(content, str):
            content = str(content)
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": content,
            "is_error": bool(block.is_error),
        }
    return None


class AgentSession:
    def __init__(self, session_id: str, cwd: str, model: str,
                 broadcaster: Callable[[dict], None]):
        self.id = session_id
        self.cwd = cwd
        self.model = model
        self._broadcaster = broadcaster
        self._client: Optional[ClaudeSDKClient] = None
        self._pending_perms: dict = {}
        self._ready = threading.Event()
        self._closed = False

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name=f"claude-bridge-{session_id}", daemon=True
        )
        self._thread.start()
        # Kick off connect on the session's own loop.
        asyncio.run_coroutine_threadsafe(self._start(), self._loop)

    # ---- loop lifecycle -------------------------------------------------
    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _start(self):
        try:
            # Only overlay auth-related env when it isn't already inherited.
            # Auth (ANTHROPIC_AUTH_TOKEN / API key) and the base URL come from the
            # shell/launcher that started the backend; the SDK merges os.environ
            # under our overlay, so we must not clobber those. We forward the
            # bridge's configured fallbacks only for keys the process is missing —
            # mirrors the pm2/non-interactive case in knowledge_vault/ai_client.py.
            env_overlay = {}
            if not os.environ.get("ANTHROPIC_BASE_URL"):
                env_overlay["ANTHROPIC_BASE_URL"] = config.base_url()
            if not os.environ.get("ANTHROPIC_AUTH_TOKEN") and config.AUTH_TOKEN:
                env_overlay["ANTHROPIC_AUTH_TOKEN"] = config.AUTH_TOKEN

            options = ClaudeAgentOptions(
                cwd=self.cwd,
                model=self.model or None,   # empty => let the CLI use its default model
                # A PreToolUse hook (below) is the sole approval authority. We do
                # NOT list write/exec tools in allowed_tools (that would
                # auto-approve them before any gating). Read-only tools are
                # auto-allowed inside the hook instead.
                allowed_tools=[],
                # Don't inherit the user's local settings.json permission allowlist
                # (e.g. Bash(echo:*)); those allow-rules would shadow our hook.
                setting_sources=[],
                hooks={"PreToolUse": [HookMatcher(matcher="*", hooks=[self._pre_tool_hook])]},
                include_partial_messages=True,
                env=env_overlay,
            )
            self._client = ClaudeSDKClient(options=options)
            await self._client.connect()
            self._ready.set()
            self._emit({"type": "session_status", "status": "ready"})
            async for msg in self._client.receive_messages():
                self._on_message(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — surface any startup/stream error
            self._emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            self._ready.set()  # unblock waiters even on failure

    # ---- message streaming ---------------------------------------------
    def _on_message(self, msg):
        if isinstance(msg, (AssistantMessage, UserMessage)):
            for block in msg.content:
                payload = _serialize_block(block)
                if payload:
                    self._emit(payload)
        elif isinstance(msg, SystemMessage):
            self._emit({"type": "session_status", "status": "system", "subtype": msg.subtype})
        elif isinstance(msg, ResultMessage):
            self._emit({
                "type": "result",
                "is_error": bool(msg.is_error),
                "num_turns": msg.num_turns,
                "total_cost_usd": msg.total_cost_usd,
                "duration_ms": msg.duration_ms,
                "result": msg.result,
            })

    def _emit(self, payload: dict):
        payload = {"session_id": self.id, **payload}
        try:
            self._broadcaster(payload)
        except Exception as exc:  # never let a broadcast error kill the loop
            print(f"[claude_bridge] broadcast failed: {exc}")

    # ---- inbound actions (called from socketio thread) ------------------
    def submit(self, text: str):
        if not self._client:
            return
        asyncio.run_coroutine_threadsafe(self._client.query(text), self._loop)

    def interrupt(self):
        if not self._client:
            return
        asyncio.run_coroutine_threadsafe(self._client.interrupt(), self._loop)

    def set_model(self, model: str):
        if not self._client:
            return
        self.model = model
        asyncio.run_coroutine_threadsafe(self._client.set_model(model), self._loop)

    def resolve_permission(self, request_id: str, decision: str):
        fut = self._pending_perms.get(request_id)
        if fut and not fut.done():
            self._loop.call_soon_threadsafe(fut.set_result, decision)

    def close(self):
        if self._closed:
            return
        self._closed = True

        async def _shutdown():
            try:
                if self._client:
                    await self._client.disconnect()
            finally:
                self._loop.stop()

        try:
            asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)
        except RuntimeError:
            # loop already stopped
            self._loop.call_soon_threadsafe(self._loop.stop)

    # ---- tool approval (PreToolUse hook) -------------------------------
    async def _pre_tool_hook(self, input_data, tool_use_id, context):
        """Gate every tool call. Read-only tools auto-allow; the rest wait for a
        phone decision. Returns the SDK's PreToolUse hookSpecificOutput shape."""
        tool_name = input_data.get("tool_name", "?")
        tool_input = input_data.get("tool_input", {}) or {}

        # Auto-allow read-only tools without bothering the phone.
        if tool_name in config.DEFAULT_ALLOWED_TOOLS:
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "auto-allowed (read-only)",
            }}

        request_id = uuid.uuid4().hex
        fut = self._loop.create_future()
        self._pending_perms[request_id] = fut
        self._emit({
            "type": "permission_request",
            "request_id": request_id,
            "tool": tool_name,
            "risk": config.tool_risk(tool_name),
            "summary": _permission_summary(tool_name, tool_input),
            "input": tool_input,
        })
        try:
            decision = await fut
        finally:
            self._pending_perms.pop(request_id, None)

        if decision == "allow":
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "approved on phone",
            }}
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "denied on phone",
        }}

    def to_dict(self) -> dict:
        return {"session_id": self.id, "cwd": self.cwd, "model": self.model,
                "ready": self._ready.is_set()}
