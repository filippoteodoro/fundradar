"""Site-specific extractors for www.altopartners.it."""
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
import re
import logging

DOMAIN = "www.altopartners.it"


# URL paths for monitoring — verified against url_status.json
URLS = {
    "portfolio": "/portafoglio/",
    "team": "/team/",
    "news": None,
}
logger = logging.getLogger(__name__)


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from altopartners.it portfolio page.

    Structure:
    - Container: div.single-carousel
    - Name: h3 inside div.panel-carouser
    - Sector: span.titoletto "Sector" + span.valore
    - Deal type: span.titoletto "Deal type" + span.valore
    - Year: span.titoletto "Year" + span.valore
    - Status: span.titoletto "Status" + span.valore
    - Link: a.investimentoclick
    - Logo: div.img-carousel with background-image
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Find all carousel items
    for carousel in soup.find_all(class_="single-carousel"):
        # Get company name from h3
        name = None
        h3 = carousel.find("h3")
        if h3:
            name = h3.get_text(strip=True)

        if not name or len(name) < 2:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get field values from titoletto/valore pairs
        sector = None
        deal_type = None
        year = None
        status = "current"

        titolettos = carousel.find_all(class_="titoletto")
        valores = carousel.find_all(class_="valore")

        for t, v in zip(titolettos, valores):
            label = t.get_text(strip=True).lower()
            value = v.get_text(strip=True)

            if "sector" in label:
                sector = value
            elif "deal type" in label or "tipo" in label:
                deal_type = value
            elif "year" in label or "anno" in label:
                year = value
            elif "status" in label or "stato" in label:
                # Check for explicit status field values (this is a labeled field, so keyword check is appropriate)
                value_lower = value.lower()
                if value_lower in ("exited", "exit", "dismissed", "ceduto", "ceduta", "divested"):
                    status = "exited"
                elif "exit" in value_lower or "dismiss" in value_lower or "cedut" in value_lower:
                    # Fallback to substring if exact match not found
                    status = "exited"

        # Get link
        detail_url = None
        link = carousel.find("a", class_="investimentoclick")
        if link:
            detail_url = link.get("href")
            if detail_url:
                detail_url = urljoin(base_url, detail_url)

        # Get logo from background-image
        logo_url = None
        img_div = carousel.find(class_="img-carousel")
        if img_div:
            style = img_div.get("style", "")
            url_match = re.search(r"url\(([^)]+)\)", style)
            if url_match:
                logo_url = url_match.group(1).strip("'\"")
                logo_url = urljoin(base_url, logo_url)

        results.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": deal_type,  # Store deal type as description
            "logo_url": logo_url,
            "detail_url": detail_url,
            "status": status,
            "investment_year": year,
            "source": "alto_partners_carousel",
        })

    logger.info(f"Extracted {len(results)} companies from alto_partners")
    return results


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from altopartners.it team page."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Look for team member cards
    for el in soup.find_all(["div", "article"], class_=re.compile(r"team|member|person", re.I)):
        name = None
        title = None

        # Get name from heading
        h = el.find(["h2", "h3", "h4"])
        if h:
            name = h.get_text(strip=True)

        if not name or len(name) < 5:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get title
        p = el.find("p")
        if p:
            title = p.get_text(strip=True)

        # Get photo
        photo_url = None
        img = el.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        results.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "source": "alto_partners_team",
        })

    logger.info(f"Extracted {len(results)} team members from alto_partners")
    return results


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
