"""Site-specific extractors for montefiore.eu."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "montefiore.eu"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/en/portfolio/",
    "team": "/en/team/",
    "news": "/en/medias/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Montefiore portfolio page.

    Structure:
    - Container: .nectar-post-grid-item
    - Name: h3
    - Sector: from content text (after name)
    - Status: derived from data attributes or page section
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for item in soup.select(".nectar-post-grid-item"):
        # Get name from h3
        h3 = item.find("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector from content (text after name)
        sector = None
        content = item.select_one(".content")
        if content:
            text = content.get_text(strip=True)
            # Sector comes after the name
            if name in text:
                sector_text = text.replace(name, "").strip()
                if sector_text:
                    sector = sector_text

        # Get link to company page
        website = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and "/portfolio/" in href:
                website = urljoin(base_url, href)

        # Determine status (default to current for this page)
        status = "current"
        # Check for data attributes indicating divested
        item_class = item.get("class", [])
        if isinstance(item_class, list):
            item_class = " ".join(item_class)
        if "divested" in item_class.lower():
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
    """
    Extract team members from Montefiore team page.

    Structure:
    - Container: .nectar-post-grid-item
    - Name: h3
    - Title: .meta-excerpt
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select(".nectar-post-grid-item"):
        # Get name from h3
        h3 = item.find("h3")
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

        # Get title from meta-excerpt
        title = None
        excerpt = item.select_one(".meta-excerpt")
        if excerpt:
            title = excerpt.get_text(strip=True)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower or "managing partner" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "managing director" in title_lower:
                role = "director"
            elif "director" in title_lower:
                role = "director"
            elif "senior" in title_lower and "manager" in title_lower:
                role = "manager"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"
            elif "senior advisor" in title_lower or "advisor" in title_lower:
                role = "advisor"

        # Get photo URL
        photo_url = None
        img = item.find("img")
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-nectar-img-src")
            if src and not src.endswith(".svg"):
                photo_url = urljoin(base_url, src)

        # Get profile URL
        profile_url = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and "/team/" in href:
                profile_url = urljoin(base_url, href)

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
    Extract news from Montefiore medias page.

    Structure:
    - Container: .nectar-post-grid-item or article
    - Title: h3 or .post-heading
    - Date: time element or meta
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Try grid items first
    for item in soup.select(".nectar-post-grid-item"):
        h3 = item.find("h3")
        if not h3:
            continue

        title = h3.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Get URL
        url = None
        link = item.find("a", href=True)
        if link:
            url = urljoin(base_url, link.get("href", ""))

        # Get date
        date = None
        time_el = item.find("time")
        if time_el:
            date = time_el.get("datetime") or time_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.80,
        })

    # Also try article elements
    for article in soup.find_all("article"):
        heading = article.find(["h2", "h3"])
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = None
        link = heading.find("a") or article.find("a")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        date = None
        time_el = article.find("time")
        if time_el:
            date = time_el.get("datetime") or time_el.get_text(strip=True)

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
