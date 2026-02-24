"""Site-specific extractors for unitedventures.com (United Ventures SGR).

United Ventures is an Italian VC firm (~€500M AUM, HQ Milan) focused on tech.
Founded by Massimiliano Magrini and Paolo Gesess. Portfolio: Moneyfarm, D-Orbit,
Young Platform, Fiscozen, Musixmatch, Cleafy, Exein.

Portfolio at /portfolio/, team at /team/.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "unitedventures.com"

URLS = {
    "portfolio": "/portfolio/",
    "team": "/team/",
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from United Ventures portfolio page.

    UV uses WordPress portfolio CPT (article.type-portfolio). Company names
    are NOT in text — only derivable from the URL slug of each portfolio item.
    Images have no useful alt text.
    """
    import re

    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Primary: portfolio article items with links
    for article in soup.select("article.type-portfolio, article[class*='portfolio']"):
        link = article.select_one("a[href*='/portfolio/']")
        if not link:
            continue

        href = link.get("href", "")
        # Extract slug from URL path
        match = re.search(r'/portfolio/([^/]+)/?$', href)
        if not match:
            continue

        slug = match.group(1)
        # Skip numeric-only slugs (meaningless IDs)
        if re.match(r'^\d+(-\d+)?$', slug):
            continue

        # Convert slug to title case name
        name = slug.replace('-', ' ').title()
        if not name or len(name) < 2 or name.lower() in seen:
            continue
        seen.add(name.lower())

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": "current",
            "confidence": 0.80,
            "detail_page_url": urljoin(base_url, href),
        })

    # Fallback: any links to /portfolio/ subpages
    if not companies:
        for link in soup.select("a[href*='/portfolio/']"):
            href = link.get("href", "")
            match = re.search(r'/portfolio/([^/]+)/?$', href)
            if not match:
                continue
            slug = match.group(1)
            if re.match(r'^\d+(-\d+)?$', slug):
                continue
            name = slug.replace('-', ' ').title()
            if not name or len(name) < 3 or name.lower() in seen:
                continue
            if name.lower() in ("portfolio", "page"):
                continue
            seen.add(name.lower())
            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.75,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from United Ventures team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    for item in soup.select(
        ".team-member, .person, .card, article, "
        "[class*='team'], [class*='person']"
    ):
        name_el = item.select_one("h2, h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen:
            continue
        if any(skip in name.lower() for skip in ["team", "about", "contact"]):
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
