"""Site-specific extractors for bic-capital.com (BIC Capital / Buono Investment Club).

BIC Capital (Buono Investment Club) is a club deal advisory firm (founded 2021,
HQ Milan) promoted by former Permira professionals. Focus on consumer/restaurant,
industrial mid-market. Italian investments include Bomaki, OTK Kart Group,
Nashi Argan, and Técnicas SanJorge.

Track record page at /track-record/ shows investments.
Team page at /team/. No dedicated news page.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "bic-capital.com"

URLS = {
    "portfolio": "/track-record/",
    "team": "/team/",
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from BIC Capital track record page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Try common card/grid selectors
    for item in soup.select(
        "article, .portfolio-item, .investment, .card, .post, "
        ".elementor-post, .jet-listing-grid__item, .e-loop-item, "
        ".wp-block-post"
    ):
        heading = item.select_one("h2, h3, h4, a")
        if not heading:
            continue

        name = heading.get_text(strip=True)
        if not name or len(name) < 2 or name.lower() in seen:
            continue

        if name.lower() in (
            "track record", "back", "view all", "home",
            "members area", "contact", "who we are",
            "what we look for", "our approach", "why bic",
        ):
            continue

        seen.add(name.lower())

        website = None
        link = item.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "bic-capital.com" not in href:
                website = href

        description = None
        desc_el = item.select_one("p, .excerpt, .summary, .description")
        if desc_el and desc_el != heading:
            text = desc_el.get_text(strip=True)
            if len(text) > 15:
                description = text[:500]

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description,
            "status": "current",
            "confidence": 0.80,
        })

    # Fallback: links that point to individual investment pages
    if not companies:
        for link in soup.select("a[href]"):
            href = link.get("href", "")
            if "bic-capital.com/" not in href or href.endswith("/track-record/"):
                continue
            if any(skip in href for skip in [
                "/team/", "/contact/", "/who-we-are/", "/what-we-look-for/",
                "/our-approach/", "/why-bic/", "/members-area/"
            ]):
                continue

            text = link.get_text(strip=True)
            if not text or len(text) < 3 or text.lower() in seen:
                continue
            if text.lower() in (
                "track record", "home", "back", "contact",
                "members area", "who we are", "what we look for",
                "our approach", "why bic",
            ):
                continue

            seen.add(text.lower())
            companies.append({
                "name": text,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.70,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from BIC Capital team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    for item in soup.select(
        ".team-member, .person, .card, article, "
        ".elementor-widget-container, .jet-listing-grid__item, "
        ".wp-block-group"
    ):
        name_el = item.select_one("h2, h3, h4, .name, strong")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen:
            continue

        # Skip non-name headings
        if any(skip in name.lower() for skip in [
            "team", "who we are", "contact", "our approach",
        ]):
            continue

        seen.add(name.lower())

        title = None
        title_el = item.select_one(".title, .position, .role, p, em")
        if title_el and title_el != name_el:
            title = title_el.get_text(strip=True)

        linkedin = None
        for a in item.select("a[href*='linkedin']"):
            linkedin = a.get("href")
            break

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": None,
            "confidence": 0.85,
        })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
