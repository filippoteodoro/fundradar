"""Site-specific extractors for axonpartnersgroup.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "axonpartnersgroup.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": "/about-us/",
    "news": "/insights/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Axon Partners portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Portfolio items: div.blog-post
    for item in soup.select("div.blog-post"):
        # Company name in h4.wp-block-heading
        name_el = item.select_one("h4.wp-block-heading")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Description in p element after h4
        description = None
        desc_el = item.select_one("p")
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        # Company website from external-link
        website = None
        link = item.select_one("a.external-link")
        if link:
            href = link.get("href", "")
            if href and not href.startswith("#"):
                website = href

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Axon Partners about page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Known management team members on the about page
    # They use wp-block-column with wp-block-cover containing images
    # and h4.wp-block-heading for names

    # Find all columns that contain team member info
    columns = soup.select("div.wp-block-column")

    for col in columns:
        # Look for h4 with person name (not values like "Collaboration", etc.)
        h4 = col.select_one("h4.wp-block-heading")
        if not h4:
            continue

        name = h4.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-person headings (values section)
        skip_words = ["collaboration", "excellence", "independence", "talent",
                      "responsibility", "privacy", "cookie"]
        if any(sw in name.lower() for sw in skip_words):
            continue

        # Get title from paragraphs in column
        title = None
        for p in col.select("p"):
            title_text = p.get_text(strip=True)
            # Check if it looks like a job title
            if title_text and any(kw in title_text.lower() for kw in [
                "partner", "ceo", "director", "manager", "chairman",
                "board", "founder", "president", "head", "officer"
            ]):
                title = title_text
                break

        # Get photo from wp-block-cover__image-background
        photo_url = None
        img = col.select_one("img.wp-block-cover__image-background")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        # Get LinkedIn link if available
        linkedin = None
        linkedin_link = col.select_one("a[href*='linkedin']")
        if linkedin_link:
            linkedin = linkedin_link.get("href")

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if any(k in title_lower for k in ["partner", "founder", "chairman"]):
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"

        members.append({
            "name": name,
            "title": title,
            "role": role,
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
