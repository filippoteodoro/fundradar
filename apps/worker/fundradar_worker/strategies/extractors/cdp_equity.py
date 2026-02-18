"""Site-specific extractors for cdp.it (CDP Equity)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# CRITICAL: Domain must match exactly
DOMAIN = "www.cdp.it"



# URL paths — verified against live site
URLS = {
    "portfolio": "/it/cdp_equity_portafoglio.page",
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from CDP Equity portfolio page.

    Structure: Multiple tables containing direct participations,
    asset managers, and managed funds. Each table has company name,
    sector/asset class, and ownership percentage.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all tables
    tables = soup.find_all("table")

    for table in tables:
        # Get headers to understand table type
        headers = table.find_all("th")
        header_text = " ".join(h.get_text(strip=True).lower() for h in headers)

        # Process rows (skip header row)
        rows = table.find_all("tr")[1:]

        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue

            # First cell is always the company/fund name
            name = cells[0].get_text(strip=True)

            # Clean name: remove footnote numbers at the end (e.g., "Company Name1")
            name = re.sub(r"\d+$", "", name).strip()

            if not name or len(name) < 2:
                continue

            # Skip section headers (e.g., "Fondi gestiti daFII SGR")
            if name.lower().startswith("fondi gestiti da"):
                continue

            # Skip other fund/SGR names (not portfolio companies)
            name_lower = name.lower()
            if any(p in name_lower for p in ["fondo ", "portafoglio", " sgr", "fipec", "fof "]):
                continue

            # Skip duplicates
            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # Extract sector (second column for direct participations)
            sector = None
            if len(cells) > 1:
                sector_text = cells[1].get_text(strip=True)
                # Skip if it's just a percentage or "IMPRESE"/"INFRASTRUTTURE" generic category
                if sector_text and not re.match(r"^\d", sector_text):
                    sector = sector_text

            # Map Italian sector names to English
            sector_map = {
                "INFRASTRUTTURE": "Infrastructure",
                "INDUSTRIA": "Industrial",
                "COSTRUZIONI": "Construction",
                "TELCO INFRASTRUCTURE": "Telecom Infrastructure",
                "DIGITAL PAYMENTS": "Digital Payments",
                "TURISMO": "Tourism",
                "FINANCIAL INFRASTRUCTURE": "Financial Infrastructure",
                "HEALTHCARE": "Healthcare",
                "ENERGIA": "Energy",
                "CLOUD SERVICES": "Cloud Services",
                "DIGITAL SOLUTIONS & SECURITY": "Digital Solutions & Security",
                "DIGITAL HEALTHCARE": "Digital Healthcare",
                "DIGITAL AGRICULTURE": "Digital Agriculture",
                "IMPRESE": "Enterprises",
            }
            if sector:
                sector = sector_map.get(sector.upper(), sector)

            companies.append({
                "name": name,
                "sector": sector,
                "website": None,
                "description": None,
                "status": "current",  # Portfolio page entries
                "confidence": 0.85,
            })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
}
