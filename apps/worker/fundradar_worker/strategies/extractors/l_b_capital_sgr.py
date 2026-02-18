"""Site-specific extractors for milanoinvestment.com (L&B Capital SGR / MIP)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Domain matches db.json (site just links to milanoinvestment.com and soprarnosgr.it)
DOMAIN = "www.lbcapitalsgr.it"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Milano Investment Partners.

    Structure:
    - Companies in .gallery-item divs
    - Name in img alt attribute
    - Website in a[href]
    - Category in additional class names (lifestyletech, deeptech, etc.)
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Category mapping
    category_map = {
        "lifestyletech": "Lifestyle Tech",
        "deeptech": "Deep Tech",
        "healthcare": "Healthcare",
        "fintech": "Fintech",
    }

    for item in soup.select(".gallery-item"):
        # Get image for company name
        img = item.select_one("img")
        if not img:
            continue

        name = img.get("alt", "").strip()
        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get website
        website = None
        link = item.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href and not href.startswith("#"):
                website = href if href.startswith("http") else urljoin(base_url, href)

        # Get sector from class
        sector = None
        classes = item.get("class", [])
        for cls in classes:
            if cls in category_map:
                sector = category_map[cls]
                break

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
}
