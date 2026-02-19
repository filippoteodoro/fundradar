"""Site-specific extractors for www.capdyn.com (Capital Dynamics SGR).

Top-level navigation pages often return 403. Prefer deep press-release paths for
signal coverage and treat portfolio/team as non-monitored until stable endpoints
are consistently available.

Capital Dynamics is a global private asset manager with offices worldwide,
including Milan. They focus on private equity, clean energy, and infrastructure.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.capdyn.com"

# URL paths for monitoring.
# Keep NEWS coverage via press-release endpoints that historically returned content.
URLS = {
    "portfolio": None,
    "team": None,
    "news": [
        "https://news.google.com/rss/search?q=site%3Acapdyn.com+%22Capital+Dynamics%22+when%3A30d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=site%3Acapitaldynamics.com+%22Capital+Dynamics%22+when%3A30d&hl=en-US&gl=US&ceid=US:en",
    ],
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Capital Dynamics investments page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for company cards/items
    for item in soup.select(".portfolio-item, .investment-card, .company-card, article, .card"):
        name_el = item.select_one("h2, h3, h4, .name, .title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        if any(skip in name_lower for skip in ["capital dynamics", "portfolio", "menu"]):
            continue

        website = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "capdyn" not in href.lower():
                website = href

        sector = None
        sector_el = item.select_one(".sector, .category, .industry")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        description = None
        desc_el = item.select_one("p, .description, .summary")
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

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Capital Dynamics team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select(".team-member, .person, article"):
        name_el = item.select_one("h2, h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or len(name.split()) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        if any(skip in name_lower for skip in ["team", "capital dynamics"]):
            continue

        title = None
        title_el = item.select_one(".title, .role, .position, p")
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
    """Extract news from Capital Dynamics news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Detail page fallback.
    detail_h1 = soup.find("h1")
    if detail_h1:
        title = detail_h1.get_text(strip=True)
        if title and len(title) >= 15:
            date = None
            date_el = soup.select_one("time, .date, [datetime]")
            if date_el:
                date = date_el.get("datetime") or date_el.get_text(strip=True)
                if date and "T" in date:
                    date = date.split("T", 1)[0]

            summary = None
            summary_el = soup.select_one("article p, .news-content p, main p")
            if summary_el:
                summary = summary_el.get_text(strip=True)[:280] or None

            return [{
                "title": title,
                "url": base_url,
                "date": date,
                "summary": summary,
                "confidence": 0.85,
            }]

    for item in soup.select(".news-item, article, .card"):
        heading = item.select_one("h2, h3, h4, a")
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        if any(skip in title_lower for skip in ["all news", "view more"]):
            continue

        url = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and not href.startswith("javascript"):
                url = urljoin(base_url, href)

        date = None
        date_el = item.select_one("time, .date, [datetime]")
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
