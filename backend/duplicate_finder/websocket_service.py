"""
Duplicate Finder WebSocket Service

Provides real-time progress updates during image scanning
"""

# Check if flask-socketio is available
try:
    from flask_socketio import SocketIO
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    print("[Duplicate Finder] flask-socketio not available - WebSocket disabled")

socketio = None


def init_socketio(app):
    """
    Initialize Socket.IO with Flask app

    Args:
        app: Flask application instance

    Returns:
        socketio instance or None if not available
    """
    global socketio

    if not SOCKETIO_AVAILABLE:
        return None

    socketio = SocketIO(app, cors_allowed_origins="*")
    print("[Duplicate Finder] WebSocket initialized")
    return socketio


def emit_progress(scan_id: str, current: int, total: int, message: str = ""):
    """
    Emit scanning progress update to connected clients

    Args:
        scan_id: Unique scan operation ID
        current: Current progress count
        total: Total count
        message: Optional status message

    Example:
        emit_progress('scan-123', 50, 100, 'Scanning image 50/100')
    """
    if not SOCKETIO_AVAILABLE or socketio is None:
        return

    try:
        progress_data = {
            'scan_id': scan_id,
            'current': current,
            'total': total,
            'percentage': int((current / total * 100)) if total > 0 else 0,
            'message': message
        }

        # Emit to specific scan room
        socketio.emit(f'scan:{scan_id}:progress', progress_data)

        # Also emit to general progress channel
        socketio.emit('duplicate-finder:progress', progress_data)

        print(f"[Duplicate Finder] Progress emitted for {scan_id}: {current}/{total} - {message}")

    except Exception as e:
        print(f"[Duplicate Finder] Failed to emit progress: {e}")


def emit_complete(scan_id: str, result: dict):
    """
    Emit scan completion event with summary data.

    IMPORTANT: Only pass summary data, NOT the full result with duplicate_groups.
    For large datasets (e.g., 640k+ files), sending the full result can crash
    the WebSocket thread due to message size limitations.

    Args:
        scan_id: Unique scan operation ID
        result: Summary dictionary with:
            - scan_id: str
            - total_files: int
            - scanned_files: int
            - duplicate_count: int
            - groups_count: int
            - error_count: int
            - skipped_count: int
            - stats: dict

    Example:
        completion_summary = {
            "scan_id": "scan-123",
            "total_files": 1000,
            "scanned_files": 995,
            "duplicate_count": 50,
            "groups_count": 10,
            "error_count": 5,
            "skipped_count": 0,
            "stats": {...}
        }
        emit_complete("scan-123", completion_summary)
    """
    if not SOCKETIO_AVAILABLE or socketio is None:
        return

    try:
        complete_data = {
            'scan_id': scan_id,
            'result': result
        }

        socketio.emit(f'scan:{scan_id}:complete', complete_data)
        socketio.emit('duplicate-finder:complete', complete_data)

        print(f"[Duplicate Finder] Scan complete emitted for {scan_id}")

    except Exception as e:
        print(f"[Duplicate Finder] Failed to emit completion: {e}")


def emit_error(scan_id: str, error: str):
    """
    Emit error event

    Args:
        scan_id: Unique scan operation ID
        error: Error message
    """
    if not SOCKETIO_AVAILABLE or socketio is None:
        return

    try:
        error_data = {
            'scan_id': scan_id,
            'error': error
        }

        socketio.emit(f'scan:{scan_id}:error', error_data)
        socketio.emit('duplicate-finder:error', error_data)

        print(f"[Duplicate Finder] Error emitted for {scan_id}: {error}")

    except Exception as e:
        print(f"[Duplicate Finder] Failed to emit error: {e}")
