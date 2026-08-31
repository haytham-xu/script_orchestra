"""Claude Bridge — WebSocket bridge (shared SocketIO, pass-in mode).

Mirrors browser_agent/websocket_service.py: receives the shared SocketIO
instance, exposes broadcast_event() (wired to the session manager by app.py),
and relays client actions on the /claude-bridge namespace.

Inbound events:
  cb_user_message        {session_id, text}
  cb_permission_response {session_id, request_id, decision}
  cb_interrupt           {session_id}
  cb_set_model           {session_id, model}
Outbound (single event, payload.type discriminates):
  cb_event               {session_id, type, ...}
"""
from .session_manager import get_manager
from .auth import check_ws_auth

socketio = None
NAMESPACE = "/claude-bridge"


def init_socketio(app_socketio):
    """Receive the shared SocketIO instance created by duplicate_finder."""
    global socketio
    socketio = app_socketio
    return socketio


def broadcast_event(payload: dict):
    """Push one serialized agent event to connected clients (thread-safe in
    threading mode)."""
    if socketio:
        socketio.emit("cb_event", payload, namespace=NAMESPACE)


def register_socketio_events():
    if not socketio:
        print("[claude_bridge] Cannot register events: SocketIO not initialized")
        return

    manager = get_manager()

    @socketio.on("connect", namespace=NAMESPACE)
    def handle_connect(auth=None):
        # Reject the handshake if a token is required and missing/wrong.
        if not check_ws_auth(auth):
            print("[claude_bridge] client rejected (bad/missing token)")
            return False
        print("[claude_bridge] client connected")

    @socketio.on("disconnect", namespace=NAMESPACE)
    def handle_disconnect():
        pass

    @socketio.on("cb_user_message", namespace=NAMESPACE)
    def handle_user_message(data):
        data = data or {}
        manager.submit(data.get("session_id", ""), data.get("text", ""))

    @socketio.on("cb_permission_response", namespace=NAMESPACE)
    def handle_permission_response(data):
        data = data or {}
        manager.resolve_permission(
            data.get("session_id", ""),
            data.get("request_id", ""),
            data.get("decision", "deny"),
        )

    @socketio.on("cb_interrupt", namespace=NAMESPACE)
    def handle_interrupt(data):
        manager.interrupt((data or {}).get("session_id", ""))

    @socketio.on("cb_set_model", namespace=NAMESPACE)
    def handle_set_model(data):
        data = data or {}
        manager.set_model(data.get("session_id", ""), data.get("model", ""))

    # ---- PTY events ----
    @socketio.on("cb_pty_input", namespace=NAMESPACE)
    def handle_pty_input(data):
        data = data or {}
        manager.pty_write(data.get("pty_id", ""), data.get("data", ""))

    @socketio.on("cb_pty_resize", namespace=NAMESPACE)
    def handle_pty_resize(data):
        data = data or {}
        try:
            cols = int(data.get("cols", 80))
            rows = int(data.get("rows", 24))
        except (TypeError, ValueError):
            return
        manager.pty_resize(data.get("pty_id", ""), cols, rows)
