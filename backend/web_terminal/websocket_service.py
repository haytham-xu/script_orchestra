"""Web Terminal — WebSocket service (shared SocketIO, pass-in mode).

Namespace: /web-terminal

Inbound events:
  wt_input   {window_id, data}
  wt_resize  {window_id, cols, rows}

Outbound (via broadcast_event, called by PtyManager reader threads):
  wt_event   {window_id, event, ...}   event = 'wt_output' | 'wt_exit'
"""
from .pty_manager import get_manager

socketio = None
NAMESPACE = '/web-terminal'


def init_socketio(app_socketio):
    global socketio
    socketio = app_socketio
    return socketio


def broadcast_event(payload: dict):
    if socketio:
        socketio.emit('wt_event', payload, namespace=NAMESPACE)


def register_socketio_events():
    if not socketio:
        print('[web_terminal] Cannot register events: SocketIO not initialized')
        return

    mgr = get_manager()
    mgr.register_broadcaster(broadcast_event)

    @socketio.on('connect', namespace=NAMESPACE)
    def handle_connect(auth=None):
        print('[web_terminal] client connected')

    @socketio.on('disconnect', namespace=NAMESPACE)
    def handle_disconnect():
        pass

    @socketio.on('wt_input', namespace=NAMESPACE)
    def handle_input(data):
        data = data or {}
        mgr.write(data.get('window_id', ''), data.get('data', ''))

    @socketio.on('wt_resize', namespace=NAMESPACE)
    def handle_resize(data):
        data = data or {}
        try:
            cols = int(data.get('cols', 80))
            rows = int(data.get('rows', 24))
        except (TypeError, ValueError):
            return
        mgr.resize(data.get('window_id', ''), cols, rows)
