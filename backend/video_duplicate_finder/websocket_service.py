"""
Video Duplicate Finder — WebSocket Service.

Real-time progress updates over Socket.IO.

DECOUPLED: this module must not import from duplicate_finder.

Event namespace conventions (see DECISIONS D-09 / D-16):
    Per-scan rooms:   vscan:{scan_id}:progress
                      vscan:{scan_id}:complete
                      vscan:{scan_id}:error
    Tool-wide:        video-duplicate-finder:progress
                      video-duplicate-finder:complete
                      video-duplicate-finder:error

init_socketio() accepts EITHER:
  - a Flask `app` instance — creates a new SocketIO bound to it
  - an existing SocketIO instance — adopts it (pass-in mode, see D-16)

The pass-in mode is how `backend/app.py` will wire this up: a single
SocketIO is created by duplicate_finder.websocket_service, then handed to
this module via init_socketio(socketio_instance). Per D-11, we cannot
import duplicate_finder code — only the runtime instance is passed in.
"""

try:
    from flask_socketio import SocketIO
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    SocketIO = None  # type: ignore
    print("[Video WebSocket] flask-socketio not available — WebSocket disabled")

# Module-level socketio reference. emit_* functions call .emit() on this.
socketio = None  # type: ignore


def init_socketio(target):
    """
    Initialize Socket.IO for this module.

    Args:
        target: Flask `app` (creates new SocketIO) OR an existing SocketIO
                instance (pass-in mode). See module docstring.

    Returns:
        The SocketIO instance (newly created or adopted), or None if
        flask-socketio isn't installed.
    """
    global socketio

    if not SOCKETIO_AVAILABLE:
        print("[Video WebSocket] init_socketio: flask-socketio not installed; skipping")
        return None

    # If `target` already looks like a SocketIO instance, adopt it.
    # We can't `isinstance(target, SocketIO)` cleanly if SocketIO is None
    # at import time on systems without flask_socketio, so use duck-typing.
    if hasattr(target, 'emit') and hasattr(target, 'on'):
        socketio = target
        print("[Video WebSocket] Adopted existing SocketIO instance (pass-in mode)")
        return socketio

    # Otherwise treat as Flask app and create our own.
    socketio = SocketIO(target, cors_allowed_origins="*")
    print("[Video WebSocket] Created new SocketIO bound to Flask app")
    return socketio


def emit_progress(scan_id: str, current: int, total: int,
                  message: str = "", extra_data: dict = None):
    """
    Emit a progress event for a running scan.

    Args:
        scan_id: identifier matching the room (vscan:{scan_id}:progress)
        current: progress count
        total: total count
        message: human-readable status
        extra_data: optional dict merged into the payload
                    (e.g. {'groups_batch': [...]} for incremental UI updates)

    Critical (see DECISION D-09 / image-version-gotchas):
      - For groups_batch payloads, suppress the log line — otherwise large
        scans flood stdout with thousands of identical messages.
    """
    if not SOCKETIO_AVAILABLE or socketio is None:
        return

    try:
        payload = {
            'scan_id': scan_id,
            'current': current,
            'total': total,
            'percentage': int((current / total * 100)) if total > 0 else 0,
            'message': message,
        }
        if extra_data:
            payload.update(extra_data)

        socketio.emit(f'vscan:{scan_id}:progress', payload)
        socketio.emit('video-duplicate-finder:progress', payload)

        if not extra_data or 'groups_batch' not in extra_data:
            print(f"[Video WebSocket] progress {scan_id}: {current}/{total} - {message}")
    except Exception as e:
        print(f"[Video WebSocket] emit_progress failed: {e}")


def emit_complete(scan_id: str, result: dict):
    """
    Emit a scan completion event.

    IMPORTANT: `result` must be a SUMMARY ONLY, not the full duplicate_groups
    payload. On large libraries (tens of thousands of files) sending the
    full result over WebSocket crashes the worker thread due to message
    size limits. The frontend retrieves details via HTTP (/phase3/get-duplicates).

    Expected summary keys (mirrors duplicate_finder convention):
        scan_id, total_files, scanned_files, duplicate_count,
        groups_count, error_count, skipped_count, stats
    """
    if not SOCKETIO_AVAILABLE or socketio is None:
        return

    try:
        payload = {'scan_id': scan_id, 'result': result}
        socketio.emit(f'vscan:{scan_id}:complete', payload)
        socketio.emit('video-duplicate-finder:complete', payload)
        print(f"[Video WebSocket] complete emitted for {scan_id}")
    except Exception as e:
        print(f"[Video WebSocket] emit_complete failed: {e}")


def emit_error(scan_id: str, error: str):
    """Emit a scan error event."""
    if not SOCKETIO_AVAILABLE or socketio is None:
        return

    try:
        payload = {'scan_id': scan_id, 'error': error}
        socketio.emit(f'vscan:{scan_id}:error', payload)
        socketio.emit('video-duplicate-finder:error', payload)
        print(f"[Video WebSocket] error emitted for {scan_id}: {error}")
    except Exception as e:
        print(f"[Video WebSocket] emit_error failed: {e}")
