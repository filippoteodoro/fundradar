"""Site-specific extractors for antin-ip.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "antin-ip.com"

# URL paths for monitoring — verified 2026-02-25
URLS = {
    "portfolio": "/investments",
    "team": None,
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Antin's investments page.

    Structure: investment links under sector h2 headings.
    Status indicated by "(Realised)" in company name text.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()
    current_sector = None

    for el in soup.find_all(["h2", "a"]):
        if el.name == "h2":
            text = el.get_text(strip=True)
            if text and len(text) < 60:
                current_sector = text
            continue

        # Look for investment links
        href = el.get("href", "")
        if "/investments/" not in href or href.rstrip("/") == "/investments":
            continue

        h3 = el.find("h3")
        if not h3:
            continue

        raw_name = h3.get_text(strip=True)
        if not raw_name or len(raw_name) < 2:
            continue

        # Detect status from "(Realised)" suffix
        status = "current"
        if "(realised)" in raw_name.lower() or "(realized)" in raw_name.lower():
            status = "exited"
            raw_name = raw_name.split("(")[0].strip()

        name_lower = raw_name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        detail_url = urljoin(base_url, href)

        companies.append({
            "name": raw_name,
            "sector": current_sector,
            "website": None,
            "description": None,
            "status": status,
            "detail_page_url": detail_url,
            "confidence": 0.85,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
}
