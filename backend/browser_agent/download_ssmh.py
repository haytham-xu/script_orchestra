"""Browser Agent — Download SSMH.

Interactive per-tab download workflow:

  source_url  ─▶ GET, parse HTML, find `<a>` linking to /download-index-aid-…
              ─▶ GET that page, parse HTML, find the anchor whose visible
                 text contains `downloadSSMH.linkLabel` (site-specific)
              ─▶ Verify the anchor's host is in downloadDomains allowlist
              ─▶ Extract filename from `?n=<filename>`
              ─▶ Stream-download the .zip to downloadPath
              ─▶ On success, ask the browser extension to close the source tab

Runs as a single background job at a time; progress state is exposed via
`get_status()` so the UI can poll.
"""
from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlsplit, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

from . import settings_manager, agent_bridge


_TIMEOUT = 60            # seconds per HTTP call (source pages can be slow)
_RETRIES = 2             # retries after the first attempt fails (total = 3 tries)
_RETRY_BACKOFF = 2.0     # seconds between retries
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_SOURCE_PATH_RE = re.compile(r"/photos-index-aid-(\d+)\.html", re.I)
_DOWNLOAD_INDEX_HREF_RE = re.compile(r"/download-index-aid-\d+\.html", re.I)


# --------------------------------------------------------------------------
# job state (single job at a time)

_lock = threading.Lock()
_job_status: Dict[str, Any] = {
    "running": False,
    "total": 0,
    "done": 0,
    "items": [],   # per-URL: {"url", "status", "message", "filename", "download_url", "final_path"}
}


def _reset_status() -> None:
    with _lock:
        _job_status.update({"running": False, "total": 0, "done": 0, "items": []})


def get_status() -> Dict[str, Any]:
    with _lock:
        # Return a shallow copy so external readers can't mutate the ref.
        return {
            "running": _job_status["running"],
            "total": _job_status["total"],
            "done": _job_status["done"],
            "items": list(_job_status["items"]),
        }


# --------------------------------------------------------------------------
# URL / tab filtering

def _normalize_host(u: str) -> str:
    try:
        p = urlparse(u)
        host = (p.hostname or "").lower()
        # strip a leading www. so "www.foo.com" matches "foo.com" in the list.
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _host_in_allowlist(host: str, allow: List[str]) -> bool:
    host = host.lower()
    host_bare = host[4:] if host.startswith("www.") else host
    for d in allow:
        d = d.lower().strip()
        if not d:
            continue
        d_bare = d[4:] if d.startswith("www.") else d
        if host == d or host_bare == d_bare:
            return True
    return False


def is_source_tab(url: str, source_domains: List[str]) -> bool:
    """A tab counts as a Type-1 candidate if its host is in the source
    allowlist AND its path matches photos-index-aid-<digits>.html."""
    if not url or not source_domains:
        return False
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    if not _host_in_allowlist(p.hostname or "", source_domains):
        return False
    return bool(_SOURCE_PATH_RE.search(p.path or ""))


def scan(tab_urls: List[str], cfg: dict) -> List[Dict[str, Any]]:
    src = cfg.get("sourceDomains", [])
    out = []
    for u in tab_urls:
        if is_source_tab(u, src):
            m = _SOURCE_PATH_RE.search(urlparse(u).path or "")
            out.append({"url": u, "aid": m.group(1) if m else ""})
    return out


# --------------------------------------------------------------------------
# HTML fetch + link resolution

def _http_get(url: str, referer: Optional[str] = None) -> str:
    headers = {"User-Agent": _UA}
    if referer:
        headers["Referer"] = referer
    last_exc: Optional[Exception] = None
    for attempt in range(_RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, timeout=_TIMEOUT, allow_redirects=True)
            r.raise_for_status()
            return r.text
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
            if attempt < _RETRIES:
                time.sleep(_RETRY_BACKOFF * (attempt + 1))
                continue
            raise
        except requests.HTTPError:
            raise
    if last_exc:
        raise last_exc
    return ""


def _resolve_download_index_url(source_url: str, html: str) -> Optional[str]:
    """From the source (photos-index) page, find the first anchor that links
    to a /download-index-aid-*.html path."""
    soup = BeautifulSoup(html, "html.parser")
    chosen = None
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if _DOWNLOAD_INDEX_HREF_RE.search(href):
            chosen = href
            break
    if not chosen:
        return None
    # Resolve relative → absolute.
    if chosen.startswith("//"):
        chosen = urlparse(source_url).scheme + ":" + chosen
    elif chosen.startswith("/"):
        p = urlparse(source_url)
        chosen = f"{p.scheme}://{p.netloc}{chosen}"
    return chosen


def _resolve_final_download_link(download_index_url: str, html: str,
                                 link_label: str) -> Optional[str]:
    """From the download-index page, find the anchor whose visible text
    contains `link_label` and return its absolute href."""
    if not link_label:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip()
        if link_label in text:
            href = a["href"].strip()
            if href.startswith("//"):
                href = urlparse(download_index_url).scheme + ":" + href
            elif href.startswith("/"):
                p = urlparse(download_index_url)
                href = f"{p.scheme}://{p.netloc}{href}"
            return href
    return None


def _sanitize_filename(name: str) -> str:
    """Make `name` safe as a leaf filename: no separators, no reserved chars,
    no path-traversal, capped at 200 chars. Falls back to 'download.zip'."""
    if not name:
        return "download.zip"
    # Decode percent-encoding + unicode-normalize.
    try:
        name = unquote(name)
    except Exception:
        pass
    name = unicodedata.normalize("NFC", name)
    # Reject anything path-ish.
    name = name.replace("\\", "_").replace("/", "_")
    # Windows reserved + control chars.
    for ch in '<>:"|?*':
        name = name.replace(ch, "_")
    name = "".join(c for c in name if ord(c) >= 32)
    name = name.strip(" .")
    if not name:
        return "download.zip"
    return name[:200]


def _filename_from_link(url: str) -> str:
    """Pull filename from the `n=…` query param; if absent, use the URL's
    basename. Also preserve the URL's file extension — sites often set `n` to
    a human-readable name without the extension, but the actual resource is
    the .zip at the path, so we want `<n>.zip` as the on-disk name."""
    try:
        parts = urlsplit(url)
        qs = parse_qs(parts.query)
        n = (qs.get("n") or [""])[0]
        path_ext = os.path.splitext(parts.path)[1]  # ".zip"
        if n:
            name = _sanitize_filename(n)
            if path_ext and not name.lower().endswith(path_ext.lower()):
                name = name + path_ext
            return name
        base = os.path.basename(parts.path)
        return _sanitize_filename(base or "download.zip")
    except Exception:
        return "download.zip"


def _stream_download(url: str, dest_path: str, referer: Optional[str] = None,
                    on_progress: Optional[callable] = None) -> None:
    """Stream `url` into `dest_path`. Calls `on_progress(bytes_done, bytes_total,
    speed_bps)` at most every 500ms so the UI can render a live bar without
    us paying the update overhead per-chunk."""
    tmp_path = dest_path + ".part"
    headers = {"User-Agent": _UA}
    if referer:
        headers["Referer"] = referer
    last_exc: Optional[Exception] = None
    for attempt in range(_RETRIES + 1):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=_TIMEOUT) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length") or 0)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                bytes_done = 0
                window_bytes = 0
                window_started = time.monotonic()
                last_report = 0.0
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        bytes_done += len(chunk)
                        window_bytes += len(chunk)
                        now = time.monotonic()
                        if on_progress and (now - last_report) >= 0.5:
                            elapsed = max(now - window_started, 1e-3)
                            speed = window_bytes / elapsed
                            try:
                                on_progress(bytes_done, total, speed)
                            except Exception:
                                pass
                            last_report = now
                            window_started = now
                            window_bytes = 0
                # Final "100%" report so the UI settles cleanly.
                if on_progress:
                    try:
                        on_progress(bytes_done, total or bytes_done, 0.0)
                    except Exception:
                        pass
            os.replace(tmp_path, dest_path)
            return
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            if attempt < _RETRIES:
                time.sleep(_RETRY_BACKOFF * (attempt + 1))
                continue
            raise
    if last_exc:
        raise last_exc


def _close_source_tab(url: str) -> None:
    """Ask the extension to close every tab matching this URL."""
    result, err = agent_bridge.enqueue_and_wait("list_tabs", timeout=5.0)
    if err or not result:
        return
    ids = [t["id"] for t in result.get("tabs", []) if t.get("url") == url]
    if not ids:
        return
    agent_bridge.enqueue_and_wait("close_tabs", {"tab_ids": ids}, timeout=5.0)


# --------------------------------------------------------------------------
# job runner

def _update_item(index: int, **patch) -> None:
    with _lock:
        if 0 <= index < len(_job_status["items"]):
            _job_status["items"][index].update(patch)


def _process_one(index: int, source_url: str, cfg: dict) -> None:
    _update_item(index, status="fetching_source")
    try:
        source_html = _http_get(source_url)
    except Exception as e:
        _update_item(index, status="error", message=f"fetch source failed: {e}")
        return

    download_index_url = _resolve_download_index_url(source_url, source_html)
    if not download_index_url:
        _update_item(index, status="error",
                     message="could not find download-index link on source page")
        return

    _update_item(index, status="fetching_download_page")
    try:
        dl_html = _http_get(download_index_url, referer=source_url)
    except Exception as e:
        _update_item(index, status="error",
                     message=f"fetch download page failed: {e}")
        return

    final_url = _resolve_final_download_link(
        download_index_url, dl_html, cfg.get("linkLabel", ""))
    if not final_url:
        _update_item(index, status="error",
                     message="could not find the configured link label on the download page")
        return

    host = _normalize_host(final_url)
    if not _host_in_allowlist(host, cfg.get("downloadDomains", [])):
        _update_item(index, status="unmatched_download_domain",
                     message=f"download host '{host}' not in downloadDomains allowlist",
                     download_url=final_url)
        return

    filename = _filename_from_link(final_url)
    dest_dir = cfg.get("downloadPath", "").strip()
    if not dest_dir:
        _update_item(index, status="error", message="downloadPath not configured")
        return
    final_path = os.path.join(dest_dir, filename)

    _update_item(index, status="downloading",
                 download_url=final_url, filename=filename, final_path=final_path,
                 bytes_downloaded=0, bytes_total=0, speed_bps=0.0, progress_percent=0)

    def _report(done: int, total: int, speed: float) -> None:
        pct = int(done * 100 / total) if total > 0 else 0
        _update_item(index,
                     bytes_downloaded=done,
                     bytes_total=total,
                     speed_bps=speed,
                     progress_percent=pct)

    try:
        _stream_download(final_url, final_path, referer=download_index_url,
                         on_progress=_report)
    except Exception as e:
        _update_item(index, status="error", message=f"download failed: {e}")
        return

    try:
        _close_source_tab(source_url)
    except Exception as e:
        # Download succeeded — don't fail the whole item just because tab
        # close hiccupped. Note it in the message.
        _update_item(index, status="done",
                     message=f"downloaded, but close-tab failed: {e}")
        return

    _update_item(index, status="done", message="downloaded and tab closed")


def start_job(source_urls: List[str]) -> Dict[str, Any]:
    """Kick off a background Type-1 job. Rejects with error dict if a job is
    already running or config is missing."""
    settings = settings_manager.load_settings()
    cfg = settings.get("downloadSSMH", {}) or {}
    if not cfg.get("sourceDomains") or not cfg.get("downloadDomains"):
        return {"error": "downloadSSMH sourceDomains and downloadDomains must be configured"}
    if not cfg.get("downloadPath", "").strip():
        return {"error": "downloadSSMH downloadPath must be configured"}
    if not cfg.get("linkLabel", "").strip():
        return {"error": "downloadSSMH linkLabel must be configured"}

    with _lock:
        if _job_status["running"]:
            return {"error": "another Type 1 job is already running"}
        _job_status.update({
            "running": True,
            "total": len(source_urls),
            "done": 0,
            "items": [{"url": u, "status": "pending", "message": "",
                       "filename": "", "download_url": "", "final_path": "",
                       "bytes_downloaded": 0, "bytes_total": 0,
                       "speed_bps": 0.0, "progress_percent": 0}
                      for u in source_urls],
        })

    def _run():
        try:
            for i, u in enumerate(source_urls):
                _process_one(i, u, cfg)
                with _lock:
                    _job_status["done"] = i + 1
        finally:
            with _lock:
                _job_status["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "job started", "total": len(source_urls)}
