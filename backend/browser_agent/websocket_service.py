"""Browser Agent — WebSocket bridge (shared SocketIO, pass-in mode).

Mirrors caffeinate/websocket_service.py: receives the shared SocketIO
instance, exposes a broadcaster the service wires in, and emits progress
on the /browser_agent namespace.
"""
socketio = None
NAMESPACE = "/browser_agent"


def init_socketio(app_socketio):
    """Receive the shared SocketIO instance created by duplicate_finder."""
    global socketio
    socketio = app_socketio
    return socketio


def broadcast_progress(payload: dict):
    """Push a download-progress event to connected frontends."""
    if socketio:
        socketio.emit("browser_agent_progress", payload, namespace=NAMESPACE)


def register_socketio_events():
    if not socketio:
        return

    @socketio.on("connect", namespace=NAMESPACE)
    def handle_connect():
        print("[browser_agent] client connected")

    @socketio.on("disconnect", namespace=NAMESPACE)
    def handle_disconnect():
        pass
