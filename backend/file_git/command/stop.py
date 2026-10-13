"""
Stop command — signal the active drain loop to halt cleanly.

Writes a ``stopped=true`` (and clears ``paused``) flag to the control sidecar.

When the drain is **actively running** (paused=false, no rate-limit):
    The drain loop reads the control file before each item and breaks on
    ``stopped=true``.  Because the loop exits normally (not via exception),
    the push/pull/apply_filter handler continues its post-drain cleanup
    automatically:
        push         → _rebuild_cloud_index_after_push() + release()
        pull         → scan_local_files() + release()
        apply_filter → rebuild both indices + upload + release()
    Completed items are preserved; remaining TODO items are discarded and
    will be re-detected on the next push/pull via a fresh diff.

When the drain is **user-paused** (paused=true, rate_limited_until=None):
    The drain is idle.  command_queue is called directly to run the full
    cleanup + release in one step (identical to what Resume would do, but
    immediately broken by the stopped flag so no new items are processed).

When the drain is **rate-limited** (paused=true, rate_limited_until set):
    The stop flag is written and the rate_limited_until is preserved so the
    scheduled auto-resume timer fires at its original time, then immediately
    sees stopped=true and does cleanup + release.  (Attempting an immediate
    cloud_index upload while Baidu is still rate-limiting would just fail.)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..service import QueueService
from ..service.queue_service import CONTROL_FILENAME
from ..service._fsutil import atomic_write_json
from .context import build_context


@dataclass
class StopResult:
    ok: bool
    message: str = ""


def command_stop(repo_id: str) -> StopResult:
    ctx = build_context(repo_id)
    state = QueueService.load(ctx.repo_root)
    if not state.lock:
        return StopResult(ok=False, message="No action is currently in progress")

    ctrl = QueueService.read_control(ctx.repo_root)
    is_rate_limited = bool(ctrl.get("rate_limited_until"))
    # Drain is idle when paused (user-pause or rate-limit).
    was_idle = state.paused

    # Write the stopped flag.  Keep rate_limited_until so the auto-resume
    # timer still fires and handles cleanup for the rate-limited case.
    atomic_write_json(
        os.path.join(ctx.repo_root, ".fgit", CONTROL_FILENAME),
        {
            "paused": False,
            "rate_limited_until": ctrl["rate_limited_until"],
            "stopped": True,
        },
    )

    if was_idle and not is_rate_limited:
        # User-paused: drain is not running and no network issue.
        # Trigger cleanup immediately via command_queue (which calls
        # consume_queue → breaks on stopped → rebuilds indices + release).
        from .queue import command_queue
        result = command_queue(repo_id)
        if result.ok:
            return StopResult(ok=True, message=result.message)
        return StopResult(
            ok=False,
            message=f"Stop signal sent but cleanup failed: {result.message}",
        )

    if is_rate_limited:
        return StopResult(
            ok=True,
            message=(
                "Stop signal sent — the action will finalize automatically "
                "when the Baidu rate limit clears."
            ),
        )

    return StopResult(
        ok=True,
        message="Stop signal sent — current file will finish, then the action will finalize and unlock",
    )

