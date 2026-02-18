"""Site-specific extractors for www.wisesgr.com."""
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
import re
import logging

DOMAIN = "www.wisesgr.com"


# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/en/investimenti",
    "team": "/en/team",
    "news": "/en/news",
}
logger = logging.getLogger(__name__)


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from wisesgr.com investments page.

    Structure:
    - Container: div.invest-card
    - Name: div.invest-label
    - Status/Year: span.invest-overlay-title (e.g., "ACQUIRED 2025", "DIVESTED 2023")
    - Description: p.invest-overlay-desc
    - Website: div.invest-overlay-link > a
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Find all invest-card elements
    for card in soup.find_all("div", class_="invest-card"):
        # Determine which tab/grid this card belongs to (current vs fully divested)
        grid = card.find_parent("div", class_="invest-grid")
        grid_id = ""
        if grid and isinstance(grid, Tag):
            grid_id = (grid.get("id") or "").strip().lower()
        # Get name from invest-label
        name = None
        name_el = card.find("div", class_="invest-label")
        if name_el:
            name = name_el.get_text(strip=True)

        if not name or len(name) < 2:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Determine status from structural context (grid ID), NOT text keywords
        # The page has #invest-portafoglio (current) and #invest-cedute (exited) tabs
        status = "current"
        if grid_id == "invest-cedute":
            status = "exited"
        elif grid_id == "invest-portafoglio":
            status = "current"

        # Extract year from overlay title (but NOT status - that comes from grid)
        year = None
        status_el = card.find("span", class_="invest-overlay-title")
        if status_el:
            status_text = status_el.get_text(strip=True)
            year_match = re.search(r"(\d{4})", status_text)
            if year_match:
                year = year_match.group(1)

        # Get description
        description = None
        desc_el = card.find("p", class_="invest-overlay-desc")
        if desc_el:
            description = desc_el.get_text(strip=True)

        # Get website from invest-overlay-link
        website = None
        link_div = card.find("div", class_="invest-overlay-link")
        if link_div:
            link = link_div.find("a", href=True)
            if link:
                website = link.get("href")

        # Get logo
        logo_url = None
        img = card.find("img", src=True)
        if img:
            src = img.get("src")
            if src and not "grafica" in src.lower():  # Skip decorative images
                logo_url = urljoin(base_url, src)

        results.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description,
            "logo_url": logo_url,
            "status": status,
            "investment_year": year,
            "source": "wise_invest_cards",
        })

    logger.info(f"Extracted {len(results)} companies from wise")
    return results


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from wisesgr.com team page.

    Structure:
    - Container: div.team-card
    - Name: h3.team-name
    - Title: p.team-role
    - Photo: img.team-photo
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Find all team-card elements
    for card in soup.find_all("div", class_="team-card"):
        # Get name from h3.team-name
        name = None
        name_el = card.find("h3", class_="team-name")
        if name_el:
            name = name_el.get_text(strip=True)

        if not name or len(name) < 5:
            continue

        # Validate it looks like a person name
        words = name.split()
        if len(words) < 2:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get title from p.team-role
        title = None
        title_el = card.find("p", class_="team-role")
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo
        photo_url = None
        img = card.find("img", class_="team-photo")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        results.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "source": "wise_team_cards",
        })

    logger.info(f"Extracted {len(results)} team members from wise")
    return results


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from wisesgr.com news page.

    Structure:
    - Container: a.news-item-link
    - Date: p.text-muted (YYYY-MM-DD format)
    - Title: h3 (may contain nested p or span elements)
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # News items are in a.news-item-link elements
    for item in soup.find_all("a", class_="news-item-link"):
        # Get title from h3
        h3 = item.find("h3")
        if not h3:
            continue

        # Use separator=" " to prevent concatenation of nested elements
        # e.g. <h3>Wise Equity e<strong>Absolute</strong>insieme</h3> → "Wise Equity e Absolute insieme"
        title = h3.get_text(separator=" ", strip=True)
        # Collapse multiple spaces
        title = re.sub(r"\s{2,}", " ", title).strip()
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL
        url = None
        href = item.get("href")
        if href:
            url = urljoin(base_url, href)

        # Get date from p.text-muted (format: YYYY-MM-DD)
        date = None
        date_el = item.find("p", class_="text-muted")
        if date_el:
            date = date_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    logger.info(f"Extracted {len(news)} news items from wise")
    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
