"""Site-specific extractors for kairospartners.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.kairospartners.com"

# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": "/ventures-esg-one/chi-siamo/",
    "news": "/ventures-esg-one/media/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract funds from Kairos Partners.

    Note: This is an asset manager - extracts fund names, not portfolio companies.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for fund names in headings
    for heading in soup.find_all(["h2", "h3"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip navigation
        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "menu", "chi siamo", "contatti", "kairos partners", "asset management"
        ]):
            continue

        # Skip duplicates
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find link
        website = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            website = urljoin(base_url, parent_link.get("href", ""))

        companies.append({
            "name": name,
            "sector": "Fund",
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.75,
        })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Kairos Partners chi-siamo page.

    Structure: .slider-team with .box cards containing .kros-h3 names and p titles.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for slider-team section
    slider = soup.find(class_="slider-team")
    search_area = slider if slider else soup

    # Look for .box cards
    for box in search_area.find_all(class_="box"):
        # Get name from .kros-h3 or span
        name_el = box.find(class_="kros-h3") or box.find("span") or box.find("h3")
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

        # Get title from p element
        title = None
        p = box.find("p")
        if p:
            title = p.get_text(strip=True)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["amministratore", "ceo", "presidente", "president"]):
                role = "partner"
            elif any(r in title_lower for r in ["direttore", "director", "general"]):
                role = "director"
            elif "manager" in title_lower:
                role = "manager"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.85,
        })

    # Fallback: look for links to /management/ profiles
    if not members:
        for link in search_area.find_all("a", href=re.compile(r"/management/", re.I)):
            # Get name from link text or contained elements
            name = None
            span = link.find("span")
            if span:
                name = span.get_text(strip=True)
            else:
                name = link.get_text(strip=True)

            if not name or len(name) < 3:
                continue

            # Basic name check
            words = name.split()
            if len(words) < 2:
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # Find title
            title = None
            parent = link.find_parent(["div", "article"])
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
    Extract news from Kairos Partners.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Italian date pattern
    date_pattern = re.compile(r"(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(\d{4})", re.I)

    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["news", "video", "notizie", "kairos"]):
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
