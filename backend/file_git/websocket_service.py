"""
WebSocket Service for File-Git Progress Updates
Requires: flask-socketio

Installation:
    pip install flask-socketio==5.3.5 python-socketio==5.10.0

Usage:
    from file_git.websocket_service import socketio, emit_progress

    # In your operation
    emit_progress(repo_id, 'push', 'uploading', 5, 10, 'Uploading file.txt')
"""

try:
    from flask_socketio import SocketIO, emit
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    print("[WebSocket] flask-socketio not installed. WebSocket features disabled.")
    print("[WebSocket] To enable: pip install flask-socketio==5.3.5 python-socketio==5.10.0")


# Global SocketIO instance (will be initialized in app.py)
socketio = None if not SOCKETIO_AVAILABLE else None  # Will be set by init_socketio()


def init_socketio(app):
    """
    Initialize SocketIO with Flask app

    Args:
        app: Flask application instance

    Returns:
        SocketIO instance or None if not available
    """
    global socketio

    if not SOCKETIO_AVAILABLE:
        print("[WebSocket] SocketIO not available, progress updates disabled")
        return None

    socketio = SocketIO(app, cors_allowed_origins="*")
    print("[WebSocket] SocketIO initialized")

    @socketio.on('connect')
    def handle_connect():
        print(f"[WebSocket] Client connected")

    @socketio.on('disconnect')
    def handle_disconnect():
        print(f"[WebSocket] Client disconnected")

    return socketio


def emit_progress(repo_id: str, operation: str, phase: str, current: int, total: int, message: str = ""):
    """
    Emit progress update to connected clients

    Args:
        repo_id: Repository ID
        operation: Operation type (push, pull, verify, scan)
        phase: Current phase (scanning, uploading, downloading, etc.)
        current: Current progress count
        total: Total count
        message: Optional status message

    Example:
        emit_progress('repo-123', 'push', 'uploading', 5, 10, 'Uploading file5.txt')
    """
    if not SOCKETIO_AVAILABLE or socketio is None:
        return

    try:
        progress_data = {
            'repo_id': repo_id,
            'operation': operation,
            'phase': phase,
            'current': current,
            'total': total,
            'percentage': int((current / total * 100)) if total > 0 else 0,
            'message': message
        }

        # Emit to specific repo room
        socketio.emit(f'repo:{repo_id}:progress', progress_data)

        # Also emit to general progress channel
        socketio.emit('progress', progress_data)

        print(f"[WebSocket] Progress emitted for {repo_id}: {current}/{total} - {message}")

    except Exception as e:
        print(f"[WebSocket] Error emitting progress: {e}")


def emit_status(repo_id: str, status: str, message: str = ""):
    """
    Emit status update to connected clients

    Args:
        repo_id: Repository ID
        status: Status (ready, syncing, error, success)
        message: Status message
    """
    if not SOCKETIO_AVAILABLE or socketio is None:
        return

    try:
        status_data = {
            'repo_id': repo_id,
            'status': status,
            'message': message
        }

        socketio.emit(f'repo:{repo_id}:status', status_data)
        socketio.emit('status', status_data)

        print(f"[WebSocket] Status emitted for {repo_id}: {status} - {message}")

    except Exception as e:
        print(f"[WebSocket] Error emitting status: {e}")


def emit_log(repo_id: str, level: str, message: str):
    """
    Emit log message to connected clients

    Args:
        repo_id: Repository ID
        level: Log level (info, warning, error)
        message: Log message
    """
    if not SOCKETIO_AVAILABLE or socketio is None:
        return

    try:
        import datetime

        log_data = {
            'repo_id': repo_id,
            'level': level,
            'message': message,
            'timestamp': datetime.datetime.now().isoformat()
        }

        socketio.emit(f'repo:{repo_id}:log', log_data)

        print(f"[WebSocket] Log emitted for {repo_id} [{level}]: {message}")

    except Exception as e:
        print(f"[WebSocket] Error emitting log: {e}")
