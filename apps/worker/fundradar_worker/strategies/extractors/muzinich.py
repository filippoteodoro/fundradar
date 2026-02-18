"""
Muzinich & Co. - Private Debt portfolio extractor.

Fund: muzinich
Website: https://www.muzinich.com/
Portfolio page: https://www.muzinich.com/private-markets/private-debt/investments

Structure:
- Grid of investment cards with data-region, data-sector, data-status attributes
- Company logos with names in alt text
- Modal dialogs with descriptions in modal-body
- Filter by region="Italy" to get Italian portfolio only
"""

from bs4 import BeautifulSoup

DOMAIN = "www.muzinich.com"

URLS = {
    "portfolio": "/private-markets/private-debt/investments",
    "team": None,
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract Italian portfolio companies from filterable grid."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all investment cards with data-region="Italy"
    investments = soup.find_all("div", attrs={"data-region": "Italy", "data-status": True})

    for inv in investments:
        # Get company name from logo alt text
        img = inv.find("img")
        if not img or not img.get("alt"):
            continue

        name = img.get("alt", "").replace(" logo", "").strip()
        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get metadata from data attributes
        sector = inv.get("data-sector", "") or None
        status_text = inv.get("data-status", "").lower()

        # Map Muzinich status to standard status
        status = None
        if status_text == "active":
            status = "current"
        elif status_text == "realized":
            status = "exited"

        # Find the modal reference for description
        link = inv.find("a", attrs={"data-bs-toggle": "modal"})
        modal_id = link.get("href", "").lstrip("#") if link else ""

        description = None
        if modal_id:
            modal = soup.find("div", id=modal_id)
            if modal:
                modal_body = modal.find("div", class_="modal-body")
                if modal_body:
                    description = modal_body.get_text(" ", strip=True)

        companies.append(
            {
                "name": name,
                "sector": sector,
                "website": None,
                "description": description,
                "status": status,
                "confidence": 0.90,
            }
        )

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
}
