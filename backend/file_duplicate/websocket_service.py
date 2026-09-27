"""
File Duplicate — WebSocket service (receives shared socketio from app.py)
"""

SOCKETIO_AVAILABLE = False
socketio = None

try:
    from flask_socketio import SocketIO  # noqa: F401 — just checks availability
    SOCKETIO_AVAILABLE = True
except ImportError:
    pass


def init_socketio(sio) -> None:
    global socketio, SOCKETIO_AVAILABLE
    socketio = sio
    SOCKETIO_AVAILABLE = sio is not None


def emit_progress(op_id: str, current: int, total: int, message: str = '',
                  extra: dict = None) -> None:
    if not socketio:
        return
    try:
        data = {
            'op_id': op_id,
            'current': current,
            'total': total,
            'percentage': int(current / total * 100) if total > 0 else 0,
            'message': message,
        }
        if extra:
            data.update(extra)
        socketio.emit('file-duplicate:progress', data)
        socketio.emit(f'file-duplicate:{op_id}:progress', data)
    except Exception as e:
        print(f'[FileDuplicate] emit_progress error: {e}')


def emit_complete(op_id: str, result: dict) -> None:
    if not socketio:
        return
    try:
        socketio.emit('file-duplicate:complete', {'op_id': op_id, 'result': result})
        socketio.emit(f'file-duplicate:{op_id}:complete', {'op_id': op_id, 'result': result})
    except Exception as e:
        print(f'[FileDuplicate] emit_complete error: {e}')


def emit_error(op_id: str, error: str) -> None:
    if not socketio:
        return
    try:
        socketio.emit('file-duplicate:error', {'op_id': op_id, 'error': error})
        socketio.emit(f'file-duplicate:{op_id}:error', {'op_id': op_id, 'error': error})
    except Exception as e:
        print(f'[FileDuplicate] emit_error error: {e}')
