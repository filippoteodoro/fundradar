"""Site-specific extractors for varde.com (Varde Partners).

Varde Partners is a global alternative investment firm (~$16B AUM, HQ Minneapolis)
specializing in distressed credit, NPLs, and real estate. Significant Italian activity
including Guber Banca (33% stake), Borio Mangiarotti (20%), and historical Boscolo Hotels.

No public portfolio page (credit fund pattern — same as Ares Management).
News page at /news/ contains press releases about deals, exits, and partnerships.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "varde.com"

URLS = {
    "portfolio": None,  # Credit fund — no public portfolio page
    "team": None,
    "news": "/news/",
}


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract press releases from Varde Partners news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Try common news/press release selectors
    for item in soup.select("article, .news-item, .press-release, .post, .card, .news-card"):
        heading = item.select_one("h2, h3, h4, a")
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        if any(skip in title_lower for skip in ["all news", "view more", "load more", "read more"]):
            continue

        url = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and not href.startswith("javascript"):
                url = urljoin(base_url, href)

        date = None
        date_el = item.select_one("time, .date, [datetime], .published, .post-date")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        summary = None
        desc_el = item.select_one("p, .excerpt, .summary, .description")
        if desc_el and desc_el != heading:
            text = desc_el.get_text(strip=True)
            if len(text) > 20:
                summary = text[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.80,
        })

    # Fallback: look for linked headings if no structured items found
    if not news:
        for link in soup.select("a[href]"):
            heading = link.select_one("h2, h3, h4")
            if not heading:
                # Check if the link itself contains substantial text
                text = link.get_text(strip=True)
                if len(text) < 20 or len(text) > 200:
                    continue
                title = text
            else:
                title = heading.get_text(strip=True)

            if not title or len(title) < 15:
                continue

            title_lower = title.lower()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)

            # Skip navigation links
            if any(skip in title_lower for skip in [
                "varde", "home", "about", "contact", "privacy", "terms",
                "all news", "view more", "menu", "navigation"
            ]):
                continue

            href = link.get("href", "")
            url = urljoin(base_url, href) if href and not href.startswith("javascript") else None

            news.append({
                "title": title,
                "url": url,
                "date": None,
                "summary": None,
                "confidence": 0.70,
            })

    return news


EXTRACTORS = {
    "news": extract_news,
}
