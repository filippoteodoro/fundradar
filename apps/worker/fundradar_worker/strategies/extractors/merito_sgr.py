"""Site-specific extractors for meritosgr.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.meritosgr.it"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/investimenti/",
    "team": "/team/",
    "news": "/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Merito SGR investments page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Portfolio items: div.caf-post-layout11
    for item in soup.select("div.caf-post-layout11"):
        # Company link and name from a.caf-f-link
        link = item.select_one("a.caf-f-link")
        if not link:
            continue

        href = link.get("href", "")
        if not href:
            continue

        # Extract company name from URL path
        # e.g., https://www.meritosgr.it/futur-a-group-spa/ -> Futur-a Group SpA
        path = href.rstrip("/").split("/")[-1]
        if not path:
            continue

        # Convert slug to name: futur-a-group-spa -> Futur A Group Spa
        name = path.replace("-", " ").title()

        # Handle common suffixes
        name = re.sub(r"\bSpa\b", "S.p.A.", name)
        name = re.sub(r"\bSrl\b", "S.r.l.", name)
        name = re.sub(r"\bSas\b", "S.a.s.", name)

        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get fund category from tags
        # Status determined by explicit category tag values, not keyword substring
        fund_name = None
        status = "current"
        for cat in item.select(".caf-meta-content-cats li"):
            cat_text = cat.get_text(strip=True).lower()
            # Check for explicit status categories (not substring match)
            if cat_text in ("portafoglio", "portfolio", "portafoglio attuale", "current"):
                status = "current"
            elif cat_text in ("exit", "exits", "disinvestimenti", "disinvestimento", "exited"):
                status = "exited"
            # Get fund name
            if "fondo" in cat_text or "antares" in cat_text:
                fund_name = cat.get_text(strip=True)

        companies.append({
            "name": name,
            "sector": fund_name,  # Use fund name as sector for grouping
            "website": href,  # Link to company detail page on Merito site
            "description": None,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members - not implemented for this site."""
    return []


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news articles from Merito SGR news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # News items: div.caf-post-layout4 (AJAX-loaded WordPress posts)
    for item in soup.select("div.caf-post-layout4"):
        # Title from h2.caf-post-title > a
        title_el = item.select_one("h2.caf-post-title a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # URL from title link
        href = title_el.get("href", "")
        url = urljoin(base_url, href) if href else None

        # Date from .date element
        date = None
        date_el = item.select_one(".date")
        if date_el:
            date_text = date_el.get_text(strip=True)
            # Parse "January 15, 2024" format
            try:
                from datetime import datetime
                # Try common Italian/English date formats
                for fmt in ["%B %d, %Y", "%d %B %Y", "%d/%m/%Y"]:
                    try:
                        parsed = datetime.strptime(date_text, fmt)
                        date = parsed.strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
            except:
                pass  # Keep date as None if parsing fails

        # Summary from .caf-content
        summary = None
        content_el = item.select_one(".caf-content")
        if content_el:
            summary = content_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
