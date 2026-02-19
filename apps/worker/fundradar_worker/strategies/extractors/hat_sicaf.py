"""Site-specific extractors for hatsicaf.it (HAT Sicaf).

`www.hatsicaf.it` pages are lightweight iframe wrappers. This extractor resolves
the underlying `hat.it` pages (live first, cached snapshots as fallback) and
reuses the production-tested `hat_sgr` parsers for portfolio/team/news.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .hat_sgr import extract_news as _hat_extract_news
from .hat_sgr import extract_portfolio as _hat_extract_portfolio
from .hat_sgr import extract_team as _hat_extract_team

# Domain matches db.json
DOMAIN = "www.hatsicaf.it"

# Wrapper HTML is effectively static, while real content is on hat.it.
ALWAYS_EXTRACT = True

# Keep monitored URLs on hatsicaf.it so the slug mapping stays correct.
URLS = {
    "portfolio": "/portfolio/our-partnership/",
    "team": "/people/our-team/",
    "news": "/blog/",
}

_TARGET_URLS = {
    "portfolio": "https://hat.it/portfolio/our-partnership/",
    "team": "https://hat.it/people/our-team/",
}

_NEWS_TARGETS = [
    "https://hat.it/press/",
    "https://hat.it/blog/",
]

_REQUEST_TIMEOUT_SECONDS = 20


def _repo_root() -> Path:
    # .../apps/worker/fundradar_worker/strategies/extractors/hat_sicaf.py -> repo root
    return Path(__file__).resolve().parents[5]


def _derived_dir() -> Path:
    return _repo_root() / "data" / "derived"


def _is_wrapper_html(html: str) -> bool:
    """Detect hatsicaf iframe wrappers."""
    if not html or len(html) > 2000:
        return False

    soup = BeautifulSoup(html, "html.parser")
    iframe = soup.find("iframe")
    title = (soup.title.string or "").strip().lower() if soup.title else ""
    iframe_src = (iframe.get("src") or "").lower() if iframe else ""

    return bool(iframe and ("hatsicaf.it" in title or "hat.it" in iframe_src))


def _fetch_live_html(url: str) -> str | None:
    """Fetch a target URL directly from hat.it."""
    try:
        response = requests.get(
            url,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            headers={
                "User-Agent": "Fundradar/1.0 (https://fundradar.io; research purposes)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        if response.status_code == 200 and response.text:
            return response.text
    except requests.RequestException:
        return None
    return None


@lru_cache(maxsize=1)
def _load_snapshots_data() -> tuple[dict, dict]:
    """
    Load snapshots index once and keep it cached.

    Returns:
        (url_index, snapshots_by_id)
    """
    snapshots_path = _derived_dir() / "snapshots.json"
    if not snapshots_path.exists():
        return {}, {}

    try:
        with open(snapshots_path, encoding="utf-8") as f:
            data = json.load(f)
        url_index = data.get("url_index", {}) or {}
        snapshots = data.get("snapshots", []) or []
        by_id = {snap.get("id"): snap for snap in snapshots if snap.get("id")}
        return url_index, by_id
    except Exception:
        return {}, {}


def _read_snapshot_html(snapshot_id: str, blob_hash: str | None) -> str | None:
    """Read HTML from blob storage or snapshots_html fallback."""
    derived = _derived_dir()

    if blob_hash:
        blob_path = derived / "blobs" / f"{blob_hash}.html"
        if blob_path.exists():
            try:
                return blob_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

    html_path = derived / "snapshots_html" / f"{snapshot_id}.html"
    if html_path.exists():
        try:
            return html_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    return None


@lru_cache(maxsize=16)
def _load_cached_html(url: str) -> str | None:
    """
    Load cached HTML for a URL from local snapshot storage.

    Works with both modern blob-backed snapshots and older snapshots_html files.
    """
    url_index, snapshots_by_id = _load_snapshots_data()

    # Primary lookup via snapshots url_index.
    snapshot_ids = url_index.get(url) or []
    for snapshot_id in reversed(snapshot_ids):
        snap = snapshots_by_id.get(snapshot_id, {})
        html = _read_snapshot_html(snapshot_id, snap.get("blob_hash"))
        if html:
            return html

    # Fallback lookup by historical filename suffix based on URL md5 hash.
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    snapshots_html_dir = _derived_dir() / "snapshots_html"
    if snapshots_html_dir.exists():
        candidates = sorted(snapshots_html_dir.glob(f"*-{url_hash}.html"), reverse=True)
        for candidate in candidates:
            try:
                html = candidate.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if html:
                return html

    return None


def _resolve_target_html(target_url: str) -> str | None:
    """Resolve real page HTML from live fetch, then local cache fallback."""
    live_html = _fetch_live_html(target_url)
    if live_html and not _is_wrapper_html(live_html):
        return live_html

    cached_html = _load_cached_html(target_url)
    if cached_html:
        return cached_html

    return live_html


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio entries from hatsicaf wrapper (via hat.it page)."""
    effective_html = html
    effective_url = base_url

    if _is_wrapper_html(html):
        target_url = _TARGET_URLS["portfolio"]
        resolved_html = _resolve_target_html(target_url)
        if resolved_html:
            effective_html = resolved_html
            effective_url = target_url

    return _hat_extract_portfolio(effective_html, effective_url)


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from hatsicaf wrapper (via hat.it page)."""
    effective_html = html
    effective_url = base_url

    if _is_wrapper_html(html):
        target_url = _TARGET_URLS["team"]
        resolved_html = _resolve_target_html(target_url)
        if resolved_html:
            effective_html = resolved_html
            effective_url = target_url

    return _hat_extract_team(effective_html, effective_url)


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from hatsicaf wrapper using hat.it press/blog pages."""
    if not _is_wrapper_html(html):
        return _hat_extract_news(html, base_url)

    items = []
    seen_titles = set()

    for target_url in _NEWS_TARGETS:
        target_html = _resolve_target_html(target_url)
        if not target_html:
            continue

        for item in _hat_extract_news(target_html, target_url):
            title = (item.get("title") or "").strip()
            key = title.lower()
            if not title or key in seen_titles:
                continue
            seen_titles.add(key)
            items.append(item)

    return items


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}

