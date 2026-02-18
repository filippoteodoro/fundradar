"""Site-specific extractors for quattror.com.

QuattroR - Italian private equity firm.
Portfolio companies displayed as logo images in article elements.
Company names extracted from image alt attributes.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.quattrorsgr.it"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/it/portfolio-companies/",
    "team": "/it/people",
    "news": "/it/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from QuattroR portfolio page.

    Structure:
    - article.str__article contains each portfolio company
    - img inside article has company logo
    - alt attribute contains company name (e.g., " CASALASCO MONO")
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    for article in soup.select("article.str__article"):
        img = article.select_one("img")
        if not img:
            continue

        alt = img.get("alt", "").strip()
        src = img.get("src", "")

        # Skip generic/placeholder images
        if not alt or "group" in alt.lower() or len(alt) < 2:
            continue

        # Clean name - remove MONO suffix and extra whitespace
        name = re.sub(r"\s*MONO\s*$", "", alt, flags=re.IGNORECASE).strip()
        name = " ".join(name.split())  # Normalize whitespace

        # Convert to proper case
        # Special handling for acronyms (all caps <= 4 chars stay uppercase)
        words = name.split()
        formatted_words = []
        for word in words:
            if len(word) <= 4 and word.isupper():
                formatted_words.append(word)  # Keep acronyms
            else:
                formatted_words.append(word.title())
        name = " ".join(formatted_words)

        if not name or len(name) < 2:
            continue

        # Skip concatenated headings without spaces (e.g. "Ourportfoliocompanies")
        if " " not in name and len(name) > 15:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen:
            continue
        seen.add(name_lower)

        # Get logo URL
        logo_url = urljoin(base_url, src) if src else None

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": "current",  # Single-section portfolio page = all current
            "logo_url": logo_url,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from QuattroR team page.

    Note: QuattroR's team page doesn't have structured team data.
    Returns an empty list.
    """
    return []


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
