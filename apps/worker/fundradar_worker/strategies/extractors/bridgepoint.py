"""Site-specific extractors for Bridgepoint (bridgepointgroup.com).

Note: bridgepoint.eu redirects to bridgepointgroup.com.
The portfolio page is JS-rendered (AEM/Adobe Experience Manager) and requires
headless browser. Company cards load dynamically.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fundradar_worker.date_utils import MONTH_NAMES as _MONTH_NAMES

DOMAIN = "www.bridgepointgroup.com"

# URL paths for monitoring - verified against live site Feb 2026
# Note: The domain redirected from bridgepoint.eu to bridgepointgroup.com
URLS = {
    "portfolio": "/private-equity/portfolio",
    "team": "/about-us/our-people",
    "news": "/about-us/news-and-insights",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Bridgepoint portfolio page.

    Note: Page may use JavaScript rendering.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for h3/h4 elements that might be company names
    for heading in soup.find_all(["h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip navigation/section headings
        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "portfolio", "private equity", "news", "contact", "about",
            "menu", "search", "filter", "all", "bridgepoint"
        ]):
            continue

        # Skip duplicates
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Try to find parent link
        website = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            href = parent_link.get("href", "")
            if href and "portfolio" in href.lower():
                website = urljoin(base_url, href)

        # Look for sector in nearby elements
        sector = None
        parent = heading.find_parent(["div", "article", "li"])
        if parent:
            for el in parent.find_all(["span", "div"], class_=re.compile(r"sector|tag|category", re.I)):
                sector = el.get_text(strip=True)
                if sector:
                    break

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.75,
        })

    # Also try to extract from images with alt text
    for img in soup.find_all("img", alt=True):
        alt = img.get("alt", "").strip()
        if not alt or len(alt) < 2:
            continue

        alt_lower = alt.lower()
        if alt_lower in seen_names:
            continue

        # Check if it looks like a company logo
        src = img.get("src", "").lower()
        if "logo" in src or "portfolio" in src or "company" in src:
            seen_names.add(alt_lower)
            companies.append({
                "name": alt,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",  # Portfolio page entries
                "confidence": 0.65,
            })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Bridgepoint people page.

    Structure: Leadership Team, Management Committee, Operating Committee sections.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for headings that might be names
    for heading in soup.find_all(["h3", "h4", "h5"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip section headings
        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "leadership", "committee", "team", "management", "operating",
            "board", "directors", "governance", "bridgepoint", "about"
        ]):
            continue

        # Basic name check (should have at least 2 words)
        words = name.split()
        if len(words) < 2:
            continue

        # Skip duplicates
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find title from nearby elements
        title = None
        parent = heading.find_parent(["div", "article", "li"])
        if parent:
            for p in parent.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) < 100 and text.lower() != name_lower:
                    title = text
                    break

        # Get photo
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        # Determine role from title or section context
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["chief", "ceo", "chairman", "managing partner"]):
                role = "partner"
            elif any(r in title_lower for r in ["partner", "managing director"]):
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif any(r in title_lower for r in ["head of", "manager"]):
                role = "manager"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.80,
        })

    return members

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from Bridgepoint news page.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Date patterns
    date_pattern = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)

    for heading in soup.find_all(["h3", "h2"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        # Skip navigation
        title_lower = title.lower()
        if any(skip in title_lower for skip in ["news", "insights", "filter", "menu", "bridgepoint"]):
            continue

        # Skip duplicates
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Find link
        url = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            url = urljoin(base_url, parent_link.get("href", ""))
        else:
            link = heading.find("a", href=True)
            if link:
                url = urljoin(base_url, link.get("href", ""))

        # Find date
        date = None
        parent = heading.find_parent(["article", "div", "li"])
        if parent:
            text = parent.get_text()
            match = date_pattern.search(text)
            if match:
                day, month, year = match.groups()
                month_num = _MONTH_NAMES.get(month.lower(), "01")
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
