"""Browser Agent — service layer.

Holds the global lock for tab ingestion, the broadcaster hook (so the
dispatcher can push progress to the frontend without importing sockets),
and the tab-store logic ported from the 2023 prototype.
"""
import threading
from typing import Callable, Optional

from . import repository, settings_manager, http_service
from .entity import BrowserTab

_lock = threading.Lock()


class BrowserAgentService:
    def __init__(self):
        self._broadcaster: Optional[Callable[[dict], None]] = None

    def register_broadcaster(self, broadcaster: Callable[[dict], None]) -> None:
        self._broadcaster = broadcaster

    def broadcast(self, payload: dict) -> None:
        if self._broadcaster:
            try:
                self._broadcaster(payload)
            except Exception as e:
                print(f"[browser_agent] broadcast failed: {e}")

    def store_tabs(self, tab_urls: list) -> dict:
        """Ingest a list of tab URLs: match a site rule, resolve the real
        download link, and insert as TODO (deduped by aid code)."""
        settings = settings_manager.load_settings()
        site_rules = settings.get("siteRules", [])
        added, skipped, unmatched = 0, 0, 0
        with _lock:
            for url in tab_urls:
                rule, aid = http_service.match_rule(url, site_rules)
                if not rule or not aid:
                    unmatched += 1
                    continue
                if repository.get_by_code(aid) is not None:
                    skipped += 1
                    continue
                domain_scheme, domain, _ = http_service.parse_url(url)
                page_url = http_service.build_download_page_url(domain_scheme, domain, rule, aid)
                link, name, size = http_service.get_file_meta(
                    page_url, rule.get("downloadLinkRegex", ""))
                if not link:
                    unmatched += 1
                    continue
                tab = BrowserTab.new_instance(code=aid, file_name=name,
                                              size=size or 0, download_link=link)
                repository.insert_browser_tab(tab)
                added += 1
        return {"added": added, "skipped": skipped, "unmatched": unmatched}


_service_singleton: Optional[BrowserAgentService] = None


def get_service() -> BrowserAgentService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = BrowserAgentService()
    return _service_singleton
