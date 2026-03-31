"""Site-specific extractors for algebris.com.

Main landing/list pages are frequently blocked by bot protection. This extractor
targets deeper portfolio/press URLs that historically returned usable content.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from fundradar_worker.date_utils import MONTH_NAMES as _MONTH_NAMES

DOMAIN = "www.algebris.com"

# URL paths for monitoring.
# Keep this focused on deep pages that historically worked despite top-level WAF blocks.
URLS = {
    # Portfolio/team pages are currently hard-blocked by WAF (403/Akamai).
    "portfolio": None,
    "team": None,
    # Reachable RSS fallback scoped to Algebris domain mentions.
    "news": [
        "https://news.google.com/rss/search?q=site%3Aalgebris.com+Algebris+when%3A30d&hl=en-US&gl=US&ceid=US:en",
    ],
}

def _name_from_slug(slug: str) -> str:
    """Convert URL slug to readable company/article name."""
    cleaned = re.sub(r"[-_]+", " ", (slug or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title()

def _extract_date_iso(text: str | None) -> str | None:
    """Extract YYYY-MM-DD from common date formats."""
    if not text:
        return None
    value = text.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    if "T" in value and re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        return value.split("T", 1)[0]

    month_pattern = re.search(
        r"(\d{1,2})\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{4})",
        value,
        re.IGNORECASE,
    )
    if month_pattern:
        day, month, year = month_pattern.groups()
        month_num = _MONTH_NAMES.get(month.lower(), "01")
        if month_num:
            return f"{year}-{month_num}-{day.zfill(2)}"
    return None

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Algebris.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Portfolio detail pages: /portfolio/<company-slug>/
    parsed = urlparse(base_url)
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) >= 2 and path_parts[0] == "portfolio" and path_parts[1]:
        title_el = soup.find(["h1", "h2"])
        title = title_el.get_text(strip=True) if title_el else ""
        company_name = title if len(title) >= 2 else _name_from_slug(path_parts[-1])
        if company_name:
            return [{
                "name": company_name,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.90,
            }]

    for heading in soup.find_all(["h2", "h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["portfolio", "algebris", "menu", "investment"]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        website = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            href = parent_link.get("href", "")
            if href.startswith("http") and "algebris" not in href:
                website = href

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.75,
        })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Algebris team page.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for heading in soup.find_all(["h2", "h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["team", "algebris", "menu", "about"]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        title = None
        parent = heading.find_parent("div")
        if parent:
            for p in parent.find_all(["p", "span"]):
                text = p.get_text(strip=True)
                if text and len(text) < 100 and text.lower() != name_lower:
                    title = text
                    break

        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["ceo", "founder", "chairman"]):
                role = "partner"
            elif "partner" in title_lower or "managing director" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif any(r in title_lower for r in ["manager", "head"]):
                role = "manager"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.75,
        })

    return members

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from Algebris.

    NOTE: This site is blocked by Akamai Bot Manager WAF.
    If you're seeing 0 results, check if HTML contains "Access Denied".
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Check for WAF blocking.
    if "Access Denied" in html and "algebris.com" in html.lower():
        return []

    # Single article/detail page fallback.
    detail_title = None
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        detail_title = og_title.get("content", "").strip()
    if not detail_title:
        h1 = soup.find("h1")
        if h1:
            detail_title = h1.get_text(strip=True)
    if detail_title and len(detail_title) >= 15:
        date = None
        time_el = soup.find("time")
        if time_el:
            date = _extract_date_iso(time_el.get("datetime") or time_el.get_text(" ", strip=True))
        if not date:
            date = _extract_date_iso(soup.get_text(" ", strip=True))
        summary = None
        p = soup.find("p")
        if p:
            summary = p.get_text(strip=True)[:280] or None
        return [{
            "title": detail_title,
            "url": base_url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        }]

    date_pattern = re.compile(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        re.I,
    )
    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if title_lower in ["news", "latest news", "menu", "about us", "our news"]:
            continue

        if title_lower == "algebris" or title_lower == "algebris investments":
            continue

        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = None
        # Try 1: heading contains <a>
        child_link = heading.find("a", href=True)
        if child_link:
            url = urljoin(base_url, child_link.get("href", ""))
        else:
            # Try 2: heading wrapped in <a>
            parent_link = heading.find_parent("a", href=True)
            if parent_link:
                url = urljoin(base_url, parent_link.get("href", ""))
            # Try 3: <a> sibling in same parent container
            parent = heading.find_parent(["article", "div"])
            if parent:
                link = parent.find("a", href=True)
                if link and link.get("href"):
                    url = urljoin(base_url, link.get("href", ""))

        date = None
        parent = heading.find_parent(["article", "div"])
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
            "confidence": 0.70,
        })

    return news

EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
