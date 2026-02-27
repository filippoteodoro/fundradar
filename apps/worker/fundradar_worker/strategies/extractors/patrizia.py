"""Site-specific extractors for www.patrizia.ag (PATRIZIA)."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

DOMAIN = "www.patrizia.ag"

URLS = {
    # No reliable public portfolio index page; keep manual portfolio entries only.
    "portfolio": None,
    "team": None,
    # Direct news hubs now return persistent 404. Use RSS fallback for stable monitoring.
    "news": [
        "https://news.google.com/rss/search?q=site%3Apatrizia.ag+PATRIZIA+when%3A30d&hl=en-US&gl=US&ceid=US:en",
    ],
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """No reliable public portfolio index on this domain."""
    return []


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract press-release/news entries from PATRIZIA pages."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for node in soup.select("article, .news-item, .press-item, .teaser, [class*='news'], [class*='press']"):
        title_el = node.select_one("h1, h2, h3, h4, .title, .heading")
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        if not title or len(title) < 10:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)

        link = node.select_one("a[href]")
        if not link:
            continue

        date = None
        date_el = node.select_one("time, .date, [datetime], .published")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(" ", strip=True)

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
