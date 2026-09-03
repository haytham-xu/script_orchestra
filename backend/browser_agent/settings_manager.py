"""Browser Agent — settings manager (JSON persistence).

Mirrors the manga_classifier / photo_classifier settings pattern: load/save
a JSON file inside the package dir, deep-merge defaults so new keys survive
across upgrades. settings.json is gitignored.
"""
import os
import json
import copy
from typing import Any, Dict

SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

# Defaults are intentionally empty — every deployment configures its own
# site info via the Browser Agent Settings page.
DEFAULT_SETTINGS: Dict[str, Any] = {
    "downloadDir": "",            # target dir; empty → dispatcher refuses to download
    "maxRetries": 3,
    "pollIntervalSec": 60,
    "siteRules": [],
    # Download SSMH — interactive per-tab flow that resolves the real .zip
    # URL from a paginated download page. See download_ssmh.py.
    "downloadSSMH": {
        "sourceDomains": [],       # allowlisted hosts, no scheme
        "downloadDomains": [],     # allowlisted final-download hosts
        "downloadPath": "",        # absolute local dir where .zip files land
        # Text label of the anchor to pick on the download-index page.
        # e.g. the site's "backup line / Server 2" link.
        "linkLabel": "",
    },
    # Download JM — Cloudflare-protected site that requires the user to be
    # logged in via their real browser. The extension hands back cookies.
    # See download_jm.py.
    "downloadJM": {
        "sourceDomain": "",        # single host, no scheme
        "downloadPath": "",        # absolute local dir where downloads land
    },
    "tabArchive": {
        "safeExcludeDomains": [],    # host/domain fragments excluded by safe archive
        "safeExcludeKeywords": [],   # URL/title keywords excluded by safe archive
        "embedModel": "",           # optional sentence-transformers model name
        "semanticTopK": 120,
        "heatThresholds": {
            "high": 4.0,
            "medium": 2.0,
            "low": 0.8,
        },
        "healthCheckTimeoutSec": 4,
    },
}


def _ensure_settings_file_exists() -> None:
    if not os.path.exists(SETTINGS_FILE):
        try:
            save_settings(copy.deepcopy(DEFAULT_SETTINGS))
            print(f"✓ Created default browser_agent settings.json at {SETTINGS_FILE}")
        except Exception as e:
            print(f"⚠️ Failed to create browser_agent settings.json: {e}")


def _migrate_legacy_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """Rename any legacy key names to their current form so old settings
    files keep working after a rename. Non-destructive: leaves other keys
    alone."""
    if "downloadType1" in data and "downloadSSMH" not in data:
        data["downloadSSMH"] = data.pop("downloadType1")
    if "downloadType2" in data and "downloadJM" not in data:
        data["downloadJM"] = data.pop("downloadType2")
    return data


def load_settings() -> Dict[str, Any]:
    _ensure_settings_file_exists()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = _migrate_legacy_keys(data or {})
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(data)
        for key in ("downloadSSMH", "downloadJM", "tabArchive"):
            default_block = copy.deepcopy(DEFAULT_SETTINGS.get(key, {}))
            loaded_block = merged.get(key)
            if isinstance(default_block, dict) and isinstance(loaded_block, dict):
                default_block.update(loaded_block)
                merged[key] = default_block

        tab_archive = merged.get("tabArchive")
        if isinstance(tab_archive, dict):
            default_heat = copy.deepcopy(DEFAULT_SETTINGS["tabArchive"].get("heatThresholds", {}))
            loaded_heat = tab_archive.get("heatThresholds")
            if isinstance(loaded_heat, dict):
                default_heat.update(loaded_heat)
            tab_archive["heatThresholds"] = default_heat
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
    patch = _migrate_legacy_keys(dict(patch))

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

    if "downloadSSMH" in patch:
        merged["downloadSSMH"] = _validate_download_ssmh(patch["downloadSSMH"])

    if "downloadJM" in patch:
        merged["downloadJM"] = _validate_download_jm(patch["downloadJM"])

    if "tabArchive" in patch:
        merged["tabArchive"] = _validate_tab_archive(patch["tabArchive"])

    return merged


def _validate_download_ssmh(cfg: Any) -> dict:
    if not isinstance(cfg, dict):
        raise ValueError("downloadSSMH must be an object")
    src = cfg.get("sourceDomains", [])
    dst = cfg.get("downloadDomains", [])
    path = cfg.get("downloadPath", "")
    link_label = cfg.get("linkLabel", "")
    if not isinstance(src, list) or not all(isinstance(d, str) for d in src):
        raise ValueError("downloadSSMH.sourceDomains must be a list of strings")
    if not isinstance(dst, list) or not all(isinstance(d, str) for d in dst):
        raise ValueError("downloadSSMH.downloadDomains must be a list of strings")
    if not isinstance(path, str):
        raise ValueError("downloadSSMH.downloadPath must be a string")
    if not isinstance(link_label, str):
        raise ValueError("downloadSSMH.linkLabel must be a string")
    return {
        "sourceDomains": [d.strip().lower() for d in src if d.strip()],
        "downloadDomains": [d.strip().lower() for d in dst if d.strip()],
        "downloadPath": path.strip(),
        "linkLabel": link_label.strip(),
    }


def _validate_download_jm(cfg: Any) -> dict:
    if not isinstance(cfg, dict):
        raise ValueError("downloadJM must be an object")
    src = cfg.get("sourceDomain", "")
    path = cfg.get("downloadPath", "")
    if not isinstance(src, str):
        raise ValueError("downloadJM.sourceDomain must be a string")
    if not isinstance(path, str):
        raise ValueError("downloadJM.downloadPath must be a string")
    return {
        "sourceDomain": src.strip().lower(),
        "downloadPath": path.strip(),
    }


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


def _validate_tab_archive(cfg: Any) -> dict:
    if not isinstance(cfg, dict):
        raise ValueError("tabArchive must be an object")

    safe_exclude_domains = cfg.get("safeExcludeDomains", [])
    safe_exclude_keywords = cfg.get("safeExcludeKeywords", [])
    heat_thresholds = cfg.get("heatThresholds", {})
    health_check_timeout = cfg.get("healthCheckTimeoutSec", 4)
    embed_model = cfg.get("embedModel", "")
    semantic_top_k = cfg.get("semanticTopK", 120)

    if not isinstance(safe_exclude_domains, list) or not all(isinstance(v, str) for v in safe_exclude_domains):
        raise ValueError("tabArchive.safeExcludeDomains must be a list of strings")
    if not isinstance(safe_exclude_keywords, list) or not all(isinstance(v, str) for v in safe_exclude_keywords):
        raise ValueError("tabArchive.safeExcludeKeywords must be a list of strings")
    if not isinstance(heat_thresholds, dict):
        raise ValueError("tabArchive.heatThresholds must be an object")
    if not isinstance(embed_model, str):
        raise ValueError("tabArchive.embedModel must be a string")

    try:
        high = float(heat_thresholds.get("high", 4.0))
        medium = float(heat_thresholds.get("medium", 2.0))
        low = float(heat_thresholds.get("low", 0.8))
    except (TypeError, ValueError):
        raise ValueError("tabArchive.heatThresholds.high/medium/low must be numbers")

    if not (high > medium > low >= 0):
        raise ValueError("tabArchive.heatThresholds must satisfy: high > medium > low >= 0")

    try:
        health_timeout = int(health_check_timeout)
    except (TypeError, ValueError):
        raise ValueError("tabArchive.healthCheckTimeoutSec must be an integer")
    health_timeout = max(1, min(15, health_timeout))

    try:
        semantic_top_k_value = int(semantic_top_k)
    except (TypeError, ValueError):
        raise ValueError("tabArchive.semanticTopK must be an integer")
    semantic_top_k_value = max(10, min(500, semantic_top_k_value))

    return {
        "safeExcludeDomains": [v.strip().lower() for v in safe_exclude_domains if v.strip()],
        "safeExcludeKeywords": [v.strip().lower() for v in safe_exclude_keywords if v.strip()],
        "embedModel": embed_model.strip(),
        "semanticTopK": semantic_top_k_value,
        "heatThresholds": {
            "high": high,
            "medium": medium,
            "low": low,
        },
        "healthCheckTimeoutSec": health_timeout,
    }
