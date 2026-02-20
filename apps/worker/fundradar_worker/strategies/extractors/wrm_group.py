"""Site-specific extractors for wrmgroup.net."""
from bs4 import BeautifulSoup

DOMAIN = "wrmgroup.net"



# URL paths — verified against live site
URLS = {
    "portfolio": "/track-record/",
    "team": None,
    "news": "/media/?fr_src=fundradar",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from WRM Group investments page (mixed current/exited)."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Portfolio items: article.m-editorial
    for article in soup.select("article.m-editorial"):
        # Company name from h2
        h2 = article.select_one("h2")
        if not h2:
            continue

        name = h2.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip duplicates (some companies appear multiple times with different deals)
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get description from p element
        description = None
        p = article.select_one(".m-editorial__text p")
        if p:
            description = p.get_text(strip=True)[:500]

        # Get year from caption
        year = None
        caption = article.select_one(".m-editorial__caption")
        if caption:
            year = caption.get_text(strip=True)

        # WRM Group track record is mixed - shows both current and exited deals.
        # No consistent structural indicators exist for status.
        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": description,
            "status": None,  # Mixed track record - cannot reliably determine status
            "investment_year": year,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members - not implemented for this site."""
    return []


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/media items from WRM Group media page.

    Structure: article.m-editorial (same as portfolio)
    - Title: h2
    - Year: strong.m-editorial__caption
    - URL: a.m-cta in .m-editorial__cta
    """
    soup = BeautifulSoup(html, "html.parser")
    from urllib.parse import urljoin

    news = []
    seen_titles = set()

    # News items are in article.m-editorial elements
    for article in soup.select("article.m-editorial"):
        # Get title from h2
        h2 = article.select_one("h2")
        if not h2:
            continue

        title = h2.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get year from strong.m-editorial__caption
        date = None
        caption = article.select_one("strong.m-editorial__caption")
        if caption:
            date = caption.get_text(strip=True)

        # Get URL from a.m-cta
        url = None
        cta = article.select_one(".m-editorial__cta a.m-cta")
        if cta:
            href = cta.get("href")
            if href:
                url = urljoin(base_url, href)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
