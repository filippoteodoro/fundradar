"""Site-specific extractors for ambercapital.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.ambercapital.com"



# URL paths for monitoring — verified 2026-02-23
# Single-page site: team is at /#team-sec (hash navigation, extracted from /)
URLS = {
    "portfolio": None,
    "team": "/",
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Amber Capital.

    Note: Amber Capital is a hedge fund that does not publicly disclose their
    portfolio holdings. The website focuses on investment strategies and team,
    not specific portfolio companies. This extractor correctly returns an empty
    list as there is no portfolio data available on their public website.
    """
    # Amber Capital does not publicly list portfolio companies
    # This is expected behavior for hedge funds
    return []


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Amber Capital homepage.

    Structure: Team section with h3 names and p elements for title/location.
    Team members: Joseph Oughourlian, Olivier Fortesa, Camilio Azzouz,
                  Giorgio Martorelli, Cameron Brown
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find the team section
    team_section = soup.find(id="team-sec") or soup.find(class_="team-section")
    search_area = team_section if team_section else soup

    # Look for h3 elements that are team member names
    for h3 in search_area.find_all("h3"):
        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip section headings
        name_lower = name.lower()
        if any(skip in name_lower for skip in ["team", "about", "leadership", "management", "our team"]):
            continue

        # Skip duplicates
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find title from following p elements
        title = None
        location = None
        bio = None

        parent = h3.find_parent(["div", "li", "article", "section"])
        if parent:
            paragraphs = parent.find_all("p")
            for i, p in enumerate(paragraphs):
                text = p.get_text(strip=True)
                if not text or text.lower() == "click for bio":
                    continue
                if not title and len(text) < 100:
                    title = text
                elif not location and any(loc in text.lower() for loc in ["london", "milan", "new york", "paris", "office"]):
                    location = text
                elif not bio and len(text) > 100:
                    bio = text[:500]
        else:
            # Check next siblings
            next_el = h3.find_next_sibling("p")
            while next_el and next_el.name == "p":
                text = next_el.get_text(strip=True)
                if text and text.lower() != "click for bio":
                    if not title and len(text) < 100:
                        title = text
                    elif not bio and len(text) > 100:
                        bio = text[:500]
                next_el = next_el.find_next_sibling("p")

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["chairman", "founder", "ceo", "chief"]):
                role = "partner"
            elif any(r in title_lower for r in ["partner", "managing director"]):
                role = "partner"
            elif any(r in title_lower for r in ["head of", "director"]):
                role = "director"
            elif any(r in title_lower for r in ["manager", "portfolio manager"]):
                role = "manager"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.85,
        })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
