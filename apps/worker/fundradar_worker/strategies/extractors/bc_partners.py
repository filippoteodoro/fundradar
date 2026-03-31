"""Site-specific extractors for bcpartners.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fundradar_worker.date_utils import MONTH_NAMES as _MONTH_NAMES

DOMAIN = "www.bcpartners.com"

# URL paths for monitoring — verified 2026-02-23
URLS = {
    "portfolio": "/portfolio/",
    "team": "/people/",
    "news": "/news-insights/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from BC Partners portfolio page.

    Structure:
    - article.imagebg-card contains each company
    - h3 a.imagebg-card__link has name and detail URL
    - .tag elements have sector, fund type, and region
    - img has company image
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for article in soup.select("article.imagebg-card"):
        # Get name from h3 link
        link = article.select_one("h3 a.imagebg-card__link")
        if not link:
            link = article.select_one("h3 a")
        if not link:
            continue

        name = link.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Clean up name - remove fund indicator like "(IX)"
        name_clean = re.sub(r'\s*\([IVX]+\)\s*$', '', name).strip()

        name_lower = name_clean.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get detail URL
        detail_url = None
        href = link.get("href")
        if href:
            detail_url = urljoin(base_url, href)

        # Get tags (sector, fund, region)
        sector = None
        fund = None
        region = None
        for tag in article.select(".tag"):
            tag_text = tag.get_text(strip=True)
            if tag_text.lower() in ["private equity", "private credit", "real estate"]:
                fund = tag_text
            elif tag_text.lower() in ["europe", "north america", "asia", "global"]:
                region = tag_text
            else:
                # Assume it's a sector
                if not sector:
                    sector = tag_text

        # Get image URL
        logo_url = None
        img = article.select_one("img")
        if img:
            src = img.get("src")
            if src:
                logo_url = urljoin(base_url, src)

        companies.append({
            "name": name_clean,
            "sector": sector,
            "website": None,
            "description": None,
            "status": "current",  # Portfolio page entries
            "fund": fund,
            "region": region,
            "detail_url": detail_url,
            "logo_url": logo_url,
            "confidence": 0.85,
        })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from BC Partners team page.

    Structure:
    - article.team-card contains each member
    - h3 has name
    - .team-card__title has job title
    - img has photo
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for article in soup.select("article.team-card"):
        # Get name from h3
        h3 = article.select_one("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title
        title = None
        title_el = article.select_one(".team-card__title")
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo
        photo_url = None
        img = article.select_one("img")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower or "chairman" in title_lower:
                role = "partner"
            elif "managing director" in title_lower:
                role = "director"
            elif "director" in title_lower:
                role = "director"
            elif "vice president" in title_lower or "vp" in title_lower:
                role = "vp"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "analyst"

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
    Extract news items from BC Partners news page.

    Structure:
    - article.post-card contains each news item
    - h3 has title (may contain link)
    - Date in text format "Month DD, YYYY"
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Month name to number mapping

    for article in soup.select("article.post-card, article"):
        # Get title from h3
        h3 = article.find("h3")
        if not h3:
            continue

        title = h3.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_key = title.lower()[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Get URL from link
        url = None
        link = h3.find("a", href=True) or article.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and not href.startswith("#"):
                url = urljoin(base_url, href)

        # Get date - look for "Month DD, YYYY" pattern
        date = None
        article_text = article.get_text(" ", strip=True)
        date_match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", article_text)
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

    return news

EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
