"""Site-specific extractors for dbagitalia.com (DBAG Italia).

DBAG Italia is the Italian arm of Deutsche Beteiligungs AG (DBAG).
Portfolio companies are displayed at /attuali-investimenti/ with links
to individual company pages. Team and news are on parent dbag.com.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.dbagitalia.com"


# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/",  # Portfolio companies listed on homepage
    "team": None,  # Team info on parent dbag.com
    "news": None,  # News on parent dbag.com
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from DBAG portfolio companies page.

    Companies are in .isotope-item divs with links to individual company pages.
    URL pattern: /portfolio/current-portfolio-companies/{company-slug}/
    Sector info available in data-filter-sector attribute.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Map filter-sector class to readable sector names
    sector_map = {
        "filter-sector-4": "Business services",
        "filter-sector-5": "Environment, energy and infrastructure",
        "filter-sector-6": "Industry and industrial technology",
        "filter-sector-7": "Healthcare",
        "filter-sector-25": "IT services & software",
        "filter-sector-28": "Other",
    }

    # Find portfolio items
    for item in soup.select(".isotope-item"):
        # Get link to company page
        link = item.select_one("a[href*='/portfolio/current-portfolio-companies/']")
        if not link:
            continue

        href = link.get("href", "")
        if not href or href.endswith("/current-portfolio-companies/"):
            continue

        # Extract company name from URL slug
        slug = href.rstrip("/").split("/")[-1]
        if not slug:
            continue

        # Convert slug to proper name
        name = slug.replace("-", " ").title()

        # Skip the fund's own name
        if any(fund in name.lower() for fund in ["dbag", "deutsche", "portfolio", "current"]):
            continue

        # Handle special cases
        name = re.sub(r'\bGmbh\b', 'GmbH', name)
        name = re.sub(r'\bAg\b', 'AG', name)
        name = re.sub(r'\bKgaa\b', 'KGaA', name)

        if not name or len(name) < 2 or name.lower() in seen_names:
            continue

        seen_names.add(name.lower())

        # Extract sector from class attribute
        sector = None
        classes = item.get("class", [])
        for cls in classes:
            if cls.startswith("filter-sector-"):
                sector = sector_map.get(cls)
                break

        # Get full URL
        website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from DBAG team page.

    Team members are in .tx_mpmteamdata__item divs with:
    - img[alt]: Person's name and photo
    - .subheadline p: Title
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find team member items
    for item in soup.select(".tx_mpmteamdata__item"):
        # Get name from image alt attribute
        img = item.select_one("img[alt]")
        if not img:
            continue

        name = img.get("alt", "").strip()
        if not name or len(name) < 3 or name.lower() in seen_names:
            continue

        # Skip generic/logo images
        if any(skip in name.lower() for skip in ["logo", "icon", "image"]):
            continue

        seen_names.add(name.lower())

        # Get photo URL
        photo_url = None
        src = img.get("src")
        if src:
            photo_url = urljoin(base_url, src)

        # Get title from subheadline
        title = None
        title_el = item.select_one(".subheadline p")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if "board of management" in title_lower or "spokesman" in title_lower:
                role = "partner"
            elif "managing director" in title_lower:
                role = "director"
            elif "partner" in title_lower:
                role = "partner"
            elif "principal" in title_lower:
                role = "principal"
            elif "director" in title_lower:
                role = "director"
            elif "vice president" in title_lower or "vp" in title_lower:
                role = "vp"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "analyst"
            elif "head" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"

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
    Extract news items from DBAG newsroom page.

    News items are in .grid-item.article divs with:
    - h3[itemprop="headline"]: Title
    - time[datetime]: Date
    - a[href]: Link to full article
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find news article items
    for article in soup.select(".grid-item.article"):
        # Get title
        title_el = article.select_one("h3[itemprop='headline']")
        if not title_el:
            title_el = article.select_one("h3")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        # Get URL
        url = None
        link = article.select_one("a[href*='/newsroom/detail/']")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        # Get date
        date = None
        time_el = article.select_one("time[datetime]")
        if time_el:
            date = time_el.get("datetime")

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
