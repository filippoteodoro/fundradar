"""Site-specific extractors for sella.vc (Sella Venture Partners).

Sella Venture Partners SGR is the VC arm of the Sella Group, investing in
early-stage technology companies. Part of the Sella Group.

Note: sella.vc has no dedicated portfolio page. Team bios mention investments
(Satispay, Talent Garden, Credimi, etc.) but no structured portfolio listing.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "sella.vc"

URLS = {
    "portfolio": None,
    "team": "/#team",
    "news": None,
}


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from sella.vc."""
    soup = BeautifulSoup(html, "html.parser")
    team = []
    seen = set()

    # Look for team member cards/sections
    for el in soup.select("[class*='team'], [id*='team']"):
        for name_el in el.select("h3, h4, .name, [class*='name']"):
            name = name_el.get_text(strip=True)
            if not name or len(name) < 3 or name.lower() in seen:
                continue
            seen.add(name.lower())

            # Try to find role/title nearby
            role = None
            sibling = name_el.find_next_sibling()
            if sibling:
                role = sibling.get_text(strip=True)[:100]

            team.append({
                "name": name,
                "role": role,
                "confidence": 0.8,
            })

    return team


EXTRACTORS = {
    "team": extract_team,
}
