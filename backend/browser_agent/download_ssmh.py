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

import concurrent.futures
import os
import re
import threading
import time
import unicodedata
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlsplit, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

from . import settings_manager, agent_bridge, repository


_TIMEOUT = 60            # seconds per HTTP call (source pages can be slow)
_RETRIES = 2             # retries after the first attempt fails (total = 3 tries)
_RETRY_BACKOFF = 2.0     # seconds between retries
_MAX_PARTS = 16          # upper bound for cleanup — always cleans up to this many .part.N files
_DEFAULT_PARTS = 1       # fallback when not specified in cfg; override via settings.downloadParts
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_SOURCE_PATH_RE = re.compile(r"/photos-index-aid-(\d+)\.html", re.I)
_DOWNLOAD_INDEX_HREF_RE = re.compile(r"/download-index-aid-\d+\.html", re.I)
_CH_ROW_AID_RE = re.compile(r"/download-index-aid-(\d+)\.html", re.I)

# Type 2 — Tailwind page with inline WORKER_API CONFIG block
_TYPE2_CONFIG_RE = re.compile(r'const\s+CONFIG\s*=\s*\{([^}]+)\}', re.S)
_CH_WRAP_RE = re.compile(r'<div[^>]+id=["\']ch-wrap["\'][^>]*>', re.I)

# Bytes that appear in the "quota exceeded" HTML page returned by the CDN
# (Traditional Chinese: "Download quota exhausted").
_QUOTA_BYTES = b"\xe4\xb8\x8b\xe8\xbc\x89\xe9\x85\x8d\xe9\xa1\x8d\xe5\xb7\xb2\xe7\x94\xa8\xe5\xae\x8c"


class QuotaExceededError(Exception):
    """Raised when the CDN reports the per-IP daily download quota is exhausted."""


# --------------------------------------------------------------------------
# scan state

_scan_lock = threading.Lock()
_scan_status: Dict[str, Any] = {
    "running": False,
    "total_tabs": 0,   # all open tabs seen
    "total": 0,        # matching candidates to classify
    "done": 0,         # classified so far
    "candidates": [],
}


def get_scan_status() -> Dict[str, Any]:
    with _scan_lock:
        return dict(_scan_status)


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


def _classify_source(url: str) -> str:
    """Return cached dl_type from DB if known; otherwise fetch source page to classify,
    then persist the result. Returns 'type1'/'type2'/'unknown'."""
    path = urlparse(url).path
    cached = repository.get_ssmh_scan_type(path)
    if cached in ("type1", "type2"):
        return cached
    try:
        html = _http_get(url)
        _, is_type1 = _resolve_download_index_url(url, html)
        dl_type = "type1" if is_type1 else "type2"
    except Exception:
        dl_type = "unknown"
    if dl_type != "unknown":
        repository.upsert_ssmh_scan_type(path, dl_type)
    return dl_type


def start_scan_job(tab_urls: List[str], cfg: dict, total_tabs: int) -> bool:
    """Filter tabs to candidates, classify type1/type2 in background.

    Returns False if a scan is already running. Progress is readable via
    get_scan_status().
    """
    src = cfg.get("sourceDomains", [])
    pending: List[Dict[str, Any]] = []
    for u in tab_urls:
        if is_source_tab(u, src):
            m = _SOURCE_PATH_RE.search(urlparse(u).path or "")
            pending.append({"url": u, "aid": m.group(1) if m else "", "dl_type": "unknown"})

    with _scan_lock:
        if _scan_status["running"]:
            return False
        _scan_status.update({
            "running": True,
            "total_tabs": total_tabs,
            "total": len(pending),
            "done": 0,
            "candidates": [],
        })

    if not pending:
        with _scan_lock:
            _scan_status["running"] = False
        return True

    def _run() -> None:
        def _classify_one(c: Dict[str, Any]) -> None:
            c["dl_type"] = _classify_source(c["url"])
            with _scan_lock:
                _scan_status["candidates"].append(c)
                _scan_status["done"] += 1

        with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(len(pending), 8)) as pool:
            list(pool.map(_classify_one, pending))

        with _scan_lock:
            _scan_status["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return True


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


def _resolve_download_index_url(source_url: str, html: str) -> tuple:
    """Return (url, is_type1) where is_type1=True means an explicit
    /download-index-aid-*.html link was found on the source page (Type 1 —
    single album); False means the URL was derived from the source AID
    (Type 2 — series/collection page)."""
    soup = BeautifulSoup(html, "html.parser")
    chosen = None
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if _DOWNLOAD_INDEX_HREF_RE.search(href):
            chosen = href
            break
    if chosen:
        if chosen.startswith("//"):
            chosen = urlparse(source_url).scheme + ":" + chosen
        elif chosen.startswith("/"):
            p = urlparse(source_url)
            chosen = f"{p.scheme}://{p.netloc}{chosen}"
        return chosen, True   # Type 1

    # Fallback: derive from source AID — this is a series page (Type 2).
    m = _SOURCE_PATH_RE.search(urlparse(source_url).path or "")
    if m:
        p = urlparse(source_url)
        return f"{p.scheme}://{p.netloc}/download-index-aid-{m.group(1)}.html", False
    return None, False


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


def _close_source_tab(url: str) -> None:
    """Ask the extension to close every tab matching this URL."""
    result, err = agent_bridge.enqueue_and_wait("list_tabs", timeout=5.0)
    if err or not result:
        return
    ids = [t["id"] for t in result.get("tabs", []) if t.get("url") == url]
    if not ids:
        return
    agent_bridge.enqueue_and_wait("close_tabs", {"tab_ids": ids}, timeout=5.0)


def _stream_download(url: str, dest_path: str, referer: Optional[str] = None,
                     on_progress: Optional[callable] = None,
                     parts: int = _DEFAULT_PARTS) -> None:
    """Download url to dest_path.

    Tries parallel range-download first when parts > 1 (bypasses per-connection
    CDN speed caps). Falls back to single stream if the server does not support
    Accept-Ranges or if parts == 1.
    """
    headers = {"User-Agent": _UA}
    if referer:
        headers["Referer"] = referer

    if parts > 1:
        try:
            hr = requests.head(url, headers=headers, timeout=_TIMEOUT, allow_redirects=True)
            total = int(hr.headers.get("Content-Length") or 0)
            if total > 0 and "bytes" in hr.headers.get("Accept-Ranges", ""):
                _parallel_range_download(url, dest_path, headers, total, on_progress, parts)
                return
        except Exception:
            pass  # fall through to single stream

    _single_stream_download(url, dest_path, headers, on_progress)


def _single_stream_download(url: str, dest_path: str, headers: dict,
                             on_progress: Optional[callable] = None) -> None:
    tmp_path = dest_path + ".part"
    last_exc: Optional[Exception] = None
    for attempt in range(_RETRIES + 1):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=_TIMEOUT) as r:
                r.raise_for_status()
                ct = r.headers.get("Content-Type", "").lower()
                total = int(r.headers.get("Content-Length") or 0)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                bytes_done = 0
                window_bytes = 0
                window_started = time.monotonic()
                last_report = 0.0
                first_chunk = True
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        if first_chunk:
                            first_chunk = False
                            if "text/html" in ct:
                                if _QUOTA_BYTES in chunk:
                                    raise QuotaExceededError(
                                        "Download quota exceeded (100 files per IP per 24 h)")
                                raise RuntimeError(
                                    f"Server returned HTML instead of file content")
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
        except requests.HTTPError:
            raise
    if last_exc:
        raise last_exc


def _parallel_range_download(url: str, dest_path: str, base_headers: dict,
                              total: int, on_progress: Optional[callable] = None,
                              n: int = _DEFAULT_PARTS) -> None:
    """Download file using n concurrent range requests, then concatenate."""
    part_size = (total + n - 1) // n
    tmp_parts = [f"{dest_path}.part.{i}" for i in range(n)]

    bytes_lock = threading.Lock()
    bytes_per_part = [0] * n
    last_report_at = [time.monotonic()]
    last_report_bytes = [0]
    errors: List[Exception] = []

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    def fetch_part(i: int) -> None:
        start = i * part_size
        end = min(start + part_size - 1, total - 1)
        h = dict(base_headers)
        h["Range"] = f"bytes={start}-{end}"
        path = tmp_parts[i]
        last_exc: Optional[Exception] = None
        for attempt in range(_RETRIES + 1):
            try:
                with requests.get(url, headers=h, stream=True, timeout=_TIMEOUT) as r:
                    r.raise_for_status()
                    with open(path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=64 * 1024):
                            if not chunk:
                                continue
                            f.write(chunk)
                            with bytes_lock:
                                bytes_per_part[i] += len(chunk)
                                now = time.monotonic()
                                elapsed = now - last_report_at[0]
                                if on_progress and elapsed >= 0.5:
                                    done = sum(bytes_per_part)
                                    delta = done - last_report_bytes[0]
                                    speed = delta / max(elapsed, 1e-3)
                                    try:
                                        on_progress(done, total, speed)
                                    except Exception:
                                        pass
                                    last_report_at[0] = now
                                    last_report_bytes[0] = done
                return
            except (requests.Timeout, requests.ConnectionError) as e:
                last_exc = e
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
                if attempt < _RETRIES:
                    time.sleep(_RETRY_BACKOFF * (attempt + 1))
                    continue
                errors.append(e)
                return
            except requests.HTTPError as e:
                errors.append(e)
                return
        if last_exc:
            errors.append(last_exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(fetch_part, range(n)))

    if errors:
        for p in tmp_parts:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        raise errors[0]

    # Concatenate segments in order.
    final_tmp = dest_path + ".part"
    try:
        with open(final_tmp, "wb") as out:
            for p in tmp_parts:
                with open(p, "rb") as pf:
                    while True:
                        chunk = pf.read(64 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                try:
                    os.remove(p)
                except OSError:
                    pass
        os.replace(final_tmp, dest_path)
    except Exception:
        try:
            if os.path.exists(final_tmp):
                os.remove(final_tmp)
        except OSError:
            pass
        for p in tmp_parts:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        raise

    if on_progress:
        try:
            on_progress(total, total, 0.0)
        except Exception:
            pass

def _is_type2(html: str) -> bool:
    """True if the download-index page uses the WORKER_API CONFIG pattern."""
    m = _TYPE2_CONFIG_RE.search(html)
    return bool(m and 'WORKER_API' in m.group(0))


def _extract_direct_link(html: str, page_url: str) -> str:
    """Return the direct CDN link (class=ads) from a download-index page, resolved to absolute URL."""
    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        if 'ads' in (a.get('class') or []):
            if href.startswith('//'):
                p = urlparse(page_url)
                return f"{p.scheme}:{href}"
            if urlparse(href).netloc:
                return href
    return ''


def _extract_type2_config(html: str) -> Dict[str, str]:
    """Extract WORKER_API, FILE_KEY, FILE_NAME from inline CONFIG JS block."""
    m = _TYPE2_CONFIG_RE.search(html)
    if not m or 'WORKER_API' not in m.group(0):
        return {}
    block = m.group(1)

    def _pick(key: str) -> str:
        p = re.search(rf'{key}\s*:\s*["\']([^"\']+)["\']', block)
        return p.group(1) if p else ''

    return {
        'worker_api': _pick('WORKER_API'),
        'file_key':   _pick('FILE_KEY'),
        'file_name':  _pick('FILE_NAME'),
    }


def _extract_h1_title(html: str) -> str:
    """Return text of the Tailwind h1 (used as folder name for Type 2)."""
    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1', class_=lambda c: c and 'text-xl' in c)
    if h1:
        return h1.get_text(separator=' ', strip=True).strip()
    return ''


def _sanitize_dirname(name: str) -> str:
    """Make name safe as a directory name (no separators, no reserved chars)."""
    if not name:
        return 'download'
    try:
        name = unquote(name)
    except Exception:
        pass
    name = unicodedata.normalize('NFC', name)
    name = name.replace('\\', '_').replace('/', '_')
    for ch in '<>:"|?*':
        name = name.replace(ch, '_')
    name = ''.join(c for c in name if ord(c) >= 32)
    name = name.strip(' .')
    return (name[:180] or 'download')


def _call_worker_api(worker_api: str, file_key: str, file_name: str,
                     referer: str) -> Optional[str]:
    """POST {file_key, file_name} to WORKER_API; return the generated download URL."""
    p = urlparse(referer)
    origin = f'{p.scheme}://{p.netloc}'
    headers = {
        'User-Agent': _UA,
        'Content-Type': 'application/json',
        'Referer': referer,
        'Origin': origin,
    }
    last_exc: Optional[Exception] = None
    for attempt in range(_RETRIES + 1):
        try:
            r = requests.post(
                worker_api,
                json={'file_key': file_key, 'file_name': file_name},
                headers=headers,
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            if data.get('success'):
                return data.get('url')
            return None
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
            if attempt < _RETRIES:
                time.sleep(_RETRY_BACKOFF * (attempt + 1))
                continue
            raise
    if last_exc:
        raise last_exc
    return None


def _is_multi_chapter(html: str) -> bool:
    return bool(_CH_WRAP_RE.search(html))


def _get_ch_wrap_attrs(html: str) -> Dict[str, Any]:
    m = _CH_WRAP_RE.search(html)
    if not m:
        return {}
    tag = m.group(0)

    def _attr(name: str) -> str:
        a = re.search(rf'data-{name}=["\']([^"\']+)["\']', tag)
        return a.group(1) if a else ''

    return {
        'sid':   _attr('sid'),
        'limit': int(_attr('limit') or 30),
        'total': int(_attr('total') or 0),
    }


def _parse_ch_list_html(html: str) -> List[Dict[str, str]]:
    """Parse first-page chapter rows from server-rendered #ch-list."""
    soup = BeautifulSoup(html, 'html.parser')
    ch_list = soup.find(id='ch-list')
    if not ch_list:
        return []
    result = []
    for row in ch_list.find_all(class_='ch-row'):
        key = row.get('data-key', '')
        name_el = row.find(class_='ch-name')
        name = name_el.get_text(strip=True) if name_el else ''
        dl2_el = row.find(class_='ch-dl2')
        dl2 = dl2_el.get('href', '') if dl2_el else ''
        # Per-chapter AID from the download-index anchor (distinct from series AID).
        ch_aid = ''
        for a in row.find_all('a', href=True):
            ma = _CH_ROW_AID_RE.search(a['href'])
            if ma:
                ch_aid = ma.group(1)
                break
        if key:
            result.append({'key': key, 'name': name, 'dl2': dl2, 'ch_aid': ch_aid})
    return result


def _fetch_chapters_page(base_url: str, sid: str, page: int) -> dict:
    url = f'{base_url}/?ctl=download&act=chapters&sid={sid}&page={page}'
    r = requests.get(url, headers={'User-Agent': _UA}, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _get_all_chapters(html: str, base_url: str, ch_attrs: Dict[str, Any]) -> List[Dict[str, str]]:
    """Combine SSR first page + pagination API to collect all chapter items."""
    first = _parse_ch_list_html(html)
    sid   = ch_attrs.get('sid', '')
    limit = ch_attrs.get('limit', 30)
    total = ch_attrs.get('total', 0)
    if not sid or not first:
        return first
    if len(first) >= total:
        return first
    all_items: List[Dict[str, str]] = list(first)
    page = 1
    while page * limit < total:
        page += 1
        try:
            data = _fetch_chapters_page(base_url, sid, page)
            if data.get('code') != 0:
                break
            for item in data.get('list', []):
                # API returns 'id' as the per-chapter AID, 'key' as data-key.
                all_items.append({
                    'key':    item.get('key', ''),
                    'name':   item.get('name', ''),
                    'dl2':    item.get('dl2', ''),
                    'ch_aid': str(item.get('id', '')),
                })
            total = data.get('total', total)
        except Exception:
            break
    return all_items


# --------------------------------------------------------------------------
# image-level fallback helpers

def _derive_slide_url(source_url: str, data_key: str) -> Optional[str]:
    """Build the reader/slide page URL from source AID + optional SID in data_key.

    Series chapters store key as 'down/{SID}/{HASH}.zip', so SID lives at index 1.
    Single-album keys don't follow that format → no SID, use plain aid-only URL.
    """
    p = urlparse(source_url)
    m = _SOURCE_PATH_RE.search(p.path or "")
    if not m:
        return None
    aid = m.group(1)
    base = f"{p.scheme}://{p.netloc}"
    parts = (data_key or "").split("/")
    if len(parts) >= 3 and parts[0] == "down":
        sid = parts[1]
        return f"{base}/photos-slide-aid-{aid}-sid-{sid}.html"
    return f"{base}/photos-slide-aid-{aid}.html"


def _fetch_slide_images(html: str) -> List[Dict]:
    """Extract (index, url, ext) triples from a reader/slide page HTML.

    Primary: parses mReader.initData({key: [url, ...]}) from the photos-item
    script that the slide page embeds via <script src="/photos-item-aid-N.html">.
    Fallback: looks for <img data-src/src data-index="N"> elements (lazy-load).

    Privacy: never logs or exposes actual src values.
    """
    soup = BeautifulSoup(html, 'html.parser')
    p = urlparse(html[:200].split('\n')[0]) if html.startswith('http') else None  # unused, just a comment anchor

    # ── Primary: photos-item script (mReader.initData) ─────────────────────
    # The slide page loads /photos-item-aid-{chapter_aid}.html as a <script>.
    # That script calls mReader.initData({"key": ["url1","url2",...]}).
    for sc in soup.find_all('script', src=True):
        src = sc.get('src', '')
        if re.search(r'/photos-item-aid-\d+\.html', src, re.I):
            return None  # signal caller to fetch this URL separately

    # ── Fallback: <img data-index> scan ─────────────────────────────────────
    items = []
    for img in soup.find_all('img', attrs={'data-index': True}):
        src_url = (img.get('data-src', '').strip()
                   or img.get('data-original', '').strip()
                   or img.get('src', '').strip())
        idx_raw = img.get('data-index', '')
        if not src_url or not idx_raw:
            continue
        if src_url.startswith('data:') or '.' not in src_url.split('/')[-1]:
            continue
        try:
            idx = int(idx_raw)
        except ValueError:
            continue
        path = urlparse(src_url).path
        ext = os.path.splitext(path)[1].lstrip('.').lower() or 'jpg'
        items.append({'index': idx, 'url': src_url, 'ext': ext})
    items.sort(key=lambda x: x['index'])
    return items


_MREADER_RE = re.compile(
    r'mReader\.initData\s*\(\s*\{\s*["\']?[^"\']+["\']?\s*:\s*(\[[^\]]+\])',
    re.S,
)


def _parse_photos_item(js_text: str) -> List[Dict]:
    """Parse image URLs from a photos-item-aid-N.html JS payload.

    Expected format:  mReader.initData({"key": ["url1","url2",...]})
    Returns list of {index, url, ext} dicts (1-based index).
    Privacy: URLs are used for download only, never logged.
    """
    m = _MREADER_RE.search(js_text)
    if not m:
        return []
    arr_text = m.group(1)
    urls = re.findall(r'"([^"]+)"', arr_text)
    items = []
    for i, url in enumerate(urls, start=1):
        url = url.strip()
        if not url:
            continue
        path = urlparse(url).path
        ext = os.path.splitext(path)[1].lstrip('.').lower() or 'jpg'
        items.append({'index': i, 'url': url, 'ext': ext})
    return items


def _download_images_fallback(
    index: int,
    sub_index: Optional[int],
    source_url: str,
    data_key: str,
    file_name: str,
    folder_path: str,
    dl_page_url: str,
    ch_aid: str = '',
) -> tuple:
    """Last-resort: fetch the reader/slide page and download images one by one.

    ch_aid: per-chapter AID (Type 2 only). When provided, the slide URL is derived
    directly as photos-slide-aid-{ch_aid}.html instead of using data_key's SID.
    Multiple chapters in a series can share the same SID in their data_key, so
    using ch_aid is the only reliable way to get per-chapter images.

    Returns (success: bool, reason: str). reason is non-empty on failure.
    Privacy: image URLs and actual filenames are never logged or exposed.
    """
    # Build slide URL: prefer ch_aid (unambiguous per-chapter), fall back to data_key SID.
    if ch_aid:
        pu = urlparse(source_url)
        base = f"{pu.scheme}://{pu.netloc}"
        slide_url = f"{base}/photos-slide-aid-{ch_aid}.html"
    else:
        slide_url = _derive_slide_url(source_url, data_key)
    if not slide_url:
        return False, "could not derive slide URL from source/key"

    def _upd(**kw: Any) -> None:
        if sub_index is not None:
            _update_subitem(index, sub_index, **kw)
        else:
            _update_item(index, **kw)

    _upd(status="fetching_slide", message="Fetching reader page for image download",
         progress_percent=0)
    try:
        slide_html = _http_get(slide_url, referer=source_url)
    except Exception as e:
        return False, f"slide page fetch failed: {e}"

    # ── Primary: photos-item-aid script embedded in the slide page ──────────
    images: List[Dict] = []
    soup = BeautifulSoup(slide_html, 'html.parser')
    p = urlparse(slide_url)
    base = f"{p.scheme}://{p.netloc}"

    for sc in soup.find_all('script', src=True):
        sc_src = sc.get('src', '')
        if re.search(r'/photos-item-aid-\d+\.html', sc_src, re.I):
            item_url = sc_src if sc_src.startswith('http') else base + sc_src
            try:
                item_js = _http_get(item_url, referer=slide_url)
                images = _parse_photos_item(item_js)
            except Exception as e:
                return False, f"photos-item fetch failed: {e}"
            break

    # ── Fallback: <img data-index> scan ─────────────────────────────────────
    if not images:
        images = _fetch_slide_images(slide_html) or []

    if not images:
        return False, "no images found on slide page (no photos-item script and no data-index imgs)"

    base_name = os.path.splitext(file_name)[0] or file_name
    img_dir = os.path.join(folder_path, _sanitize_dirname(base_name))

    os.makedirs(img_dir, exist_ok=True)

    n_imgs = len(images)
    _upd(status="downloading_images",
         message=f"Downloading {n_imgs} images",
         progress_percent=0)

    errors = 0
    for i, img_info in enumerate(images):
        idx = img_info['index']
        ext = img_info['ext']
        img_path = os.path.join(img_dir, f"{idx:03d}.{ext}")
        _upd(progress_percent=int(i * 100 / n_imgs),
             message=f"Image {i + 1}/{n_imgs}")
        try:
            _single_stream_download(
                img_info['url'], img_path,
                {"User-Agent": _UA, "Referer": slide_url},
            )
        except QuotaExceededError:
            raise
        except Exception:
            errors += 1

    if errors >= n_imgs:
        return False, f"all {n_imgs} image downloads failed"

    _upd(status="done", progress_percent=100,
         message=f"Downloaded {n_imgs - errors}/{n_imgs} images")
    return True, ""


# --------------------------------------------------------------------------
# job runner

def _cleanup_partial(dest_path: str) -> None:
    """Remove .part and .part.N temp files left by a failed download."""
    for suffix in [".part"] + [f".part.{i}" for i in range(_MAX_PARTS)]:
        p = dest_path + suffix
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def _log(source_url: str, dl_type: str, method: str,
         status: str, filename: str = '', error: Exception = None) -> None:
    """Fire-and-forget DB log for one download attempt. Never raises."""
    repository.log_ssmh_download(
        source_url, dl_type, method, status, filename,
        str(error) if error else '',
    )

def _update_item(index: int, **patch) -> None:
    with _lock:
        if 0 <= index < len(_job_status["items"]):
            _job_status["items"][index].update(patch)


def _update_subitem(item_index: int, sub_index: int, **patch) -> None:
    with _lock:
        items = _job_status["items"]
        if 0 <= item_index < len(items):
            subs = items[item_index].get("sub_items", [])
            if 0 <= sub_index < len(subs):
                subs[sub_index].update(patch)


def _process_type1_inner(index: int, source_url: str, download_index_url: str,
                          dl_html: str, cfg: dict) -> bool:
    """Type 1 (single album): WORKER_API → direct CDN → image fallback → manual."""
    dest_dir = cfg.get("downloadPath", "").strip()
    if not dest_dir:
        _update_item(index, status="error", message="downloadPath not configured")
        return False

    parts = max(1, int(cfg.get("downloadParts", _DEFAULT_PARTS)))
    t2_cfg = _extract_type2_config(dl_html)
    direct_link = _extract_direct_link(dl_html, download_index_url)

    raw_name = (t2_cfg.get("file_name")
                or (t2_cfg.get("file_key", "").split("/")[-1] if t2_cfg.get("file_key") else "")
                or _filename_from_link(direct_link))
    filename  = _sanitize_filename(raw_name)
    final_path = os.path.join(dest_dir, filename)

    def _report(done: int, total: int, speed: float) -> None:
        pct = int(done * 100 / total) if total > 0 else 0
        _update_item(index, bytes_downloaded=done, bytes_total=total,
                     speed_bps=speed, progress_percent=pct)

    downloaded = False

    # Skip if a valid file already exists.
    if filename and os.path.isfile(final_path) and os.path.getsize(final_path) > 1024:
        _update_item(index, status="skipped", filename=filename, final_path=final_path,
                     message="File already exists", progress_percent=100)
        return True

    # Candidate 1: WORKER_API
    if not downloaded and t2_cfg.get("worker_api") and t2_cfg.get("file_key"):
        _update_item(index, status="calling_worker_api",
                     message=f"Getting download link for {filename}", progress_percent=0)
        wapi_url = None
        wapi_err: Optional[Exception] = None
        try:
            wapi_url = _call_worker_api(
                t2_cfg["worker_api"], t2_cfg["file_key"], filename, download_index_url)
        except Exception as e:
            wapi_err = e
        if wapi_url:
            _update_item(index, status="downloading",
                         download_url=wapi_url, filename=filename, final_path=final_path,
                         bytes_downloaded=0, bytes_total=0, speed_bps=0.0, progress_percent=0)
            dl_err: Optional[Exception] = None
            try:
                _stream_download(wapi_url, final_path, referer=download_index_url,
                                 on_progress=_report, parts=parts)
                downloaded = True
            except QuotaExceededError:
                raise
            except Exception as e:
                dl_err = e
                _cleanup_partial(final_path)
            _log(source_url, "type1", "worker_api",
                 "ok" if downloaded else "failed", filename, dl_err)
        else:
            _log(source_url, "type1", "worker_api", "failed", filename, wapi_err)

    # Candidate 2: direct CDN link (class=ads)
    if not downloaded and direct_link:
        _update_item(index, status="downloading",
                     message="Retrying with direct CDN link",
                     download_url=direct_link, filename=filename, final_path=final_path,
                     bytes_downloaded=0, bytes_total=0, speed_bps=0.0, progress_percent=0)
        cdn_err: Optional[Exception] = None
        try:
            _stream_download(direct_link, final_path, referer=download_index_url,
                             on_progress=_report, parts=parts)
            downloaded = True
        except QuotaExceededError:
            raise
        except Exception as e:
            cdn_err = e
            _cleanup_partial(final_path)
        _log(source_url, "type1", "direct_cdn",
             "ok" if downloaded else "failed", filename, cdn_err)

    if downloaded:
        return True

    # Candidate 3: image-by-image from reader/slide page
    data_key = t2_cfg.get("file_key", "")
    img_ok, img_reason = _download_images_fallback(index, None, source_url, data_key,
                                                    filename, dest_dir, download_index_url)
    _log(source_url, "type1", "images", "ok" if img_ok else "failed", filename,
         Exception(img_reason) if img_reason else None)
    if img_ok:
        return True

    _update_item(index, status="manual_required",
                 message=f"All download methods failed — open {download_index_url} to download manually")
    _log(source_url, "type1", "all_failed", "manual", filename)
    return False


def _process_type2_inner(index: int, source_url: str, download_index_url: str,
                          dl_html: str, cfg: dict) -> bool:
    """WORKER_API flow: extract CONFIG, create folder, download all files."""
    dest_dir = cfg.get("downloadPath", "").strip()
    if not dest_dir:
        _update_item(index, status="error", message="downloadPath not configured")
        return False

    parts = max(1, int(cfg.get("downloadParts", _DEFAULT_PARTS)))
    t2_cfg = _extract_type2_config(dl_html)
    if not t2_cfg.get("worker_api"):
        _update_item(index, status="error",
                     message="Type 2: WORKER_API not found on download page")
        return False

    title = _extract_h1_title(dl_html)
    folder_name = _sanitize_dirname(title) if title else "download"
    folder_path = os.path.join(dest_dir, folder_name)

    if _is_multi_chapter(dl_html):
        ch_attrs = _get_ch_wrap_attrs(dl_html)
        _update_item(index, status="fetching_chapters",
                     message=f'Loading chapters (total={ch_attrs.get("total", "?")})')
        base_url = f"{urlparse(source_url).scheme}://{urlparse(source_url).netloc}"
        chapters = _get_all_chapters(dl_html, base_url, ch_attrs)
        if not chapters:
            _update_item(index, status="error", message="Type 2: no chapters found")
            return False
        files = [
            {"key": ch.get("key", ""),
             "name": _filename_from_link(ch.get("dl2", "")) if ch.get("dl2") else
                     _sanitize_filename((ch.get("name") or ch.get("key", "").split("/")[-1]) + ".zip"),
             "dl2": ch.get("dl2", ""),
             "ch_aid": ch.get("ch_aid", "")}
            for ch in chapters if ch.get("key") or ch.get("dl2")
        ]
    else:
        if not t2_cfg.get("file_key"):
            _update_item(index, status="error",
                         message="Type 2: FILE_KEY empty and no ch-wrap chapters found")
            return False
        raw_name = t2_cfg.get("file_name") or t2_cfg["file_key"].split("/")[-1]
        files = [{"key": t2_cfg["file_key"], "name": _sanitize_filename(raw_name), "dl2": ""}]

    n_total = len(files)
    if n_total == 0:
        _update_item(index, status="error", message="Type 2: no files to download")
        return False

    multi = n_total > 1
    if multi:
        _update_item(index,
                     status="downloading",
                     filename=folder_name,
                     bytes_downloaded=0, bytes_total=0,
                     speed_bps=0.0, progress_percent=0,
                     sub_items=[
                         {"filename": f["name"], "status": "pending",
                          "bytes_downloaded": 0, "bytes_total": 0,
                          "speed_bps": 0.0, "progress_percent": 0, "message": ""}
                         for f in files
                     ])

    for i_file, f in enumerate(files):
        dl2 = f.get("dl2", "")
        data_key = f.get("key", "")
        final_path = os.path.join(folder_path, f["name"])

        # Resolve protocol-relative dl2 URL once.
        dl2_url: Optional[str] = None
        if dl2:
            if dl2.startswith("//"):
                dl2_url = f"{urlparse(download_index_url).scheme}:{dl2}"
            else:
                dl2_url = dl2

        def _report(done: int, total: int, speed: float,
                    _i: int = i_file, _multi: bool = multi) -> None:
            pct = int(done * 100 / total) if total > 0 else 0
            if _multi:
                _update_subitem(index, _i, bytes_downloaded=done, bytes_total=total,
                                speed_bps=speed, progress_percent=pct)
                with _lock:
                    item = _job_status["items"][index]
                    subs = item.get("sub_items", [])
                    t_done = sum(s["bytes_downloaded"] for s in subs)
                    t_size = sum(s["bytes_total"] for s in subs)
                    item["bytes_downloaded"] = t_done
                    item["bytes_total"] = t_size
                    item["speed_bps"] = sum(s["speed_bps"] for s in subs)
                    if t_size > 0:
                        item["progress_percent"] = int(t_done * 100 / t_size)
            else:
                _update_item(index, bytes_downloaded=done, bytes_total=total,
                             speed_bps=speed, progress_percent=pct)

        def _set_status(status, msg="", url=""):
            if multi:
                _update_subitem(index, i_file, status=status, message=msg)
            else:
                _update_item(index, status=status, message=msg,
                             filename=f"{folder_name}/{f['name']}",
                             download_url=url, final_path=final_path,
                             bytes_downloaded=0, bytes_total=0,
                             speed_bps=0.0, progress_percent=0)

        downloaded = False

        # Skip if a valid file already exists (avoids re-downloading on quota retry).
        if os.path.isfile(final_path) and os.path.getsize(final_path) > 1024:
            if multi:
                _update_subitem(index, i_file, status="skipped",
                                message="File already exists", progress_percent=100)
            else:
                _update_item(index, status="skipped",
                             filename=f"{folder_name}/{f['name']}",
                             final_path=final_path,
                             message="File already exists", progress_percent=100)
            downloaded = True

        # Skip image fallback folder if it already exists with content.
        if not downloaded:
            base_name = os.path.splitext(f['name'])[0] or f['name']
            img_dir_check = os.path.join(folder_path, _sanitize_dirname(base_name))
            if os.path.isdir(img_dir_check):
                existing_imgs = [fn for fn in os.listdir(img_dir_check)
                                 if os.path.getsize(os.path.join(img_dir_check, fn)) > 0]
                if existing_imgs:
                    if multi:
                        _update_subitem(index, i_file, status="skipped",
                                        message=f"Images already downloaded ({len(existing_imgs)} files)",
                                        progress_percent=100)
                    else:
                        _update_item(index, status="skipped",
                                     filename=f"{folder_name}/{f['name']}",
                                     message=f"Images already downloaded ({len(existing_imgs)} files)",
                                     progress_percent=100)
                    downloaded = True

        # Candidate 1: direct CDN link (ch-dl2)
        if dl2_url:
            if multi:
                _update_subitem(index, i_file, status="downloading",
                                bytes_downloaded=0, bytes_total=0,
                                speed_bps=0.0, progress_percent=0)
            else:
                _update_item(index, status="downloading",
                             filename=f"{folder_name}/{f['name']}",
                             download_url=dl2_url, final_path=final_path,
                             bytes_downloaded=0, bytes_total=0,
                             speed_bps=0.0, progress_percent=0)
            cdn_err: Optional[Exception] = None
            try:
                _stream_download(dl2_url, final_path,
                                 referer=download_index_url, on_progress=_report,
                                 parts=parts)
                downloaded = True
            except QuotaExceededError:
                raise
            except Exception as e:
                cdn_err = e
                _cleanup_partial(final_path)
            _log(source_url, "type2", "direct_cdn",
                 "ok" if downloaded else "failed", f["name"], cdn_err)

        # Candidate 2: WORKER_API fallback
        if not downloaded and t2_cfg.get("worker_api") and data_key:
            if multi:
                _update_subitem(index, i_file, status="calling_worker_api",
                                message="Retrying via WORKER_API")
            else:
                _update_item(index, status="calling_worker_api",
                             message=f"Retrying via WORKER_API for {f['name']}")
            wapi_url = None
            wapi_err: Optional[Exception] = None
            try:
                wapi_url = _call_worker_api(
                    t2_cfg["worker_api"], data_key, f["name"], download_index_url)
            except Exception as e:
                wapi_err = e
            if wapi_url:
                if multi:
                    _update_subitem(index, i_file, status="downloading",
                                    bytes_downloaded=0, bytes_total=0,
                                    speed_bps=0.0, progress_percent=0)
                else:
                    _update_item(index, status="downloading",
                                 download_url=wapi_url, filename=f"{folder_name}/{f['name']}",
                                 final_path=final_path,
                                 bytes_downloaded=0, bytes_total=0,
                                 speed_bps=0.0, progress_percent=0)
                wdl_err: Optional[Exception] = None
                try:
                    _stream_download(wapi_url, final_path,
                                     referer=download_index_url, on_progress=_report,
                                     parts=parts)
                    downloaded = True
                except QuotaExceededError:
                    raise
                except Exception as e:
                    wdl_err = e
                    _cleanup_partial(final_path)
                _log(source_url, "type2", "worker_api",
                     "ok" if downloaded else "failed", f["name"], wdl_err)
            else:
                _log(source_url, "type2", "worker_api", "failed", f["name"], wapi_err)

        if not downloaded:
            # Candidate 3: image-by-image from reader/slide page
            img_ok, img_reason = _download_images_fallback(
                index, i_file if multi else None,
                source_url, data_key, f["name"],
                folder_path, download_index_url,
                ch_aid=f.get('ch_aid', ''))
            _log(source_url, "type2", "images",
                 "ok" if img_ok else "failed", f["name"],
                 Exception(img_reason) if img_reason else None)
            if img_ok:
                downloaded = True
            else:
                msg = f"All methods failed — open {download_index_url} to download manually"
                _log(source_url, "type2", "all_failed", "manual", f["name"])
                if multi:
                    _update_subitem(index, i_file, status="manual_required", message=msg)
                else:
                    _update_item(index, status="manual_required", message=msg)
                if not multi:
                    return False
                continue

        if multi:
            _update_subitem(index, i_file, status="done", progress_percent=100)

    if multi:
        with _lock:
            subs = _job_status["items"][index].get("sub_items", [])
            n_ok  = sum(1 for s in subs if s["status"] == "done")
            n_err = sum(1 for s in subs if s["status"] in ("error", "manual_required"))
        if n_err == 0:
            _update_item(index, progress_percent=100,
                         message=f'Downloaded {n_ok} file(s) to "{folder_name}"')
        else:
            _update_item(index, status="error", progress_percent=100,
                         message=f'{n_ok}/{n_total} downloaded to "{folder_name}", {n_err} need attention')
        return n_err == 0
    else:
        _update_item(index, progress_percent=100)
        return True


def _process_one(index: int, source_url: str, cfg: dict) -> None:
    _update_item(index, status="fetching_source")
    try:
        source_html = _http_get(source_url)
    except Exception as e:
        _update_item(index, status="error", message=f"fetch source failed: {e}")
        return

    download_index_url, is_type1 = _resolve_download_index_url(source_url, source_html)
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

    if is_type1:
        success = _process_type1_inner(index, source_url, download_index_url, dl_html, cfg)
    else:
        success = _process_type2_inner(index, source_url, download_index_url, dl_html, cfg)

    if not success:
        return

    try:
        _close_source_tab(source_url)
    except Exception as e:
        _update_item(index, status="done",
                     message=f"downloaded, but close-tab failed: {e}")
        return

    _update_item(index, status="done", message="downloaded and tab closed")


def start_job(source_items: List[Dict[str, str]]) -> Dict[str, Any]:
    """Kick off a background download job.

    source_items: list of {"url": ..., "dl_type": "type1"/"type2"/"unknown"}.
    Type 1 items are processed first.
    """
    settings = settings_manager.load_settings()
    cfg = settings.get("downloadSSMH", {}) or {}
    if not cfg.get("sourceDomains") or not cfg.get("downloadPath", "").strip():
        return {"error": "downloadSSMH sourceDomains and downloadPath must be configured"}

    def _type_order(item: Dict[str, str]) -> int:
        t = item.get("dl_type", "unknown")
        return 0 if t == "type1" else (1 if t == "type2" else 2)

    ordered = sorted(source_items, key=_type_order)

    with _lock:
        if _job_status["running"]:
            return {"error": "another job is already running"}
        _job_status.update({
            "running": True,
            "total": len(ordered),
            "done": 0,
            "items": [{"url": it["url"], "status": "pending", "message": "",
                       "filename": "", "download_url": "", "final_path": "",
                       "bytes_downloaded": 0, "bytes_total": 0,
                       "speed_bps": 0.0, "progress_percent": 0,
                       "dl_type": it.get("dl_type", "unknown"),
                       "sub_items": []}
                      for it in ordered],
        })

    def _run():
        try:
            for i, it in enumerate(ordered):
                try:
                    _process_one(i, it["url"], cfg)
                except QuotaExceededError as qe:
                    _update_item(i, status="quota_exceeded", message=str(qe))
                    with _lock:
                        for j in range(i + 1, len(ordered)):
                            if _job_status["items"][j]["status"] == "pending":
                                _job_status["items"][j]["status"] = "quota_exceeded"
                                _job_status["items"][j]["message"] = "Skipped — quota exceeded"
                        _job_status["done"] = len(ordered)
                    break
                with _lock:
                    _job_status["done"] = i + 1
        finally:
            with _lock:
                _job_status["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "job started", "total": len(ordered)}
