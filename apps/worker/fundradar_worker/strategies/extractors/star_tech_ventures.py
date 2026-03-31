"""Site-specific extractors for startechventures.eu (Star Tech Ventures).

Note: Website was unreachable during extractor creation.
May need verification of correct URL.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fundradar_worker.date_utils import MONTH_NAMES as _MONTH_NAMES

DOMAIN = "startechventures.eu"

# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Star Tech Ventures.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for heading in soup.find_all(["h2", "h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["portfolio", "star tech", "menu", "investment"]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        website = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            href = parent_link.get("href", "")
            if href.startswith("http") and "startech" not in href:
                website = href

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.75,
        })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Star Tech Ventures team page.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for heading in soup.find_all(["h2", "h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["team", "star tech", "menu", "about"]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        title = None
        parent = heading.find_parent("div")
        if parent:
            for p in parent.find_all(["p", "span"]):
                text = p.get_text(strip=True)
                if text and len(text) < 100 and text.lower() != name_lower:
                    title = text
                    break

        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["ceo", "founder", "managing"]):
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.75,
        })

    return members

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from Star Tech Ventures.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    date_pattern = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})", re.I)

    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["news", "star tech", "menu"]):
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
                month, day, year = match.groups()
                month_num = _MONTH_NAMES.get(month.lower(), "01")
                date = f"{year}-{month_num}-{day.zfill(2)}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.70,
        })

    return news

EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
