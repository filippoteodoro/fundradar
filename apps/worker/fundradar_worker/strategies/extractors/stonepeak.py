"""Site-specific extractors for stonepeak.com (Stonepeak)."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

DOMAIN = "stonepeak.com"

URLS = {
    # No reliable public portfolio index page; keep manual portfolio entries only.
    "portfolio": None,
    "team": None,
    "news": "/news/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """No reliable public portfolio index on this domain."""
    return []


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract Stonepeak news items."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for link in soup.select("a[href*='/news/']"):
        href = (link.get("href") or "").strip()
        if not href:
            continue
        if href.rstrip("/") == "/news":
            continue

        title_el = link.select_one("h1, h2, h3, h4")
        title = (title_el.get_text(" ", strip=True) if title_el else link.get_text(" ", strip=True)).strip()
        if not title or len(title) < 10:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)

        card = link.parent if getattr(link, "parent", None) else link
        date = None
        date_el = card.select_one("time, .date, [datetime], .published") if hasattr(card, "select_one") else None
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(" ", strip=True)

        summary = None
        summary_el = card.select_one("p, .summary, .excerpt") if hasattr(card, "select_one") else None
        if summary_el:
            summary = summary_el.get_text(" ", strip=True)[:300]

        items.append(
            {
                "title": title,
                "url": urljoin(base_url, href),
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
