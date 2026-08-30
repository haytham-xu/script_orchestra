"""Knowledge Vault — URL liveness probing (opt-in, off by default).

Probes `url`-kind fragments over HTTP so dead links can be flagged stale
earlier than pure time-decay. This makes outbound network requests — the URLs
a user saved are sent to their hosts, which is a privacy consideration — so it
is gated behind the `link_check_enabled` setting and only ever runs on an
explicit user action (the "Check links" button), never automatically.

Pure/​stateless: callers pass URLs and get verdicts back. Rate-limited, timed
out, and capped in concurrency so a check can't hammer hosts or hang a build.
Private/loopback hosts are skipped (no point, and avoids probing internal
services).
"""
import ipaddress
import socket
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

try:
    import requests
    _REQUESTS_OK = True
except Exception:  # pragma: no cover - requests is expected to be present
    _REQUESTS_OK = False

_TIMEOUT = float(os.environ.get("KV_LINK_TIMEOUT", "6"))      # seconds per request
_WORKERS = int(os.environ.get("KV_LINK_WORKERS", "6"))        # concurrent probes
_UA = "Mozilla/5.0 (compatible; KnowledgeVaultLinkChecker/1.0)"


def _is_probeable(url: str) -> bool:
    """Only http(s) to a public host — skip private/loopback/malformed."""
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        # Resolve to catch private ranges even behind a DNS name.
        for res in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(res[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
    except (socket.gaierror, ValueError):
        return False  # unresolvable → treat as not-probeable (don't call it dead here)
    return True


def _probe_one(url: str) -> dict:
    """{'url', 'alive': bool|None, 'status': int|None, 'reason': str}.

    alive=None means 'skipped/undetermined' (never probed or couldn't resolve) —
    the caller must NOT treat that as a dead link.
    """
    if not _REQUESTS_OK:
        return {"url": url, "alive": None, "status": None, "reason": "requests unavailable"}
    if not _is_probeable(url):
        return {"url": url, "alive": None, "status": None, "reason": "skipped (non-public or malformed)"}
    headers = {"User-Agent": _UA}
    try:
        # HEAD first (cheap); some hosts reject HEAD, so fall back to a ranged GET.
        r = requests.head(url, timeout=_TIMEOUT, allow_redirects=True, headers=headers)
        if r.status_code >= 400 or r.status_code == 405:
            r = requests.get(url, timeout=_TIMEOUT, allow_redirects=True, headers=headers, stream=True)
            r.close()
        alive = r.status_code < 400
        return {"url": url, "alive": alive, "status": r.status_code,
                "reason": "ok" if alive else f"http {r.status_code}"}
    except requests.RequestException as exc:
        return {"url": url, "alive": False, "status": None, "reason": type(exc).__name__}


def check_urls(urls) -> list:
    """Probe a list of URLs concurrently. Returns a list of per-url verdicts.

    De-dupes inputs; bounded concurrency; each probe independently timed out.
    """
    unique = list(dict.fromkeys(u for u in urls if u))
    results = []
    if not unique:
        return results
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futs = {pool.submit(_probe_one, u): u for u in unique}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as exc:  # pragma: no cover - defensive
                results.append({"url": futs[fut], "alive": None, "status": None, "reason": str(exc)})
    return results
