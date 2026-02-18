"""Site-specific extractors for triton-partners.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.triton-partners.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": "/about/",  # Team info is on about page
    "news": "/media/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Triton portfolio page.

    Structure: a.investment[href="/portfolio/{slug}/"] contains:
    - img[alt]: company name
    - .investment-atributes .label span.value: sector (first), location (second)
    - .investment-abstract p: description
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for link in soup.select("a.investment[href^='/portfolio/']"):
        href = link.get("href", "")
        if href == "/portfolio/" or not href:
            continue

        # Get company name from image alt attribute
        img = link.select_one("img[alt]")
        if not img:
            continue

        name = img.get("alt", "")
        # Clean up "logo" suffix if present
        name = re.sub(r"\s*\blogo\b\s*", "", name, flags=re.IGNORECASE).strip()
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector and location from attributes
        sector = None
        location = None
        labels = link.select(".investment-atributes .label")
        for label in labels:
            label_text = label.get_text(strip=True)
            value = label.select_one("span.value, span")
            if value:
                value_text = value.get_text(strip=True)
                if "Sector" in label_text:
                    sector = value_text
                elif "Location" in label_text:
                    location = value_text

        # Get description
        description = None
        desc_el = link.select_one(".investment-abstract p")
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        # Skip remaining logo references the replace didn't catch
        if "logo" in name_lower:
            continue

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,  # Actual company websites not available on listing
            "description": description,
            "status": "current",
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Triton team page.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Team members are typically in cards with name and title
    for card in soup.select(".team-member, .person-card, a[href^='/team/']"):
        # Get name from heading or text
        name_el = card.select_one("h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title
        title = None
        title_el = card.select_one(".title, .role, p")
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo
        photo_url = None
        img = card.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                photo_url = urljoin(base_url, src)

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "associate" in title_lower:
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
    Extract news items from Triton media page.

    Note: News page is on subdomain media.triton-partners.com
    Structure: a.news-item-main links with:
    - .news-item-title: Title
    - .news-date-list: Date (DD/MM/YYYY)
    - .news-company-list span: Company
    - .news-sector-list span: Sector
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # News items are in a.news-item-main links
    for item in soup.select("a.news-item-main"):
        # Get title from .news-item-title
        title_el = item.select_one(".news-item-title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL
        url = None
        href = item.get("href")
        if href:
            url = urljoin(base_url, href)

        # Get date from .news-date-list (format: DD/MM/YYYY)
        date = None
        date_el = item.select_one(".news-date-list")
        if date_el:
            date = date_el.get_text(strip=True)

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
