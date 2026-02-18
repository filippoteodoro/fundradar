"""Site-specific extractors for portobellocapital.es."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin


DOMAIN = "www.portobellocapital.es"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/en/portfolio-companies/",
    "team": "/en/portobello/",
    "news": "/en/actualidad/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Portobello Capital portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Portfolio companies are in article.participada
    for article in soup.select("article.participada"):
        # Get company name from h4
        name_el = article.select_one("h4.participada__titulo a")
        if not name_el:
            name_el = article.select_one("h4 a")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get sector/description from p.sector
        description = None
        sector_el = article.select_one("p.sector")
        if sector_el:
            description = sector_el.get_text(strip=True)

        # Get detail URL
        detail_url = None
        href = name_el.get("href")
        if href:
            detail_url = urljoin(base_url, href)

        # Get logo/image URL
        logo_url = None
        img = article.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                logo_url = urljoin(base_url, src)

        # Determine status from URL or page context
        status = "current"
        if "divested" in base_url.lower() or "desinvertidas" in base_url.lower():
            status = "exited"

        companies.append({
            "name": name,
            "sector": description,  # Description typically contains sector info
            "website": None,
            "description": description,
            "status": status,
            "logo_url": logo_url,
            "detail_url": detail_url,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Portobello Capital team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    # Team members are in article.miembro
    for article in soup.select("article.miembro"):
        # Get name from h4
        name_el = article.select_one("h4.miembro__titulo a")
        if not name_el:
            name_el = article.select_one("h4 a")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get title from p.cargo
        title = None
        title_el = article.select_one("p.cargo")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "founding partner" in title_lower or "socio fundador" in title_lower:
                role = "partner"
            elif "partner" in title_lower or "socio" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "vice president" in title_lower or "vp" in title_lower:
                role = "vp"
            elif "analyst" in title_lower or "analista" in title_lower:
                role = "analyst"
            elif "associate" in title_lower:
                role = "associate"

        # Get photo
        photo_url = None
        img = article.select_one("img")
        if img:
            photo_url = img.get("src") or img.get("data-src")
            if photo_url:
                photo_url = urljoin(base_url, photo_url)

        # Get profile URL
        profile_url = None
        href = name_el.get("href")
        if href:
            profile_url = urljoin(base_url, href)

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,  # No LinkedIn in page HTML
            "photo_url": photo_url,
            "profile_url": profile_url,
            "confidence": 0.85,
        })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
