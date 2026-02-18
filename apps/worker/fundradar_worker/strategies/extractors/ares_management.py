"""Site-specific extractors for www.aresmgmt.com (Ares Management).

Note: This site returns 403 Forbidden for plain HTTP requests.
Requires headless browser (Playwright) via domain_policies.json.

Ares Management is a global alternative asset manager with ~$450B AUM.
They have multiple strategies: credit, private equity, real estate, and infrastructure.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.aresmgmt.com"

# URL paths for monitoring - requires headless browser
# Note: Ares does NOT publicly list portfolio companies (primarily a credit fund)
# We monitor news/team pages for signals instead
URLS = {
    "portfolio": None,  # Ares doesn't have a public portfolio page
    "team": "/about-ares-management-corporation/our-team",
    "news": "/news-views",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Ares investments page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for company cards/items
    for item in soup.select(".portfolio-item, .investment-card, .company-card, article, .card"):
        # Get company name
        name_el = item.select_one("h2, h3, h4, .name, .title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Skip navigation items
        if any(skip in name_lower for skip in ["ares", "portfolio", "menu", "investments"]):
            continue

        # Get website
        website = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "ares" not in href.lower():
                website = href

        # Get sector
        sector = None
        sector_el = item.select_one(".sector, .category, .industry")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Get description
        description = None
        desc_el = item.select_one("p, .description, .summary")
        if desc_el:
            description = desc_el.get_text(strip=True)[:300]

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",
            "confidence": 0.80,
        })

    # Fallback: look for company names in headings
    if not companies:
        for heading in soup.find_all(["h2", "h3", "h4"]):
            name = heading.get_text(strip=True)
            if not name or len(name) < 3 or len(name) > 80:
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue

            # Skip section headers
            if any(skip in name_lower for skip in [
                "ares", "portfolio", "investments", "our", "strategy",
                "team", "news", "about", "contact"
            ]):
                continue

            seen_names.add(name_lower)
            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",  # Portfolio page entries
                "confidence": 0.70,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Ares leadership page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select(".team-member, .person, .leader, article"):
        name_el = item.select_one("h2, h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or len(name.split()) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        if any(skip in name_lower for skip in ["leadership", "team", "ares"]):
            continue

        title = None
        title_el = item.select_one(".title, .role, .position, p")
        if title_el and title_el != name_el:
            title = title_el.get_text(strip=True)

        photo_url = None
        img = item.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.80,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from Ares news/insights page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for item in soup.select(".news-item, article, .card, .press-release"):
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

        if any(skip in title_lower for skip in ["all news", "view more", "load more"]):
            continue

        url = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and not href.startswith("javascript"):
                url = urljoin(base_url, href)

        date = None
        date_el = item.select_one("time, .date, [datetime]")
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
