"""Site-specific extractors for tagescapitalsgr.com.

Tages Capital SGR - Italian asset management company focused on
infrastructure, private debt, and other alternative investments.

Note: Site has no public portfolio page showing investments.
Team members are on the /people/ page.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.tagescapitalsgr.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": None,  # No public portfolio page
    "team": "/people/",
    "news": None,
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Tages Capital people page.

    Structure:
    - h4.fusion-title-heading contains links to member bios
    - a.fusion-one-page-text-link has name and optional title
    - Name and title separated by | when using get_text(separator='|')
    - Board of Directors members listed first (no titles)
    - Team members listed after with titles
    """
    soup = BeautifulSoup(html, "html.parser")
    all_entries = {}  # name_key -> (title, profile_url)

    for h4 in soup.select("h4.fusion-title-heading"):
        a = h4.select_one("a.fusion-one-page-text-link")
        if not a:
            continue

        # Get text parts (name and optional title)
        full_text = a.get_text(separator="|", strip=True)
        parts = full_text.split("|")

        name = parts[0].strip() if parts else ""
        title = parts[1].strip() if len(parts) > 1 else None

        # Clean excess whitespace in name
        name = " ".join(name.split())

        # Skip if not a person name
        if not name or len(name.split()) < 2:
            continue

        name_key = name.upper()
        link = a.get("href", "")
        profile_url = urljoin(base_url, link) if link else None

        # Prefer entries with titles (avoid duplicates)
        if name_key not in all_entries or (title and not all_entries[name_key][0]):
            all_entries[name_key] = (title, profile_url)

    # Build final member list
    members = []
    for name_key, (title, profile_url) in all_entries.items():
        # Proper case for name
        name = name_key.title()

        # Infer role from title
        role = None
        if title:
            title_lower = title.lower()
            if "cio" in title_lower or "general manager" in title_lower or "coo" in title_lower:
                role = "partner"
            elif "senior partner" in title_lower or "partner" in title_lower:
                role = "partner"
            elif "head of" in title_lower or "director" in title_lower:
                role = "director"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,  # Photos not available on main page
            "profile_url": profile_url,
            "confidence": 0.85,
        })

    return members


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Tages Capital website.

    Note: Tages Capital does not have a public portfolio page.
    The funds-under-management page only describes fund strategies,
    not individual portfolio companies.
    """
    return []


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
