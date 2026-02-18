"""Site-specific extractors for excellis.it.

Excellis Holding is a single-page site using Duda platform.
Portfolio companies are displayed in a photo gallery with captions.
Team members are shown with photos, names in h4, and LinkedIn links.

NO NEWS PAGE: Excellis has no dedicated news/press section.
The sitemap shows only 2 pages (IT homepage + EN version).
Structure is single-page with hash navigation (/#PORTFOLIO, /#TEAM, etc.).
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.excellis.it"


# Single-page site with hash navigation (/#PORTFOLIO, /#TEAM, etc.)
# Both portfolio and team are on the homepage — no separate subpages exist.
URLS = {
    "portfolio": "/",
    "team": "/",
    "news": None,
}
# Sectors to filter out from portfolio (these are category headers, not companies)
SECTOR_NAMES = {
    "tecnologie abilitanti",
    "robotica automazione",
    "cleantech",
    "med-tech",
    "medtech",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Duda photo gallery captions."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all caption containers in the photo gallery
    for container in soup.select(".caption-container"):
        # Get company name from caption-title
        title_el = container.select_one(".caption-title, h3.caption-title")
        if not title_el:
            continue

        name = title_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Filter out sector headers
        if name.lower() in SECTOR_NAMES:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get description from caption-text
        description = None
        desc_el = container.select_one(".caption-text")
        if desc_el:
            # Clean up the description text
            description = desc_el.get_text(strip=True)[:500]

        # Get website from caption-button link
        website = None
        button = container.select_one(".caption-button")
        if button:
            href = button.get("href", "")
            if href and href.startswith("http"):
                website = href

        companies.append({
            "name": name,
            "sector": None,  # Sectors are in a different gallery, not linked to companies
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Duda page structure."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Team members have:
    # - h4.text-align-center with name inside a dmNewParagraph
    # - LinkedIn links in nearby dmSocialHub
    # - Photos in imageWidget

    # Look for dmNewParagraph divs containing h4 with names
    for paragraph in soup.select(".dmNewParagraph"):
        h4 = paragraph.select_one("h4.text-align-center")
        if not h4:
            continue

        name = h4.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-name content (look for typical name patterns)
        # Names usually have 2+ words, start with uppercase, no special keywords
        words = name.split()
        if len(words) < 2:
            continue

        # Filter out footer/navigation items
        skip_keywords = {"link", "utili", "seguici", "holding", "s.r.l", "contatti"}
        if any(kw in name.lower() for kw in skip_keywords):
            continue

        # Check if first word looks like a first name (capitalized, not all caps)
        if not words[0][0].isupper() or words[0].isupper():
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find the parent column/container to get related elements
        parent = paragraph.find_parent("div", class_="dmRespCol")
        if not parent:
            parent = paragraph.find_parent("div")

        # Get LinkedIn link from nearby dmSocialHub
        linkedin = None
        if parent:
            social_hub = parent.select_one(".dmSocialHub")
            if social_hub:
                for link in social_hub.select("a[href*='linkedin']"):
                    linkedin = link.get("href")
                    break
            # Also try direct search in parent
            if not linkedin:
                for link in parent.select("a[href*='linkedin']"):
                    linkedin = link.get("href")
                    break

        # Get photo URL from nearby imageWidget
        photo_url = None
        if parent:
            img_widget = parent.select_one(".imageWidget img")
            if img_widget:
                src = img_widget.get("src") or img_widget.get("data-src") or img_widget.get("data-dm-image-path")
                if src:
                    photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": None,
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
