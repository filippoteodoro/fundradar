"""Site-specific extractors for eurekaventure.it.

Note: This site requires a browser User-Agent header to access.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.eurekaventure.it"



# URL paths — verified against live site
URLS = {
    "portfolio": "/portfolio",
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Eureka Venture portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Each portfolio item is in div.cbp-item with fund class
    for item in soup.select("div.cbp-item"):
        # Get company name from a.sup-title > h4
        title_el = item.select_one("a.sup-title h4")
        if not title_el:
            continue

        name = title_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Get fund name from div.sup-meta
        fund = None
        meta_el = item.select_one("div.sup-meta")
        if meta_el:
            fund = meta_el.get_text(strip=True)

        # Note: a.sup-title href points to internal detail page, not company website

        companies.append({
            "name": name,
            "sector": None,  # Fund name is not a sector; actual sector not available
            "website": None,  # Actual company website not available on listing
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Eureka Venture company/team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Team members are in a.cbp-caption elements
    for item in soup.select("a.cbp-caption"):
        # Get name from div.cbp-l-caption-title
        name_el = item.select_one("div.cbp-l-caption-title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Get title from div.cbp-l-caption-desc
        title = None
        title_el = item.select_one("div.cbp-l-caption-desc")
        if title_el:
            title = title_el.get_text(strip=True)

        # Can also get from data-title attribute (format: "Name // Title")
        data_title = item.get("data-title", "")
        if " // " in data_title and not title:
            parts = data_title.split(" // ", 1)
            if len(parts) > 1:
                title = parts[1]

        # Get photo URL
        photo_url = None
        img = item.select_one("img")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower or "chairman" in title_lower or "chairwoman" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "analyst" in title_lower or "associate" in title_lower:
                role = "associate"
            elif "board" in title_lower or "independent" in title_lower.lower():
                role = "board"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from Eureka Venture press page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []

    # News items are in div.catItemView
    for item in soup.select("div.catItemView"):
        # Get title from div.catItemTitle
        title_el = item.select_one("div.catItemTitle")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # Get date from div.catItemDateCreated
        date = None
        date_el = item.select_one("div.catItemDateCreated")
        if date_el:
            date = date_el.get_text(strip=True)

        # Get source from span.catItemExtraFieldsValue---
        source = None
        source_el = item.select_one("span.catItemExtraFieldsValue---")
        if source_el:
            source = source_el.get_text(strip=True)

        # Get download link
        url = None
        link = item.select_one("a[href*='download']")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": f"Published in: {source}" if source else None,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
