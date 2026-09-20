"""Browser Agent tab archive service.

Implements live/archive synchronization, safe archival, and batch restore.
"""
from __future__ import annotations

import logging
import math
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
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
        pass

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

    def move_live_tab(self, tab_id: int, index: int, window_id: Optional[int] = None) -> Dict[str, Any]:
        capability_error = self._extension_capability_error("move_tab")
        if capability_error:
            raise RuntimeError(capability_error)

        params: Dict[str, Any] = {"tab_id": tab_id, "index": index}
        if window_id is not None:
            params["window_id"] = window_id

        result, err = agent_bridge.enqueue_and_wait("move_tab", params)
        if err:
            raise RuntimeError(err)
        return result or {}

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

        if mode == "group":
            cards.sort(
                key=lambda r: (
                    str(r.get("group_name") or "￿"),
                    str(r.get("title") or "").lower(),
                ),
                reverse=reverse,
            )
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
    ) -> Dict[str, Any]:
        logger.debug(
            "tab_archive.snapshot.start scope=%s query_len=%s",
            scope,
            len(query or ""),
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

        current_tab_ids = [int(tab["id"]) for tab in live_tabs]
        first_seen_map = archive_repo.sync_live_first_seen(current_tab_ids)
        live_group_map = archive_repo.sync_live_tab_groups(current_tab_ids)
        live_custom_headers = archive_repo.get_live_tab_custom_headers(current_tab_ids)
        live_group_tree = archive_repo.live_get_group_tree()
        archive_group_tree = archive_repo.archive_get_group_tree()
        group_name_by_id: Dict[int, str] = self._flatten_group_names(live_group_tree)
        group_name_by_id.update(self._flatten_group_names(archive_group_tree))

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
            tab_id_int = int(tab["id"])
            grp_entry = live_group_map.get(tab_id_int)
            grp_id = grp_entry["group_id"] if grp_entry else None
            grp_display_order = grp_entry["display_order"] if grp_entry else None
            live_cards.append(
                {
                    "tab_id": tab_id_int,
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
                    "first_seen_at": first_seen_map.get(tab_id_int),
                    "group_id": grp_id,
                    "group_name": group_name_by_id.get(grp_id) if grp_id is not None else None,
                    "display_order": grp_display_order,
                    "custom_header": live_custom_headers.get(tab_id_int),
                }
            )

        archive_cards: List[Dict[str, Any]] = []
        if scope in ("all", "archive"):
            for record in by_norm.values():
                is_live = record["normalized_url"] in live_norm_map
                if is_live:
                    continue
                if not self._record_matches_query(record, query):
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

        archive_cards = archive_cards  # order already from DB (display_order ASC)

        cfg = settings_manager.load_settings().get("tabArchive", {})
        expire_days = int(cfg.get("expireDays", 365))
        cutoff = (datetime.now() - timedelta(days=expire_days)).strftime("%Y-%m-%d %H:%M:%S")
        expiring_count = sum(
            1 for r in archive_cards
            if not r.get("eternal")
            and (r.get("last_opened_at") or r.get("last_archived_at") or r.get("created_at") or "") < cutoff
        )

        logger.debug(
            "tab_archive.snapshot.done live=%s archive=%s total_archived=%s",
            len(live_cards),
            len(archive_cards),
            len(by_norm),
        )

        return {
            "extension_available": live_error is None,
            "live_error": live_error,
            "live": live_cards,
            "archive": archive_cards,
            "live_group_tree": live_group_tree,
            "archive_group_tree": archive_group_tree,
            "expiring_count": expiring_count,
            "expire_days": expire_days,
            "counts": {
                "live": len(live_cards),
                "archive": len(archive_cards),
                "total_archived": len(by_norm),
            },
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

    # -------------------------------------------------------------------------
    # Group methods
    # -------------------------------------------------------------------------

    @staticmethod
    def _flatten_group_names(tree: List[Dict[str, Any]]) -> Dict[int, str]:
        """Walk tree recursively, return {id: name} for all nodes."""
        result: Dict[int, str] = {}
        stack = list(tree)
        while stack:
            node = stack.pop()
            result[node["id"]] = node["name"]
            stack.extend(node.get("children") or [])
        return result

    def get_group_tree(self, scope: str = "archive") -> List[Dict[str, Any]]:
        return archive_repo.get_group_tree(scope)

    def list_groups(self, parent_id: Optional[int] = None, scope: str = "archive") -> List[Dict[str, Any]]:
        return archive_repo.list_groups(parent_id, scope)

    def create_group(
        self,
        name: str,
        parent_id: Optional[int] = None,
        scope: str = "archive",
        display_order: Optional[float] = None,
    ) -> Dict[str, Any]:
        return archive_repo.create_group(name, parent_id=parent_id, scope=scope, display_order=display_order)

    def rename_group(self, group_id: int, name: str) -> Optional[Dict[str, Any]]:
        return archive_repo.rename_group(group_id, name)

    def move_group(self, group_id: int, new_parent_id: Optional[int], new_display_order: float) -> Optional[Dict[str, Any]]:
        return archive_repo.move_group(group_id, new_parent_id, new_display_order)

    def delete_group(self, group_id: int) -> bool:
        return archive_repo.delete_group(group_id)

    # --- Per-pane group methods (split tables) --------------------------------

    def live_list_groups(self, parent_id=None):
        return archive_repo.live_list_groups(parent_id)

    def live_get_group_tree(self):
        return archive_repo.live_get_group_tree()

    def live_create_group(self, name: str, parent_id=None, display_order=None):
        return archive_repo.live_create_group(name, parent_id, display_order)

    def live_rename_group(self, group_id: int, name: str):
        return archive_repo.live_rename_group(group_id, name)

    def live_move_group(self, group_id: int, new_parent_id, new_display_order: float):
        return archive_repo.live_move_group(group_id, new_parent_id, new_display_order)

    def live_delete_group(self, group_id: int) -> bool:
        return archive_repo.live_delete_group(group_id)

    def archive_list_groups(self, parent_id=None):
        return archive_repo.archive_list_groups(parent_id)

    def archive_get_group_tree(self):
        return archive_repo.archive_get_group_tree()

    def archive_create_group(self, name: str, parent_id=None, display_order=None):
        return archive_repo.archive_create_group(name, parent_id, display_order)

    def archive_rename_group(self, group_id: int, name: str):
        return archive_repo.archive_rename_group(group_id, name)

    def archive_move_group(self, group_id: int, new_parent_id, new_display_order: float):
        return archive_repo.archive_move_group(group_id, new_parent_id, new_display_order)

    def archive_delete_group(self, group_id: int) -> bool:
        return archive_repo.archive_delete_group(group_id)

    def shelf_list_groups(self, parent_id=None):
        return archive_repo.shelf_list_groups(parent_id)

    def shelf_get_group_tree(self):
        return archive_repo.shelf_get_group_tree()

    def shelf_create_group(self, name: str, parent_id=None, display_order=None, bookmark_id=None):
        return archive_repo.shelf_create_group(name, parent_id, display_order, bookmark_id)

    def shelf_rename_group(self, group_id: int, name: str):
        return archive_repo.shelf_rename_group(group_id, name)

    def shelf_move_group(self, group_id: int, new_parent_id, new_display_order: float):
        return archive_repo.shelf_move_group(group_id, new_parent_id, new_display_order)

    def shelf_delete_group(self, group_id: int) -> bool:
        return archive_repo.shelf_delete_group(group_id)

    def set_archive_record_group(self, record_id: int, group_id: Optional[int]) -> Optional[Dict[str, Any]]:
        return archive_repo.set_archive_record_group(record_id, group_id)

    def set_archive_record_order(self, record_id: int, new_display_order: float) -> None:
        archive_repo.set_archive_record_order(record_id, new_display_order)

    def set_live_tabs_group(self, tab_ids: List[int], group_id: Optional[int]) -> Dict[str, Any]:
        archive_repo.set_live_tabs_group(tab_ids, group_id)
        return {"updated": len(tab_ids)}

    def set_live_tab_group_and_order(self, tab_id: int, group_id: Optional[int], display_order: float) -> None:
        archive_repo.set_live_tab_group_and_order(tab_id, group_id, display_order)

    def batch_set_live_tab_orders(self, items: List[Dict[str, Any]]) -> None:
        archive_repo.batch_set_live_tab_orders(items)

    def set_live_tab_custom_header(self, tab_id: int, custom_header: Optional[str]) -> None:
        archive_repo.set_live_tab_custom_header(tab_id, custom_header)

    def group_as_window(self, window_id: int, group_name: str) -> Dict[str, Any]:
        live_tabs = self._fetch_live_tabs()
        window_tabs = [t for t in live_tabs if int(t.get("windowId") or 0) == int(window_id)]
        if not window_tabs:
            raise ValueError(f"No live tabs found in window {window_id}")

        group = archive_repo.live_create_group(group_name)
        tab_ids = [int(t["id"]) for t in window_tabs]
        archive_repo.set_live_tabs_group(tab_ids, group["id"])
        return {"group": group, "count": len(tab_ids)}

    def sort_live_by_group(self, window_id: Optional[int] = None) -> Dict[str, Any]:
        live_tabs = self._fetch_live_tabs()

        if window_id is not None:
            window_tabs = [t for t in live_tabs if int(t.get("windowId") or 0) == int(window_id)]
            if not window_tabs:
                raise ValueError(f"No live tabs in window {window_id}")
            target_window_id = int(window_id)
        else:
            from collections import Counter
            counts = Counter(int(t.get("windowId") or 0) for t in live_tabs)
            target_window_id = counts.most_common(1)[0][0] if counts else 0
            window_tabs = [t for t in live_tabs if int(t.get("windowId") or 0) == target_window_id]

        all_tab_ids = [int(t["id"]) for t in window_tabs]
        group_map = archive_repo.get_live_tab_groups(all_tab_ids)
        group_name_by_id = self._flatten_group_names(archive_repo.live_get_group_tree())

        grouped: Dict[int, List[Dict[str, Any]]] = {}
        ungrouped: List[Dict[str, Any]] = []
        for tab in window_tabs:
            gid = group_map.get(int(tab["id"]))
            if gid is not None:
                grouped.setdefault(gid, []).append(tab)
            else:
                ungrouped.append(tab)

        sorted_group_ids = sorted(grouped.keys(), key=lambda gid: group_name_by_id.get(gid, ""))

        group_order = []
        needs_separator = False
        for gid in sorted_group_ids:
            tabs_in_group = grouped[gid]
            if needs_separator:
                group_order.append({"is_separator": True})
            for tab in tabs_in_group:
                group_order.append({"tab_id": int(tab["id"]), "is_separator": False})
            needs_separator = True

        if ungrouped:
            if needs_separator:
                group_order.append({"is_separator": True})
            for tab in ungrouped:
                group_order.append({"tab_id": int(tab["id"]), "is_separator": False})

        result, err = agent_bridge.enqueue_and_wait(
            "sort_tabs_by_group",
            {"window_id": target_window_id, "group_order": group_order},
        )
        if err:
            raise RuntimeError(err)

        return (result or {})

    def split_live_by_groups(self) -> Dict[str, Any]:
        live_tabs = self._fetch_live_tabs()
        all_tab_ids = [int(t["id"]) for t in live_tabs]
        group_map = archive_repo.get_live_tab_groups(all_tab_ids)
        group_name_by_id = self._flatten_group_names(archive_repo.live_get_group_tree())

        grouped: Dict[int, List[int]] = {}
        for tab in live_tabs:
            gid = group_map.get(int(tab["id"]))
            if gid is not None:
                grouped.setdefault(gid, []).append(int(tab["id"]))

        if not grouped:
            return {"windows_created": 0, "message": "No live tabs have group assignments"}

        groups_payload = [
            {
                "group_id": gid,
                "group_name": group_name_by_id.get(gid, ""),
                "tab_ids": tab_ids,
            }
            for gid, tab_ids in grouped.items()
        ]

        result, err = agent_bridge.enqueue_and_wait(
            "split_tabs_by_groups",
            {"groups": groups_payload},
        )
        if err:
            raise RuntimeError(err)

        return (result or {})

    # -------------------------------------------------------------------------
    # Tab activation (heat tracking)
    # -------------------------------------------------------------------------

    def record_activations(self, activations: List[Dict[str, Any]]) -> None:
        archive_repo.record_tab_activations(activations)

    def get_tab_activations(self, urls: List[str]) -> Dict[str, Dict[str, Any]]:
        return archive_repo.get_tab_activations(urls)

    # -------------------------------------------------------------------------
    # Shelf methods
    # -------------------------------------------------------------------------

    def get_shelf_snapshot(self) -> Dict[str, Any]:
        items = archive_repo.get_all_shelf_items()
        group_tree = archive_repo.shelf_get_group_tree()
        return {"items": items, "group_tree": group_tree}

    def create_shelf_item(self, *, url: str, title: Optional[str] = None, favicon_url: Optional[str] = None,
                          group_id: Optional[int] = None, bookmark_id: Optional[str] = None,
                          display_order: Optional[float] = None) -> Dict[str, Any]:
        return archive_repo.create_shelf_item(
            url=url, title=title, favicon_url=favicon_url,
            group_id=group_id, bookmark_id=bookmark_id, display_order=display_order,
        )

    def delete_shelf_item(self, item_id: int) -> bool:
        return archive_repo.delete_shelf_item(item_id)

    def set_shelf_item_order(self, item_id: int, new_display_order: float) -> None:
        archive_repo.set_shelf_item_order(item_id, new_display_order)

    def set_shelf_item_group(self, item_id: int, group_id: Optional[int]) -> Optional[Dict[str, Any]]:
        return archive_repo.set_shelf_item_group(item_id, group_id)

    def sync_shelf_from_bookmarks(self, bookmark_nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Deprecated flat sync — kept for direct callers passing pre-flattened nodes."""
        upserted = 0
        for node in bookmark_nodes:
            url = str(node.get("url") or "").strip()
            if not url:
                continue
            archive_repo.upsert_shelf_item_by_bookmark_id(
                bookmark_id=str(node["id"]),
                url=url,
                title=node.get("title"),
                favicon_url=node.get("favIconUrl"),
                group_id=None,
                display_order=float(node.get("index") or 0) * 1000.0,
            )
            upserted += 1
        return {"upserted": upserted}

    def _sync_bookmark_tree(self, nodes: List[Dict[str, Any]]) -> Dict[str, int]:
        """Recreate the Chrome bookmark folder hierarchy as nested shelf groups.

        Each folder node (has children, no url) becomes a shelf-scoped group whose parent_id
        chains to the enclosing folder's group; each bookmark node (has url) is upserted into
        the enclosing folder's group. Synthetic root nodes (the top-level containers Chrome
        returns, e.g. "Bookmarks Bar" / "Other Bookmarks") have no url and are walked into as
        top-level shelf groups.
        """
        counters = {"upserted": 0, "groups_created": 0}

        def walk(items: List[Dict[str, Any]], parent_group_id: Optional[int]) -> None:
            for index, item in enumerate(items):
                url = str(item.get("url") or "").strip()
                if url:
                    raw_item_id = item.get("id")
                    archive_repo.upsert_shelf_item_by_bookmark_id(
                        bookmark_id=str(raw_item_id) if raw_item_id is not None else None,
                        url=url,
                        title=item.get("title"),
                        favicon_url=item.get("favIconUrl"),
                        group_id=parent_group_id,
                        display_order=float(index) * 1000.0,
                    )
                    counters["upserted"] += 1
                    continue

                # Folder node: resolve/create its group, then descend.
                children = item.get("children") or []
                title = str(item.get("title") or "").strip()
                if not title:
                    # Unnamed containers (e.g. the invisible root) pass through without
                    # creating a group so their children attach to the current parent.
                    walk(children, parent_group_id)
                    continue

                raw_id = item.get("id")
                group = archive_repo.shelf_find_or_create_group(
                    title, parent_group_id, bookmark_id=str(raw_id) if raw_id is not None else None
                )
                if group.get("_created"):
                    counters["groups_created"] += 1
                walk(children, group["id"])

        walk(nodes, None)
        return counters

    def get_shelf_export_tree(self) -> List[Dict[str, Any]]:
        """Build a nested folder/item payload from shelf groups + items for write_bookmarks.

        Shape per folder:
            {"folder": name, "bookmark_id": <id|None>,
             "items": [{"bookmark_id", "url", "title"}],
             "children": [<folder>, ...]}
        Ungrouped items are returned at the top level alongside root folders.
        """
        group_tree = archive_repo.shelf_get_group_tree()
        items = archive_repo.get_all_shelf_items()
        items_by_group: Dict[Optional[int], List[Dict[str, Any]]] = {}
        for item in items:
            items_by_group.setdefault(item.get("group_id"), []).append(item)

        def item_payload(item: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "bookmark_id": item.get("bookmark_id"),
                "url": item["url"],
                "title": item.get("title") or item["url"],
            }

        def folder_payload(node: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "folder": node["name"],
                "bookmark_id": node.get("bookmark_id"),
                "items": [item_payload(i) for i in items_by_group.get(node["id"], [])],
                "children": [folder_payload(child) for child in node.get("children") or []],
            }

        payload: List[Dict[str, Any]] = [folder_payload(node) for node in group_tree]
        payload.extend(item_payload(i) for i in items_by_group.get(None, []))
        return payload

    def sync_shelf_from_browser_bookmarks(self) -> Dict[str, Any]:
        """Fetch bookmarks from the extension and recreate their folder tree in the shelf."""
        capability_error = self._extension_capability_error("get_bookmarks")
        if capability_error:
            return {"error": capability_error}
        result, err = agent_bridge.enqueue_and_wait("get_bookmarks")
        if err:
            return {"error": err}
        tree = (result or {}).get("tree") or []
        return self._sync_bookmark_tree(tree)

    def export_shelf_to_browser_bookmarks(self) -> Dict[str, Any]:
        """Send the shelf folder tree to the extension to write as browser bookmarks."""
        capability_error = self._extension_capability_error("write_bookmarks")
        if capability_error:
            return {"error": capability_error}
        tree = self.get_shelf_export_tree()
        result, err = agent_bridge.enqueue_and_wait("write_bookmarks", {"tree": tree})
        if err:
            return {"error": err}
        return result or {"ok": True}

    def open_shelf_item(self, item_id: int, destination: str = "current_window") -> Dict[str, Any]:
        item = archive_repo.get_shelf_item(item_id)
        if not item:
            return {"error": "item not found"}
        results = self._open_tabs([{"url": item["url"], "record_id": 0}], destination=destination)
        if results and results[0].get("ok"):
            return {"ok": True, "tab_id": results[0].get("tab_id")}
        err = (results[0].get("error") or "open failed") if results else "no result"
        return {"ok": False, "error": err}

    def replace_url(
        self,
        find: str,
        replace: str,
        record_ids: Optional[List[int]] = None,
        preview: bool = False,
    ) -> Dict[str, Any]:
        if not find:
            return {"error": "find must not be empty"}

        all_records = archive_repo.list_records(limit=50000)
        if record_ids is not None:
            id_set = set(record_ids)
            all_records = [r for r in all_records if r["id"] in id_set]

        rows = []
        for r in all_records:
            old_url = r.get("url") or ""
            if find not in old_url:
                continue
            new_url = old_url.replace(find, replace)
            rows.append({
                "id": r["id"],
                "title": r.get("title") or "",
                "old_url": old_url,
                "new_url": new_url,
            })

        if preview:
            return {"preview": rows, "count": len(rows)}

        updated = 0
        for row in rows:
            new_url = row["new_url"]
            new_domain = self._domain_from_url(new_url)
            new_normalized = self.normalize_url(new_url) or new_url
            archive_repo.update_record_url(
                row["id"],
                url=new_url,
                domain=new_domain,
                normalized_url=new_normalized,
            )
            updated += 1

        return {"updated": updated}


_service_singleton = TabArchiveService()


def get_tab_archive_service() -> TabArchiveService:
    return _service_singleton
