"""Browser Agent — HTTP helpers to resolve a real download link from a
site's overview/download page.

Ported from the 2023 prototype. Site rules (domains, URL formats, the
download-link regex) now come from settings instead of a hardcoded config.
"""
import re
import html
import time
from urllib.parse import urlparse

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}


def parse_url(url: str):
    """Split a URL into (scheme, domain, path)."""
    parsed = urlparse(url)
    return parsed.scheme or "https", parsed.netloc, parsed.path


def match_rule(url: str, site_rules: list):
    """Return the first site rule whose domain + overview format matches ``url``.

    Returns (rule, aid) or (None, None).
    """
    _scheme, domain, path = parse_url(url)
    for rule in site_rules:
        if domain not in rule.get("coverDomains", []):
            continue
        overview = rule.get("overviewUriFormat", "")
        if not overview:
            continue
        pattern = re.escape(overview).replace(re.escape("{aid}"), r"(\d+)")
        m = re.search(pattern, path)
        if m:
            return rule, m.group(1)
    return None, None


def build_download_page_url(scheme: str, domain: str, rule: dict, aid: str) -> str:
    download_fmt = rule.get("downloadUriFormat", "")
    path = download_fmt.replace("{aid}", str(aid))
    return f"{scheme}://{domain}/{path}"


def get_file_meta(download_page_url: str, download_link_regex: str):
    """Fetch the download page, extract the real link + name + size (MB).

    Returns (download_link, file_name, size_mb) or (None, None, None) on failure.
    """
    html_content = _get_html(download_page_url)
    if not html_content:
        return None, None, None
    link = _extract_download_link(html_content, download_link_regex)
    if not link:
        return None, None, None
    size_mb = _get_file_size_mb(link)
    name = _get_file_name(link)
    return link, name, size_mb


def _get_html(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=(10, 30))
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        print(f"[browser_agent] fetch page failed: {e}")
        return None


def _extract_download_link(html_text: str, regex: str):
    if not regex:
        return None
    m = re.search(regex, html_text)
    if not m:
        return None
    link = m.group(1)
    return f"https:{link}" if link.startswith("//") else link


def _get_file_name(download_link: str) -> str:
    m = re.search(r"\?.*?=(.*)", download_link)
    if not m:
        return "download"
    return html.unescape(m.group(1))


def _get_file_size_mb(url: str, max_retries: int = 3, retry_delay: int = 2):
    for attempt in range(max_retries):
        try:
            r = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=(10, 30))
            r.raise_for_status()
            length = r.headers.get("Content-Length")
            if length is None:
                return None
            return int(int(length) / (1024 * 1024))
        except requests.RequestException as e:
            print(f"[browser_agent] size attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    return None
