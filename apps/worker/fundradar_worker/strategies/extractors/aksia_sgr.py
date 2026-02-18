"""Site-specific extractors for aksiasgr.com (Aksia SGR).

Aksia SGR uses Essential Grid plugin for portfolio display.
The grid items are li elements with filter classes for sector, fund, and status.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "aksiasgr.com"



# URL paths for monitoring — verified against url_status.json
URLS = {
    "portfolio": "/portfolio/",
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Aksia SGR portfolio page.

    Structure:
    - li.eg-portfolio-wrapper: container for each company
    - filter-*-it classes: filters for sector, fund, status
    - Text content contains company name, status, fund, sector concatenated
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Portfolio items are in li elements with eg-portfolio-wrapper class
    for item in soup.select("li.eg-portfolio-wrapper"):
        classes = item.get("class", [])

        # Extract sector from filter classes
        sector = None
        sector_map = {
            "filter-food": "Food",
            "filter-industrial": "Industrial",
            "filter-healthcare": "Healthcare",
            "filter-fashion-luxury": "Fashion & Luxury",
            "filter-services": "Services",
        }
        for cls in classes:
            for prefix, sector_name in sector_map.items():
                if cls.startswith(prefix):
                    sector = sector_name
                    break
            if sector:
                break

        # Extract status from filter classes
        status = "current"
        if "filter-exited" in str(classes):
            status = "exited"

        # Extract fund from filter classes
        fund = None
        fund_patterns = re.findall(r"filter-aksia-capital-([iv]+)", str(classes))
        if fund_patterns:
            fund_num = fund_patterns[0].upper()
            fund = f"Aksìa Capital {fund_num}"

        # Get company name from text
        # The text is concatenated like "Fornaio del CasaleIn portfolioAksìa Capital VIFood"
        text = item.get_text(strip=True)

        # Split by known patterns to extract company name
        # Pattern: CompanyName + "In portfolio"/"Exited" + FundName + Sector
        name = None

        # Try to find company name by splitting at status markers
        for marker in ["In portfolio", "In Portfolio", "Exited"]:
            if marker in text:
                name = text.split(marker)[0].strip()
                break

        if not name:
            # Fallback: try first significant text portion
            # Skip if it looks like just a sector or fund name
            words = text.split()
            if words:
                name = words[0]

        if not name or len(name) < 2:
            continue

        # Clean up name
        name = name.strip()

        # Skip if looks like a fund name only
        if name.lower().startswith("aksia") or name.lower().startswith("aksìa"):
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get link to company detail page
        website = None
        link = item.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href and "/portfolio/" in href:
                website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": status,
            "fund": fund,
            "confidence": 0.85,
        })

    # Strategy 2: Fallback - look for portfolio links
    if not companies:
        for link in soup.find_all("a", href=re.compile(r"/portfolio/[^/]+/?$")):
            href = link.get("href", "")
            slug = href.rstrip("/").split("/")[-1]
            if slug and slug != "portfolio" and len(slug) > 2:
                name = slug.replace("-", " ").title()
                if name.lower() not in seen_names:
                    seen_names.add(name.lower())
                    companies.append({
                        "name": name,
                        "sector": None,
                        "website": urljoin(base_url, href),
                        "description": None,
                        "status": "current",
                        "fund": None,
                        "confidence": 0.70,
                    })

    # Strategy 3: Generic card/item fallback
    if not companies:
        for card in soup.find_all(["article", "div", "li"], class_=re.compile(r"portfolio|investment|company", re.I)):
            heading = card.find(["h2", "h3", "h4", "strong"])
            if heading:
                name = heading.get_text(strip=True)
                if (name and len(name) > 2 and len(name) < 80
                    and name.lower() not in seen_names
                    and not any(skip in name.lower() for skip in ["menu", "filter", "aksia", "aksìa"])):
                    seen_names.add(name.lower())
                    companies.append({
                        "name": name,
                        "sector": None,
                        "website": None,
                        "description": None,
                        "status": "current",
                        "fund": None,
                        "confidence": 0.60,
                    })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
}
