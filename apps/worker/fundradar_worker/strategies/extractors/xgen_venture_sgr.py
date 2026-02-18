"""Site-specific extractors for xgenventure.com (XGen Venture SGR)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "xgenventure.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from XGen Venture portfolio page.

    Companies are in Elementor image-box widgets with:
    - h4.elementor-image-box-title: Company name
    - p.elementor-image-box-description: Description
    - figure.elementor-image-box-img img: Logo
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all image-box elements (excluding team ones which have .single-team class)
    for wrapper in soup.select(".elementor-image-box-wrapper"):
        # Skip if this is a team member
        parent = wrapper.find_parent(class_="single-team")
        if parent:
            continue

        title_el = wrapper.select_one("h4.elementor-image-box-title")
        if not title_el:
            continue

        name = title_el.get_text(strip=True)
        if not name or len(name) < 2 or name.lower() in seen_names:
            continue

        # Skip navigation/generic items
        if name.lower() in ["portfolio", "team", "news", "contact", "about"]:
            continue

        seen_names.add(name.lower())

        # Extract description
        description = None
        desc_el = wrapper.select_one("p.elementor-image-box-description")
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        # Extract logo URL from figure or direct img
        logo_url = None
        figure = wrapper.select_one("figure.elementor-image-box-img")
        if figure:
            img = figure.select_one("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    logo_url = urljoin(base_url, src)
        # Fallback to direct img
        if not logo_url:
            img = wrapper.select_one("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    logo_url = urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": "Life Sciences",  # XGen focuses on life sciences
            "website": None,
            "description": description,
            "logo_url": logo_url,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from XGen Venture people page.

    Team members are in .single-team containers with Elementor image-box:
    - h4.elementor-image-box-title: Person's name
    - p.elementor-image-box-description: Title/role
    - figure.elementor-image-box-img img: Photo
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find team members in .single-team containers
    for team_el in soup.select(".single-team"):
        wrapper = team_el.select_one(".elementor-image-box-wrapper")
        if not wrapper:
            continue

        name_el = wrapper.select_one("h4.elementor-image-box-title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen_names:
            continue

        seen_names.add(name.lower())

        # Extract title
        title = None
        title_el = wrapper.select_one("p.elementor-image-box-description")
        if title_el:
            title = title_el.get_text(strip=True)

        # Extract photo URL
        photo_url = None
        img = wrapper.select_one("figure.elementor-image-box-img img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower:
                role = "partner"
            elif "ceo" in title_lower or "chief" in title_lower:
                role = "executive"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "analyst"
            elif "advisor" in title_lower:
                role = "advisor"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.95,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from XGen Venture news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Look for news article patterns
    for article in soup.select("article, .elementor-post, .news-item"):
        title_el = article.select_one("h2, h3, h4, .entry-title, .elementor-post__title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        # Extract URL
        url = None
        link = title_el.select_one("a") or article.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        # Extract date
        date = None
        date_el = article.select_one("time, .date, [datetime], .elementor-post-date")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

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
