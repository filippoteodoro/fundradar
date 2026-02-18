"""Site-specific extractors for www.investindustrial.com."""
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
import re
import logging

DOMAIN = "www.investindustrial.com"


# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/our-business/portfolio-overview.html",
    "team": "/who-we-are/People-1.html",
    "news": None,
}
logger = logging.getLogger(__name__)


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from investindustrial.com.

    Structure (as of 2025):
    - Companies as <a> links to /our-business/portfolio-overview/current-portfolio/Company.html
    - Company name is the link text (no special class)
    - May include an <img> before the company name text
    - Sections for "Current portfolio" and "Prior investments"
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Strategy 1: Find links to portfolio detail pages
    portfolio_url_pattern = re.compile(r"/our-business/portfolio-overview/(?:current-portfolio|prior-investments)/", re.I)
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if not portfolio_url_pattern.search(href):
            continue

        # Get company name from link text
        name = link.get_text(strip=True)

        # Fallback: try img alt text
        if not name:
            img = link.find("img")
            if img:
                name = (img.get("alt") or "").strip()

        if not name or len(name) < 2 or len(name) > 80:
            continue

        # Skip nav items
        name_lower = name.lower()
        if name_lower in ("current portfolio", "prior investments", "portfolio overview",
                          "back", "view all", "portfolio", "investments", "our portfolio",
                          "explore portfolio", "discover"):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        detail_url = urljoin(base_url, href)

        # Find logo from img inside the link
        logo_url = None
        img = link.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                logo_url = urljoin(base_url, src)

        # Determine status from URL path
        status = "current"
        if "prior-investments" in href.lower():
            status = "exited"

        results.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "logo_url": logo_url,
            "status": status,
            "detail_page_url": detail_url,
            "source": "investindustrial_portfolio",
        })

    # Strategy 2: Fallback — look for span.caseTitle (legacy structure)
    if not results:
        for title_el in soup.find_all("span", class_="caseTitle"):
            name = title_el.get_text(strip=True)
            if not name or len(name) < 2:
                continue

            name_key = name.lower()
            if name_key in seen_names:
                continue
            seen_names.add(name_key)

            detail_url = None
            parent_link = title_el.find_parent("a")
            if parent_link:
                href = parent_link.get("href")
                if href:
                    detail_url = urljoin(base_url, href)

            status = "current"
            if detail_url and "prior" in detail_url.lower():
                status = "exited"

            results.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "status": status,
                "detail_page_url": detail_url,
                "source": "investindustrial_portfolio",
            })

    logger.info(f"Extracted {len(results)} companies from investindustrial")
    return results


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from investindustrial.com who-we-are page.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Find team member elements
    for el in soup.find_all(class_=re.compile(r"team-member|person|staff", re.I)):
        name = None
        name_el = el.find(["h2", "h3", "h4", "span"], class_=re.compile(r"name|title", re.I))
        if name_el:
            name = name_el.get_text(strip=True)

        if not name or len(name) < 5:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get title/role
        title = None
        title_el = el.find(class_=re.compile(r"role|position|job", re.I))
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo
        photo_url = None
        img = el.find("img")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        results.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "source": "investindustrial_team",
        })

    logger.info(f"Extracted {len(results)} team members from investindustrial")
    return results


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from investindustrial.com publications/news page.

    Structure:
    - News links to /publications/news/{article-name}.html
    - Link text format: "DD.MM.YYYYTitle of article" (date prepended to title)
    - News page at /publications/news.html
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_titles = set()

    # Pattern to match news article URLs
    news_url_pattern = re.compile(r"/publications/news/", re.I)

    # Pattern to extract date from beginning of text: DD.MM.YYYY
    date_prefix_pattern = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})")

    # Find all news links
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if not news_url_pattern.search(href):
            continue

        # Get raw text from link, strip "more details" navigation artifact
        raw_text = link.get_text(strip=True)
        raw_text = re.sub(r'more\s*details\s*$', '', raw_text, flags=re.I).strip()
        if not raw_text or len(raw_text) < 15:
            continue

        # Extract date from beginning of text and separate from title
        date = None
        title = raw_text
        date_match = date_prefix_pattern.match(raw_text)
        if date_match:
            day, month, year = date_match.groups()
            date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            # Remove date from title
            title = raw_text[date_match.end():].strip()

        if not title or len(title) < 10:
            continue

        # Skip navigation items
        title_lower = title.lower()
        if title_lower in ("read more", "more", "view all", "publications", "news", "back"):
            continue

        title_key = title_lower[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        url = urljoin(base_url, href)

        results.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    logger.info(f"Extracted {len(results)} news items from investindustrial")
    return results


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
