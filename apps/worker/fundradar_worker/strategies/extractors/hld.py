"""Site-specific extractors for groupehld.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fundradar_worker.date_utils import MONTH_NAMES as _MONTH_NAMES

DOMAIN = "www.groupehld.com"

# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/en/participations/",
    "team": "/en/team/",
    "news": "/en/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from HLD participations page.

    Structure: Company cards with names, sectors, and turnover info.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for h2/h3 headings that are company names
    for heading in soup.find_all(["h2", "h3"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip section headings
        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "participation", "portfolio", "investment", "hld", "menu",
            "approach", "team", "news", "contact"
        ]):
            continue

        # Skip duplicates
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find parent container
        parent = heading.find_parent(["div", "article", "a"])

        sector = None
        description = None
        website = None

        if parent:
            # Get sector from text
            parent_text = parent.get_text(strip=True)
            sectors = ["business services", "consumer", "industry", "healthcare", "technology"]
            for s in sectors:
                if s in parent_text.lower():
                    sector = s.title()
                    break

            # Get description
            for p in parent.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 20 and "turnover" not in text.lower():
                    description = text[:500]
                    break

            # Get link
            link = parent if parent.name == "a" else parent.find("a", href=True)
            if link and link.get("href"):
                href = link.get("href")
                if "participation" in href.lower():
                    website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from HLD team page.

    Structure: .team__person cards with .team__name (h2) and .team__bio (p).
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for team person cards
    for card in soup.find_all(class_="team__person"):
        # Get name from .team__name or h2
        name_el = card.find(class_="team__name") or card.find("h2")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from .team__bio
        title = None
        bio_el = card.find(class_="team__bio")
        if bio_el:
            title = bio_el.get_text(strip=True)

        # Get tags/roles
        tags = []
        for tag in card.find_all(class_="team__tag"):
            tags.append(tag.get_text(strip=True))

        # Get photo
        photo_url = None
        img = card.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower:
                role = "partner"
            elif "board" in title_lower or "director" in title_lower:
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

    # Fallback: look for h2 names if no .team__person found
    if not members:
        for h2 in soup.find_all("h2"):
            name = h2.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            words = name.split()
            if len(words) < 2:
                continue

            name_lower = name.lower()
            if any(skip in name_lower for skip in ["team", "hld", "menu"]):
                continue

            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # Find title from next p
            title = None
            parent = h2.find_parent(["div", "article"])
            if parent:
                p = parent.find("p")
                if p:
                    title = p.get_text(strip=True)

            members.append({
                "name": name,
                "title": title,
                "role": None,
                "linkedin": None,
                "email": None,
                "photo_url": None,
                "confidence": 0.80,
            })

    return members

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from HLD news page.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Date patterns - match both "DD Month YYYY" and "Month YYYY" formats
    date_pattern_full = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)
    date_pattern_month_year = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)

    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["news", "filter", "hld"]):
            continue

        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Find link
        url = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            url = urljoin(base_url, parent_link.get("href", ""))

        # Find date
        date = None
        parent = heading.find_parent(["article", "div", "li"])
        if parent:
            text = parent.get_text()

            # Try full date pattern first (DD Month YYYY)
            match = date_pattern_full.search(text)
            if match:
                day, month, year = match.groups()
                month_num = _MONTH_NAMES.get(month.lower(), "01")
                date = f"{year}-{month_num}-{day.zfill(2)}"
            else:
                # Try month-year only pattern (Month YYYY)
                match = date_pattern_month_year.search(text)
                if match:
                    month, year = match.groups()
                    month_num = _MONTH_NAMES.get(month.lower(), "01")
                    # Default to first of month when day is not specified
                    date = f"{year}-{month_num}-01"

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
