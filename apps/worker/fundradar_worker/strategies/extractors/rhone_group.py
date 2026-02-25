"""Site-specific extractors for rhonegroup.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.rhonegroup.com"

# URL paths for monitoring — verified 2026-02-25
# Portfolio page uses WPBakery grid layout
URLS = {
    "portfolio": "/portfolio/",
    "team": None,
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Rhone Group's portfolio page.

    Structure: WPBakery grid with company logos and links to /portfolio/{slug}/.
    All visible companies are active portfolio (no realized section on main page).
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Try portfolio links first
    for link in soup.select("a[href*='/portfolio/']"):
        href = link.get("href", "")
        if href.rstrip("/") == "/portfolio" or href.rstrip("/") == "/portfolio/":
            continue

        # Get name from heading or link text
        name = None
        for tag in ["h3", "h4", "h2"]:
            el = link.find(tag)
            if el:
                name = el.get_text(strip=True)
                break
        if not name:
            # Try getting name from image alt text
            img = link.find("img")
            if img and img.get("alt"):
                alt = img.get("alt", "").strip()
                # Skip generic alt text
                if alt and len(alt) > 1 and alt.lower() not in ["logo", "image"]:
                    name = alt
        if not name:
            name = link.get_text(strip=True)

        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        detail_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": "current",
            "detail_page_url": detail_url,
            "confidence": 0.80,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
}
