"""Site-specific extractors for stylecapital.it."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.stylecapital.it"



# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/style_capital_investimenti.php",
    "team": "/chi_siamo_team.php",
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Style Capital case studies.

    Structure:
    - Case study links: a[href*="case_"]
    - Company names in navigation menu
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find case study links
    for link in soup.find_all("a", href=re.compile(r"case_.*\.php")):
        name = link.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get link URL
        website = None
        href = link.get("href", "")
        if href:
            website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": "Fashion & Luxury",
            "website": website,
            "description": "Style Capital portfolio company",
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Style Capital team page.

    Structure:
    - Image: .team_img img
    - Name: .fontSize_16 strong
    - Title: .fontSize_14 (following name)
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find all name elements (strong inside fontSize_16)
    for name_container in soup.select(".fontSize_16"):
        strong = name_container.find("strong")
        if not strong:
            continue

        name = strong.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-name text
        if name.lower() in ["profilo", "profile"]:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from following fontSize_14 div
        title = None
        next_el = name_container.find_next_sibling("div", class_="fontSize_14")
        if next_el:
            title = next_el.get_text(strip=True)
            # Clean up HTML entities
            title = title.replace("&amp;", "&")

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower or "amministratore delegato" in title_lower:
                role = "partner"
            elif "managing partner" in title_lower or "partner" in title_lower:
                role = "partner"
            elif "cfo" in title_lower or "chief" in title_lower:
                role = "director"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "associate"

        # Get photo URL from preceding team_img div
        photo_url = None
        parent = name_container.find_parent()
        if parent:
            team_img = parent.find_previous("div", class_="team_img")
            if team_img:
                img = team_img.find("img")
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
    No dedicated news page for this fund.
    """
    return []


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
