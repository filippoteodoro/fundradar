"""Site-specific extractors for alphape.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.alphape.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio",
    "team": "/about-us",  # Team info is on the about page
    "news": "/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Alpha Associati portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Portfolio items: div.Portfolio-item
    for item in soup.select("div.Portfolio-item"):
        # Company name in div.Portfolio-item-title > a
        name_el = item.select_one("div.Portfolio-item-title a")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Sector in div.Portfolio-item-category
        sector = None
        sector_el = item.select_one("div.Portfolio-item-category")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Detail page URL
        website = None
        href = name_el.get("href")
        if href:
            website = urljoin(base_url, href)

        # Status from data-statusproject attribute (1 = current, other = may be exited)
        status = "current"
        status_attr = item.get("data-statusproject", "")
        if status_attr and status_attr != "1":
            status = "exited"

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": status,
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Alpha Associati about page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Team members: a.Team-item
    for item in soup.select("a.Team-item"):
        # Name in span.font-weight-bold (format: "FirstName LASTNAME")
        name_el = item.select_one("span.font-weight-bold")
        if not name_el:
            continue

        name_raw = name_el.get_text(strip=True)
        if not name_raw or len(name_raw) < 3:
            continue

        # Convert "FirstName LASTNAME" to title case properly
        # Names like "Patrick HERMAN" -> "Patrick Herman"
        parts = name_raw.split()
        name_parts = []
        for p in parts:
            if p.isupper() and len(p) > 2:
                name_parts.append(p.title())
            else:
                name_parts.append(p)
        name = " ".join(name_parts)

        # Title in span.font-weight-lighter > strong
        title = None
        title_el = item.select_one("span.font-weight-lighter strong")
        if title_el:
            title = title_el.get_text(strip=True)

        # Photo URL from img.Team-portrait
        photo_url = None
        img = item.select_one("img.Team-portrait")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower or "founder" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower or "head" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/press items from Alpha Associati news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # News items: div.News-item
    for item in soup.select("div.News-item"):
        # Title in div.News-title
        title_el = item.select_one("div.News-title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # URL from a[href]
        url = None
        link = item.select_one("a[href]")
        if link and link.get("href"):
            url = urljoin(base_url, link["href"])

        # Date: combine .News-date (DD | MM) and .News-year (YYYY)
        date = None
        date_el = item.select_one("div.News-date")
        year_el = item.select_one("div.News-year")
        if date_el and year_el:
            date_text = date_el.get_text(strip=True)  # "07 | 10"
            year_text = year_el.get_text(strip=True)  # "2025"
            # Format: DD | MM -> convert to YYYY-MM-DD
            parts = date_text.split("|")
            if len(parts) == 2:
                day = parts[0].strip()
                month = parts[1].strip()
                date = f"{year_text}-{month.zfill(2)}-{day.zfill(2)}"

        # Category in div.News-category
        category = None
        category_el = item.select_one("div.News-category")
        if category_el:
            category = category_el.get_text(strip=True)

        # Use category as summary if available
        summary = category if category else None

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
