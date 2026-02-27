"""Site-specific extractors for www.oaktreecapital.com (Oaktree Capital Management)."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

DOMAIN = "www.oaktreecapital.com"

URLS = {
    # No reliable public portfolio index page; keep manual portfolio entries only.
    "portfolio": None,
    "team": None,
    "news": "/insights/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """No reliable public portfolio index on this domain."""
    return []


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract insights/news-like items from Oaktree's insights page."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for node in soup.select("article, .card, .insight, .news-item, [class*='insight'], [class*='news']"):
        title_el = node.select_one("h1, h2, h3, h4, .title, .heading")
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        if not title or len(title) < 12:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)

        link = node.select_one("a[href]")
        if not link:
            continue
        url = urljoin(base_url, link.get("href", ""))

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
                "url": url,
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
