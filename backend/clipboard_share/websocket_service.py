"""
WebSocket Service for Clipboard Share

Handles real-time push of clipboard updates to connected clients.
"""
from flask_socketio import emit

# Will be initialized from main app
socketio = None

def init_socketio(app_socketio):
    """Initialize with the app's socketio instance"""
    global socketio
    socketio = app_socketio
    return socketio


def broadcast_clipboard_update(clipboard_item: dict):
    """
    Broadcast clipboard update to all connected clients

    Args:
        clipboard_item: The clipboard item to broadcast
    """
    if socketio:
        try:
            socketio.emit(
                'clipboard_update',
                clipboard_item,
                namespace='/clipboard',
                broadcast=True
            )
            print(f"[ClipboardShare] Broadcasted update: ID={clipboard_item.get('id')}")
        except Exception as e:
            print(f"[ClipboardShare] Failed to broadcast: {e}")
    else:
        print("[ClipboardShare] Warning: SocketIO not initialized")


# SocketIO event handlers
def register_socketio_events():
    """Register SocketIO event handlers for clipboard namespace"""
    if not socketio:
        print("[ClipboardShare] Cannot register events: SocketIO not initialized")
        return

    @socketio.on('connect', namespace='/clipboard')
    def handle_connect():
        print('[ClipboardShare] Client connected to /clipboard namespace')

    @socketio.on('disconnect', namespace='/clipboard')
    def handle_disconnect():
        print('[ClipboardShare] Client disconnected from /clipboard namespace')

    @socketio.on('ping', namespace='/clipboard')
    def handle_ping():
        emit('pong', {'timestamp': str(__import__('datetime').datetime.now())})
