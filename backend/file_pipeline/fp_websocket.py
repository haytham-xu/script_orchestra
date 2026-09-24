_socketio = None


def init_socketio(socketio):
    global _socketio
    _socketio = socketio


def make_progress_callback(run_id, pipeline_id):
    def cb(event: dict):
        if _socketio:
            _socketio.emit('fp_progress', {'run_id': run_id, 'pipeline_id': pipeline_id, **event})
    return cb
