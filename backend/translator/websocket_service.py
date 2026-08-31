"""Translator — WebSocket service.

Pushes streaming translation progress to connected clients over the shared
Socket.IO instance (created by duplicate_finder, passed in via app.py). Mirrors
clipboard_share/websocket_service.py.

Events are emitted on the '/translator' namespace as 'translator_progress' with
payload {job_id, scene, phase, delta?, text?}. Clients correlate events to
their request by job_id. All emits are guarded so translation still works when
Socket.IO is unavailable (e.g. tests) — streaming is purely a progress overlay;
the authoritative result is the HTTP response.
"""

# Set by app.py from the shared socketio; None until then (and in tests).
socketio = None

NAMESPACE = "/translator"


def init_socketio(app_socketio):
    """Adopt the app's shared socketio instance."""
    global socketio
    socketio = app_socketio
    return socketio


def register_socketio_events():
    """Register connect/disconnect handlers for the /translator namespace."""
    if not socketio:
        print("[Translator] Cannot register events: SocketIO not initialized")
        return

    @socketio.on("connect", namespace=NAMESPACE)
    def handle_connect():
        print("[Translator] Client connected to /translator namespace")

    @socketio.on("disconnect", namespace=NAMESPACE)
    def handle_disconnect():
        print("[Translator] Client disconnected from /translator namespace")


def emit_progress(job_id, scene, phase, delta=None, text=None):
    """Emit one streaming-progress event. No-op when socketio/job_id is absent.

    phase: 'translating' (with delta) | 'back_translating' | 'learning_points' | 'done'.
    """
    if not socketio or not job_id:
        return
    payload = {"job_id": job_id, "scene": scene, "phase": phase}
    if delta is not None:
        payload["delta"] = delta
    if text is not None:
        payload["text"] = text
    try:
        socketio.emit("translator_progress", payload, namespace=NAMESPACE)
    except Exception as e:  # never let a progress emit break a translation
        print(f"[Translator] Failed to emit progress: {e}")
