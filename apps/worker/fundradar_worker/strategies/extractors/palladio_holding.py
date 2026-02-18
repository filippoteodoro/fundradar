"""Site-specific extractors for pfh.eu (Palladio Holding / PFH)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.pfh.eu"



# URL paths — verified against live site
URLS = {
    "portfolio": "/private-equity/",
    "team": None,
    "news": "/media",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Palladio Holding private-equity page.

    Companies are linked from /portfolio/{slug}/ URLs.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all links to portfolio pages
    for link in soup.select("a[href*='/portfolio/']"):
        href = link.get("href", "")
        if not href or "/portfolio/" not in href:
            continue

        # Skip non-company pages
        if href.endswith("/portfolio/") or "privacy" in href:
            continue

        # Extract company name from URL slug
        parts = href.rstrip("/").split("/")
        slug = parts[-1] if parts else ""
        if not slug:
            continue

        # Convert slug to proper name
        name = slug.replace("-", " ").title()

        # Special case handling for known names
        name = name.replace("F I L A", "F.I.L.A.").replace("Hds ", "HDS ")
        name = name.replace("Dpa", "DPA").replace("Rcf ", "RCF ")
        name = name.replace("Tch", "TCH").replace("Vei ", "VEI ")

        if not name or len(name) < 2 or name.lower() in seen_names:
            continue

        seen_names.add(name.lower())

        companies.append({
            "name": name,
            "sector": None,
            "website": urljoin(base_url, href),
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Palladio Holding team page.

    Team members are in .t-entry-text-tc containers with:
    - h3.t-entry-title a: Person's name
    - .t-entry-meta span: Title/role
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find all team entries
    for entry in soup.select(".t-entry"):
        # Get name from h3 title
        name_el = entry.select_one("h3.t-entry-title")
        if not name_el:
            continue

        # Get text from link or directly
        name_link = name_el.select_one("a")
        if name_link:
            name = name_link.get_text(strip=True)
        else:
            name = name_el.get_text(strip=True)

        if not name or len(name) < 3 or name.lower() in seen_names:
            continue

        seen_names.add(name.lower())

        # Get title from meta
        title = None
        title_el = entry.select_one(".t-entry-meta span")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if "managing partner" in title_lower:
                role = "partner"
            elif "senior partner" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "associate" in title_lower:
                role = "associate"
            elif "head" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "analyst" in title_lower:
                role = "analyst"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Palladio Holding media/press page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Look for news/article patterns
    for article in soup.select("article, .post, .t-entry, .news-item"):
        title_el = article.select_one("h2 a, h3 a, h4 a, .t-entry-title a")
        if not title_el:
            title_el = article.select_one("h2, h3, h4, .t-entry-title")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        # Extract URL
        url = None
        if title_el.name == "a":
            url = title_el.get("href")
        else:
            link = article.select_one("a[href]")
            if link:
                url = link.get("href")
        if url:
            url = urljoin(base_url, url)

        # Extract date
        date = None
        date_el = article.select_one("time, .date, [datetime], .t-entry-date")
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
