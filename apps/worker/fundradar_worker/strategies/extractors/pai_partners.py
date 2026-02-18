"""Site-specific extractors for paipartners.com.

PAI Partners organizes investments on a single /investments/ page with JS-rendered
company cards that can be filtered by sector. The page requires headless browser.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.paipartners.com"

# URL paths for monitoring - verified against live site
# The /investments/ page shows all portfolio companies in a filterable grid
URLS = {
    "portfolio": "/investments/",
    "team": "/group/investment-group-en/",
    "news": "/media/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from PAI Partners investments page.

    Structure (verified Feb 2026 - headless browser required):
    - Company cards are <li> elements containing:
      - <h3> with company name
      - <div class="info-text"> with description
      - <div class="info-extra"> with sector label
    - Page also has stat headings (h3/h4 with numbers) — these must be skipped
    - No individual company detail page links (all cards on one page)
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Primary strategy: <li> cards with h3 name + info-text description
    for li in soup.find_all("li"):
        h3 = li.find("h3")
        info_text = li.find(class_="info-text")

        # Require both heading and description to avoid stat/nav items
        if not h3 or not info_text:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 2 or len(name) > 80:
            continue

        # Skip stat values that leak into headings
        if re.match(r"^[\d,.\s€$£%+>]+$", name):
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector from info-extra
        sector = None
        sector_el = li.find(class_="info-extra")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Get description
        description = info_text.get_text(strip=True)[:500] if info_text else None

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": description,
            "status": "current",
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from PAI Partners team page.

    Structure: List items (<li>) containing:
    - <h3> with member name
    - <p> with job title and location
    - <img> with photo
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Team members are in li elements with h3 names
    for li in soup.find_all("li"):
        h3 = li.find("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip navigation items
        if name.lower() in ("menu", "nav", "search", "home", "about", "team", "contact"):
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from first p tag after name
        title = None
        team_name = None
        for p in li.find_all("p"):
            text = p.get_text(strip=True)
            if not text or len(text) < 3:
                continue
            if not team_name and len(text) < 50:
                team_name = text
            elif not title:
                title = text

        if not title and team_name:
            title = team_name
            team_name = None

        # Get photo URL
        photo_url = None
        img = li.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower or "chairman" in title_lower or "ceo" in title_lower:
                role = "partner"
            elif "managing director" in title_lower or "md" in title_lower:
                role = "director"
            elif "director" in title_lower:
                role = "director"
            elif "principal" in title_lower or "manager" in title_lower:
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
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/media items from PAI Partners media page.

    Structure: List items with date, title (h3), and description.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for li in soup.find_all("li"):
        heading = li.find("h2") or li.find("h3")
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Get link
        url = None
        link = li.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and not href.startswith("javascript"):
                url = urljoin(base_url, href)

        # Try to find date
        date = None
        time_el = li.find("time")
        if time_el:
            date = time_el.get("datetime") or time_el.get_text(strip=True)
        else:
            text = li.get_text()
            date_match = re.search(r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}", text, re.I)
            if date_match:
                date = date_match.group(0)

        # Get summary
        summary = None
        for p in li.find_all("p"):
            text = p.get_text(strip=True)
            if text and len(text) > 20 and text != title:
                summary = text[:300]
                break

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
