"""Browser Agent tab archive service.

Implements live/archive synchronization, safe archival, and batch restore.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib import request as url_request
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import agent_bridge
from . import settings_manager
from . import tab_archive_repository as archive_repo

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}

_INTERNAL_URL_PREFIXES = (
    "chrome://",
    "chrome-extension://",
    "edge://",
    "about:",
    "devtools://",
    "view-source:",
)

_embed_model = None
_embed_model_name: Optional[str] = None
logger = logging.getLogger(__name__)


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(value[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class TabArchiveService:
    def __init__(self) -> None:
        self._health_lock = threading.Lock()
        self._health_jobs: Dict[str, Dict[str, Any]] = {}
        self._health_cancel_events: Dict[str, threading.Event] = {}
        self._health_current_job_id: Optional[str] = None

    @staticmethod
    def _extension_capability_error(command: str) -> Optional[str]:
        status = agent_bridge.extension_status()
        if not status.get("last_seen_at"):
            return None
        capabilities = status.get("capabilities") or []
        if command in capabilities:
            return None
        version = status.get("extension_version") or "legacy"
        return (
            f"extension_outdated: command {command} is unsupported by Browser Agent "
            f"extension {version}; reload the unpacked extension in chrome://extensions"
        )

    def _tab_archive_settings(self) -> Dict[str, Any]:
        settings = settings_manager.load_settings() or {}
        tab_archive = settings.get("tabArchive") or {}
        if not isinstance(tab_archive, dict):
            return {}
        return tab_archive

    def _heat_thresholds(self) -> Dict[str, float]:
        cfg = self._tab_archive_settings().get("heatThresholds") or {}
        try:
            high = float(cfg.get("high", 4.0))
            medium = float(cfg.get("medium", 2.0))
            low = float(cfg.get("low", 0.8))
        except (TypeError, ValueError):
            return {"high": 4.0, "medium": 2.0, "low": 0.8}
        if not (high > medium > low >= 0):
            return {"high": 4.0, "medium": 2.0, "low": 0.8}
        return {"high": high, "medium": medium, "low": low}

    def _health_check_timeout_sec(self) -> int:
        raw = self._tab_archive_settings().get("healthCheckTimeoutSec", 4)
        try:
            timeout = int(raw)
        except (TypeError, ValueError):
            timeout = 4
        return max(1, min(15, timeout))

    def _semantic_model_name(self) -> str:
        value = self._tab_archive_settings().get("embedModel", "")
        return str(value or "").strip()

    def _semantic_top_k(self) -> int:
        raw = self._tab_archive_settings().get("semanticTopK", 120)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 120
        return max(10, min(500, value))

    def _semantic_text(self, record: Dict[str, Any]) -> str:
        normalized_url = str(record.get("normalized_url") or "")
        path_tokens = ""
        if normalized_url:
            try:
                parsed = urlsplit(normalized_url)
                parts = [p for p in parsed.path.split("/") if p]
                path_tokens = " ".join(parts)
            except ValueError:
                path_tokens = ""

        return "\n".join(
            [
                str(record.get("title") or ""),
                str(record.get("comment") or ""),
                str(record.get("domain") or ""),
                path_tokens,
                " ".join(record.get("labels") or []),
            ]
        ).strip()

    def _semantic_content_hash(self, record: Dict[str, Any]) -> str:
        text = self._semantic_text(record)
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    def _get_embed_model(self):
        global _embed_model, _embed_model_name
        want = self._semantic_model_name()
        if not want:
            raise RuntimeError("No tabArchive.embedModel configured")
        if _embed_model is None or _embed_model_name != want:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            from sentence_transformers import SentenceTransformer

            _embed_model = SentenceTransformer(want)
            _embed_model_name = want
        return _embed_model, want

    def _embed_many(self, texts: List[str]) -> List[List[float]]:
        model, _ = self._get_embed_model()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in vec] for vec in vectors]

    def _embed_one(self, text: str) -> List[float]:
        model, _ = self._get_embed_model()
        vec = model.encode(text or "", normalize_embeddings=True)
        return [float(x) for x in vec]

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        n = min(len(a), len(b))
        return sum(a[i] * b[i] for i in range(n))

    @staticmethod
    def _is_active_health_status(status: str) -> bool:
        return status in ("queued", "running", "cancelling")

    def _health_job_snapshot(self, job: Dict[str, Any]) -> Dict[str, Any]:
        total = int(job.get("total") or 0)
        processed = int(job.get("processed") or 0)
        progress = 0.0
        if total > 0:
            progress = round(min(100.0, max(0.0, (processed * 100.0) / total)), 2)
        return {
            "job_id": str(job.get("job_id") or ""),
            "status": str(job.get("status") or "unknown"),
            "created_at": str(job.get("created_at") or ""),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "updated_at": str(job.get("updated_at") or ""),
            "total": total,
            "processed": processed,
            "healthy": int(job.get("healthy") or 0),
            "unavailable": int(job.get("unavailable") or 0),
            "unknown": int(job.get("unknown") or 0),
            "batch_size": int(job.get("batch_size") or 0),
            "cancel_requested": bool(job.get("cancel_requested")),
            "last_error": str(job.get("last_error") or ""),
            "progress_percent": progress,
        }

    def get_health_check_status(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        with self._health_lock:
            target_id = (job_id or "").strip() or self._health_current_job_id
            if not target_id:
                return {"exists": False, "job": None}
            job = self._health_jobs.get(target_id)
            if not job:
                return {"exists": False, "job": None}
            return {"exists": True, "job": self._health_job_snapshot(job)}

    def _update_health_job(self, job_id: str, patch: Dict[str, Any]) -> None:
        with self._health_lock:
            job = self._health_jobs.get(job_id)
            if not job:
                return
            job.update(patch)
            job["updated_at"] = _now_text()

    def cancel_health_check(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        with self._health_lock:
            target_id = (job_id or "").strip() or self._health_current_job_id
            if not target_id:
                return {"exists": False, "job": None}

            job = self._health_jobs.get(target_id)
            if not job:
                return {"exists": False, "job": None}

            cancel_event = self._health_cancel_events.get(target_id)
            if cancel_event:
                cancel_event.set()
            if self._is_active_health_status(str(job.get("status") or "")):
                job["status"] = "cancelling"
            job["cancel_requested"] = True
            job["updated_at"] = _now_text()
            return {"exists": True, "job": self._health_job_snapshot(job)}

    def start_health_check(
        self,
        *,
        record_ids: Optional[List[int]] = None,
        limit: int = 200,
        batch_size: int = 20,
    ) -> Dict[str, Any]:
        with self._health_lock:
            if self._health_current_job_id:
                current = self._health_jobs.get(self._health_current_job_id)
                if current and self._is_active_health_status(str(current.get("status") or "")):
                    running_id = str(current.get("job_id") or self._health_current_job_id)
                    raise RuntimeError(f"health_check_job_already_running:{running_id}")

        if record_ids is not None:
            records = archive_repo.get_records_by_ids([int(x) for x in record_ids])
        else:
            records = archive_repo.list_records_for_health(limit=limit)

        logger.info(
            "tab_archive.health_check.start requested=%s resolved=%s limit=%s batch_size=%s",
            len(record_ids or []),
            len(records),
            limit,
            batch_size,
        )

        job_id = uuid.uuid4().hex
        now = _now_text()
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "updated_at": now,
            "total": len(records),
            "processed": 0,
            "healthy": 0,
            "unavailable": 0,
            "unknown": 0,
            "batch_size": max(1, min(100, int(batch_size))),
            "cancel_requested": False,
            "last_error": "",
        }
        cancel_event = threading.Event()

        with self._health_lock:
            # Records are loaded outside the lock, so another request may have
            # registered a job after the initial fast-path check. Recheck while
            # atomically reserving the single active-job slot.
            if self._health_current_job_id:
                current = self._health_jobs.get(self._health_current_job_id)
                if current and self._is_active_health_status(str(current.get("status") or "")):
                    running_id = str(current.get("job_id") or self._health_current_job_id)
                    raise RuntimeError(f"health_check_job_already_running:{running_id}")
            self._health_jobs[job_id] = job
            self._health_cancel_events[job_id] = cancel_event
            self._health_current_job_id = job_id

        thread = threading.Thread(
            target=self._run_health_check_job,
            args=(job_id, records, cancel_event),
            daemon=True,
        )
        thread.start()
        return self._health_job_snapshot(job)

    def _run_health_check_job(
        self,
        job_id: str,
        records: List[Dict[str, Any]],
        cancel_event: threading.Event,
    ) -> None:
        self._update_health_job(
            job_id,
            {
                "status": "running",
                "started_at": _now_text(),
            },
        )

        timeout_sec = self._health_check_timeout_sec()
        with self._health_lock:
            batch_size = int((self._health_jobs.get(job_id) or {}).get("batch_size") or 20)
        batch_size = max(1, min(100, batch_size))
        logger.info(
            "tab_archive.health_check.job_running job_id=%s total=%s timeout_sec=%s batch_size=%s",
            job_id,
            len(records),
            timeout_sec,
            batch_size,
        )

        try:
            for start in range(0, len(records), batch_size):
                if cancel_event.is_set():
                    self._update_health_job(
                        job_id,
                        {
                            "status": "cancelled",
                            "finished_at": _now_text(),
                        },
                    )
                    logger.info("tab_archive.health_check.cancelled job_id=%s processed=%s", job_id, start)
                    return

                batch = records[start:start + batch_size]
                for record in batch:
                    if cancel_event.is_set():
                        self._update_health_job(
                            job_id,
                            {
                                "status": "cancelled",
                                "finished_at": _now_text(),
                            },
                        )
                        logger.info(
                            "tab_archive.health_check.cancelled job_id=%s processed=%s",
                            job_id,
                            int((self._health_jobs.get(job_id) or {}).get("processed") or 0),
                        )
                        return

                    outcome = self._check_single_record_health(record, timeout_sec=timeout_sec)
                    bucket = str(outcome.get("bucket") or "unknown")

                    with self._health_lock:
                        job = self._health_jobs.get(job_id)
                        if not job:
                            return
                        job["processed"] = int(job.get("processed") or 0) + 1
                        if bucket == "healthy":
                            job["healthy"] = int(job.get("healthy") or 0) + 1
                        elif bucket == "unavailable":
                            job["unavailable"] = int(job.get("unavailable") or 0) + 1
                        else:
                            job["unknown"] = int(job.get("unknown") or 0) + 1
                        err = str(outcome.get("error") or "")
                        if err:
                            job["last_error"] = err
                        job["updated_at"] = _now_text()

            self._update_health_job(
                job_id,
                {
                    "status": "completed",
                    "finished_at": _now_text(),
                },
            )
            snapshot = self.get_health_check_status(job_id=job_id)
            job = snapshot.get("job") or {}
            logger.info(
                "tab_archive.health_check.completed job_id=%s processed=%s healthy=%s unavailable=%s unknown=%s",
                job_id,
                int(job.get("processed") or 0),
                int(job.get("healthy") or 0),
                int(job.get("unavailable") or 0),
                int(job.get("unknown") or 0),
            )
        except Exception as e:  # noqa: BLE001
            self._update_health_job(
                job_id,
                {
                    "status": "failed",
                    "last_error": str(e),
                    "finished_at": _now_text(),
                },
            )
            logger.exception("tab_archive.health_check.failed job_id=%s", job_id)
        finally:
            with self._health_lock:
                self._health_cancel_events.pop(job_id, None)

    def _matches_safe_exclusion_rules(self, tab: Dict[str, Any]) -> Optional[str]:
        cfg = self._tab_archive_settings()
        domains = cfg.get("safeExcludeDomains") or []
        keywords = cfg.get("safeExcludeKeywords") or []
        if not isinstance(domains, list):
            domains = []
        if not isinstance(keywords, list):
            keywords = []

        host = self._domain_from_url(tab.get("url") or "")
        hay = f"{tab.get('url') or ''}\n{tab.get('title') or ''}".lower()

        for token in domains:
            text = str(token or "").strip().lower()
            if text and text in host:
                return f"exclude_domain:{text}"

        for token in keywords:
            text = str(token or "").strip().lower()
            if text and text in hay:
                return f"exclude_keyword:{text}"

        return None

    def _fetch_live_tabs(self) -> List[Dict[str, Any]]:
        result, err = agent_bridge.enqueue_and_wait("list_tabs")
        if err:
            raise RuntimeError(err)

        rows = (result or {}).get("tabs") or []
        tabs: List[Dict[str, Any]] = []
        for row in rows:
            raw_id = row.get("id")
            if not isinstance(raw_id, int):
                continue
            tabs.append(
                {
                    "id": int(raw_id),
                    "title": str(row.get("title") or "").strip(),
                    "url": str(row.get("url") or "").strip(),
                    "windowId": int(row.get("windowId") or 0),
                    "active": bool(row.get("active")),
                    "pinned": bool(row.get("pinned")),
                    "favIconUrl": str(row.get("favIconUrl") or "").strip(),
                }
            )
        return tabs

    def _close_tabs(self, tab_ids: List[int]) -> Dict[str, Any]:
        if not tab_ids:
            return {"closed_ids": [], "failed": []}

        result, err = agent_bridge.enqueue_and_wait("close_tabs", {"tab_ids": tab_ids})
        if err:
            raise RuntimeError(err)

        payload = result or {}
        closed_ids = payload.get("closed_ids")
        if not isinstance(closed_ids, list):
            closed_count = int(payload.get("closed", 0))
            closed_ids = tab_ids[:closed_count]

        failed = payload.get("failed") or []
        parsed_closed_ids: List[int] = []
        for item in closed_ids:
            if isinstance(item, int):
                parsed_closed_ids.append(item)
        return {
            "closed_ids": parsed_closed_ids,
            "failed": failed if isinstance(failed, list) else [],
        }

    def _open_tabs(self, items: List[Dict[str, Any]], destination: str) -> List[Dict[str, Any]]:
        if not items:
            return []

        capability_error = self._extension_capability_error("open_tabs")
        if capability_error:
            raise RuntimeError(capability_error)

        result, err = agent_bridge.enqueue_and_wait(
            "open_tabs",
            {
                "items": items,
                "destination": destination,
            },
        )
        if err:
            if "unknown command type" in err.lower():
                raise RuntimeError(
                    "extension_outdated: command open_tabs is unsupported; "
                    "reload the unpacked Browser Agent extension in chrome://extensions"
                )
            raise RuntimeError(err)

        rows = (result or {}).get("results") or []
        if not isinstance(rows, list):
            return []

        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "record_id": int(row.get("record_id") or 0),
                    "url": str(row.get("url") or ""),
                    "ok": bool(row.get("ok")),
                    "tab_id": int(row["tab_id"]) if isinstance(row.get("tab_id"), int) else None,
                    "error": str(row.get("error") or ""),
                }
            )
        return out

    def _focus_tabs(self, tab_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not tab_ids:
            return {}

        capability_error = self._extension_capability_error("focus_tabs")
        if capability_error:
            raise RuntimeError(capability_error)

        result, err = agent_bridge.enqueue_and_wait("focus_tabs", {"tab_ids": tab_ids})
        if err:
            if "unknown command type" in err.lower():
                raise RuntimeError(
                    "extension_outdated: command focus_tabs is unsupported; "
                    "reload the unpacked Browser Agent extension in chrome://extensions"
                )
            raise RuntimeError(err)

        rows = (result or {}).get("results") or []
        out: Dict[int, Dict[str, Any]] = {}
        if not isinstance(rows, list):
            return out

        for row in rows:
            tab_id = row.get("tab_id")
            if not isinstance(tab_id, int):
                continue
            out[tab_id] = {
                "ok": bool(row.get("ok")),
                "error": str(row.get("error") or ""),
            }
        return out

    @staticmethod
    def _focus_failure_allows_open_fallback(error: str) -> bool:
        text = (error or "").strip().lower()
        return any(
            marker in text
            for marker in (
                "no tab with id",
                "invalid tab id",
                "tab not found",
            )
        )

    @staticmethod
    def normalize_url(url: str) -> Optional[str]:
        value = str(url or "").strip()
        if not value:
            return None

        try:
            split = urlsplit(value)
        except ValueError:
            return None

        scheme = split.scheme.lower()
        if scheme not in ("http", "https"):
            return None

        host = (split.hostname or "").strip().lower()
        if not host:
            return None

        port = split.port
        default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        netloc = host if (port is None or default_port) else f"{host}:{port}"

        path = split.path or "/"
        if path != "/":
            path = path.rstrip("/") or "/"

        filtered_query: List[Tuple[str, str]] = []
        for key, val in parse_qsl(split.query, keep_blank_values=True):
            lower_key = key.lower()
            if lower_key.startswith("utm_"):
                continue
            if lower_key in _TRACKING_QUERY_KEYS:
                continue
            filtered_query.append((key, val))
        filtered_query.sort(key=lambda x: (x[0], x[1]))

        query_text = urlencode(filtered_query, doseq=True)
        return urlunsplit((scheme, netloc, path, query_text, ""))

    @staticmethod
    def _domain_from_url(url: str) -> str:
        try:
            return (urlsplit(url).hostname or "").strip().lower()
        except ValueError:
            return ""

    @staticmethod
    def _is_internal_url(url: str) -> bool:
        value = str(url or "").strip().lower()
        if not value:
            return True
        return value.startswith(_INTERNAL_URL_PREFIXES)

    @staticmethod
    def _is_browser_agent_url(url: str) -> bool:
        value = str(url or "").strip().lower()
        if not value:
            return False
        return "/browser-agent" in value

    def _safe_archive_exclusion_reason(self, tab: Dict[str, Any], include_pinned: bool) -> Optional[str]:
        if not tab.get("url"):
            return "missing_url"
        if tab.get("pinned") and not include_pinned:
            return "pinned"
        custom_reason = self._matches_safe_exclusion_rules(tab)
        if custom_reason:
            return custom_reason
        if self._is_internal_url(tab["url"]):
            return "internal_url"
        if self._is_browser_agent_url(tab["url"]):
            return "browser_agent_page"
        if self.normalize_url(tab["url"]) is None:
            return "unsupported_url"
        return None

    def _manual_archive_exclusion_reason(self, tab: Dict[str, Any]) -> Optional[str]:
        if not tab.get("url"):
            return "missing_url"
        if self._is_internal_url(tab["url"]):
            return "internal_url"
        if self._is_browser_agent_url(tab["url"]):
            return "browser_agent_page"
        if self.normalize_url(tab["url"]) is None:
            return "unsupported_url"
        return None

    def _compute_heat_score(self, record: Dict[str, Any]) -> float:
        open_count = int(record.get("open_count") or 0)
        archive_count = int(record.get("archive_count") or 0)

        anchor = (
            record.get("last_opened_at")
            or record.get("last_archived_at")
            or record.get("created_at")
        )
        anchor_ts = _parse_time(anchor)
        recency_bonus = 0.0
        age_days = 3650.0
        if anchor_ts is not None:
            age_days = max(0.0, (datetime.now() - anchor_ts).total_seconds() / 86400.0)
            recency_bonus = math.exp(-age_days / 14.0)

        score = 1.3 * math.log1p(open_count) + 0.7 * math.log1p(archive_count) + recency_bonus
        if bool(record.get("eternal")):
            score += 1.5
        return round(score, 4)

    def _heat_level(self, score: float) -> str:
        thresholds = self._heat_thresholds()
        if score >= thresholds["high"]:
            return "high"
        if score >= thresholds["medium"]:
            return "medium"
        if score >= thresholds["low"]:
            return "low"
        return "cold"

    def _record_matches_query(self, record: Dict[str, Any], query: str) -> bool:
        q = query.strip().lower()
        if not q:
            return True
        labels = " ".join(record.get("labels") or [])
        hay = " ".join(
            [
                str(record.get("title") or ""),
                str(record.get("comment") or ""),
                str(record.get("domain") or ""),
                str(record.get("url") or ""),
                labels,
            ]
        ).lower()
        return q in hay

    def _live_matches_query(self, tab: Dict[str, Any], linked_record: Optional[Dict[str, Any]], query: str) -> bool:
        q = query.strip().lower()
        if not q:
            return True

        extras = ""
        if linked_record:
            extras = " ".join(
                [
                    str(linked_record.get("comment") or ""),
                    " ".join(linked_record.get("labels") or []),
                ]
            )
        hay = " ".join(
            [
                str(tab.get("title") or ""),
                str(tab.get("url") or ""),
                self._domain_from_url(str(tab.get("url") or "")),
                extras,
            ]
        ).lower()
        return q in hay

    def _archive_query_score(self, record: Dict[str, Any], query: str) -> int:
        q = query.strip().lower()
        if not q:
            return 0

        score = 0
        title = str(record.get("title") or "").lower()
        comment = str(record.get("comment") or "").lower()
        domain = str(record.get("domain") or "").lower()
        url = str(record.get("url") or "").lower()
        labels = [str(x).lower() for x in (record.get("labels") or [])]

        if q in title:
            score += 5
        if q in comment:
            score += 3
        if q in domain:
            score += 2
        if q in url:
            score += 1
        for label in labels:
            if q in label:
                score += 2
        return score

    def _ensure_vectors_for_cards(self, cards: List[Dict[str, Any]]) -> Dict[int, List[float]]:
        if not cards:
            return {}

        _, model_name = self._get_embed_model()
        ids = [int(card["id"]) for card in cards if isinstance(card.get("id"), int)]
        existing_rows = archive_repo.get_vectors(ids)
        existing = {int(row["tab_id"]): row for row in existing_rows}

        to_rebuild: List[Dict[str, Any]] = []
        out: Dict[int, List[float]] = {}

        for card in cards:
            tab_id = int(card["id"])
            want_hash = self._semantic_content_hash(card)
            row = existing.get(tab_id)
            if row and row.get("content_hash") == want_hash and row.get("model_name") == model_name:
                vec = row.get("embedding") or []
                if isinstance(vec, list) and vec:
                    out[tab_id] = [float(x) for x in vec]
                    continue
            to_rebuild.append(card)

        if to_rebuild:
            texts = [self._semantic_text(card) for card in to_rebuild]
            vectors = self._embed_many(texts)
            for idx, card in enumerate(to_rebuild):
                tab_id = int(card["id"])
                vec = vectors[idx]
                out[tab_id] = vec
                archive_repo.upsert_vector(
                    tab_id=tab_id,
                    embedding=vec,
                    content_hash=self._semantic_content_hash(card),
                    model_name=model_name,
                )

        return out

    def _hybrid_rank_cards(
        self,
        cards: List[Dict[str, Any]],
        *,
        query: str,
        semantic_top_k: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        q = query.strip()
        if not q:
            return cards, {
                "semantic_requested": True,
                "semantic_available": False,
                "semantic_error": "empty_query",
                "semantic_model": self._semantic_model_name(),
                "semantic_top_k": 0,
            }

        top_k = semantic_top_k if semantic_top_k is not None else self._semantic_top_k()
        top_k = max(10, min(500, int(top_k)))

        query_vec = self._embed_one(q)
        vector_map = self._ensure_vectors_for_cards(cards)

        max_heat = max([float(card.get("heat_score") or 0.0) for card in cards] + [1.0])
        max_kw = max([self._archive_query_score(card, q) for card in cards] + [1])

        now = datetime.now()
        for card in cards:
            tab_id = int(card["id"])
            vec = vector_map.get(tab_id)
            semantic_score = self._cosine(query_vec, vec) if vec else 0.0
            semantic_score = max(0.0, min(1.0, semantic_score))

            keyword_score = self._archive_query_score(card, q) / max_kw
            heat_score = float(card.get("heat_score") or 0.0) / max_heat

            anchor = card.get("last_opened_at") or card.get("last_archived_at") or card.get("created_at")
            anchor_ts = _parse_time(anchor)
            recency = 0.0
            if anchor_ts is not None:
                age_days = max(0.0, (now - anchor_ts).total_seconds() / 86400.0)
                recency = math.exp(-age_days / 21.0)

            eternal_boost = 1.0 if bool(card.get("eternal")) else 0.0

            hybrid = (
                0.58 * semantic_score
                + 0.17 * keyword_score
                + 0.15 * heat_score
                + 0.07 * recency
                + 0.03 * eternal_boost
            )

            card["semantic_score"] = round(semantic_score, 6)
            card["keyword_score"] = round(keyword_score, 6)
            card["search_score"] = round(hybrid, 6)

        cards.sort(
            key=lambda r: (
                float(r.get("search_score") or 0.0),
                float(r.get("heat_score") or 0.0),
                str(r.get("last_opened_at") or r.get("last_archived_at") or ""),
            ),
            reverse=True,
        )

        return cards[:top_k], {
            "semantic_requested": True,
            "semantic_available": True,
            "semantic_error": "",
            "semantic_model": self._semantic_model_name(),
            "semantic_top_k": top_k,
        }

    def _sort_archive_cards(
        self,
        cards: List[Dict[str, Any]],
        *,
        query: str,
        sort_by: str,
        sort_order: str,
    ) -> List[Dict[str, Any]]:
        reverse = sort_order != "asc"
        mode = sort_by.strip().lower()

        def as_num(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        if mode == "title":
            cards.sort(key=lambda r: str(r.get("title") or "").lower(), reverse=reverse)
            return cards

        if mode == "open_count":
            cards.sort(key=lambda r: as_num(r.get("open_count")), reverse=reverse)
            return cards

        if mode == "last_opened":
            cards.sort(
                key=lambda r: (
                    str(r.get("last_opened_at") or ""),
                    as_num(r.get("id")),
                ),
                reverse=reverse,
            )
            return cards

        if mode == "last_archived":
            cards.sort(
                key=lambda r: (
                    str(r.get("last_archived_at") or ""),
                    as_num(r.get("id")),
                ),
                reverse=reverse,
            )
            return cards

        if mode == "relevance":
            cards.sort(
                key=lambda r: (
                    float(r.get("search_score") or self._archive_query_score(r, query)),
                    as_num(r.get("heat_score")),
                    str(r.get("last_opened_at") or r.get("last_archived_at") or ""),
                ),
                reverse=True,
            )
            if sort_order == "asc":
                cards.reverse()
            return cards

        # default: heat
        cards.sort(
            key=lambda r: (
                as_num(r.get("heat_score")),
                str(r.get("last_opened_at") or r.get("last_archived_at") or ""),
                as_num(r.get("open_count")),
            ),
            reverse=reverse,
        )
        return cards

    def get_snapshot(
        self,
        query: str = "",
        scope: str = "all",
        archive_limit: int = 1000,
        include_live_urls: bool = False,
        sort_by: str = "heat",
        sort_order: str = "desc",
        semantic: bool = False,
        semantic_top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        logger.debug(
            "tab_archive.snapshot.start scope=%s query_len=%s sort_by=%s sort_order=%s semantic=%s",
            scope,
            len(query or ""),
            sort_by,
            sort_order,
            semantic,
        )
        records = archive_repo.list_records(limit=archive_limit)
        by_norm = {record["normalized_url"]: record for record in records}

        live_tabs: List[Dict[str, Any]] = []
        live_error: Optional[str] = None
        try:
            live_tabs = self._fetch_live_tabs()
        except Exception as exc:  # noqa: BLE001
            live_error = str(exc)
            logger.warning("tab_archive.snapshot.live_fetch_failed error=%s", live_error)

        now = _now_text()
        live_norm_map: Dict[str, int] = {}
        live_cards: List[Dict[str, Any]] = []

        for tab in live_tabs:
            normalized = self.normalize_url(tab["url"]) if tab.get("url") else None
            linked_record: Optional[Dict[str, Any]] = None
            if normalized:
                live_norm_map[normalized] = int(tab["id"])
                linked_record = by_norm.get(normalized)
                if linked_record:
                    linked_record = archive_repo.touch_existing_from_live(
                        normalized_url=normalized,
                        url=tab["url"],
                        title=tab.get("title") or "",
                        domain=self._domain_from_url(tab["url"]),
                        favicon_url=tab.get("favIconUrl") or "",
                        touch_seen_at=now,
                    )
                    if linked_record:
                        by_norm[normalized] = linked_record

            if scope == "archive":
                continue
            if not self._live_matches_query(tab, linked_record, query):
                continue

            heat_score = self._compute_heat_score(linked_record) if linked_record else 0.0
            live_cards.append(
                {
                    "tab_id": int(tab["id"]),
                    "title": tab.get("title") or "",
                    "favicon_url": tab.get("favIconUrl") or "",
                    "pinned": bool(tab.get("pinned")),
                    "active": bool(tab.get("active")),
                    "window_id": int(tab.get("windowId") or 0),
                    "url": tab.get("url") if include_live_urls else "",
                    "domain": self._domain_from_url(tab.get("url") or ""),
                    "normalized_url": normalized,
                    "record_id": linked_record.get("id") if linked_record else None,
                    "comment": linked_record.get("comment") if linked_record else "",
                    "labels": linked_record.get("labels") if linked_record else [],
                    "eternal": bool(linked_record.get("eternal")) if linked_record else False,
                    "heat_score": heat_score,
                    "heat_level": self._heat_level(heat_score),
                }
            )

        archive_cards: List[Dict[str, Any]] = []
        if scope in ("all", "archive"):
            for record in by_norm.values():
                is_live = record["normalized_url"] in live_norm_map
                if is_live:
                    continue
                if (not semantic) and (not self._record_matches_query(record, query)):
                    continue

                heat_score = self._compute_heat_score(record)
                archive_cards.append(
                    {
                        **record,
                        "is_live": False,
                        "heat_score": heat_score,
                        "heat_level": self._heat_level(heat_score),
                    }
                )

        semantic_meta = {
            "semantic_requested": bool(semantic),
            "semantic_available": False,
            "semantic_error": "",
            "semantic_model": self._semantic_model_name(),
            "semantic_top_k": 0,
        }

        if semantic:
            try:
                archive_cards, semantic_meta = self._hybrid_rank_cards(
                    archive_cards,
                    query=query,
                    semantic_top_k=semantic_top_k,
                )
            except Exception as exc:  # noqa: BLE001
                semantic_meta = {
                    "semantic_requested": True,
                    "semantic_available": False,
                    "semantic_error": str(exc),
                    "semantic_model": self._semantic_model_name(),
                    "semantic_top_k": 0,
                }
                # Degrade to keyword-only behavior.
                archive_cards = [card for card in archive_cards if self._record_matches_query(card, query)]
                logger.warning("tab_archive.snapshot.semantic_degraded error=%s", semantic_meta["semantic_error"])
        else:
            archive_cards = [card for card in archive_cards if self._record_matches_query(card, query)]

        archive_cards = self._sort_archive_cards(
            archive_cards,
            query=query,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        logger.debug(
            "tab_archive.snapshot.done live=%s archive=%s total_archived=%s semantic_available=%s",
            len(live_cards),
            len(archive_cards),
            len(by_norm),
            bool(semantic_meta.get("semantic_available")),
        )

        return {
            "extension_available": live_error is None,
            "live_error": live_error,
            "live": live_cards,
            "archive": archive_cards,
            "counts": {
                "live": len(live_cards),
                "archive": len(archive_cards),
                "total_archived": len(by_norm),
            },
            "search": semantic_meta,
        }

    def preview_safe_archive(self, include_pinned: bool = False) -> Dict[str, Any]:
        live_tabs = self._fetch_live_tabs()
        candidates: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []

        for tab in live_tabs:
            reason = self._safe_archive_exclusion_reason(tab, include_pinned=include_pinned)
            row = {
                "tab_id": int(tab["id"]),
                "title": tab.get("title") or "",
                "favicon_url": tab.get("favIconUrl") or "",
                "pinned": bool(tab.get("pinned")),
                "domain": self._domain_from_url(tab.get("url") or ""),
                "url": tab.get("url") or "",
                "reason": reason,
            }
            if reason:
                excluded.append(row)
            else:
                candidates.append(row)

        return {
            "include_pinned": bool(include_pinned),
            "requested": len(live_tabs),
            "candidates": candidates,
            "excluded": excluded,
            "candidate_count": len(candidates),
            "excluded_count": len(excluded),
        }

    def _archive_from_live_tabs(self, live_tabs: List[Dict[str, Any]], selected_ids: List[int], mode: str) -> Dict[str, Any]:
        selected_set = {int(x) for x in selected_ids}
        seen_selected_ids: set[int] = set()
        now = _now_text()

        persisted: List[Dict[str, Any]] = []
        close_tab_ids: List[int] = []
        close_tab_to_record_id: Dict[int, int] = {}
        failures: List[Dict[str, Any]] = []

        for tab in live_tabs:
            tab_id = int(tab["id"])
            if tab_id not in selected_set:
                continue
            seen_selected_ids.add(tab_id)

            reason = self._manual_archive_exclusion_reason(tab)
            if reason:
                failures.append(
                    {
                        "tab_id": tab_id,
                        "title": tab.get("title") or "",
                        "ok": False,
                        "reason": reason,
                    }
                )
                continue

            normalized = self.normalize_url(tab.get("url") or "")
            if normalized is None:
                failures.append(
                    {
                        "tab_id": tab_id,
                        "title": tab.get("title") or "",
                        "ok": False,
                        "reason": "normalize_failed",
                    }
                )
                continue

            record = archive_repo.upsert_from_live(
                normalized_url=normalized,
                url=tab.get("url") or "",
                title=tab.get("title") or "",
                domain=self._domain_from_url(tab.get("url") or ""),
                favicon_url=tab.get("favIconUrl") or "",
                touch_seen_at=now,
            )
            persisted.append(record)
            close_tab_ids.append(tab_id)
            close_tab_to_record_id[tab_id] = int(record["id"])

        for missing_tab_id in sorted(selected_set - seen_selected_ids):
            failures.append(
                {
                    "tab_id": missing_tab_id,
                    "title": "",
                    "ok": False,
                    "reason": "tab_not_found",
                }
            )

        closed_record_ids: List[int] = []
        close_error = ""
        failed_close: List[Dict[str, Any]] = []
        if close_tab_ids:
            try:
                close_result = self._close_tabs(close_tab_ids)
                closed_tab_ids = close_result.get("closed_ids") or []
                for tab_id in closed_tab_ids:
                    record_id = close_tab_to_record_id.get(int(tab_id))
                    if record_id is not None:
                        closed_record_ids.append(record_id)
                failed_close = close_result.get("failed") or []
            except Exception as exc:  # noqa: BLE001
                close_error = str(exc)
                failed_close = [
                    {
                        "tab_id": tab_id,
                        "error": close_error,
                    }
                    for tab_id in close_tab_ids
                ]

        if closed_record_ids:
            archive_repo.mark_archived(closed_record_ids, timestamp_text=now)

        for item in failed_close:
            failures.append(
                {
                    "tab_id": int(item.get("tab_id") or 0),
                    "title": "",
                    "ok": False,
                    "reason": str(item.get("error") or "close_failed"),
                }
            )

        persisted_count = len(persisted)
        closed_count = len(closed_record_ids)
        failed_count = len(failures)

        batch_id = archive_repo.insert_archive_batch(
            mode=mode,
            requested_count=len(selected_set),
            persisted_count=persisted_count,
            closed_count=closed_count,
            failed_count=failed_count,
        )

        return {
            "mode": mode,
            "batch_id": batch_id,
            "requested": len(selected_set),
            "persisted_count": persisted_count,
            "closed_count": closed_count,
            "failed_count": failed_count,
            "close_error": close_error,
            "closed_record_ids": closed_record_ids,
            "failures": failures,
        }

    def archive_selected(self, tab_ids: List[int]) -> Dict[str, Any]:
        ids = [int(x) for x in tab_ids]
        if not ids:
            return {
                "mode": "selected",
                "batch_id": None,
                "requested": 0,
                "persisted_count": 0,
                "closed_count": 0,
                "failed_count": 0,
                "close_error": "",
                "closed_record_ids": [],
                "failures": [],
            }

        live_tabs = self._fetch_live_tabs()
        return self._archive_from_live_tabs(live_tabs, ids, mode="selected")

    def archive_safe_all(self, include_pinned: bool = False) -> Dict[str, Any]:
        live_tabs = self._fetch_live_tabs()
        selected_ids: List[int] = []
        excluded: List[Dict[str, Any]] = []

        for tab in live_tabs:
            reason = self._safe_archive_exclusion_reason(tab, include_pinned=include_pinned)
            if reason:
                excluded.append(
                    {
                        "tab_id": int(tab["id"]),
                        "title": tab.get("title") or "",
                        "reason": reason,
                    }
                )
                continue
            selected_ids.append(int(tab["id"]))

        result = self._archive_from_live_tabs(live_tabs, selected_ids, mode="safe_all")
        result["excluded"] = excluded
        result["excluded_count"] = len(excluded)
        return result

    def restore_records(self, record_ids: List[int], destination: str = "new_window") -> Dict[str, Any]:
        ids = [int(x) for x in record_ids]
        logger.info(
            "tab_archive.restore.start requested=%s destination=%s",
            len(ids),
            destination,
        )
        if not ids:
            return {
                "requested": 0,
                "destination": destination,
                "opened_count": 0,
                "already_live_count": 0,
                "failed_count": 0,
                "results": [],
            }

        if destination not in ("new_window", "current_window"):
            raise ValueError("destination must be one of: new_window, current_window")

        records = archive_repo.get_records_by_ids(ids)
        if not records:
            logger.warning("tab_archive.restore.no_records requested=%s", len(ids))
            return {
                "requested": len(ids),
                "destination": destination,
                "opened_count": 0,
                "already_live_count": 0,
                "failed_count": len(ids),
                "results": [
                    {
                        "record_id": record_id,
                        "ok": False,
                        "status": "failed",
                        "tab_id": None,
                        "error": "record_not_found",
                        "title": "",
                        "url": "",
                    }
                    for record_id in ids
                ],
            }

        found_ids = {int(record["id"]) for record in records}
        records_by_id = {int(record["id"]): record for record in records}

        live_tabs = self._fetch_live_tabs()
        live_norm_to_tab: Dict[str, Dict[str, Any]] = {}
        for tab in live_tabs:
            normalized = self.normalize_url(tab.get("url") or "")
            if normalized:
                live_norm_to_tab[normalized] = tab

        success_ids: List[int] = []
        to_open: List[Dict[str, Any]] = []
        queued_open_ids: set[int] = set()
        to_focus: List[Dict[str, int]] = []
        results: List[Dict[str, Any]] = []

        def _queue_open(record_id: int) -> bool:
            if record_id in queued_open_ids:
                return True
            record = records_by_id.get(record_id)
            if not record:
                return False
            url = str(record.get("url") or "").strip()
            if not url:
                return False
            to_open.append({"record_id": record_id, "url": url})
            queued_open_ids.add(record_id)
            return True

        for record in records:
            normalized = record.get("normalized_url")
            existing_tab = live_norm_to_tab.get(normalized)
            if existing_tab is not None:
                existing_id = existing_tab.get("id")
                if isinstance(existing_id, int):
                    to_focus.append({"record_id": int(record["id"]), "tab_id": existing_id})
                else:
                    results.append(
                        {
                            "record_id": int(record["id"]),
                            "ok": False,
                            "status": "failed",
                            "tab_id": None,
                            "error": "invalid_live_tab_id",
                            "title": str(record.get("title") or ""),
                            "url": str(record.get("url") or ""),
                        }
                    )
                continue

            record_id = int(record["id"])
            if not _queue_open(record_id):
                results.append(
                    {
                        "record_id": record_id,
                        "ok": False,
                        "status": "failed",
                        "tab_id": None,
                        "error": "missing_url",
                        "title": str(record.get("title") or ""),
                        "url": "",
                    }
                )

        opened_count = 0
        failed_count = 0

        for record_id in ids:
            if record_id in found_ids:
                continue
            failed_count += 1
            results.append(
                {
                    "record_id": record_id,
                    "ok": False,
                    "status": "failed",
                    "tab_id": None,
                    "error": "record_not_found",
                    "title": "",
                    "url": "",
                }
            )

        if to_focus:
            focus_ids = [int(item["tab_id"]) for item in to_focus]
            focus_command_error = ""
            try:
                focus_result_map = self._focus_tabs(focus_ids)
            except Exception as exc:  # noqa: BLE001
                focus_command_error = str(exc)
                focus_result_map = {}
                logger.warning(
                    "tab_archive.restore.focus_command_failed count=%s error=%s",
                    len(focus_ids),
                    focus_command_error,
                )

            for item in to_focus:
                tab_id = int(item["tab_id"])
                record_id = int(item["record_id"])
                focus_status = focus_result_map.get(tab_id)
                if focus_status and focus_status.get("ok"):
                    record = records_by_id.get(record_id) or {}
                    success_ids.append(record_id)
                    results.append(
                        {
                            "record_id": record_id,
                            "ok": True,
                            "status": "already_live",
                            "tab_id": tab_id,
                            "error": "",
                            "title": str(record.get("title") or ""),
                            "url": str(record.get("url") or ""),
                        }
                    )
                else:
                    record = records_by_id.get(record_id) or {}
                    focus_error = focus_command_error or str(
                        (focus_status or {}).get("error") or "focus_failed"
                    )
                    # Focus can fail if the tab closed between snapshot and action.
                    # Only that explicit race is safe to handle by opening a new
                    # tab. Transport, capability, and permission errors must not
                    # create a duplicate of a tab that may still be open.
                    if self._focus_failure_allows_open_fallback(focus_error):
                        if _queue_open(record_id):
                            continue

                    failed_count += 1
                    logger.warning(
                        "tab_archive.restore.focus_failed_no_fallback record_id=%s tab_id=%s error=%s",
                        record_id,
                        tab_id,
                        focus_error,
                    )
                    results.append(
                        {
                            "record_id": record_id,
                            "ok": False,
                            "status": "failed",
                            "tab_id": tab_id,
                            "error": focus_error,
                            "title": str(record.get("title") or ""),
                            "url": str(record.get("url") or ""),
                        }
                    )

        if to_open:
            try:
                open_results = self._open_tabs(to_open, destination=destination)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "tab_archive.restore.open_tabs_failed count=%s error=%s",
                    len(to_open),
                    str(exc),
                )
                open_results = [
                    {
                        "record_id": int(row["record_id"]),
                        "url": row.get("url") or "",
                        "ok": False,
                        "tab_id": None,
                        "error": str(exc),
                    }
                    for row in to_open
                ]

            for row in open_results:
                if row.get("ok"):
                    record = records_by_id.get(int(row["record_id"])) or {}
                    opened_count += 1
                    success_ids.append(int(row["record_id"]))
                    results.append(
                        {
                            "record_id": int(row["record_id"]),
                            "ok": True,
                            "status": "opened",
                            "tab_id": row.get("tab_id"),
                            "error": "",
                            "title": str(record.get("title") or ""),
                            "url": str(record.get("url") or ""),
                        }
                    )
                else:
                    record = records_by_id.get(int(row["record_id"])) or {}
                    failed_count += 1
                    results.append(
                        {
                            "record_id": int(row["record_id"]),
                            "ok": False,
                            "status": "failed",
                            "tab_id": None,
                            "error": str(row.get("error") or "open_failed"),
                            "title": str(record.get("title") or ""),
                            "url": str(record.get("url") or ""),
                        }
                    )

            # If extension returned fewer rows than expected, add synthetic failures.
            returned_ids = {int(row.get("record_id") or 0) for row in open_results}
            for row in to_open:
                record_id = int(row["record_id"])
                if record_id in returned_ids:
                    continue
                failed_count += 1
                record = records_by_id.get(record_id) or {}
                results.append(
                    {
                        "record_id": record_id,
                        "ok": False,
                        "status": "failed",
                        "tab_id": None,
                        "error": "missing_result",
                        "title": str(record.get("title") or ""),
                        "url": str(record.get("url") or ""),
                    }
                )

        if success_ids:
            archive_repo.mark_opened(success_ids, timestamp_text=_now_text())

        already_live_count = len([x for x in results if x.get("status") == "already_live"])
        logger.info(
            "tab_archive.restore.done requested=%s opened=%s already_live=%s failed=%s",
            len(ids),
            opened_count,
            already_live_count,
            len([x for x in results if not x.get("ok")]),
        )
        return {
            "requested": len(ids),
            "destination": destination,
            "opened_count": opened_count,
            "already_live_count": already_live_count,
            "failed_count": len([x for x in results if not x.get("ok")]),
            "results": results,
        }

    def _probe_url_once(self, url: str, timeout_sec: int, method: str) -> Dict[str, Any]:
        req = url_request.Request(
            url,
            method=method,
            headers={"User-Agent": "script-orchestra-browser-agent/1.0"},
        )
        with url_request.urlopen(req, timeout=timeout_sec) as resp:
            status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
            final_url = str(resp.geturl() or url)
            if method == "GET":
                # Read minimal bytes to validate connection without downloading content.
                _ = resp.read(1)
            return {
                "status": status,
                "final_url": final_url,
                "error": "",
            }

    def _probe_url(self, url: str, timeout_sec: int) -> Dict[str, Any]:
        try:
            return self._probe_url_once(url, timeout_sec, method="HEAD")
        except HTTPError as e:
            # Some sites reject HEAD, so fallback to GET for better signal quality.
            if int(e.code or 0) in (400, 403, 405, 500, 501):
                try:
                    return self._probe_url_once(url, timeout_sec, method="GET")
                except Exception as nested_exc:  # noqa: BLE001
                    return {
                        "status": int(getattr(e, "code", 0) or 0),
                        "final_url": str(getattr(e, "url", "") or url),
                        "error": str(nested_exc),
                    }
            return {
                "status": int(getattr(e, "code", 0) or 0),
                "final_url": str(getattr(e, "url", "") or url),
                "error": str(e),
            }
        except URLError as e:
            return {
                "status": None,
                "final_url": url,
                "error": str(e.reason) if getattr(e, "reason", None) else str(e),
            }
        except Exception as e:  # noqa: BLE001
            return {
                "status": None,
                "final_url": url,
                "error": str(e),
            }

    def _check_single_record_health(self, record: Dict[str, Any], timeout_sec: int) -> Dict[str, Any]:
        record_id = int(record["id"])
        url = str(record.get("url") or "").strip()
        checked_at = _now_text()

        if not url or self.normalize_url(url) is None:
            updated = archive_repo.update_record_health(
                record_id,
                health_status="unknown",
                checked_at=checked_at,
                last_http_status=None,
                final_url=url,
            )
            return {
                "bucket": "unknown",
                "record": updated,
                "error": "",
            }

        probe = self._probe_url(url, timeout_sec=timeout_sec)
        status = probe.get("status")
        ok = isinstance(status, int) and 200 <= status < 400
        health_status = "healthy" if ok else "unavailable"

        updated = archive_repo.update_record_health(
            record_id,
            health_status=health_status,
            checked_at=checked_at,
            last_http_status=(int(status) if isinstance(status, int) else None),
            final_url=str(probe.get("final_url") or url),
        )

        return {
            "bucket": health_status,
            "record": updated,
            "error": str(probe.get("error") or ""),
        }

    def check_health(self, record_ids: Optional[List[int]] = None, limit: int = 200) -> Dict[str, Any]:
        timeout_sec = self._health_check_timeout_sec()
        if record_ids is not None:
            records = archive_repo.get_records_by_ids([int(x) for x in record_ids])
        else:
            records = archive_repo.list_records_for_health(limit=limit)
        logger.info(
            "tab_archive.health_check.sync_start requested=%s resolved=%s limit=%s timeout_sec=%s",
            len(record_ids or []),
            len(records),
            limit,
            timeout_sec,
        )

        results: List[Dict[str, Any]] = []
        healthy = 0
        unavailable = 0
        unknown = 0

        for record in records:
            outcome = self._check_single_record_health(record, timeout_sec=timeout_sec)
            bucket = outcome.get("bucket")
            if bucket == "healthy":
                healthy += 1
            elif bucket == "unavailable":
                unavailable += 1
            else:
                unknown += 1

            updated = outcome.get("record")
            if updated:
                updated["health_error"] = str(outcome.get("error") or "")
                results.append(updated)

        return {
            "checked": len(records),
            "healthy": healthy,
            "unavailable": unavailable,
            "unknown": unknown,
            "timeout_sec": timeout_sec,
            "records": results,
        }

    def update_record(self, record_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return archive_repo.update_record(record_id, patch)

    def delete_record(self, record_id: int) -> bool:
        return archive_repo.delete_record(record_id)

    def list_labels(self) -> List[Dict[str, Any]]:
        return archive_repo.list_labels()

    def create_label(self, name: str) -> Dict[str, Any]:
        return archive_repo.create_label(name)

    def delete_label(self, label_id: int) -> bool:
        return archive_repo.delete_label(label_id)

    def set_record_labels(self, record_id: int, label_ids: List[int]) -> Optional[Dict[str, Any]]:
        archive_repo.set_record_labels(record_id, label_ids)
        return archive_repo.get_record_by_id(record_id)


_service_singleton = TabArchiveService()


def get_tab_archive_service() -> TabArchiveService:
    return _service_singleton
