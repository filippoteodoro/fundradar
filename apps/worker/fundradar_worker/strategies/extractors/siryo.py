"""Site-specific extractors for siryo.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.siryo.it"



# URL paths for monitoring — verified against url_status.json
URLS = {
    "portfolio": "/investimenti",
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Siryo portfolio page.

    Structure: div.nectar-post-grid-item > div.inner > div.content >
               div.item-main > h3.post-heading > a[href] > span
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    for item in soup.select("div.nectar-post-grid-item"):
        h3 = item.select_one("h3.post-heading")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip navigation/page section text
        if name.lower() in {
            "uploads", "chi siamo", "lavora con noi", "contatti",
            "team", "news", "press", "portfolio", "investimenti",
            "italiano", "english", "home", "privacy", "cookie",
            "eventi", "informativa candidati", "informativa whistleblowing",
            "careers", "jobs", "governance", "whistleblowing",
        }:
            continue

        # Get detail page URL (not company website)
        link = h3.select_one("a[href]")
        # Note: link points to Siryo detail page, not company website

        companies.append({
            "name": name,
            "sector": None,  # Not available on listing page
            "website": None,  # Would need to fetch detail pages
            "description": None,  # Not available on listing page
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Siryo team page.

    Structure varies:
    - Board/Leadership: <h5>[Title]</h5><h3>[Name]</h3><img><p>[Bio]</p>
    - Committee: <img><h4>[Name]</h4><p>[Desc]</p>
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # First approach: find h3 elements with names (board members)
    for h3 in soup.find_all("h3"):
        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip headings that aren't names
        if any(skip in name.lower() for skip in [
            "team", "consiglio", "board", "comitato", "committee",
            "siryo", "chi siamo", "about"
        ]):
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Look for title in h5 before the name
        title = None
        h5 = h3.find_previous_sibling("h5")
        if h5:
            title = h5.get_text(strip=True)

        # Find parent container
        parent = h3.find_parent(["div", "article", "section"])

        # Extract photo
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src and "team" in src.lower():
                    photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["president", "amministratore", "ceo"]):
                role = "partner"
            elif any(r in title_lower for r in ["direttore", "director"]):
                role = "director"
            elif any(r in title_lower for r in ["consigliere", "board member"]):
                role = "manager"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    # Second approach: find h4 elements (committee members)
    for h4 in soup.find_all("h4"):
        name = h4.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-name text
        if any(skip in name.lower() for skip in [
            "team", "comitato", "committee", "collegio", "sindaci"
        ]):
            continue

        # Clean up name if it has role appended
        # Format might be "Name - Role" or "Dott. Name"
        clean_name = name
        if " - " in clean_name:
            clean_name = clean_name.split(" - ")[0].strip()

        name_lower = clean_name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Extract title from the full text if present
        title = None
        if " - " in name:
            title = name.split(" - ")[1].strip()

        # Find parent and photo
        parent = h4.find_parent(["div", "article", "section"])
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        members.append({
            "name": clean_name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.80,
        })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
