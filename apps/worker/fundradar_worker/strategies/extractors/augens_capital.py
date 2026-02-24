"""Site-specific extractors for www.augenscapital.com (Augens Capital).

Augens Capital is an Italian PE firm (founded 2014, HQ Milan) focused on
majority MBO and growth equity in the Italian mid-market. Sectors: healthcare,
consumer, business services, industrial.

Portfolio page at /portfolio/ shows current investments (SRG Associati, HOFI,
Bomaki, Delta Med). Team page at /team/. No dedicated news page.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.augenscapital.com"

URLS = {
    "portfolio": "/portfolio/",
    "team": "/team/",
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Augens Capital portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Try common portfolio card selectors
    for item in soup.select(
        "article, .portfolio-item, .investment, .card, .post, "
        ".elementor-post, .jet-listing-grid__item, .e-loop-item"
    ):
        heading = item.select_one("h2, h3, h4, a.elementor-post__title")
        if not heading:
            continue

        name = heading.get_text(strip=True)
        if not name or len(name) < 2 or name.lower() in seen:
            continue

        # Skip navigation text
        if name.lower() in ("investments", "portfolio", "back", "view all"):
            continue

        seen.add(name.lower())

        website = None
        link = item.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "augenscapital.com" not in href:
                website = href

        description = None
        desc_el = item.select_one("p, .excerpt, .summary, .description")
        if desc_el and desc_el != heading:
            text = desc_el.get_text(strip=True)
            if len(text) > 15:
                description = text[:500]

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page shows current holdings
            "confidence": 0.85,
        })

    # Fallback: look for linked headings
    if not companies:
        for link in soup.select("a[href*='/portfolio/']"):
            text = link.get_text(strip=True)
            if not text or len(text) < 3 or text.lower() in seen:
                continue
            if text.lower() in ("investments", "portfolio", "back", "view all"):
                continue
            seen.add(text.lower())
            companies.append({
                "name": text,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.70,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Augens Capital team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    for item in soup.select(
        ".team-member, .person, .card, article, "
        ".elementor-widget-container, .jet-listing-grid__item"
    ):
        name_el = item.select_one("h2, h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen:
            continue
        seen.add(name.lower())

        title = None
        title_el = item.select_one(".title, .position, .role, p")
        if title_el and title_el != name_el:
            title = title_el.get_text(strip=True)

        linkedin = None
        for a in item.select("a[href*='linkedin']"):
            linkedin = a.get("href")
            break

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": None,
            "confidence": 0.85,
        })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
