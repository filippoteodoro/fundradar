"""Site-specific extractors for www.patrizia.ag (PATRIZIA)."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

DOMAIN = "www.patrizia.ag"

URLS = {
    # No reliable public portfolio index page; keep manual portfolio entries only.
    "portfolio": None,
    "team": None,
    # Verified 2026-02-27: old /en/news-and-press/* paths return 404.
    # Current working press hub:
    "news": [
        "/en/press-releases-pr/",
    ],
}


def _parse_date(value: str | None) -> str | None:
    """Normalize common date formats to YYYY-MM-DD."""
    if not value:
        return None

    raw = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    if "T" in raw and re.match(r"^\d{4}-\d{2}-\d{2}T", raw):
        return raw.split("T", 1)[0]

    # TYPO3 list pages use dd/mm/yyyy.
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw)
    if m:
        day, month, year = m.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    return None


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """No reliable public portfolio index on this domain."""
    return []


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract press-release/news entries from PATRIZIA pages."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen_keys: set[str] = set()

    # TYPO3 list page structure for /en/press-releases-pr/
    for node in soup.select(".news-recent--item"):
        link = node.select_one(".news-recent--header a[href], h5 a[href], a[href*='/news-detail/']")
        if not link:
            continue

        title = (link.get("title") or link.get_text(" ", strip=True) or "").strip()
        if not title or len(title) < 10:
            continue

        url = urljoin(base_url, link.get("href", ""))
        key = (url or title).lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)

        date = None
        date_el = node.select_one("time[datetime], time, .news-recent--date")
        if date_el:
            date = _parse_date(date_el.get("datetime") or date_el.get_text(" ", strip=True))

        summary = None
        summary_el = node.select_one(
            ".news-recent--description [itemprop='description'] p, "
            ".news-recent--description p, "
            ".news-recent--description-mobile p"
        )
        if summary_el:
            summary = summary_el.get_text(" ", strip=True)[:300]

        items.append(
            {
                "title": title,
                "url": url,
                "date": date,
                "summary": summary,
                "confidence": 0.9,
            }
        )

    if items:
        return items

    for node in soup.select("article, .news-item, .press-item, .teaser, [class*='news'], [class*='press']"):
        title_el = node.select_one("h1, h2, h3, h4, .title, .heading")
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        if not title or len(title) < 10:
            continue
        key = title.lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)

        link = node.select_one("a[href]")
        if not link:
            continue

        date = None
        date_el = node.select_one("time, .date, [datetime], .published")
        if date_el:
            date = _parse_date(date_el.get("datetime") or date_el.get_text(" ", strip=True))

        summary = None
        summary_el = node.select_one("p, .summary, .excerpt, .description")
        if summary_el and summary_el != title_el:
            summary = summary_el.get_text(" ", strip=True)[:300]

        items.append(
            {
                "title": title,
                "url": urljoin(base_url, link.get("href", "")),
                "date": date,
                "summary": summary,
                "confidence": 0.8,
            }
        )

    return items


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "news": extract_news,
}
