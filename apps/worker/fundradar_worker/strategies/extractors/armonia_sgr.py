"""Site-specific extractors for armoniasgr.it."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin


DOMAIN = "www.armoniasgr.it"



# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/investimenti/",
    "team": "/chi-siamo/",
    "news": "/newsroom/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Armònia SGR investments page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Portfolio companies are in div.box-investment elements
    for box in soup.select(".box-investment"):
        # Get company name from div.title
        name_el = box.select_one(".title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get sector from div.category
        sector = None
        sector_el = box.select_one(".category")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Get detail URL
        detail_url = None
        link = box.select_one("a[href]")
        if link:
            href = link.get("href")
            if href:
                detail_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": None,
            "status": "current",  # Single-section portfolio page defaults to current
            "confidence": 0.85,
            "detail_url": detail_url,
        })

    # Strategy 2: Fallback - look for any card/item containers
    if not companies:
        for card in soup.find_all(["article", "div"], class_=re.compile(r"card|investment|portfolio|company", re.I)):
            heading = card.find(["h2", "h3", "h4", "strong", ".title"])
            if heading:
                name = heading.get_text(strip=True)
                if (name and len(name) > 2 and len(name) < 100
                    and name.lower() not in seen
                    and not any(skip in name.lower() for skip in ["menu", "filter", "cerca", "cookie"])):
                    seen.add(name.lower())
                    companies.append({
                        "name": name,
                        "sector": None,
                        "website": None,
                        "description": None,
                        "status": "current",
                        "confidence": 0.65,
                        "detail_url": None,
                    })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Armònia SGR chi-siamo page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    # Team members are in div.single-board elements
    for board in soup.select(".single-board"):
        # Get name from div.name
        name_el = board.select_one(".name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get title from div.role
        title = None
        title_el = board.select_one(".role")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "founder" in title_lower or "fondatore" in title_lower:
                role = "founder"
            elif "ceo" in title_lower or "coo" in title_lower:
                role = "c-level"
            elif "partner" in title_lower:
                role = "partner"
            elif "chairman" in title_lower:
                role = "chairman"
            elif "director" in title_lower or "manager" in title_lower:
                role = "manager"
            elif "analyst" in title_lower:
                role = "analyst"
            elif "head" in title_lower:
                role = "head"
            elif "administration" in title_lower:
                role = "admin"
            elif "assistant" in title_lower:
                role = "assistant"

        # Get photo
        photo_url = None
        img = board.select_one("img")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/press items from Armònia SGR newsroom page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # News items are in div.box-news elements
    for box in soup.select(".box-news"):
        # Get title from div.box-news-title
        title_el = box.select_one(".box-news-title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL from a.box-news-pdf
        url = None
        link = box.select_one("a.box-news-pdf[href]")
        if link:
            href = link.get("href")
            if href:
                url = urljoin(base_url, href)

        # Get date from div.data (format: DD/MM/YYYY)
        date = None
        date_el = box.select_one(".data")
        if date_el:
            date = date_el.get_text(strip=True)

        # Get summary from div.box-news-content
        summary = None
        summary_el = box.select_one(".box-news-content")
        if summary_el:
            summary = summary_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
