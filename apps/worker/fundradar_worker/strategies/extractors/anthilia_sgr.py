"""Site-specific extractors for anthilia.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "anthilia.it"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": None,  # Funds on subdomain fondi.anthilia.it, not extractable with current setup
    "team": "/anthilia/team-anthilia/",  # Team listing page
    "news": "/category/news/",  # News category page
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Anthilia team page.

    Structure: Team members displayed with:
    - <h4> tag with name inside anchor to profile
    - <img> for photo
    - Title/role text near the name
    - URL pattern: /team_anthilia/[name]/
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find h4 elements with links to team profiles
    for h4 in soup.find_all("h4"):
        # Look for anchor parent or child
        link = h4.find("a") or h4.find_parent("a")
        if not link:
            continue

        href = link.get("href", "")
        # Check if this is a team profile link
        if "/team_anthilia/" not in href and "/team-anthilia/" not in href:
            continue

        name = h4.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find parent container to look for title and photo
        parent = h4.find_parent(["li", "div", "article"])

        # Extract title from nearby text
        title = None
        if parent:
            # Look for text that's not the name (could be in p, span, or text node)
            for el in parent.find_all(["p", "span", "div"]):
                text = el.get_text(strip=True)
                # Title should be short and not be the name
                if text and text != name and len(text) < 100 and len(text) > 3:
                    # Skip if it's another person's name (contains common name patterns)
                    if not any(skip in text.lower() for skip in ["partner", "fund manager", "advisor"]):
                        continue
                    title = text
                    break

            # Alternative: look for sibling text
            if not title:
                for sibling in h4.find_next_siblings(limit=3):
                    if sibling.name in ["p", "span", "div"]:
                        text = sibling.get_text(strip=True)
                        if text and text != name and len(text) < 100:
                            title = text
                            break

        # Extract photo
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        # If no parent found, look for nearby img
        if not photo_url:
            prev_link = h4.find_previous("a")
            if prev_link and prev_link.get("href") == href:
                img = prev_link.find("img")
                if img:
                    src = img.get("src") or img.get("data-src")
                    if src:
                        photo_url = urljoin(base_url, src)

        # Build profile URL
        profile_url = urljoin(base_url, href)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["partner", "managing director", "ceo"]):
                role = "partner"
            elif any(r in title_lower for r in ["director", "head of"]):
                role = "director"
            elif any(r in title_lower for r in ["manager", "fund manager"]):
                role = "manager"
            elif any(r in title_lower for r in ["analyst", "associate", "advisor"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    # Fallback: look for img elements with team-related URLs
    if not members:
        for img in soup.find_all("img"):
            src = img.get("src", "") or img.get("data-src", "")
            alt = img.get("alt", "")

            if "team_" in src and alt and len(alt) > 3:
                name = alt
                name_lower = name.lower()
                if name_lower in seen_names:
                    continue
                seen_names.add(name_lower)

                photo_url = urljoin(base_url, src)

                members.append({
                    "name": name,
                    "title": None,
                    "role": None,
                    "linkedin": None,
                    "email": None,
                    "photo_url": photo_url,
                    "confidence": 0.70,
                })

    return members


# Note: Portfolio extraction not implemented because Anthilia's public
# website shows mutual fund products, not PE/VC portfolio companies.

EXTRACTORS = {
    "team": extract_team,
}
