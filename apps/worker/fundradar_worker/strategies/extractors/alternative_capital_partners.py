"""Site-specific extractors for alternativecapital.partners (formerly deacapitalaf.com).

Note: The company rebranded from DeA Capital Alternative Funds SGR to
Alternative Capital Partners SGR. The new site does not have a public
portfolio listing page — investments are only described in news articles.
Only team extraction is available.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "alternativecapital.partners"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": "/management",
    "news": None,
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Alternative Capital Partners team page.

    The site uses Elementor page builder. Team members are displayed as:
    - Heading elements (.elementor-heading-title) for names
    - Followed by role/title text in a sibling widget
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Strategy 1: Elementor headings (current site structure)
    # Names are in h2/h3 with class elementor-heading-title, followed by role text
    for heading in soup.select(".elementor-heading-title"):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3 or len(name) > 80:
            continue

        # Must look like a person name (at least 2 words, capitalized)
        words = name.split()
        if len(words) < 2:
            continue
        if not all(w[0].isupper() for w in words if len(w) > 1):
            continue

        # Skip headings that aren't names
        if any(skip in name.lower() for skip in [
            "team", "management", "staff", "esg", "investment",
            "client", "direct", "special", "npl", "nostri", "storie",
            "governance", "consiglio", "presidente",
        ]):
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Try to find title/role in next sibling widget
        title = None
        parent_widget = heading.find_parent(class_="elementor-widget")
        if parent_widget:
            next_widget = parent_widget.find_next_sibling(class_="elementor-widget")
            if next_widget:
                title_text = next_widget.get_text(strip=True)
                if title_text and 3 < len(title_text) < 100:
                    title = title_text

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["presidente", "ceo", "chairman", "partner", "managing director"]):
                role = "partner"
            elif any(r in title_lower for r in ["director", "head of", "direttore", "responsabile"]):
                role = "director"
            elif any(r in title_lower for r in ["manager", "investment manager", "senior"]):
                role = "manager"
            elif any(r in title_lower for r in ["analyst", "associate", "assistant"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.80,
        })

    # Strategy 2 (legacy): Look for card-based structure from old deacapitalaf.com
    if not members:
        for card in soup.select(".item_team, .card-item_team, [class*='team']"):
            h3 = card.find("h3")
            if not h3:
                continue

            name = h3.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            title = None
            h4 = card.find("h4")
            if h4:
                title = h4.get_text(strip=True)

            photo_url = None
            img = card.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

            members.append({
                "name": name,
                "title": title,
                "role": None,
                "linkedin": None,
                "email": None,
                "photo_url": photo_url,
                "confidence": 0.80,
            })

    return members


# Note: Portfolio extraction not available — the site (alternativecapital.partners)
# does not have a public portfolio listing page. Investments are only mentioned
# in news articles. Portfolio data comes from PEM deals only.

EXTRACTORS = {
    "team": extract_team,
}
