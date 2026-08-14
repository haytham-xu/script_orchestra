"""
WebSocket Service for Caffeinate

Streams heartbeat log lines to connected clients.
"""
from flask_socketio import emit

socketio = None


def init_socketio(app_socketio):
    global socketio
    socketio = app_socketio
    return socketio


def broadcast_log_entry(log_entry: dict):
    if socketio:
        try:
            socketio.emit(
                'caffeinate_log',
                log_entry,
                namespace='/caffeinate',
            )
        except Exception as exc:
            print(f"[Caffeinate] Failed to broadcast: {exc}")
    else:
        print("[Caffeinate] Warning: SocketIO not initialized")


def register_socketio_events():
    if not socketio:
        print("[Caffeinate] Cannot register events: SocketIO not initialized")
        return

    @socketio.on('connect', namespace='/caffeinate')
    def handle_connect():
        print('[Caffeinate] Client connected to /caffeinate namespace')

    @socketio.on('disconnect', namespace='/caffeinate')
    def handle_disconnect():
        print('[Caffeinate] Client disconnected from /caffeinate namespace')

    @socketio.on('ping', namespace='/caffeinate')
    def handle_ping():
        emit('pong', {'timestamp': str(__import__('datetime').datetime.now())})
