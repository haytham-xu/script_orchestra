"""Browser Agent — Download JM.

Cloudflare-protected site with a captcha-gated download flow. Direct-from-
backend login is impossible (site uses JS challenges); instead the browser
extension hands the backend the user's live cookies + User-Agent, so the
backend is effectively a proxy of the user's already-authed browser.

Flow per source URL:

    source_url  ─▶ extract album_id from /album/<id>/…
                ─▶ borrow cookies+UA from extension
                ─▶ GET /album_download/<id>  (the download-prep page)
                ─▶ parse HTML to get:
                      * filename base from  <div itemprop="name">…</div>
                      * captcha image URL   <img id="captcha_image" src=…>
                      * form action + hidden fields around  <input name="verification">
                ─▶ GET the captcha image, base64-encode it, stash into job status
                ─▶ [wait for the user to submit the answer through the UI]
                ─▶ POST the verification form with the answer
                ─▶ Response either (a) redirects to the real download URL, or
                   (b) returns a new captcha (wrong answer → retry)
                ─▶ Stream the .zip to downloadPath, name = <itemprop=name> + ext
                ─▶ Ask the extension to close the source tab

Only one JM job runs at a time. State is exposed through get_status()
for the frontend to poll.
"""
from __future__ import annotations

import base64
import os
import re
import threading
import time
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

from . import settings_manager, agent_bridge, captcha_solver

_TIMEOUT = 60
_UA_FALLBACK = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_ALBUM_PATH_RE = re.compile(r"/album/(\d+)(?:/|$)", re.I)
_ALBUM_DOWNLOAD_HREF_RE = re.compile(r"^/album_download/(\d+)$", re.I)
_CAPTCHA_WAIT_TIMEOUT = 300     # if user doesn't answer within N seconds, give up
_MAX_CAPTCHA_ATTEMPTS = 5


# --------------------------------------------------------------------------
# job state

_lock = threading.Lock()
_job_status: Dict[str, Any] = {
    "running": False,
    "total": 0,
    "done": 0,
    "items": [],
    # Waiting-for-captcha handoff: when non-empty, the UI shows the image
    # to the user; the user's answer flows back through submit_captcha_answer.
    "captcha_pending": None,   # {"item_index", "image_base64", "attempts_left"}
}
_captcha_answer_event = threading.Event()
_captcha_answer_value: Dict[str, str] = {"value": ""}


def get_status() -> Dict[str, Any]:
    with _lock:
        return {
            "running": _job_status["running"],
            "total": _job_status["total"],
            "done": _job_status["done"],
            "items": list(_job_status["items"]),
            "captcha_pending": (dict(_job_status["captcha_pending"])
                                if _job_status["captcha_pending"] else None),
        }


def submit_captcha_answer(answer: str) -> Dict[str, Any]:
    """Called by the UI when the user types the captcha result. Wakes the
    worker so it can POST the verification form."""
    with _lock:
        if not _job_status["captcha_pending"]:
            return {"error": "no captcha waiting"}
        _captcha_answer_value["value"] = str(answer).strip()
    _captcha_answer_event.set()
    return {"ok": True}


def _update_item(index: int, **patch) -> None:
    with _lock:
        if 0 <= index < len(_job_status["items"]):
            _job_status["items"][index].update(patch)


def _set_captcha_pending(item_index: int, image_bytes: bytes, attempts_left: int) -> None:
    with _lock:
        _job_status["captcha_pending"] = {
            "item_index": item_index,
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "attempts_left": attempts_left,
        }
    _captcha_answer_event.clear()


def _clear_captcha_pending() -> None:
    with _lock:
        _job_status["captcha_pending"] = None


def _wait_for_captcha_answer() -> Optional[str]:
    if not _captcha_answer_event.wait(timeout=_CAPTCHA_WAIT_TIMEOUT):
        return None
    with _lock:
        value = _captcha_answer_value["value"]
        _captcha_answer_value["value"] = ""
    _captcha_answer_event.clear()
    return value


# --------------------------------------------------------------------------
# cookies from extension

def _get_browser_session(source_domain: str) -> Optional[requests.Session]:
    """Ask the extension for the user's cookies of `source_domain`, build a
    requests.Session that mirrors the browser's authenticated state. Retries
    if the extension is temporarily unresponsive (MV3 SW warmup — a fully
    idle SW takes up to one alarm cycle ≈ 30s to wake)."""
    cookies: List[dict] = []
    ua = ""
    for attempt in range(3):
        result, err = agent_bridge.enqueue_and_wait(
            "get_cookies_for_domain", {"domain": source_domain}, timeout=35.0)
        if err:
            time.sleep(2.0)
            continue
        cookies = (result or {}).get("cookies", [])
        ua = (result or {}).get("userAgent", "") or _UA_FALLBACK
        if cookies:
            break
        time.sleep(2.0)
    if not cookies:
        return None
    ua = ua or _UA_FALLBACK
    s = requests.Session()
    s.headers.update({
        "User-Agent": ua,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    for c in cookies:
        s.cookies.set(c["name"], c["value"],
                      domain=c.get("domain") or source_domain,
                      path=c.get("path") or "/")
    return s


# --------------------------------------------------------------------------
# URL / tab filtering

def _extract_album_id(url: str) -> Optional[str]:
    try:
        m = _ALBUM_PATH_RE.search(urlparse(url).path or "")
        return m.group(1) if m else None
    except Exception:
        return None


def _normalize_host(u: str) -> str:
    try:
        h = (urlparse(u).hostname or "").lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def is_source_tab(url: str, source_domain: str) -> bool:
    if not url or not source_domain:
        return False
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    if _normalize_host(url) != _normalize_host("http://" + source_domain):
        return False
    return _extract_album_id(url) is not None


def scan(tab_urls: List[str], cfg: dict) -> List[Dict[str, Any]]:
    dom = cfg.get("sourceDomain", "")
    out = []
    for u in tab_urls:
        if is_source_tab(u, dom):
            out.append({"url": u, "album_id": _extract_album_id(u) or ""})
    return out


# --------------------------------------------------------------------------
# HTML parsing helpers

def _sanitize_filename(name: str) -> str:
    if not name:
        return "download"
    name = unicodedata.normalize("NFC", name)
    name = name.replace("\\", "_").replace("/", "_")
    for ch in '<>:"|?*':
        name = name.replace(ch, "_")
    name = "".join(c for c in name if ord(c) >= 32)
    name = name.strip(" .")
    return (name or "download")[:200]


def _parse_album_page(html: str) -> Dict[str, Any]:
    """Look for the album's title + the "download" dropdown's chapter list.

    Returns dict with:
      title: <h1 id="book-name"> text (empty if not found)
      chapters: list of {album_id, chapter_num, label}. Empty when the
                album has no chapter dropdown — i.e. single-chapter album.
    """
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.find("h1", id="book-name")
    if title_el is None:
        title_el = soup.find("h1", class_=re.compile(r"book-name"))
    title = (title_el.get_text() or "").strip() if title_el else ""

    chapters: List[Dict[str, Any]] = []
    for ul in soup.find_all("ul", class_=re.compile(r"dropdown-menu")):
        anchors = [a for a in ul.find_all("a", href=True)
                   if _ALBUM_DOWNLOAD_HREF_RE.search(a.get("href", ""))]
        if not anchors:
            continue
        for a in anchors:
            m = _ALBUM_DOWNLOAD_HREF_RE.search(a.get("href") or "")
            if not m:
                continue
            aid = m.group(1)
            text = re.sub(r"\s+", " ", (a.get_text() or "").strip())
            num_match = re.search(r"(\d+)", text)
            chapter_num = int(num_match.group(1)) if num_match else None
            chapters.append({
                "album_id": aid,
                "chapter_num": chapter_num,
                "label": text,
            })
        if chapters:
            break
    return {"title": title, "chapters": chapters}


def _parse_prep_page(html: str, prep_url: str) -> Dict[str, Any]:
    """Extract everything the worker needs from the download-prep page:
      - filename base (from <div itemprop="name">…</div>)
      - captcha image URL
      - the form containing <input name="verification">, with its action +
        all input fields (hidden values preserved).

    Iterates forms rather than starting from the input, so a stray
    verification-named input outside any form doesn't derail us.
    """
    soup = BeautifulSoup(html, "html.parser")

    name_el = soup.find(attrs={"itemprop": "name"})
    filename_base = (name_el.get_text() or "").strip() if name_el else ""

    captcha_img = soup.find("img", id=re.compile(r"^captcha", re.I))
    if not captcha_img:
        captcha_img = soup.find("img", src=re.compile(r"/captcha", re.I))
    captcha_src = captcha_img.get("src") if captcha_img else None
    captcha_url = urljoin(prep_url, captcha_src) if captcha_src else None

    form = None
    verif_name: Optional[str] = None
    for f in soup.find_all("form"):
        vi = f.find("input", attrs={"name": re.compile(r"verif", re.I)})
        if vi:
            form = f
            verif_name = vi.get("name")
            break

    if form is None:
        return {
            "filename_base": filename_base,
            "captcha_url": captcha_url,
            "form_action": "",
            "form_method": "post",
            "form_fields": {},
            "verification_field_name": "verification",
            "has_submit_button": False,
        }

    action_attr = form.get("action")
    # An empty action means "post back to the current URL"; treat it that
    # way instead of returning "".
    form_action = urljoin(prep_url, action_attr) if action_attr else prep_url
    form_method = (form.get("method") or "post").lower()
    form_fields: Dict[str, str] = {}
    for inp in form.find_all("input"):
        n = inp.get("name") or ""
        if not n:
            continue
        v = inp.get("value") or ""
        form_fields[n] = v
    submit = form.find(id="download_submit") or form.find(attrs={"name": "download_submit"})

    return {
        "filename_base": filename_base,
        "captcha_url": captcha_url,
        "form_action": form_action,
        "form_method": form_method,
        "form_fields": form_fields,
        "verification_field_name": verif_name or "verification",
        "has_submit_button": submit is not None,
    }


def _looks_like_login_page(html: str) -> bool:
    """Heuristic for "this response IS the login page (not the target)".

    Just checking for a password input is too aggressive on this site — many
    pages carry an inline login widget in the nav even when the user IS
    logged in. Two better signals:
      * URL path contains /login/ or /signin/ (redirect landed us there)
      * The page has a password input AND no logout link at all
    """
    has_pw = bool(re.search(r'type=["\']password["\']', html, re.I))
    if not has_pw:
        return False
    has_logout = bool(re.search(r'href=["\'][^"\']*/(?:logout|signout)["\']', html, re.I))
    return not has_logout


def _has_logout_marker(html: str) -> bool:
    """Positive signal: an authenticated user typically has a logout link
    somewhere on the page."""
    return bool(re.search(r'href=["\'][^"\']*/(?:logout|signout)["\']', html, re.I))


# --------------------------------------------------------------------------
# per-item worker

def _stream_download(session: requests.Session, url: str, dest_path: str,
                     referer: str, on_progress) -> None:
    tmp = dest_path + ".part"
    with session.get(url, stream=True, timeout=_TIMEOUT,
                     headers={"Referer": referer}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        bytes_done = 0
        window_bytes = 0
        window_started = time.monotonic()
        last_report = 0.0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                bytes_done += len(chunk)
                window_bytes += len(chunk)
                now = time.monotonic()
                if (now - last_report) >= 0.5:
                    elapsed = max(now - window_started, 1e-3)
                    speed = window_bytes / elapsed
                    try:
                        on_progress(bytes_done, total, speed)
                    except Exception:
                        pass
                    last_report = now
                    window_started = now
                    window_bytes = 0
        try:
            on_progress(bytes_done, total or bytes_done, 0.0)
        except Exception:
            pass
    os.replace(tmp, dest_path)


def _close_source_tab(url: str) -> None:
    try:
        r, _ = agent_bridge.enqueue_and_wait("list_tabs", timeout=5.0)
        if not r:
            return
        ids = [t["id"] for t in r.get("tabs", []) if t.get("url") == url]
        if ids:
            agent_bridge.enqueue_and_wait("close_tabs", {"tab_ids": ids}, timeout=5.0)
    except Exception:
        pass


def _process_one(index: int, task: Dict[str, Any], cfg: dict) -> None:
    """A "task" is one downloadable unit — either a whole single-chapter
    album or a single chapter of a multi-chapter album. It carries a
    pre-resolved prep_url plus an optional filename override that lets
    multi-chapter callers name each output like `<title>_ch_N.zip`.
    """
    source_url = task["source_url"]
    prep_url = task["prep_url"]
    filename_override = task.get("filename_base_override")
    close_tab_after = bool(task.get("close_tab_after", True))

    _update_item(index, status="starting")

    _update_item(index, status="fetching_cookies")
    session = _get_browser_session(cfg["sourceDomain"])
    if session is None:
        _update_item(index, status="error",
                     message="extension didn't return cookies — is it installed and enabled?")
        return

    _update_item(index, status="fetching_prep_page")
    try:
        r = session.get(prep_url, timeout=_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        _update_item(index, status="error", message=f"prep page fetch failed: {e}")
        return

    if _looks_like_login_page(r.text):
        _update_item(index, status="error",
                     message="prep page redirected to login — please log in via your browser first")
        return

    parsed = _parse_prep_page(r.text, r.url)
    if not parsed["captcha_url"] or not parsed["form_action"]:
        soup = BeautifulSoup(r.text, "html.parser")
        signals = {
            "captcha_url": bool(parsed["captcha_url"]),
            "verification_input": bool(soup.find("input", attrs={"name": re.compile(r"verification", re.I)})),
            "logout_marker": _has_logout_marker(r.text),
            "password_input": bool(soup.find("input", attrs={"type": re.compile(r"^password$", re.I)})),
            "form_count": len(soup.find_all("form")),
            "final_path": urlparse(r.url).path,
            "body_size": len(r.content),
        }
        _update_item(index, status="error",
                     message=f"couldn't locate captcha image or verification form  {signals}")
        return

    # Filename: chapter-driven override wins over the prep page's itemprop.
    if filename_override:
        filename_base = _sanitize_filename(filename_override)
    else:
        aid_hint = urlparse(prep_url).path.rsplit("/", 1)[-1] or "album"
        filename_base = _sanitize_filename(parsed["filename_base"] or f"album_{aid_hint}")
    _update_item(index, filename=filename_base, status="captcha_needed")

    attempts_left = _MAX_CAPTCHA_ATTEMPTS
    final_download_url: Optional[str] = None
    auto_tried = False

    while attempts_left > 0:
        # 1) Grab the current captcha image with the session cookies.
        try:
            img_resp = session.get(parsed["captcha_url"], timeout=_TIMEOUT,
                                   headers={"Referer": r.url})
            img_resp.raise_for_status()
        except Exception as e:
            _update_item(index, status="error",
                         message=f"captcha image fetch failed: {e}")
            return

        # 2) On the FIRST attempt, try auto-solve. If it's wrong the server
        # will hand back a new captcha and we'll fall through to human
        # input for the retry.
        auto_answer, per_glyph = (None, [])
        if not auto_tried:
            auto_answer, per_glyph = captcha_solver.solve(img_resp.content)
            auto_tried = True

        if auto_answer is not None:
            answer = str(auto_answer)
            glyph_summary = " ".join(f"{c}({s:.2f})" for c, s in per_glyph)
            _update_item(index, status="captcha_auto",
                         message=f"auto-solved: {answer}  [{glyph_summary}]")
        else:
            _set_captcha_pending(index, img_resp.content, attempts_left)
            _update_item(index, status="captcha_needed")
            answer = _wait_for_captcha_answer()
            _clear_captcha_pending()
            if answer is None:
                _update_item(index, status="error",
                             message="captcha wait timed out — user didn't answer")
                return
            # Stash raw image + answer for later manual labeling so the
            # template set can grow over time.
            try:
                captcha_solver.stash_training_sample(img_resp.content, answer)
            except Exception:
                pass

        # 3) POST the verification form.
        payload = dict(parsed["form_fields"])
        payload[parsed["verification_field_name"]] = answer
        payload["download_submit"] = payload.get("download_submit") or "download"
        _update_item(index, status="submitting_captcha")
        try:
            if parsed["form_method"] == "post":
                resp = session.post(parsed["form_action"], data=payload,
                                    timeout=_TIMEOUT, allow_redirects=False,
                                    headers={"Referer": r.url})
            else:
                resp = session.get(parsed["form_action"], params=payload,
                                   timeout=_TIMEOUT, allow_redirects=False,
                                   headers={"Referer": r.url})
        except Exception as e:
            _update_item(index, status="error", message=f"submit failed: {e}")
            return
        # Log a compact summary of the submit response so we can diagnose
        # weird server behaviors (JS redirects, HTML with embedded links,
        # unexpected status codes).
        print(
            f"[download_jm] submit response  status={resp.status_code}  "
            f"ct={resp.headers.get('Content-Type', '')!r}  "
            f"location={resp.headers.get('Location', '')!r}  "
            f"body_size={len(resp.content)}",
            flush=True,
        )

        # 4) If the response is a redirect (302) with a URL that looks like a
        # file/binary target, that's our download.
        loc = resp.headers.get("Location") or ""
        if resp.status_code in (301, 302, 303, 307, 308) and loc:
            final_download_url = urljoin(resp.url or prep_url, loc)
            break
        # Alternatively the server may stream the file directly here.
        ct = (resp.headers.get("Content-Type") or "").lower()
        if resp.status_code == 200 and ("html" not in ct):
            # Server streamed the file back. Save straight from this response.
            # Fall through to a dedicated download branch.
            final_download_url = None
            _update_item(index, status="downloading")
            filename = filename_base + _ext_from_response(resp)
            dest_path = os.path.join(cfg["downloadPath"], filename)

            def _report(done: int, total: int, speed: float) -> None:
                pct = int(done * 100 / total) if total > 0 else 0
                _update_item(index,
                             bytes_downloaded=done, bytes_total=total,
                             speed_bps=speed, progress_percent=pct,
                             final_path=dest_path)

            tmp = dest_path + ".part"
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            try:
                bytes_done = 0
                total = int(resp.headers.get("Content-Length") or 0)
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            f.write(chunk)
                            bytes_done += len(chunk)
                            _report(bytes_done, total, 0.0)
                os.replace(tmp, dest_path)
            except Exception as e:
                _update_item(index, status="error", message=f"download failed: {e}")
                return
            if close_tab_after:
                _close_source_tab(source_url)
                _update_item(index, status="done", message="downloaded and tab closed")
            else:
                _update_item(index, status="done",
                             message="downloaded (tab kept open — more chapters queued)")
            return

        # 5) Otherwise the response is HTML — likely the same page re-rendered
        # with a new captcha (wrong answer). Re-parse and retry.
        if "html" in ct:
            new_parsed = _parse_prep_page(resp.text, resp.url or prep_url)
            if new_parsed["captcha_url"]:
                parsed = new_parsed
                attempts_left -= 1
                _update_item(index, status="captcha_needed",
                             message=f"captcha wrong, retrying (attempts left: {attempts_left})")
                continue
        # Unclear response, bail.
        _update_item(index, status="error",
                     message=f"unexpected submit response  status={resp.status_code}  ct={ct}")
        return

    if not final_download_url:
        _update_item(index, status="error", message="captcha attempts exhausted")
        return

    # Follow-through download: we got a redirect URL after solving.
    _update_item(index, status="downloading")
    ext = _ext_from_url(final_download_url) or ".zip"
    filename = filename_base + ext
    dest_path = os.path.join(cfg["downloadPath"], filename)

    def _report(done: int, total: int, speed: float) -> None:
        pct = int(done * 100 / total) if total > 0 else 0
        _update_item(index, bytes_downloaded=done, bytes_total=total,
                     speed_bps=speed, progress_percent=pct,
                     final_path=dest_path)

    try:
        _stream_download(session, final_download_url, dest_path,
                         referer=r.url, on_progress=_report)
    except Exception as e:
        _update_item(index, status="error", message=f"download failed: {e}")
        return

    if close_tab_after:
        _close_source_tab(source_url)
        _update_item(index, status="done", message="downloaded and tab closed")
    else:
        _update_item(index, status="done",
                     message="downloaded (tab kept open — more chapters queued)")


def _ext_from_url(url: str) -> str:
    try:
        p = urlparse(url).path
        ext = os.path.splitext(p)[1]
        return ext if len(ext) <= 6 else ""
    except Exception:
        return ""


def _ext_from_response(resp: requests.Response) -> str:
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?["]?([^";]+)', cd, re.I)
    if m:
        ext = os.path.splitext(m.group(1))[1]
        if 0 < len(ext) <= 6:
            return ext
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "zip" in ct:
        return ".zip"
    if "pdf" in ct:
        return ".pdf"
    return ""


# --------------------------------------------------------------------------
# public entry points

def check_authenticated() -> Dict[str, Any]:
    """Fast check whether the browser is currently logged in to the
    configured source domain. Returns a dict with structural signals."""
    cfg = settings_manager.load_settings().get("downloadJM", {}) or {}
    if not cfg.get("sourceDomain"):
        return {"error": "downloadJM.sourceDomain not configured"}
    session = _get_browser_session(cfg["sourceDomain"])
    if session is None:
        return {"error": "extension didn't return cookies"}
    scheme = "https"
    try:
        r = session.get(f"{scheme}://{cfg['sourceDomain']}/",
                        timeout=_TIMEOUT, allow_redirects=True)
    except Exception as e:
        return {"error": f"probe request failed: {e}"}
    has_logout = _has_logout_marker(r.text) if r.status_code == 200 else False
    return {
        "cookie_count": len(session.cookies),
        "cookie_names": sorted({c.name for c in session.cookies}),
        "status": r.status_code,
        "final_path": urlparse(r.url).path,
        "has_logout_marker": has_logout,
        # We only report "still looks like login" when both the password
        # input is present AND no logout link is present anywhere.
        "still_looks_like_login": (_looks_like_login_page(r.text)
                                   if r.status_code == 200 else None),
    }


def _expand_source_urls(source_urls: List[str], source_domain: str) -> List[Dict[str, Any]]:
    """For each source album URL, either produce one task (single-chapter)
    or N tasks (multi-chapter dropdown expanded). Each task carries its own
    prep_url and optional filename override so `_process_one` doesn't need
    to look back at the album page."""
    tasks: List[Dict[str, Any]] = []
    session = _get_browser_session(source_domain)
    for src in source_urls:
        aid = _extract_album_id(src)
        if not aid:
            # Preserve as a single task; _process_one will error out.
            tasks.append({"source_url": src, "prep_url": "", "chapter_label": "",
                          "filename_base_override": None, "close_tab_after": True})
            continue
        scheme = urlparse(src).scheme or "https"
        # Try to fetch the album page and detect chapters. If we can't, fall
        # back to the single-chapter default.
        chapters: List[Dict[str, Any]] = []
        title = ""
        if session is not None:
            try:
                r = session.get(src, timeout=_TIMEOUT, allow_redirects=True)
                if r.ok:
                    info = _parse_album_page(r.text)
                    title = info["title"]
                    chapters = info["chapters"]
            except Exception:
                pass
        if not chapters:
            tasks.append({
                "source_url": src,
                "prep_url": f"{scheme}://{source_domain}/album_download/{aid}",
                "chapter_label": "",
                "filename_base_override": None,
                "close_tab_after": True,
            })
            continue
        title_clean = _sanitize_filename(title) if title else f"album_{aid}"
        for i, chap in enumerate(chapters):
            n = chap["chapter_num"]
            suffix = f"ch_{n}" if n is not None else chap["album_id"]
            fname = f"{title_clean}_{suffix}"
            tasks.append({
                "source_url": src,
                "prep_url": f"{scheme}://{source_domain}/album_download/{chap['album_id']}",
                "chapter_label": chap["label"] or suffix,
                "filename_base_override": fname,
                "close_tab_after": (i == len(chapters) - 1),
            })
    return tasks


def start_job(source_urls: List[str]) -> Dict[str, Any]:
    settings = settings_manager.load_settings()
    cfg = settings.get("downloadJM", {}) or {}
    if not cfg.get("sourceDomain") or not cfg.get("downloadPath"):
        return {"error": "downloadJM sourceDomain and downloadPath must be configured"}

    tasks = _expand_source_urls(source_urls, cfg["sourceDomain"])
    if not tasks:
        return {"error": "no downloadable tasks after expansion"}

    with _lock:
        if _job_status["running"]:
            return {"error": "another JM job is already running"}
        _job_status.update({
            "running": True,
            "total": len(tasks),
            "done": 0,
            "items": [{"url": t["source_url"], "status": "pending", "message": "",
                       "filename": "", "final_path": "",
                       "chapter_label": t.get("chapter_label", ""),
                       "bytes_downloaded": 0, "bytes_total": 0,
                       "speed_bps": 0.0, "progress_percent": 0}
                      for t in tasks],
            "captcha_pending": None,
        })

    def _run():
        try:
            for i, task in enumerate(tasks):
                try:
                    _process_one(i, task, cfg)
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    _update_item(i, status="error",
                                 message=f"unhandled exception: {e}\n{tb[-1000:]}")
                    print(f"[download_jm] item {i} crashed:\n{tb}", flush=True)
                with _lock:
                    _job_status["done"] = i + 1
        finally:
            with _lock:
                _job_status["running"] = False
                _job_status["captcha_pending"] = None

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "job started", "total": len(tasks),
            "expanded_from": len(source_urls)}
