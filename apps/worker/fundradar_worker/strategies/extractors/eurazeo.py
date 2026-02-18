"""Site-specific extractors for eurazeo.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.eurazeo.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/en/investments",
    "team": "/en/group/teams",
    "news": "/en/newsroom/press-releases",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Eurazeo investments page.

    Structure: article.portefeuille_single_bloc with:
    - .link_arrow a span: company name
    - .tag_wrap .tag_name: category tags (sector, status)
    - img: company image
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all portfolio company articles
    for article in soup.select("article.portefeuille_single_bloc"):
        # Get company name from .link_arrow a span
        name_el = article.select_one(".link_arrow a span")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Extract tags (sector and status)
        sector = None
        status = "current"

        for tag in article.select(".tag_wrap .tag_name"):
            tag_text = tag.get_text(strip=True)
            tag_lower = tag_text.lower()
            tag_classes = tag.get("class", [])

            # Determine status from structural context:
            # 1. Explicit status tag values (exact match)
            # 2. Grey tags (bg_grey class) are status indicators
            if tag_lower in ("divested", "exited", "sold", "exit"):
                status = "exited"
            elif "bg_grey" in tag_classes:
                # Grey tags indicate status - check for exited status values
                if tag_lower in ("divested", "exited", "sold", "exit"):
                    status = "exited"
            else:
                # Other tags are sector/category
                if not sector:
                    sector = tag_text

        # Get company image URL
        logo_url = None
        img = article.select_one(".visuel img")
        if img:
            src = img.get("src", "")
            if src:
                logo_url = urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,  # Links are javascript:void(0)
            "logo_url": logo_url,
            "description": None,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Eurazeo teams page.

    Note: Site has 435 profiles with pagination.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for links to team profiles
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/teams/profile/" not in href.lower():
            continue

        # Find name from h3 inside link
        h3 = link.find("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find title from p element
        title = None
        p = link.find("p")
        if p:
            title = p.get_text(strip=True)

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["ceo", "chief executive", "chairman"]):
                role = "partner"
            elif "managing partner" in title_lower or "partner" in title_lower:
                role = "partner"
            elif any(r in title_lower for r in ["executive board", "managing director"]):
                role = "director"
            elif "director" in title_lower:
                role = "director"
            elif any(r in title_lower for r in ["principal", "manager"]):
                role = "manager"
            elif any(r in title_lower for r in ["associate", "analyst"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from Eurazeo newsroom page.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Date pattern
    date_pattern = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)

    for heading in soup.find_all(["h3", "h2"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["news", "media", "press", "filter", "eurazeo"]):
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
                months = {
                    "january": "01", "february": "02", "march": "03", "april": "04",
                    "may": "05", "june": "06", "july": "07", "august": "08",
                    "september": "09", "october": "10", "november": "11", "december": "12"
                }
                month_num = months.get(month.lower(), "01")
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
