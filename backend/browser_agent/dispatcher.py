"""Browser Agent — background download dispatcher.

Polls the queue for TODO / FAILED tasks, downloads each with retry, and
broadcasts progress over the service's broadcaster. Fixes over the 2023
prototype: no hardcoded date dir, proper exception handling (never
crashes the thread), real retry accounting, and status stored as value.
"""
import os
import re
import time
import threading
from datetime import datetime

from . import repository, settings_manager
from .service import get_service
from .download_file import download_file
from .entity import Status


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name or "download")


def _process_one(tab, settings) -> None:
    svc = get_service()
    download_dir = settings.get("downloadDir", "")
    max_retries = settings.get("maxRetries", 3)

    # Skip tasks that have exhausted their retries.
    if tab.status == Status.FAILED.value and tab.retry_times >= max_retries:
        return

    tab.status = Status.IN_PROGRESS.value
    tab.updated_at = datetime.now()
    repository.update_browser_tab(tab)
    svc.broadcast({"taskId": tab.id, "status": tab.status, "progress": 0})

    out_path = os.path.join(download_dir, f"{_sanitize_filename(tab.file_name)}.zip")

    def on_progress(pct):
        svc.broadcast({"taskId": tab.id, "status": Status.IN_PROGRESS.value,
                       "progress": pct})

    ok = download_file(tab.download_link, out_path, tab.size, progress_cb=on_progress)

    if ok:
        tab.status = Status.COMPLETED.value
    else:
        tab.status = Status.FAILED.value
        tab.retry_times += 1
    tab.updated_at = datetime.now()
    repository.update_browser_tab(tab)
    svc.broadcast({"taskId": tab.id, "status": tab.status,
                   "progress": 100 if ok else 0, "retryTimes": tab.retry_times})


def run_once() -> None:
    settings = settings_manager.load_settings()
    if not settings.get("downloadDir"):
        # Nothing to do until a download directory is configured.
        return
    for tab in repository.get_all_need_downloaded():
        try:
            _process_one(tab, settings)
        except Exception as e:
            # Never let one bad task kill the loop.
            print(f"[browser_agent] dispatcher error on task {tab.id}: {e}")
        time.sleep(2)


def start_background_loop() -> threading.Thread:
    """Start the daemon polling loop; interval read from settings each cycle."""
    def loop():
        while True:
            try:
                run_once()
            except Exception as e:
                print(f"[browser_agent] dispatcher loop error: {e}")
            interval = settings_manager.load_settings().get("pollIntervalSec", 60)
            time.sleep(interval)

    thread = threading.Thread(target=loop, daemon=True, name="browser_agent_dispatcher")
    thread.start()
    print("[browser_agent] download dispatcher thread started")
    return thread
