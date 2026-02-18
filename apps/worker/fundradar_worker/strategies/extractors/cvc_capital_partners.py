"""Site-specific extractors for cvc.com (CVC)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.cvc.com"



# URL paths for monitoring — verified against url_status.json
URLS = {
    "portfolio": "/portfolio",
    "team": "/about/our-people",
    "news": None,
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from CVC people page.

    Structure: Cards wrapped in <a> with:
    - <img> for photo
    - <h3> for name
    - <p> for title
    - Link pattern: /about/our-people/[person-slug]/
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find all links to people profiles
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        # Match people profile URLs
        if "/our-people/" not in href or href.endswith("/our-people/"):
            continue

        # Skip filter/pagination links
        if "?" in href or "#" in href:
            continue

        # Look for name in h3
        h3 = link.find("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Extract title from <p>
        title = None
        p = link.find("p")
        if p:
            title = p.get_text(strip=True)

        # Extract photo
        photo_url = None
        img = link.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["managing partner", "partner", "chairman", "ceo"]):
                role = "partner"
            elif any(r in title_lower for r in ["director", "managing director"]):
                role = "director"
            elif any(r in title_lower for r in ["principal", "vice president", "vp"]):
                role = "manager"
            elif any(r in title_lower for r in ["associate", "analyst"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from CVC portfolio page.

    Structure: .portfolio__card-content cards with:
    - span.portfolio__card-title: Industry/sector (e.g., "Consumer/Retail")
    - h2.portfolio__card-heading: Company name
    - div.portfolio__card-wrapper: Region info
    - Parent may have image
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find portfolio cards
    for card in soup.select(".portfolio__card-content"):
        # Get company name
        name_el = card.select_one("h2.portfolio__card-heading")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip "Case Studies" and other non-company cards
        if name.lower() in ["case studies", "portfolio", "load more"]:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector from span.portfolio__card-title
        sector = None
        sector_el = card.select_one("span.portfolio__card-title")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Get region from div.portfolio__card-wrapper
        region = None
        wrapper = card.select_one("div.portfolio__card-wrapper")
        if wrapper:
            region = wrapper.get_text(strip=True)
            # Clean up region (might have extra text)
            if region and len(region) < 30:
                region = region

        # Get logo/image from parent card
        logo_url = None
        parent = card.find_parent()
        if parent:
            img = parent.select_one("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    logo_url = urljoin(base_url, src)

        # Build description from region if available
        description = f"Region: {region}" if region else None

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": description,
            "logo_url": logo_url,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/press items from CVC news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # News items are in li.downloads__item elements
    for item in soup.select(".downloads__item"):
        # Get title from a.downloads__title-link
        title_el = item.select_one("a.downloads__title-link")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL
        url = None
        href = title_el.get("href")
        if href:
            url = urljoin(base_url, href)

        # Get date from span.downloads__date (format: DD/MM/YY)
        date = None
        date_el = item.select_one(".downloads__date")
        if date_el:
            date = date_el.get_text(strip=True)

        # No summary in this layout
        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "team": extract_team,
    "portfolio": extract_portfolio,
    "news": extract_news,
}
