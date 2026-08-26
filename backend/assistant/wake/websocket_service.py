"""
WebSocket bridge for wake-word events.

The wake service pushes JSON events (wake / transcribing / transcript /
cancelled / error / status) to whoever subscribes to /wake. The
frontend listens and drops the resulting text into the composer.
"""
socketio = None


def init_socketio(app_socketio):
    global socketio
    socketio = app_socketio
    return socketio


def broadcast_wake_event(event: dict):
    if not socketio:
        print("[wake-ws] not initialized, drop event", event.get("type"))
        return
    try:
        socketio.emit("wake_event", event, namespace="/wake")
    except Exception as exc:  # noqa: BLE001
        print(f"[wake-ws] emit failed: {exc}")


def register_socketio_events():
    if not socketio:
        return

    @socketio.on("connect", namespace="/wake")
    def _connect():
        print("[wake-ws] client connected")

    @socketio.on("disconnect", namespace="/wake")
    def _disconnect():
        print("[wake-ws] client disconnected")
