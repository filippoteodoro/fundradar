"""Site-specific extractors for meritosgr.it.

Merito's investments/news pages are rendered via a WordPress AJAX plugin, so the
server-rendered HTML shell is often empty. We monitor WP JSON endpoints directly
for portfolio/news and parse popup-based team cards from the team page HTML.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    import requests
except Exception:  # pragma: no cover - requests is available in worker runtime
    requests = None

DOMAIN = "www.meritosgr.it"

# API-backed content changes without visible HTML shell changes.
ALWAYS_EXTRACT = True

PORTFOLIO_API_URL = (
    "https://www.meritosgr.it/wp-json/wp/v2/posts"
    "?per_page=100&tags=10,11&_fields=id,date,link,title,excerpt,categories,tags,_embedded"
)
NEWS_API_URL = (
    "https://www.meritosgr.it/wp-json/wp/v2/posts"
    "?per_page=50&categories=6&_fields=id,date,link,title,excerpt,categories,tags,_embedded"
)

URLS = {
    "portfolio": "/investimenti/?fr_src=fundradar",
    "team": "/team/?fr_src=fundradar",
    "news": "/news/?fr_src=fundradar",
}


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_wp_posts(raw: str) -> list[dict]:
    if not raw or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _fetch_wp_posts(url: str) -> list[dict]:
    if requests is None:
        return []
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
            },
        )
        if response.status_code != 200:
            return []
        return _parse_wp_posts(response.text)
    except Exception:
        return []


def _extract_wp_title(post: dict) -> str:
    title_obj = post.get("title")
    if isinstance(title_obj, dict):
        return _normalize_text(title_obj.get("rendered"))
    return _normalize_text(title_obj)


def _extract_wp_excerpt(post: dict) -> str | None:
    excerpt_obj = post.get("excerpt")
    excerpt = None
    if isinstance(excerpt_obj, dict):
        excerpt = excerpt_obj.get("rendered")
    else:
        excerpt = excerpt_obj
    text = _normalize_text(excerpt)
    if not text:
        return None
    return text[:300]


def _role_from_title(title: str | None) -> str | None:
    text = (title or "").lower()
    if not text:
        return None
    if "partner" in text or "founder" in text:
        return "partner"
    if "director" in text:
        return "director"
    if "manager" in text:
        return "manager"
    if "analyst" in text or "associate" in text:
        return "associate"
    return None


def _term_names(post: dict) -> list[str]:
    embedded = post.get("_embedded")
    if not isinstance(embedded, dict):
        return []
    groups = embedded.get("wp:term", [])
    names: list[str] = []
    if not isinstance(groups, list):
        return names
    for group in groups:
        if not isinstance(group, list):
            continue
        for term in group:
            if not isinstance(term, dict):
                continue
            name = _normalize_text(term.get("name"))
            if name:
                names.append(name)
    return names


def _extract_fund_name(post: dict) -> str | None:
    for name in _term_names(post):
        lower = name.lower()
        if "fondo" in lower or "antares" in lower:
            return name
    return None


def _extract_company_name_from_terms(post: dict) -> str | None:
    for name in _term_names(post):
        lower = name.lower()
        if any(
            token in lower
            for token in (
                "news",
                "investimenti",
                "portafoglio",
                "fondo",
                "private debt",
                "antares",
                "merito",
            )
        ):
            continue
        if len(name) >= 3:
            return name
    return None


def _extract_company_name_from_title(title: str) -> str | None:
    if not title:
        return None

    patterns = [
        r"(?i)\b(?:invests in|investe in|investment in|investimento in)\s+([A-Z0-9][^,;:.]+)",
        r"(?i)\b(?:acquisition of|acquisizione di|acquires|acquista)\s+([A-Z0-9][^,;:.]+)",
        r"(?i)\b(?:financing for|finanzia|supports|backs)\s+([A-Z0-9][^,;:.]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            candidate = _normalize_text(match.group(1))
            if candidate and len(candidate) >= 3:
                return candidate
    return None


def _status_from_text(*parts: str | None) -> str:
    text = " ".join(_normalize_text(part) for part in parts if part).lower()
    if any(token in text for token in ("exit", "exited", "disinvest", "sale", "sold", "cessione")):
        return "exited"
    return "current"


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract investments from Merito's WP JSON feed."""
    companies: list[dict] = []
    seen: set[str] = set()

    posts = _parse_wp_posts(html)
    if not posts:
        posts = _fetch_wp_posts(PORTFOLIO_API_URL)
    for post in posts:
        title = _extract_wp_title(post)
        if not title:
            continue

        name = _extract_company_name_from_title(title) or _extract_company_name_from_terms(post)
        if not name:
            continue

        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        excerpt = _extract_wp_excerpt(post)
        companies.append(
            {
                "name": name,
                "sector": _extract_fund_name(post),
                "website": post.get("link"),
                "description": excerpt,
                "status": _status_from_text(title, excerpt),
                "confidence": 0.78,
            }
        )

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from popup cards on the team page."""
    soup = BeautifulSoup(html, "html.parser")
    members: list[dict] = []
    seen: set[str] = set()

    for popup in soup.select("div.paoc-cb-popup-body[data-id^='paoc-popup-']"):
        name = _normalize_text(
            popup.select_one(".paoc-popup-mheading").get_text(" ", strip=True)
            if popup.select_one(".paoc-popup-mheading")
            else None
        )
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        title = _normalize_text(
            popup.select_one(".paoc-secondary-con strong").get_text(" ", strip=True)
            if popup.select_one(".paoc-secondary-con strong")
            else None
        ) or None

        photo_url = None
        img = popup.select_one(".paoc-popup-content img")
        if img and img.get("src"):
            photo_url = urljoin(base_url, img.get("src"))

        members.append(
            {
                "name": name,
                "title": title,
                "role": _role_from_title(title),
                "linkedin": None,
                "email": None,
                "photo_url": photo_url,
                "confidence": 0.90,
            }
        )

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from WP JSON payloads, with legacy HTML fallback."""
    posts = _parse_wp_posts(html)
    if not posts:
        posts = _fetch_wp_posts(NEWS_API_URL)
    if posts:
        news: list[dict] = []
        seen: set[str] = set()
        for post in posts:
            title = _extract_wp_title(post)
            if not title or len(title) < 8:
                continue

            url = post.get("link")
            key = f"{title.lower()}::{url or ''}"
            if key in seen:
                continue
            seen.add(key)

            news.append(
                {
                    "title": title,
                    "url": url,
                    "date": _parse_iso_date(post.get("date")),
                    "summary": _extract_wp_excerpt(post),
                    "confidence": 0.88,
                }
            )
        return news

    soup = BeautifulSoup(html, "html.parser")
    news: list[dict] = []
    seen: set[str] = set()

    for item in soup.select("div.caf-post-layout4"):
        title_el = item.select_one("h2.caf-post-title a")
        if not title_el:
            continue
        title = _normalize_text(title_el.get_text(" ", strip=True))
        if not title:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)

        href = title_el.get("href")
        date_el = item.select_one(".date")
        content_el = item.select_one(".caf-content")

        summary = _normalize_text(content_el.get_text(" ", strip=True) if content_el else None) or None
        if summary:
            summary = summary[:300]

        news.append(
            {
                "title": title,
                "url": urljoin(base_url, href) if href else None,
                "date": _parse_iso_date(date_el.get_text(" ", strip=True) if date_el else None),
                "summary": summary,
                "confidence": 0.80,
            }
        )

    return news


EXTRACTORS = {"portfolio": extract_portfolio, "team": extract_team, "news": extract_news}
