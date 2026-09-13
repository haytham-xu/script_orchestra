"""Apprentice — subprocess runner + SSE fan-out.

Adapted from poc03/backend/services/runner.py. One worker subprocess per task.
"""
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import repository

WORKER_SCRIPT = Path(__file__).parent / "worker.py"
LOGS_DIR = Path(__file__).resolve().parent.parent.parent / ".claude" / "log"


@dataclass
class _RunState:
    task_id: int
    process: subprocess.Popen
    pgid: int
    reader_thread: threading.Thread
    subscribers: dict = field(default_factory=dict)
    subscribers_lock: threading.Lock = field(default_factory=threading.Lock)


_state: Optional[_RunState] = None
_state_lock = threading.Lock()

_sub_counter = 0
_sub_counter_lock = threading.Lock()


def _next_sub_id() -> str:
    global _sub_counter
    with _sub_counter_lock:
        _sub_counter += 1
        return str(_sub_counter)


def subscribe() -> tuple:
    sub_id = _next_sub_id()
    q: queue.Queue = queue.Queue(maxsize=512)
    with _state_lock:
        if _state:
            with _state.subscribers_lock:
                _state.subscribers[sub_id] = q
    return sub_id, q


def unsubscribe(sub_id: str) -> None:
    with _state_lock:
        if _state:
            with _state.subscribers_lock:
                _state.subscribers.pop(sub_id, None)


def _broadcast(event: dict) -> None:
    with _state_lock:
        if not _state:
            return
        with _state.subscribers_lock:
            dead = []
            for sub_id, q in _state.subscribers.items():
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(sub_id)
            for sub_id in dead:
                _state.subscribers.pop(sub_id, None)


def _handle_event(task_id: int, event: dict) -> None:
    evt_type = event.get("event", "")
    if evt_type == "done":
        status = event.get("status", "done")
        db_status = "done" if status == "completed" else "failed"
        repository.update_task_status(task_id, db_status)


def _reader_loop(task_id: int, process: subprocess.Popen) -> None:
    try:
        for raw in process.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                event = {"event": "system", "content": raw}
            _handle_event(task_id, event)
            _broadcast({"task_id": task_id, **event})
    except Exception as e:
        _broadcast({"task_id": task_id, "event": "system", "content": f"[reader error] {e}"})
    finally:
        process.wait()
        # If the worker crashed without emitting [DONE]/[HALTED], mark as failed.
        task = repository.get_task(task_id)
        if task and task.status == "running":
            repository.update_task_status(task_id, "failed")
        _broadcast({"task_id": task_id, "event": "run_finished"})
        with _state_lock:
            global _state
            if _state and _state.task_id == task_id:
                _state = None


def start(task_id: int) -> None:
    global _state
    with _state_lock:
        if _state and _state.process.poll() is None:
            raise RuntimeError(f"Another task ({_state.task_id}) is already running")

    LOGS_DIR.mkdir(exist_ok=True)
    ts = int(time.time())
    stderr_path = LOGS_DIR / f"worker-task{task_id}-{ts}.log"

    env = dict(os.environ)
    process = subprocess.Popen(
        [sys.executable, "-u", str(WORKER_SCRIPT), str(task_id)],
        stdout=subprocess.PIPE,
        stderr=open(stderr_path, "w"),
        text=True,
        bufsize=1,
        start_new_session=True,
        env=env,
    )
    pgid = os.getpgid(process.pid)
    repository.update_task_status(task_id, "running", pid=process.pid)

    reader = threading.Thread(
        target=_reader_loop, args=(task_id, process), daemon=True, name=f"apprentice-reader-{task_id}"
    )
    reader.start()

    with _state_lock:
        _state = _RunState(
            task_id=task_id,
            process=process,
            pgid=pgid,
            reader_thread=reader,
        )


def stop(task_id: int) -> None:
    with _state_lock:
        if not _state or _state.task_id != task_id:
            return
        pgid = _state.pgid
        process = _state.process

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    for _ in range(50):
        if process.poll() is not None:
            break
        time.sleep(0.1)

    if process.poll() is None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    repository.update_task_status(task_id, "stopped")


def running_task_id() -> Optional[int]:
    with _state_lock:
        if _state and _state.process.poll() is None:
            return _state.task_id
    return None
