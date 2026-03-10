"""Site-specific extractors for blackstone.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.blackstone.com"

# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": None,
    "news": ["/news/press/", "/en/news"],
}
def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Blackstone news page.

    Structure:
    - article.bx-article-card contains each news item
    - h2/h3 has the title
    - a has the news article link
    - Element with "date" in class has the date (e.g., "January 30, 2026")
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Month name to number mapping

    # Strategy 1: article.bx-article-card (used on /en/news)
    for card in soup.select("article.bx-article-card"):
        title_el = card.find(["h2", "h3", "h4"])
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_key = title.lower()[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        url = None
        link = card.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and "/news/" in href:
                url = urljoin(base_url, href)

        date = None
        date_el = card.find(class_=lambda x: x and "date" in str(x).lower())
        if date_el:
            date_text = date_el.get_text(strip=True)
            date_match = re.search(
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
                date_text,
                re.IGNORECASE
            )
            if date_match:
                month_name, day, year = date_match.groups()
                month_num = _MONTH_NAMES.get(month_name.lower(), "01")
                if month_num:
                    date = f"{year}-{month_num}-{day.zfill(2)}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    # Strategy 2: Press release links (used on /news/press/)
    # Look for links to individual press releases
    if not news:
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            # Match press release article links (slug starts with letter after /news/press/)
            if not re.search(r"/news/press/[a-z]", href, re.IGNORECASE):
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 15:
                continue

            # Skip navigation/filter links
            title_lower = title.lower()
            if any(skip in title_lower for skip in ["press releases", "load more", "see all", "filter", "search"]):
                continue

            title_key = title_lower[:50]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            url = urljoin(base_url, href)

            # Try to find date near the link
            date = None
            parent = link.find_parent(["div", "li", "article", "section"])
            if parent:
                text = parent.get_text(" ", strip=True)
                date_match = re.search(
                    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
                    text,
                    re.IGNORECASE
                )
                if date_match:
                    month_name, day, year = date_match.groups()
                    month_num = _MONTH_NAMES.get(month_name.lower(), "01")
                    if month_num:
                        date = f"{year}-{month_num}-{day.zfill(2)}"

            news.append({
                "title": title,
                "url": url,
                "date": date,
                "summary": None,
                "confidence": 0.85,
            })

    return news

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies - not implemented for this site."""
    return []

def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members - not implemented for this site."""
    return []

EXTRACTORS = {
    "news": extract_news,
    "portfolio": extract_portfolio,
    "team": extract_team,
}
