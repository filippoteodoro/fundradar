"""Site-specific extractors for entangledcapital.com (Entangled Capital SGR)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "entangledcapital.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/en/portfolio/",
    "team": "/en/about-us/",
    "news": "/en/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Entangled Capital.

    Portfolio uses tabbed interface with "In Portfolio" and "Realized" sections.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for heading in soup.find_all(["h2", "h3", "h4", "strong"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "portfolio", "entangled", "menu", "in portfolio",
            "realized", "contact", "strategy"
        ]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        website = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            href = parent_link.get("href", "")
            if href.startswith("http") and "entangled" not in href:
                website = href

        description = None
        sector = None
        parent = heading.find_parent("div")
        if parent:
            # Look for sector/year info
            for span in parent.find_all(["span", "p"]):
                text = span.get_text(strip=True)
                if text and len(text) < 100 and text.lower() != name_lower:
                    if not description:
                        description = text
                    # Extract sector from description
                    if not sector and any(kw in text.lower() for kw in [
                        "machinery", "packaging", "producer", "processing",
                        "semiconductor", "equipment"
                    ]):
                        sector = text

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Entangled Capital about page.

    Team uses card-based layout with names, titles, and LinkedIn links.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for team member cards
    for heading in soup.find_all(["h2", "h3", "h4", "strong"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "about", "team", "entangled", "menu", "contact",
            "strategy", "company", "portfolio"
        ]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from nearby elements
        title = None
        parent = heading.find_parent("div")
        if parent:
            # Look for role/title near the name
            for p in parent.find_all(["p", "span"]):
                text = p.get_text(strip=True)
                if text and len(text) < 50 and text.lower() != name_lower:
                    # Check if this looks like a title
                    if any(kw in text.lower() for kw in [
                        "ceo", "partner", "manager", "associate",
                        "director", "analyst", "office"
                    ]):
                        title = text
                        break

        # Get LinkedIn
        linkedin = None
        if parent:
            for link in parent.find_all("a", href=True):
                href = link.get("href", "")
                if "linkedin.com" in href.lower():
                    linkedin = href
                    break

        # Get photo
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower:
                role = "partner"
            elif "managing partner" in title_lower or "partner" in title_lower:
                role = "partner"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"
            elif "back office" in title_lower:
                role = "operations"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from Entangled Capital.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    date_pattern = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})", re.I)

    # Also look for non-standard <h> tags used on this site
    for heading in soup.find_all(["h2", "h3", "h"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        # Skip navigation/section headers, but not article titles mentioning "Entangled Capital"
        if any(skip in title_lower for skip in ["latest news", "our news", "press room", "menu", "back to"]):
            continue

        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            url = urljoin(base_url, parent_link.get("href", ""))

        # Extract date from parent container (could be <a>, article, or div)
        date = None
        parent = heading.find_parent(["a", "article", "div"])
        if parent:
            text = parent.get_text()
            match = date_pattern.search(text)
            if match:
                month, day, year = match.groups()
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
