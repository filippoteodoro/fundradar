"""Site-specific extractors for www.vaminvestments.com (VAM Investments).

VAM Investments is an Italian PE firm (~€500M AUM, HQ Milan). Portfolio: DentalPro,
Gym Nation Italia, Gruppo Florence, Etjca, Soundreef, Supermoney.

Portfolio at /en/portfolio-en/. Note: site has /en/ prefix for English pages.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.vaminvestments.com"

URLS = {
    "portfolio": "/en/portfolio-en/",
    "team": "/team/",
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from VAM Investments portfolio page.

    VAM uses WordPress with trx_addons CPT. Portfolio items are
    article.type-cpt_portfolio elements with h2 company name headings.
    Also extracts from links to portfolio detail pages.
    """
    import re

    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Primary: h2 headings within portfolio CPT articles
    for article in soup.select("article[class*='cpt_portfolio'], article[class*='portfolio']"):
        heading = article.select_one("h2, h3, h4")
        if heading:
            name = heading.get_text(strip=True)
            # Strip language suffixes like " En"
            name = re.sub(r'\s+[Ee]n$', '', name).strip()

            if not name or len(name) < 2 or name.lower() in seen:
                continue
            if name.lower() in (
                "portfolio", "vam investments", "home", "team",
                "vam club", "about us",
            ):
                continue
            seen.add(name.lower())

            detail_url = None
            link = article.select_one("a[href]")
            if link:
                detail_url = urljoin(base_url, link.get("href", ""))

            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.85,
                "detail_page_url": detail_url,
            })

    # Fallback: links to portfolio detail pages
    if not companies:
        for link in soup.select("a[href*='/portfolio']"):
            href = link.get("href", "")
            match = re.search(r'/portfolio/([^/]+?)(?:-en)?/?$', href)
            if not match:
                continue
            slug = match.group(1)
            if slug in ("portfolio", ""):
                continue
            name = slug.replace('-', ' ').title()
            if not name or len(name) < 3 or name.lower() in seen:
                continue
            seen.add(name.lower())
            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.75,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from VAM Investments team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    for item in soup.select(
        ".team-member, .person, .card, article, "
        "[class*='team'], [class*='person']"
    ):
        name_el = item.select_one("h2, h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen:
            continue
        if any(skip in name.lower() for skip in ["team", "about", "contact", "vam"]):
            continue
        seen.add(name.lower())

        title = None
        title_el = item.select_one(".title, .position, .role, p")
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
