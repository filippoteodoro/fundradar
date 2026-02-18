"""Site-specific extractors for www.equiterspa.com (Equiter).

Equiter uses a WordPress site with portfolio companies listed in p tags.
Each company entry has the name in a <strong> tag and an optional link.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.equiterspa.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/en/investment/investiments-in-holding-companies/",
    "team": None,
    "news": "/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Equiter portfolio page.

    Structure:
    - p.tiny-font.blue-color: container for each company
    - strong: company name
    - a: optional link to company website
    - Text after name: description with stake info
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Portfolio companies are in p tags with specific classes
    for p in soup.select("p.tiny-font.blue-color"):
        # Get company name from strong tag
        strong = p.select_one("strong")
        if not strong:
            continue

        name = strong.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip section headers (end with colon or are category labels)
        if name.endswith(":"):
            continue
        name_lower = name.lower()
        if name_lower.rstrip(":") in {
            "infrastrutture", "rigenerazione urbana", "piccole e medie imprese",
            "investimenti", "portfolio", "aziende", "società", "settori",
        }:
            continue

        # Dedupe
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get website link
        website = None
        link = p.select_one("a")
        if link:
            href = link.get("href", "")
            if href.startswith("http"):
                website = href

        # Get description (full text minus the name and link text)
        full_text = p.get_text(strip=True)
        # Remove the name from the start
        desc = full_text
        if desc.startswith(name):
            desc = desc[len(name):].strip()
        # Remove common link text from end
        for suffix in ["Vai al sito", "Vai alla pagina"]:
            if desc.endswith(suffix):
                desc = desc[:-len(suffix)].strip()

        # Extract sector from description
        sector = None
        sector_patterns = [
            (r"multi-utility", "Utilities"),
            (r"agricol[ao]", "Agriculture"),
            (r"ospedale|sanità", "Healthcare"),
            (r"residenzial[ei]|housing", "Real Estate"),
            (r"energia|energy", "Energy"),
        ]
        for pattern, sector_name in sector_patterns:
            if re.search(pattern, desc, re.IGNORECASE):
                sector = sector_name
                break

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": desc[:500] if desc else None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
}
