"""Site-specific extractors for azimutliberaimpresa.it.

Note: This fund is an asset management company that manages funds (PE, VC, infrastructure).
They don't have a public portfolio page listing individual investments.
Only team extraction is possible.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.azimutliberaimpresa.it"



# URL paths for monitoring — verified 2026-02-23
URLS = {
    "portfolio": None,
    "team": "/team",
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    No public portfolio page available for this fund.
    They manage funds (Demos 2, Infrastrutture per la Crescita ESG, etc.)
    but don't disclose individual portfolio companies.
    """
    return []


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Azimut Libera Impresa team page.

    Structure (Liferay portal):
    - Name: h3.nome-team
    - Role: h6.ruolo-team
    - Description: div.descrizione-team
    - Photo: picture > img
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find all name elements
    for name_el in soup.select("h3.nome-team"):
        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find sibling elements for role and description
        title = None
        role_el = name_el.find_next_sibling("h6", class_="ruolo-team")
        if role_el:
            title = role_el.get_text(strip=True)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "presidente" in title_lower:
                role = "partner"
            elif "vicepresidente" in title_lower:
                role = "partner"
            elif "ceo" in title_lower or "amministratore delegato" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "head" in title_lower or "direttore" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "analyst" in title_lower or "associate" in title_lower:
                role = "associate"

        # Find photo (previous picture element)
        photo_url = None
        parent = name_el.find_parent()
        if parent:
            picture = parent.find_previous("picture")
            if picture:
                img = picture.find("img")
                if img and img.get("src"):
                    photo_url = urljoin(base_url, img.get("src"))

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    No dedicated news page available for this fund.
    """
    return []


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
