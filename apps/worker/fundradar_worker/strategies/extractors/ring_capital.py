"""Site-specific extractors for ringcp.com (Ring Capital).

Note: Team and News pages require JavaScript rendering and are not extractable
via server-side HTML parsing. Only portfolio extraction is supported.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.ringcp.com"



# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/portfolio/",
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Ring Capital portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_slugs = set()

    # Portfolio companies are in a.company elements with href="/portfolio/[slug]"
    for item in soup.select("a.company[href^='/portfolio/']"):
        # Get company slug from href
        href = item.get("href", "")
        slug = href.replace("/portfolio/", "").strip("/")

        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Get company name from aria-label or slug
        name = item.get("aria-label", "")
        if not name:
            name = slug.replace("-", " ").title()

        # Get description from div.company-title
        description = None
        desc_el = item.select_one("div.company-title")
        if desc_el:
            description = desc_el.get_text(strip=True)

        # Get sector from span.sector-content
        sector = None
        sector_el = item.select_one("span.sector-content")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Get logo URL
        logo_url = None
        img = item.select_one("img.image")
        if img:
            src = img.get("src")
            if src:
                logo_url = src.split("?")[0]  # Remove query params

        # Build detail page URL
        website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description[:300] if description else None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


# Note: Team and News pages require JavaScript rendering
# and cannot be extracted from server-side HTML
EXTRACTORS = {
    "portfolio": extract_portfolio,
}
