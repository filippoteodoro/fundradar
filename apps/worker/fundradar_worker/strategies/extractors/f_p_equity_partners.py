"""Site-specific extractors for fp-equity-partners.com (F&P Equity Partners).

Italian PE fund focused on Italian SMEs.
Portfolio at /portafoglio-investimenti/ uses WordPress with
div.single-portafoglio containers, h1 company names, and
collapsible detail sections with descriptions and website links.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.fp-equity-partners.com"


# URL paths — verified against live site
URLS = {
    "portfolio": "/portafoglio-investimenti/",
    "team": None,
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from F&P Equity Partners portfolio page.

    Structure: div.single-portafoglio elements with:
    - h1 with class txt-title-bold-white-60 for company name
    - p tags for description text
    - Collapsible sections (div.collapse) with detailed info
    - External links (a[href]) for company websites
    - Exit indicators: "ceduto la partecipazione" in text
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for entry in soup.select("div.single-portafoglio"):
        # Get company name from h1
        h1 = entry.find("h1")
        if not h1:
            continue

        name = h1.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Skip section headers
        if name_lower in ("portafoglio", "portfolio", "investimenti"):
            continue

        # Get description from first visible p tags (not inside collapse)
        description = None
        # Look for p tags in the visible area (before collapse div)
        content_div = entry.select_one("div.rounded-content-box")
        if content_div:
            # Get first mt-half-default div (visible section)
            visible = content_div.select_one("div.mt-half-default")
            if visible:
                for p in visible.find_all("p"):
                    text = p.get_text(strip=True)
                    # Skip empty, image-only, or very short paragraphs
                    if text and len(text) > 20 and not p.find("img"):
                        description = text[:500]
                        break

        # If no description found in visible, try any p with substantial text
        if not description:
            for p in entry.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 30 and not p.find("img"):
                    description = text[:500]
                    break

        # Get company website from external links
        website = None
        for a in entry.find_all("a", href=True):
            href = a.get("href", "")
            if href.startswith("http") and "fp-equity" not in href.lower():
                website = href
                break

        # Detect exit status from text
        status = "current"
        full_text = entry.get_text(separator=" ", strip=True).lower()
        if re.search(r"ceduto la partecipazione|ha ceduto|exit realizzat", full_text):
            status = "exited"

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description,
            "status": status,
            "confidence": 0.85,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
}
