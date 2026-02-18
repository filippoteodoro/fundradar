"""Site-specific extractors for nextalia.com (Nextalia SGR).

Note: www.nextaliasgr.com redirects to nextalia.com.

The portfolio page at /portfolio/ embeds company data in jQuery scripts that
dynamically replace page titles with company logos and external links. The
page needs headless browser to render properly. Extraction looks for:
1. External company links (href to non-nextalia domains)
2. JS-embedded company data (portfolio page IDs and URLs)
3. Fallback: heading elements with company names
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Domain matches the db.json website (redirects to nextalia.com)
DOMAIN = "www.nextaliasgr.com"

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": "/societa/",
    "news": None,
}

# Known navigation/section labels to skip (NOT company names)
_SKIP_LOWER = {
    "mission", "vision", "strategia esg distintiva", "strategia esg",
    "portfolio", "nextalia", "menu", "cookie", "investment", "investimenti",
    "fondi", "team", "news", "login", "area riservata", "contatti",
    "chi siamo", "societá", "societa", "home", "esg", "newsletter",
    "npe", "nco", "nve", "ncr", "first advisory",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Nextalia portfolio page.

    Strategy 1: Parse JavaScript for external company URLs (most reliable)
    Strategy 2: Find external <a> links pointing to company websites
    Strategy 3: Find company cards/sections with heading + description
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    def _add_company(name: str, website: str = None, sector: str = None,
                     description: str = None, confidence: float = 0.85):
        name = name.strip()
        if not name or len(name) < 2 or len(name) > 80:
            return
        name_lower = name.lower()
        if name_lower in seen_names or name_lower in _SKIP_LOWER:
            return
        seen_names.add(name_lower)
        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",
            "confidence": confidence,
        })

    # Strategy 1: Extract company URLs from inline JavaScript
    # The page has jQuery code like: window.location.href = 'https://firstance.com/'
    # and $('...').wrap('<a href="https://digited.it/" ...>')
    for script in soup.find_all("script"):
        text = script.string or ""
        # Find all external URLs in JS
        for match in re.finditer(r'(?:href|location\.href)\s*[=:]\s*["\']?(https?://[^"\'>\s]+)', text):
            url = match.group(1).rstrip("/")
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")

            # Skip nextalia's own domain and common non-company URLs
            if "nextalia" in domain or "jquery" in domain or "google" in domain:
                continue
            if any(skip in domain for skip in ["wp-content", "wordpress", "facebook", "linkedin", "twitter"]):
                continue

            # Extract company name from domain
            name = domain.split(".")[0]
            # Clean up and capitalize
            name = name.replace("-", " ").title()

            _add_company(name, website=url, confidence=0.85)

    # Strategy 2: Find external <a> links to company websites
    if not companies:
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if not href.startswith("http"):
                continue
            parsed = urlparse(href)
            domain = parsed.netloc.lower().replace("www.", "")

            if "nextalia" in domain or not domain:
                continue
            if any(skip in domain for skip in ["facebook", "linkedin", "twitter",
                                                "instagram", "youtube", "google",
                                                "wordpress", "wp-content"]):
                continue

            # Get name from link text or domain
            name = link.get_text(strip=True)
            if not name or len(name) < 2 or len(name) > 60:
                name = domain.split(".")[0].replace("-", " ").title()

            _add_company(name, website=href, confidence=0.80)

    # Strategy 3: Fallback — look for structured company cards
    if not companies:
        for card in soup.find_all(["div", "article", "section"], class_=True):
            heading = card.find(["h2", "h3", "h4"])
            if not heading:
                continue
            name = heading.get_text(strip=True)
            if not name or len(name) < 2:
                continue

            # Must have an external link or description to qualify
            ext_link = None
            for a in card.find_all("a", href=True):
                href = a.get("href", "")
                if href.startswith("http") and "nextalia" not in href:
                    ext_link = href
                    break

            if not ext_link:
                continue

            description = None
            p = card.find("p")
            if p:
                text = p.get_text(strip=True)
                if text and len(text) > 20:
                    description = text[:500]

            _add_company(name, website=ext_link, description=description, confidence=0.80)

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Nextalia team pages."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for heading in soup.find_all(["h2", "h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "nextalia", "team", "management", "menu", "cookie",
            "portfolio", "news", "area"
        ]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        parent = heading.find_parent(["div", "article"])
        title = None
        photo_url = None

        if parent:
            for el in parent.find_all(["p", "span"]):
                text = el.get_text(strip=True)
                if text and len(text) < 100 and text.lower() != name_lower:
                    title = text
                    break

            img = parent.find("img")
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
            "confidence": 0.85,
        })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
