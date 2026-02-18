"""Site-specific extractors for deacapitalaf.com (DeA Capital Alternative Funds SGR)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.deacapitalaf.com"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": "/gruppo/",
    "news": None,
}
def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from DeA Capital Alternative Funds media page.

    Structure:
    - div.post-articles.home-article contains each news card
    - h2/h3/h4 has the title
    - div.post_date has the date in "DD Month YYYY" format
    - a has the article link
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Month name to number mapping
    month_map = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12"
    }

    # Find all article cards
    for article in soup.select("div.post-articles.home-article"):
        # Get title from heading
        title_el = article.find(["h1", "h2", "h3", "h4"])
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_key = title.lower()[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Get URL from link
        url = None
        link = article.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href:
                url = urljoin(base_url, href)

        # Get date from post_date element
        date = None
        date_el = article.find(class_="post_date")
        if date_el:
            date_text = date_el.get_text(strip=True)
            # Parse "DD Month YYYY" format
            date_match = re.search(
                r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
                date_text,
                re.IGNORECASE
            )
            if date_match:
                day, month_name, year = date_match.groups()
                month_num = month_map.get(month_name.lower())
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
