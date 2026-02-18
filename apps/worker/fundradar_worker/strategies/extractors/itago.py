"""Site-specific extractors for www.itagopartners.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.itagopartners.it"



# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/investments",
    "team": None,
    "news": "/en/news",
}
def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Itago Partners news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all article elements (news items)
    for article in soup.select("article.post"):
        # Extract title
        title_el = article.select_one("h2")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Extract URL
        url = None
        link = title_el.find("a") or title_el.find_parent("a")
        if link and link.get("href"):
            url = urljoin(base_url, link["href"])

        # Extract date
        date = None
        date_el = article.select_one("time.date-container")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        # Extract summary if available
        summary = None
        summary_el = article.select_one("p")
        if summary_el and summary_el != title_el:
            summary = summary_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        })

    return news


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Itago Partners investments page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Companies are in av-masonry-entry elements with h3 containing name
    for item in soup.select(".av-masonry-entry"):
        h3 = item.select_one("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or name.lower() in seen:
            continue

        seen.add(name.lower())

        # Get description from paragraph if available
        p = item.select_one("p")
        description = p.get_text(strip=True) if p else None

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": description,
            "status": "current",  # Single-section portfolio page = all current
            "confidence": 0.85,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "news": extract_news,
}
