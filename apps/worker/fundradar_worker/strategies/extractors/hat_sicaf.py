"""Site-specific extractors for hat.it (HAT Sicaf / HAT SGR).

Note: www.hatsicaf.it redirects to hat.it via iframe.
HAT is an Italian private equity firm focused on mid-market investments.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

# Domain matches db.json (redirects via iframe to hat.it)
DOMAIN = "www.hatsicaf.it"

# URL paths for monitoring
URLS = {
    "portfolio": "/portfolio/our-partnership/",
    "team": "/people/our-team/",
    "news": None,  # No dedicated news page found
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from HAT portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for company cards/items
    for item in soup.select(".portfolio-item, .company-card, article, .card, .partnership-item"):
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
        if any(skip in name_lower for skip in ["hat", "portfolio", "menu", "partnership"]):
            continue

        website = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "hat.it" not in href.lower():
                website = href

        sector = None
        sector_el = item.select_one(".sector, .category, .industry")
        if sector_el:
            sector = sector_el.get_text(strip=True)

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

            if any(skip in name_lower for skip in [
                "hat", "portfolio", "partnership", "case", "about", "team", "contact"
            ]):
                continue

            seen_names.add(name_lower)
            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "status": None,
                "confidence": 0.70,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from HAT team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select(".team-member, .person, article, .card"):
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

        if any(skip in name_lower for skip in ["team", "hat", "our team"]):
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


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
