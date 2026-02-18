"""Site-specific extractors for ambientasgr.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "ambientasgr.com"



# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/our-businesses/private-equity/portfolio/",
    "team": "/firm/team/",
    "news": "/search-press/type:press-coverage,press-releases/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Ambienta SGR portfolio page.

    Structure:
    - Row container: .item-portfolio.linkall
    - Name: .portfolio-title
    - Sector: .portfolio-sector (prefixed with "SECTOR")
    - Dates: .portfolio-theme (investment/divestment dates)
    - Link: a href to /portfolio/[company]
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find portfolio rows (div.row with item-portfolio and linkall classes)
    for item in soup.select("div.row.item-portfolio.linkall"):
        # Get company name from column with portfolio-ti class (portfolio-title)
        title_col = item.select_one("[class*='portfolio-ti']")
        if not title_col:
            continue

        name = title_col.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector from column with portfolio-se class (portfolio-sector)
        sector = None
        sector_col = item.select_one("[class*='portfolio-se']")
        if sector_col:
            sector_text = sector_col.get_text(strip=True)
            # Remove "SECTOR" prefix if present
            sector = re.sub(r"^SECTOR\s*", "", sector_text, flags=re.IGNORECASE).strip()
            if sector:
                sector = sector.title()

        # Get link to company page
        website = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and "/portfolio/" in href:
                website = href if href.startswith("http") else urljoin(base_url, href)

        # Check if divested from portfolio-theme columns (portfolio-th class)
        status = "current"
        theme_cols = item.select("[class*='portfolio-th']")
        for theme in theme_cols:
            text = theme.get_text(strip=True).lower()
            if "divestment" in text:
                # Check if there's an actual date (not just "-")
                date_match = re.search(r"divestment\s*date\s*(\d{4}|\w+\s+\d{4})", text, re.I)
                if date_match:
                    status = "exited"
                break

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": status,
            "confidence": 0.85,
        })

    # Also check for card-portfolio structure (featured companies)
    for card in soup.select(".card-portfolio"):
        h2 = card.find("h2", class_="the-title")
        if not h2:
            continue

        name = h2.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector from h6 in sector-country
        sector = None
        sector_el = card.select_one(".sector-country h6")
        if sector_el:
            sector_text = sector_el.get_text(strip=True)
            # Format: "Sector | Country" - take first part
            if "|" in sector_text:
                sector = sector_text.split("|")[0].strip()
            else:
                sector = sector_text

        # Get link
        website = None
        link = card.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and "/portfolio/" in href:
                website = href if href.startswith("http") else urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": None,
            "confidence": 0.85,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
}
