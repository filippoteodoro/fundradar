"""Site-specific extractors for scientifica.vc.

Scientifica VC is an Italian deep-tech venture fund.
Modern website with team at /team/ and portfolio at /portfolio-startup/.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "scientifica.vc"



# URL paths — verified against live site
URLS = {
    "portfolio": "/portfolio-startup/",
    "team": None,
    "news": None,
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Scientifica team page.

    Structure:
    - .internal-team-card contains each member
    - h3 has the name
    - p has the title (sibling or child)
    - a[href*="linkedin"] has LinkedIn link
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for card in soup.select(".internal-team-card"):
        # Get name from h3
        h3 = card.select_one("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-names
        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from p tag
        title = None
        p = card.select_one("p")
        if p:
            title = p.get_text(strip=True)
            # Clean up title - remove @ references
            if "@" in title:
                title = title.split("@")[0].strip()

        # Get LinkedIn
        linkedin = None
        linkedin_el = card.select_one("a[href*='linkedin']")
        if linkedin_el:
            linkedin = linkedin_el.get("href")

        # Get photo
        photo_url = None
        img = card.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                photo_url = urljoin(base_url, src)

        # Infer role from title
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower:
                role = "partner"
            elif "head" in title_lower or "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "analyst"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Scientifica portfolio page.

    Structure:
    - h3.t-entry-title contains company name
    - Parent a tag has link to detail page
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for h3 in soup.select("h3.t-entry-title"):
        name = h3.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get link to detail page
        parent_link = h3.find_parent("a")
        website = None
        if parent_link:
            href = parent_link.get("href")
            if href:
                website = urljoin(base_url, href)

        # Get logo
        logo_url = None
        if parent_link:
            img = parent_link.select_one("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src and not src.startswith("data:"):
                    logo_url = urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": None,  # Sector not easily extractable from list view
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "logo_url": logo_url,
            "confidence": 0.90,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
