"""Site-specific extractors for www.oakleycapital.com."""
import re
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.oakleycapital.com"


# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/our-companies/",
    "team": "/about/who-we-are/",
    "news": "/news-and-insights/",
}
logger = logging.getLogger(__name__)


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from oakleycapital.com our-companies page.

    Structure:
    - Container: a.sector-card--component
    - Company name: img[alt]
    - Status: div.button--component.v--status ("Current" or "Realised")
    - Sector: div.h5.v--no-spacing.u--color-white
    - Logo: img[src]
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Find all company cards
    for card in soup.find_all("a", class_=re.compile(r"sector-card--component", re.I)):
        # Get company name from img alt
        name = None
        img = card.find("img", alt=True)
        if img:
            name = img.get("alt")

        if not name or len(name) < 2:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue

        # Skip CSS class name artifacts (e.g. "cky-close-icon")
        if re.match(r"^[a-z]+-[a-z]+-[a-z]+$", name_key):
            continue
        # Skip image placeholder names (e.g. "Phenna Image 2")
        if re.search(r"\bimage\s+\d", name, re.I):
            continue
        # Skip navigation/UI text from alt attributes
        if name_key in {"back to top", "scroll to top", "menu", "close", "search", "logo"}:
            continue

        seen_names.add(name_key)

        # Get status from dedicated status element (v--status class indicates status indicator)
        status = "current"
        status_el = card.find(class_=re.compile(r"v--status", re.I))
        if status_el:
            status_text = status_el.get_text(strip=True).lower()
            # Check for explicit status values (not substring matching)
            if status_text in ("realised", "realized", "exited", "sold", "divested"):
                status = "exited"
            elif status_text in ("current", "active", "portfolio"):
                status = "current"

        # Get sector
        sector = None
        sector_el = card.find("div", class_=re.compile(r"h5.*u--color-white|u--color-white.*h5", re.I))
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Get detail URL
        detail_url = card.get("href")
        if detail_url:
            detail_url = urljoin(base_url, detail_url)

        # Get logo
        logo_url = None
        if img:
            src = img.get("src")
            if src:
                logo_url = urljoin(base_url, src)

        results.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": None,
            "logo_url": logo_url,
            "detail_url": detail_url,
            "status": status,
            "source": "oakley_portfolio",
        })

    logger.info(f"Extracted {len(results)} companies from oakley")
    return results


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from oakleycapital.com team page.

    Structure: Team members are individual links to profile pages
    with names and roles visible on the main team page.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Find team member cards/links - look for links to /team/person-name/
    for link in soup.find_all("a", href=re.compile(r"/team/[a-z-]+/?$", re.I)):
        href = link.get("href", "")
        if not href or "/team/" not in href:
            continue

        # Skip if it's just the main team page
        if href.rstrip("/").endswith("/team"):
            continue

        # Get name from the link text or nearby element
        name = link.get_text(strip=True)

        if not name or len(name) < 5:
            # Try getting from parent
            parent = link.parent
            if parent:
                name = parent.get_text(strip=True)

        if not name or len(name) < 5 or len(name) > 60:
            continue

        # Skip if not a person name pattern (at least 2 words)
        words = name.split()
        if len(words) < 2:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get title if available
        title = None
        # Try to find role in parent/sibling elements
        parent = link.parent
        if parent:
            role_el = parent.find(class_=re.compile(r"role|title|position", re.I))
            if role_el:
                title = role_el.get_text(strip=True)

        # Get photo
        photo_url = None
        img = link.find("img") or (parent.find("img") if parent else None)
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        detail_url = urljoin(base_url, href)

        results.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "detail_url": detail_url,
            "source": "oakley_team",
        })

    logger.info(f"Extracted {len(results)} team members from oakley")
    return results


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/insights items from oakleycapital.com news-and-insights page.

    Structure: article.spotlight-content wrapped in <a> tags with:
    - span.h4: Title
    - span.footnote-para: Date (DD.MM.YY format)
    - span.article-type: Type (News, Newsletter, Insights)
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all spotlight articles
    for article in soup.select("article.spotlight-content"):
        # Get title from span.h4
        title_el = article.select_one("span.h4")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL from parent <a>
        url = None
        parent_link = article.find_parent("a")
        if parent_link:
            href = parent_link.get("href")
            if href:
                url = urljoin(base_url, href)

        # Get date from span.footnote-para (format: DD.MM.YY)
        date = None
        date_el = article.select_one("span.footnote-para")
        if date_el:
            date = date_el.get_text(strip=True)

        # Get article type
        article_type = None
        type_el = article.select_one(".article-type")
        if type_el:
            article_type = type_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    logger.info(f"Extracted {len(news)} news items from oakley")
    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
