"""Site-specific extractors for gradientesgr.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.gradientesgr.it"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": "/il-team/",
    "news": "/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Gradiente SGR portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Portfolio items: a.post-item
    for item in soup.select("a.post-item"):
        # Company name in h2.alt-indent
        name_el = item.select_one("h2.alt-indent")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2 or name in seen:
            continue
        # Skip trailing-underscore artifacts from image refs
        if name.endswith("_"):
            continue
        seen.add(name)

        # Capture detail page URL for potential enrichment
        # Detail pages have structured metadata: sector, status, region, year
        detail_url = None
        href = item.get("href")
        if href:
            detail_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": None,  # Mixed current/exited — status only on detail pages
            "detail_page_url": detail_url,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Gradiente SGR team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Team members: div.box-v contains each person
    for box in soup.select("div.box-v"):
        # Name: strong.title (in uppercase)
        name_el = box.select_one("strong.title")
        if not name_el:
            continue

        name_raw = name_el.get_text(strip=True)
        if not name_raw or len(name_raw) < 3:
            continue

        # Convert from UPPERCASE to Title Case
        name = name_raw.title()

        # Title: span.subtitle
        title = None
        title_el = box.select_one("span.subtitle")
        if title_el:
            title = title_el.get_text(strip=True)

        # Photo URL
        photo_url = None
        img = box.select_one("div.rib-image img")
        if img:
            src = img.get("data-lazy-src") or img.get("src")
            if src and not src.startswith("data:"):
                photo_url = urljoin(base_url, src)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if any(k in title_lower for k in ["partner", "fondatore", "founder"]):
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower or "cfo" in title_lower:
                role = "manager"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "associate"
            elif "assistant" in title_lower or "office" in title_lower:
                role = "admin"

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


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
