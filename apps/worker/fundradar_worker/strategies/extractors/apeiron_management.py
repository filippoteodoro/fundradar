"""Site-specific extractors for apeironmanagement.com.

Apeiron Management is an Italian credit investor and Apollo partner.
Built with Bricks Builder (WordPress).
Team members displayed in card format with names, roles, and photos.
No public portfolio listing available.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# apeironmgmt.com redirects to apeironmanagement.com at runtime, but
# slug normalizer resolves apeironmgmt.com → apeiron-management (from db.json)
DOMAIN = "www.apeironmgmt.com"


# URL paths for monitoring — verified against live site
URLS = {
    "portfolio": None,  # No public portfolio listing
    "team": "/team/",
    "news": None,
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Apeiron Management team page.

    Structure:
    - .team-card contains each member
    - .team-card__name (p tag) has the name
    - .team-card__role (span) has the title
    - .team-card__image (img) has the photo
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find team cards
    for card in soup.select(".team-card"):
        # Get name
        name_el = card.select_one(".team-card__name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip if not a person name
        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title/role
        title = None
        title_el = card.select_one(".team-card__role")
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo
        photo_url = None
        img = card.select_one(".team-card__image")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Infer role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "founding" in title_lower or "ceo" in title_lower:
                role = "founding partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "analyst"

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


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Apeiron Management doesn't publicly list portfolio companies.
    They focus on corporate credit and special situations investing
    through their partnership with Apollo.
    """
    return []


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
