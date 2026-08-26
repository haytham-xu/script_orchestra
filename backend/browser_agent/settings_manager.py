"""Browser Agent — settings manager (JSON persistence).

Mirrors the manga_classifier / photo_classifier settings pattern:
load/save a JSON file inside the package dir, deep-merge defaults so new
keys survive across upgrades. settings.json is gitignored.
"""
import os
import json
import copy
from typing import Any, Dict

SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "downloadDir": "",            # target dir; empty → dispatcher refuses to download
    "maxRetries": 3,
    "pollIntervalSec": 60,
    "siteRules": [
        {
            "coverDomains": ["www.wn01.cc", "www.hm17.lol", "www.wn05.cc"],
            "overviewUriFormat": "photos-slide-aid-{aid}.html",
            "downloadUriFormat": "download-index-aid-{aid}.html",
            "downloadLinkRegex":
                r'href="(//v1\.wzip\.download/down/\d+/[a-f0-9]+\.zip\?n=[^"]+)"',
        }
    ],
}


def _ensure_settings_file_exists() -> None:
    if not os.path.exists(SETTINGS_FILE):
        try:
            save_settings(copy.deepcopy(DEFAULT_SETTINGS))
            print(f"✓ Created default browser_agent settings.json at {SETTINGS_FILE}")
        except Exception as e:
            print(f"⚠️ Failed to create browser_agent settings.json: {e}")


def load_settings() -> Dict[str, Any]:
    _ensure_settings_file_exists()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(data or {})
        return merged
    except Exception as e:
        print(f"⚠️ Failed to load browser_agent settings.json: {e}")
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Failed to save browser_agent settings.json: {e}")
        raise


def get_db_path() -> str:
    """SQLite file lives next to settings, inside the package dir."""
    return os.path.join(SETTINGS_DIR, "browser_agent.db")


def validate_and_normalize(patch: dict, current: dict) -> dict:
    """Validate a settings PUT patch and merge into current."""
    merged = dict(current)

    if "downloadDir" in patch:
        v = patch["downloadDir"]
        if not isinstance(v, str):
            raise ValueError("downloadDir must be a string")
        merged["downloadDir"] = v.strip()

    if "maxRetries" in patch:
        try:
            merged["maxRetries"] = max(0, min(int(patch["maxRetries"]), 20))
        except (TypeError, ValueError):
            raise ValueError("maxRetries must be an integer")

    if "pollIntervalSec" in patch:
        try:
            merged["pollIntervalSec"] = max(5, min(int(patch["pollIntervalSec"]), 3600))
        except (TypeError, ValueError):
            raise ValueError("pollIntervalSec must be an integer")

    if "siteRules" in patch:
        merged["siteRules"] = _validate_site_rules(patch["siteRules"])

    return merged


def _validate_site_rules(rules: Any) -> list:
    if not isinstance(rules, list):
        raise ValueError("siteRules must be a list")
    out = []
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            raise ValueError(f"siteRules[{i}] must be an object")
        domains = r.get("coverDomains", [])
        if not isinstance(domains, list) or not all(isinstance(d, str) for d in domains):
            raise ValueError(f"siteRules[{i}].coverDomains must be a list of strings")
        out.append({
            "coverDomains": [d.strip() for d in domains if d.strip()],
            "overviewUriFormat": str(r.get("overviewUriFormat", "")),
            "downloadUriFormat": str(r.get("downloadUriFormat", "")),
            "downloadLinkRegex": str(r.get("downloadLinkRegex", "")),
        })
    return out
