"""Site-specific extractors for sinlocinvestimentisgr.com (Sinloc Investimenti SGR).

Sinloc Investimenti SGR focuses on real estate and infrastructure investments
in Italy, particularly student housing and urban development projects.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "sinlocinvestimentisgr.com"

# URL paths for monitoring
URLS = {
    "portfolio": "/progetti/",
    "team": "/team-di-gestione/",
    "news": "/news/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio projects from Sinloc projects page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for project cards/items
    for item in soup.select(".project-item, .portfolio-item, article, .card, .et_pb_portfolio_item"):
        name_el = item.select_one("h2, h3, h4, .name, .title, .et_pb_module_header")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Skip navigation items
        if any(skip in name_lower for skip in ["sinloc", "progetti", "menu", "home", "fondo ", " fund", "portfolio"]):
            continue
        # Skip fund/product names starting with "Fondo"
        if name_lower.startswith("fondo "):
            continue

        website = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "sinloc" not in href.lower():
                website = href

        sector = "Real Estate"  # Sinloc focuses on real estate

        description = None
        desc_el = item.select_one("p, .description, .summary, .et_pb_portfolio_description")
        if desc_el:
            description = desc_el.get_text(strip=True)[:300]

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",
            "confidence": 0.80,
        })

    # Fallback: look for project names in headings
    if not companies:
        for heading in soup.find_all(["h2", "h3", "h4"]):
            name = heading.get_text(strip=True)
            if not name or len(name) < 3 or len(name) > 80:
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue

            if any(skip in name_lower for skip in [
                "sinloc", "progetti", "portfolio", "chi siamo", "team", "news", "contatti"
            ]):
                continue

            seen_names.add(name_lower)
            companies.append({
                "name": name,
                "sector": "Real Estate",
                "website": None,
                "description": None,
                "status": "current",  # Portfolio page entries
                "confidence": 0.70,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Sinloc team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select(".team-member, .person, article, .et_pb_team_member"):
        name_el = item.select_one("h2, h3, h4, .name, .et_pb_team_member_name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or len(name.split()) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        if any(skip in name_lower for skip in ["team", "sinloc", "gestione"]):
            continue

        title = None
        title_el = item.select_one(".title, .role, .position, p, .et_pb_team_member_position")
        if title_el and title_el != name_el:
            title = title_el.get_text(strip=True)

        photo_url = None
        img = item.select_one("img")
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


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from Sinloc news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for item in soup.select(".news-item, article, .card, .et_pb_post"):
        heading = item.select_one("h2, h3, h4, a, .entry-title")
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        if any(skip in title_lower for skip in ["all news", "view more", "leggi tutto"]):
            continue

        url = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and not href.startswith("javascript"):
                url = urljoin(base_url, href)

        date = None
        date_el = item.select_one("time, .date, [datetime], .published")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
