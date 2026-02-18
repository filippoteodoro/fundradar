"""Site-specific extractors for invitalia.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.invitalia.it"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": None,
    "news": "/en/news",
}
def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Invitalia news-media page.

    Structure:
    - article.card contains each news card
    - h3 > a has the title and link
    - p.card-text has the summary
    - No dates available on listing page
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all article cards
    for article in soup.select("article.card"):
        # Get title and link from h3 > a
        title_link = article.select_one("h3 a")
        if not title_link:
            continue

        title = title_link.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_key = title.lower()[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Get URL
        url = None
        href = title_link.get("href", "")
        if href:
            url = urljoin(base_url, href)

        # Get date from span.data.pe-3 (format: "DD month YYYY", e.g. "15 january 2024")
        date = None
        date_el = article.select_one("span.data.pe-3")
        if not date_el:
            date_el = article.select_one("span.data")
        if date_el:
            date = date_el.get_text(strip=True)

        # Get summary from card-text
        summary = None
        summary_el = article.select_one("p.card-text")
        if summary_el:
            summary = summary_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.80,
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
