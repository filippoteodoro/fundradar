"""Site-specific extractors for cinven.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fundradar_worker.date_utils import MONTH_NAMES as _MONTH_NAMES

DOMAIN = "www.cinven.com"

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": None,  # Team info behind portal
    "news": "/news-insights/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Cinven portfolio page.

    Structure: div.news-card cards with div.t-bagoss for company name
    and div.category-pill for sector tags.
    """
    import re
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Image alt text patterns to reject (known garbage from Cinven)
    _IMG_ALT_PATTERNS = re.compile(
        r"(?:photograph|photo|image|picture|woman|man|young|person|abstract|"
        r"shoots?|emerging|earth|looking|sitting|standing|asian)\b",
        re.I,
    )

    # Portfolio items: div.news-card
    for card in soup.select("div.news-card"):
        # Company name: div with t-bagoss class
        name_el = card.select_one("div.t-bagoss")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2 or len(name) > 60:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue

        # Skip image alt text that leaked through
        if _IMG_ALT_PATTERNS.search(name):
            continue

        seen_names.add(name_lower)

        # Sectors: div.category-pill (can have multiple)
        sectors = []
        for pill in card.select("div.category-pill"):
            sector = pill.get_text(strip=True)
            if sector:
                sectors.append(sector)
        sector = ", ".join(sectors) if sectors else None

        # Detail page URL
        website = None
        link = card.select_one("a[href*='/portfolio/']")
        if link:
            website = link.get("href")

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Cinven team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Team members: a.people-card
    for card in soup.select("a.people-card"):
        # Name from aria-label attribute
        name = card.get("aria-label", "").strip()
        if not name or len(name) < 3:
            # Fallback: get from div.t-bagoss
            name_el = card.select_one("div.t-bagoss")
            if name_el:
                name = name_el.get_text(strip=True)

        if not name or len(name) < 3:
            continue

        # Title: div with -t-ls-1 class (appears after name)
        title = None
        title_el = card.select_one("div.-t-ls-1")
        if title_el:
            title = title_el.get_text(strip=True)

        # Photo URL
        photo_url = None
        img = card.select_one("img.people-card__img")
        if img:
            src = img.get("src")
            if src:
                photo_url = src

        # Profile URL
        profile_url = card.get("href")

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower or "founder" in title_lower:
                role = "partner"
            elif "managing director" in title_lower:
                role = "director"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower or "head" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"
            elif "vice president" in title_lower or "vp" in title_lower:
                role = "director"

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
    """
    Extract news items from Cinven news page.

    Structure: <ul> gallery with <li> items containing <figure>/<figcaption>
    and <a> links to /news-insights/[slug]/.
    Also tries div.news-card as fallback.
    """
    import re
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Strategy 1: div.news-card with aria-label on inner link
    # Structure: <div class="news-card"><a aria-label="View [title]" href="URL">
    for card in soup.select("div.news-card"):
        link = card.find("a", href=True)
        if not link:
            continue

        href = link.get("href", "")
        if "/news-insights/" not in href:
            continue
        # Skip the listing page and pagination
        path = href.rstrip("/").split("/news-insights/")[-1]
        if not path or path.startswith("page/"):
            continue

        # Title from aria-label (strip "View " prefix)
        aria = link.get("aria-label", "")
        title = aria.replace("View ", "", 1).strip() if aria.startswith("View ") else aria.strip()

        # Fallback to heading in card
        if not title or len(title) < 10:
            heading = card.find(["h2", "h3", "h4"])
            if heading:
                title = heading.get_text(strip=True)

        if not title or len(title) < 10:
            continue

        # Skip navigation/UI text
        title_lower = title.lower()
        if any(skip in title_lower for skip in ["read more", "load more", "filter", "news & insights"]):
            continue

        title_key = title_lower[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        url = urljoin(base_url, href)

        # Try to find date in card text
        date = None
        card_text = card.get_text(" ", strip=True)
        date_match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", card_text)
        if date_match:
            month_name, day, year = date_match.groups()
            month_num = _MONTH_NAMES.get(month_name.lower(), "01")
            if month_num:
                date = f"{year}-{month_num}-{day.zfill(2)}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    # Strategy 2: Fallback to div.news-card or article elements
    if not news:
        for card in soup.select("div.news-card, article, div.post"):
            heading = card.find(["h2", "h3", "h4"])
            title = heading.get_text(strip=True) if heading else None

            if not title:
                a = card.find("a")
                if a:
                    title = a.get_text(strip=True)

            if not title or len(title) < 10:
                continue

            title_key = title.lower()[:50]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            url = None
            a = card.find("a", href=True)
            if a:
                href = a.get("href", "")
                if href and "/news" in href:
                    url = urljoin(base_url, href)

            date = None
            card_text = card.get_text(" ", strip=True)
            date_match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", card_text)
            if date_match:
                month_name, day, year = date_match.groups()
                month_num = _MONTH_NAMES.get(month_name.lower(), "01")
                if month_num:
                    date = f"{year}-{month_num}-{day.zfill(2)}"

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
