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
from typing import BinaryIO, Callable, Iterator

import requests

from .base import CloudStorage, FileMeta

API = "https://pan.baidu.com/rest/2.0/xpan"
PCS = "https://d.pcs.baidu.com/rest/2.0/pcs"
HEADERS = {"User-Agent": "pan.baidu.com"}
# Super-VIP accounts allow 32MB chunks; keep a safe default that works for all.
CHUNK_SIZE = 4 * 1024 * 1024


class BaiduCloudStorage(CloudStorage):
    def __init__(self, token_provider: Callable[[], str], root_prefix: str = ""):
        # token_provider returns a currently-valid access token on each call,
        # so long-running syncs pick up refreshed tokens automatically.
        self._token_provider = token_provider
        self.root = (root_prefix or "").rstrip("/")

    # ---- path helpers -------------------------------------------------

    def _full(self, remote_path: str) -> str:
        rel = remote_path.replace("\\", "/").lstrip("/")
        return f"{self.root}/{rel}" if self.root else "/" + rel

    def _strip_root(self, full_path: str) -> str:
        p = full_path.replace("\\", "/")
        if self.root and p.startswith(self.root):
            p = p[len(self.root):]
        return "/" + p.lstrip("/")

    def _request(self, url, method, params=None, data=None, files=None):
        params = dict(params or {})
        params["access_token"] = self._token_provider()
        resp = requests.request(method, url, params=params, headers=HEADERS,
                                data=data, files=files, timeout=360)
        resp.raise_for_status()
        return resp

    def _request_json(self, url, method, params=None, data=None, files=None):
        return self._request(url, method, params, data, files).json()

    # ---- CloudStorage impl --------------------------------------------

    def upload(self, source: BinaryIO, remote_path: str, size: int) -> None:
        path = self._full(remote_path)
        chunks = []
        while True:
            c = source.read(CHUNK_SIZE)
            if not c:
                break
            chunks.append(c)
        if not chunks:
            chunks = [b""]          # allow zero-byte files
        md5s = [hashlib.md5(c).hexdigest() for c in chunks]

        # 1) precreate
        pre = self._request_json(f"{API}/file", "POST",
            params={"method": "precreate"},
            data={"path": path, "size": size, "block_list": json.dumps(md5s),
                  "isdir": "0", "autoinit": "1", "rtype": "3"})
        if "uploadid" not in pre:
            raise RuntimeError(f"precreate failed: {pre}")
        upload_id = pre["uploadid"]

        # 2) superfile2 per chunk
        for i, c in enumerate(chunks):
            self._request(f"{PCS}/superfile2", "POST",
                params={"path": path, "uploadid": upload_id,
                        "method": "upload", "type": "tmpfile", "partseq": i},
                files=[("file", c)])

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

    def list_files(self, remote_prefix: str) -> Iterator[FileMeta]:
        path = self._full(remote_prefix)
        start, limit = 0, 1000
        while True:
            res = self._request_json(f"{API}/multimedia", "GET",
                params={"method": "listall", "path": path, "web": 0,
                        "recursion": 1, "start": start, "limit": limit})
            items = res.get("list", [])
            for it in items:
                if it.get("isdir"):
                    continue
                yield FileMeta(
                    remote_path=self._strip_root(it["path"]),
                    size=int(it.get("size", 0)),
                )
            if len(items) < limit:
                break
            start += limit

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
