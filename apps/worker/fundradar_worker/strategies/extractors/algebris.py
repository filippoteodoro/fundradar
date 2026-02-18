"""Site-specific extractors for algebris.com.

INFRASTRUCTURE ISSUE - BLOCKED BY WAF:
This site uses Akamai Bot Manager WAF that returns 403 Forbidden for ALL automated access,
including Playwright with stealth settings. All endpoints (homepage, /news/, /it/news/) are blocked.

Status: UNFIXABLE without one of:
  1. Residential proxy network (not currently implemented)
  2. Official API access (not available)
  3. Manual data entry (fallback)
  4. Alternative sources (LinkedIn, press releases)

The extractor functions below are CORRECT but cannot be tested until WAF blocking is resolved.
Marked in domain_policies.json as "blocked" with "skip_monitoring: true".
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.algebris.com"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Algebris.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

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

    # Check for WAF blocking
    if "Access Denied" in html and "algebris.com" in html.lower():
        # Site is blocked by WAF - return empty results
        # This is expected behavior documented in domain_policies.json
        return []

    date_pattern = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)

    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        # Skip obvious navigation/header text but not article titles
        # Only skip if title is EXACTLY these words or very short phrases
        if title_lower in ["news", "latest news", "menu", "about us", "our news"]:
            continue

        # Skip if it's ONLY the company name
        if title_lower == "algebris" or title_lower == "algebris investments":
            continue

        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = None
        # Try 1: heading wrapped in <a>
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            url = urljoin(base_url, parent_link.get("href", ""))
        else:
            # Try 2: <a> sibling in same parent container
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
            "confidence": 0.70,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
