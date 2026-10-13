"""
BaiduCloudStorage — real Baidu NetDisk backend implementing CloudStorage.

Ported from the 2023 sync-assistant client (support/bdwp_support.py) and
adapted to the stream-based CloudStorage interface. Encryption is handled
by the caller (action_executor) before upload / after download, so this
layer only moves raw bytes.

Restricted Baidu apps can only read/write under /apps/<app>; the
root_prefix is prepended to every remote_path. list_files() strips it back
off so the index layer sees the same POSIX-relative paths as MockCloudStorage.
"""
import io
import json
import time
import hashlib
import urllib.parse
from typing import BinaryIO, Callable, Iterator, Optional

import requests

from .base import CloudStorage, FileMeta

API = "https://pan.baidu.com/rest/2.0/xpan"
PCS = "https://d.pcs.baidu.com/rest/2.0/pcs"
HEADERS = {"User-Agent": "pan.baidu.com"}
# Super-VIP accounts allow 32MB chunks; keep a safe default that works for all.
CHUNK_SIZE = 4 * 1024 * 1024

# Exponential-backoff delays (seconds) for HTTP 429 / 503 rate-limit responses.
# After all attempts are exhausted, RateLimitError is raised and the queue item
# is marked as ERROR so the user can inspect and retry manually.
RETRY_DELAYS = [30, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360, 30720]


class RateLimitError(RuntimeError):
    """Raised when Baidu API rate-limits us after all retry attempts are exhausted."""


class BaiduCloudStorage(CloudStorage):
    def __init__(
        self,
        token_provider: Callable[[], str],
        root_prefix: str = "",
        on_retry: Optional[Callable[[int, int, int], None]] = None,
    ):
        # token_provider returns a currently-valid access token on each call,
        # so long-running syncs pick up refreshed tokens automatically.
        # on_retry(attempt, delay_seconds, status_code) is called before each sleep.
        self._token_provider = token_provider
        self.root = (root_prefix or "").rstrip("/")
        self._on_retry = on_retry

    # ---- path helpers -------------------------------------------------

    def _full(self, remote_path: str) -> str:
        p = remote_path.replace("\\", "/")
        # If remote_path is already an absolute path that starts with root_prefix,
        # return it as-is to avoid double-prepending the prefix.
        if self.root and p.lstrip("/").startswith(self.root.lstrip("/")):
            return "/" + p.lstrip("/")
        rel = p.lstrip("/")
        return f"{self.root}/{rel}" if self.root else "/" + rel

    def _strip_root(self, full_path: str) -> str:
        p = full_path.replace("\\", "/")
        if self.root and p.startswith(self.root):
            p = p[len(self.root):]
        return "/" + p.lstrip("/")

    def to_listing_key(self, remote_path: str) -> str:
        return self._strip_root(self._full(remote_path)).lstrip("/")

    def _request(self, url, method, params=None, data=None, files=None):
        params = dict(params or {})
        last_exc: Optional[Exception] = None
        for attempt, delay in enumerate(RETRY_DELAYS + [None]):
            params["access_token"] = self._token_provider()
            try:
                resp = requests.request(method, url, params=params, headers=HEADERS,
                                        data=data, files=files, timeout=360)
                resp.raise_for_status()
                return resp
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status in (429, 503) and delay is not None:
                    if self._on_retry:
                        self._on_retry(attempt + 1, delay, status)
                    time.sleep(delay)
                    last_exc = exc
                    continue
                raise
        raise RateLimitError(
            f"Baidu rate-limited after {len(RETRY_DELAYS)} retries"
        ) from last_exc

    def _request_json(self, url, method, params=None, data=None, files=None):
        return self._request(url, method, params, data, files).json()

    # ---- CloudStorage impl --------------------------------------------

    def upload(
        self,
        source: BinaryIO,
        remote_path: str,
        size: int,
        on_chunk_sent: Optional[Callable[[int], None]] = None,
        on_prepare_start: Optional[Callable[[], None]] = None,
        on_prepare_done: Optional[Callable[[], None]] = None,
    ) -> None:
        path = self._full(remote_path)

        # Pass 1: compute per-chunk MD5s without holding all chunks in memory.
        # Baidu precreate needs the full block_list upfront, so we must read
        # the file twice rather than buffering everything at once.
        if on_prepare_start:
            on_prepare_start()
        md5s = []
        chunk_sizes = []
        while True:
            c = source.read(CHUNK_SIZE)
            if not c:
                break
            md5s.append(hashlib.md5(c).hexdigest())
            chunk_sizes.append(len(c))
        if not md5s:
            md5s = [hashlib.md5(b"").hexdigest()]
            chunk_sizes = [0]
        if on_prepare_done:
            on_prepare_done()

        # 1) precreate
        pre = self._request_json(f"{API}/file", "POST",
            params={"method": "precreate"},
            data={"path": path, "size": size, "block_list": json.dumps(md5s),
                  "isdir": "0", "autoinit": "1", "rtype": "3"})
        if "uploadid" not in pre:
            raise RuntimeError(f"precreate failed: {pre}")
        upload_id = pre["uploadid"]

        # Pass 2: seek back to start and upload one chunk at a time (max CHUNK_SIZE in RAM).
        source.seek(0)
        for i, expected_size in enumerate(chunk_sizes):
            c = source.read(CHUNK_SIZE)
            self._request(f"{PCS}/superfile2", "POST",
                params={"path": path, "uploadid": upload_id,
                        "method": "upload", "type": "tmpfile", "partseq": i},
                files=[("file", c)])
            if on_chunk_sent:
                on_chunk_sent(len(c))

        # 3) create (merge)
        res = self._request_json(f"{API}/file", "POST",
            params={"method": "create"},
            data={"path": path, "size": size, "uploadid": upload_id,
                  "block_list": json.dumps(md5s), "rtype": "3", "isdir": "0"})
        if "fs_id" not in res and res.get("errno", 0) != 0:
            raise RuntimeError(f"create failed: {res}")

    def download(self, remote_path: str, target: BinaryIO) -> None:
        path = self._full(remote_path)
        fs_id = self._fs_id_for(path)
        if fs_id is None:
            raise FileNotFoundError(f"remote file not found: {remote_path}")
        meta = self._request_json(f"{API}/multimedia", "GET",
            params={"method": "filemetas", "fsids": json.dumps([fs_id]),
                    "dlink": 1})
        items = meta.get("list", [])
        if not items or "dlink" not in items[0]:
            raise FileNotFoundError(f"no dlink for: {remote_path}")
        dlink = items[0]["dlink"] + "&access_token=" + self._token_provider()
        with requests.get(dlink, headers=HEADERS, stream=True, timeout=360) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    target.write(chunk)

    def delete(self, remote_path: str) -> None:
        path = self._full(remote_path)
        try:
            self._request_json(f"{API}/file", "POST",
                params={"method": "filemanager", "opera": "delete"},
                data={"async": "0", "filelist": json.dumps([path])})
        except requests.HTTPError:
            # Idempotent: treat "already gone" as success (matches MockCloudStorage).
            pass

    def exists(self, remote_path: str) -> bool:
        return self._fs_id_for(self._full(remote_path)) is not None

    # errno=31034 means "hit frequency limit" — Baidu returns HTTP 200 with this
    # code instead of 429 when the listall rate-limit is hit.  Back off and retry.
    _LISTALL_RATE_DELAYS = [30, 60, 120, 300]

    def list_files(self, remote_prefix: str) -> Iterator[FileMeta]:
        """Recursively enumerate all files under remote_prefix.

        Uses the non-recursive ``list`` API at each directory level and recurses
        into subdirectories manually.  This is more reliable than ``listall``
        with recursion=1 which Baidu silently truncates for large directories
        (~18k entries per call) and frequently rate-limits (errno=31034 or
        silent empty response).
        """
        path = self._full(remote_prefix)
        yield from self._walk(path)

    def _walk(self, full_path: str) -> Iterator[FileMeta]:
        """DFS walk via the non-recursive list API."""
        start, limit = 0, 1000
        while True:
            res = self._list_page(full_path, start, limit)
            if res is None:
                return  # directory does not exist (HTTP 400)
            errno = res.get("errno", 0)
            if errno != 0:
                raise RuntimeError(
                    f"Baidu list_files failed: errno={errno} errmsg={res.get('errmsg', '')} path={full_path!r}"
                )
            items = res.get("list", [])
            for it in items:
                if it.get("isdir"):
                    yield from self._walk(it["path"])
                else:
                    yield FileMeta(
                        remote_path=self._strip_root(it["path"]),
                        size=int(it.get("size", 0)),
                    )
            if len(items) < limit:
                break
            start += limit

    def _list_page(self, path: str, start: int, limit: int):
        """Fetch one page of directory listing (non-recursive) with retry."""
        for attempt, delay in enumerate(self._LISTALL_RATE_DELAYS + [None]):
            try:
                res = self._request_json(f"{API}/file", "GET",
                    params={"method": "list", "dir": path, "web": 0,
                            "start": start, "limit": limit})
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 400:
                    return None  # directory does not exist
                raise
            errno = res.get("errno", 0)
            if errno in (31034, 31066) and delay is not None:
                if self._on_retry:
                    self._on_retry(attempt + 1, delay, errno)
                time.sleep(delay)
                continue
            return res
        return res

    # ---- internals ----------------------------------------------------

    def _fs_id_for(self, full_path: str):
        """Return the fs_id of an exact path, or None.

        Uses a direct directory listing (list) of the parent rather than
        search: search is eventually-consistent on Baidu and misses files
        that were just uploaded, whereas list reflects them immediately.
        """
        parent = "/".join(full_path.rstrip("/").split("/")[:-1]) or "/"
        start, limit = 0, 1000
        while True:
            res = self._request_json(f"{API}/file", "GET",
                params={"method": "list", "dir": parent, "start": start,
                        "limit": limit, "web": 0})
            items = res.get("list", [])
            for it in items:
                if it.get("path") == full_path:
                    return it.get("fs_id")
            if len(items) < limit:
                return None
            start += limit
