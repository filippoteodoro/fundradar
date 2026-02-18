"""Site-specific extractors for renaissancealternatives.com (Renaissance Partners)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.renaissancealternatives.com"



# URL paths — verified against live site
URLS = {
    "portfolio": "/portfolio",
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Renaissance Partners portfolio page.

    Companies are in .toggle-portfolio containers with .portfolio-title elements.
    Investment year is in .portfolio-investment-year.
    Description is in .portfolio-body.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Pattern: portfolio-title elements followed by portfolio-info
    for title_el in soup.select(".portfolio-title"):
        name = title_el.get_text(strip=True)
        if not name or len(name) < 2 or name.lower() in seen_names:
            continue

        # Skip common non-company titles
        if name.lower() in ["portfolio", "investments", "current", "realized"]:
            continue

        seen_names.add(name.lower())

        # Find the portfolio-info sibling which contains year and sector
        info_el = title_el.find_next_sibling(class_="portfolio-info")

        # Look for investment year and sector
        year = None
        sector = None
        description = None

        if info_el:
            year_el = info_el.select_one(".portfolio-investment-year")
            if year_el:
                year_text = year_el.get_text(strip=True)
                year_match = re.search(r'\d{4}', year_text)
                if year_match:
                    year = year_match.group()

            sector_el = info_el.select_one(".portfolio-sector")
            if sector_el:
                sector_text = sector_el.get_text(strip=True)
                # Remove "Sector: " prefix
                sector = re.sub(r'^Sector:\s*', '', sector_text).strip()
                if sector:
                    sector = sector[:100]

        # Look for description in portfolio-body
        body_el = title_el.find_next(class_="portfolio-body")
        if body_el:
            p_el = body_el.select_one("p")
            if p_el:
                description = p_el.get_text(strip=True)[:500]

        # This is a single-section portfolio page at /investments showing active holdings
        # No structural indicators (tabs, sections) separate current from exited
        # Default to "current" since the page context implies active portfolio
        status = "current"

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": description,
            "status": status,
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Renaissance Partners team page.

    Note: Team data appears to be loaded dynamically via JavaScript.
    This extractor returns empty list to let generic extractor handle it.
    """
    # The team page doesn't have static team member data in HTML
    # Generic extractor handles this at 66% quality
    return []


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Renaissance Partners news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Look for news article patterns
    for article in soup.select("article, .views-row, .news-item"):
        title_el = article.select_one("h2, h3, h4, .title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        # Extract URL
        url = None
        link = article.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        # Extract date
        date = None
        date_el = article.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
