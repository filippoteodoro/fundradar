"""Site-specific extractors for eosimgroup.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "eosimgroup.com"



# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/investments",
    "team": "/management",
    "news": None,
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from EOS IM management team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Team members: div.views-row
    for row in soup.select("div.views-row"):
        # Name: div.name
        name_el = row.select_one("div.name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Title/Role: div.role
        title = None
        title_el = row.select_one("div.role")
        if title_el:
            title = title_el.get_text(strip=True)

        # Photo URL
        photo_url = None
        img = row.select_one("div.wrapper-image img")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        # Description (for context)
        description = None
        desc_el = row.select_one("div.description p")
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if any(k in title_lower for k in ["partner", "founder", "ceo"]):
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower or "head" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"
            elif "advisor" in title_lower or "advisory" in title_lower:
                role = "advisor"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract investment vehicles from EOS IM investments page.

    Note: EOS IM shows their funds rather than portfolio companies.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Find fund links
    seen = set()
    for link in soup.select("a[href*='/investments/']"):
        href = link.get("href", "")
        # Skip general pages, only get fund-specific pages
        if not href or href.endswith("/investments") or href.endswith("/investments/"):
            continue
        if "/investment-approach" in href or href.endswith("/clean-energy") or href.endswith("/private-equity"):
            continue

        name = link.get_text(strip=True)
        if not name or len(name) < 3 or name in seen:
            continue
        seen.add(name)

        # Determine sector from URL path
        sector = None
        if "/clean-energy/" in href:
            sector = "Clean Energy Infrastructure"
        elif "/private-equity/" in href:
            sector = "Private Equity"

        companies.append({
            "name": name,
            "sector": sector,
            "website": urljoin(base_url, href),
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
