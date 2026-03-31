"""Site-specific extractors for sagard.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fundradar_worker.date_utils import MONTH_NAMES as _MONTH_NAMES

DOMAIN = "www.sagard.com"

# URL paths — verified against url_status.json
URLS = {
    "portfolio": "/portfolio/",
    "team": "/team/",
    "news": "/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Sagard portfolio page.

    Structure: .portfolio-popup divs containing:
    - .portfolio-popup-top-info: logo, name (p.project-title), description (p)
    - .portfolio-popup-bottom: Founded in, Sector, Investment status
    - a[href] link: company website
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for popup in soup.select(".portfolio-popup"):
        # Get company name from p.project-title
        name_el = popup.select_one("p.project-title")
        if not name_el:
            # Fallback to logo alt text
            logo = popup.select_one("img.portfolio-logo")
            if logo:
                name = logo.get("alt", "")
            else:
                continue
        else:
            name = name_el.get_text(strip=True)

        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get description from p elements after project-title
        description = None
        info = popup.select_one(".portfolio-popup-top-info")
        if info:
            for p in info.select("p"):
                if "project-title" not in p.get("class", []):
                    text = p.get_text(strip=True)
                    if text and len(text) > 10:
                        description = text
                        break

        # Get company website from link with "Visit Website" or first external link
        website = None
        for a in popup.select("a[href]"):
            href = a.get("href", "")
            if href and not href.startswith("#") and "sagard.com" not in href:
                website = href
                break

        # Get logo URL
        logo_url = None
        logo = popup.select_one("img.portfolio-logo")
        if logo:
            logo_url = logo.get("src", "")
            if logo_url:
                logo_url = urljoin(base_url, logo_url)

        # Extract metadata from .portfolio-popup-bottom
        sector = None
        status = "current"
        founded_year = None
        invested_year = None

        bottom = popup.select_one(".portfolio-popup-bottom")
        if bottom:
            text = bottom.get_text(separator="|", strip=True)

            # Extract sector
            sector_match = re.search(r"Sector\|?([^|]+)", text)
            if sector_match:
                sector = sector_match.group(1).strip()

            # Extract investment status from structured field pattern
            # Look for "Investment status|Exited" or similar field-value pattern
            status_match = re.search(r"(?:Investment\s+)?[Ss]tatus\|?([^|]+)", text)
            if status_match:
                status_value = status_match.group(1).strip().lower()
                if status_value in ("exited", "past", "realized", "realised", "divested"):
                    status = "exited"
                elif status_value in ("current", "active", "portfolio"):
                    status = "current"

            # Extract founded year
            founded_match = re.search(r"Founded in\|?(\d{4})", text)
            if founded_match:
                founded_year = founded_match.group(1)

            # Extract first invested year
            invested_match = re.search(r"First invested in\|?(\d{4})", text)
            if invested_match:
                invested_year = invested_match.group(1)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "logo_url": logo_url,
            "description": description,
            "status": status,
            "founded_year": founded_year,
            "invested_year": invested_year,
            "confidence": 0.85,
        })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Sagard team page.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for heading in soup.find_all(["h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["team", "sagard", "board", "advisor", "menu"]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        title = None
        parent = heading.find_parent(["div", "article", "a"])
        if parent:
            for p in parent.find_all(["p", "span"]):
                text = p.get_text(strip=True)
                if text and len(text) < 100 and text.lower() != name_lower:
                    title = text
                    break

        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["ceo", "chairman", "president", "founder"]):
                role = "partner"
            elif "partner" in title_lower or "managing director" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif any(r in title_lower for r in ["principal", "manager"]):
                role = "manager"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.80,
        })

    return members

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/insights from Sagard.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    date_pattern = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)

    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["insights", "news", "sagard"]):
            continue

        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            url = urljoin(base_url, parent_link.get("href", ""))

        date = None
        parent = heading.find_parent(["article", "div"])
        if parent:
            text = parent.get_text()
            match = date_pattern.search(text)
            if match:
                day, month, year = match.groups()
                month_num = _MONTH_NAMES.get(month.lower(), "01")
                date = f"{year}-{month_num}-{day.zfill(2)}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.75,
        })

    return news

EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
