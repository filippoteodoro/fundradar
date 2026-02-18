"""Site-specific extractors for sgr.equita.eu."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "sgr.equita.eu"


# URL paths — verified against live site
URLS = {
    "portfolio": "/private-equity.html",
    "team": None,
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Equita Capital SGR private equity page.

    Structure (requires Playwright — JS-rendered):
    - article.overlay__a.inv.inv-current / .inv-realizzato wraps each company
    - Inside: div.row with 4 x div.col-md-3 columns: [logo, name, sector, fund/year]
    - Company name in h3.int__title (col[1])
    - Sector text in col[2]
    - Fund + year in col[3] (e.g. "ELTIF (2023)")
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    for title_el in soup.select("h3.int__title"):
        name = title_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_key = name.lower()
        if name_key in seen:
            continue
        seen.add(name_key)

        # Get the parent row for column data
        row = title_el.find_parent("div", class_="row")
        if not row:
            continue

        cols = row.select("div.col-md-3")
        if len(cols) < 4:
            continue

        # Sector from col[2]
        sector = None
        sector_text = cols[2].get_text(strip=True)
        if sector_text and sector_text not in ("Settore",):
            sector = sector_text

        # Fund/year from col[3]
        description = None
        fund_text = cols[3].get_text(strip=True)
        if fund_text and fund_text not in ("Fondo (anno)",):
            description = fund_text

        # Status from ancestor article class
        status = "current"
        article = title_el.find_parent("article")
        if article:
            art_classes = " ".join(article.get("class", []))
            if "inv-realizzato" in art_classes:
                status = "exited"

        # Detail page link from ancestor article
        website = None
        if article:
            link = article.find("a", href=True)
            if link:
                href = link.get("href", "")
                if href and href != "#" and "private-equity/" in href:
                    website = urljoin(base_url, href)

        # Logo from col[0]
        logo_url = None
        img = cols[0].find("img") if cols else None
        if img:
            src = img.get("src")
            if src:
                logo_url = urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": status,
            "logo_url": logo_url,
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Equita Capital SGR team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Team members: div.cv__main contains each person
    for cv in soup.select("div.cv__main"):
        # Name: h3.cv__title
        name_el = cv.select_one("h3.cv__title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Title: div.cv__leaf
        title = None
        title_el = cv.select_one("div.cv__leaf")
        if title_el:
            title = title_el.get_text(strip=True)

        # Profile URL
        profile_url = None
        link = cv.select_one("a.btn")
        if link:
            href = link.get("href")
            if href:
                profile_url = urljoin(base_url, href)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if any(k in title_lower for k in ["partner", "responsabile", "ceo", "chairman"]):
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower or "head" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"
            elif "advisor" in title_lower:
                role = "advisor"
            elif "principal" in title_lower:
                role = "director"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Equita Capital SGR news page."""
    soup = BeautifulSoup(html, "html.parser")
    news_items = []

    # News items: article.str elements
    for article in soup.find_all("article", class_="str"):
        # Find the link
        link = article.find("a", class_="str-a", href=True)
        if not link:
            continue

        url = link.get("href", "")
        if not url:
            continue

        # Make URL absolute
        if not url.startswith("http"):
            url = urljoin(base_url, url)

        # Title: h2.str__title
        title_el = article.find("h2", class_="str__title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # Date: time.list__item__time
        published_at = None
        time_el = article.find("time", class_="list__item__time")
        if time_el:
            date_text = time_el.get_text(strip=True)
            # Date format: DD/MM/YYYY
            if date_text and "/" in date_text:
                try:
                    from datetime import datetime
                    # Parse Italian date format
                    dt = datetime.strptime(date_text, "%d/%m/%Y")
                    published_at = dt.isoformat() + "Z"
                except (ValueError, ImportError):
                    published_at = None

        news_items.append({
            "title": title,
            "url": url,
            "published_at": published_at,
            "summary": None,  # No summary/excerpt in listing
            "confidence": 0.90,
        })

    return news_items


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
