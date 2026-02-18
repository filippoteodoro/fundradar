"""Site-specific extractors for eqtgroup.com.

EQT is a global investment organization with Next.js/React frontend.
Team data is embedded in React Server Components (RSC) format in the HTML.
The data is in script tags with self.__next_f.push() containing JSON.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.eqtgroup.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/about/current-portfolio",
    "team": None,  # Team info is on about pages
    "news": "/news",
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from EQT people page.

    The data is embedded as React Server Components in the HTML.
    We parse the RSC JSON payload containing team member data.
    Format: "hits":[{...team member objects...}]
    Each member has: fname, lname, role, slug
    """
    members = []
    seen_names = set()

    # Find the RSC payload containing initialResults with hits
    # Pattern: "hits":[{...}],"nbHits"
    hits_match = re.search(r'"hits":\[(.*?)\],"nbHits"', html, re.DOTALL)

    if not hits_match:
        # Fallback to traditional HTML parsing
        return _extract_team_html(html, base_url)

    hits_str = hits_match.group(1)

    # Extract individual team members
    # Pattern: "thumbnail":{...fname, lname...}...role...slug
    # Looking for: "fname":"Name","image":...,"lname":"Name"...,"role":"Title"...,"slug":{"current":"slug"}
    member_pattern = r'"fname":"([^"]+)"[^}]*\}[^"]*"lname":"([^"]+)"[^"]*"role":"([^"]*)"[^"]*"slug":\{[^}]*"current":"([^"]+)"'

    for m in re.finditer(member_pattern, hits_str):
        fname, lname, role, slug = m.groups()

        name = f"{fname} {lname}"
        name_lower = name.lower()

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Build profile URL
        profile_url = f"https://www.eqtgroup.com/about/people/{slug}"

        # Clean up role (decode unicode escapes)
        role = role.replace("\\u0026", "&").replace("\\u003e", ">")

        # Infer role category
        role_category = None
        if role:
            role_lower = role.lower()
            if "partner" in role_lower:
                role_category = "partner"
            elif "managing director" in role_lower:
                role_category = "managing director"
            elif "director" in role_lower:
                role_category = "director"
            elif "vice president" in role_lower:
                role_category = "vice president"
            elif "associate" in role_lower:
                role_category = "associate"

        members.append({
            "name": name,
            "title": role if role else None,
            "role": role_category,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "profile_url": profile_url,
            "confidence": 0.90,
        })

    return members


def _extract_team_html(html: str, base_url: str) -> list[dict]:
    """Fallback HTML-based extraction."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/about/people/" not in href or href.endswith("/people/"):
            continue
        if "?" in href or "#" in href:
            continue

        h3 = link.find("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        title = None
        p = link.find("p")
        if p:
            title = p.get_text(strip=True)

        # Build profile URL from href
        profile_url = urljoin(base_url, href)

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "profile_url": profile_url,
            "confidence": 0.75,
        })

    return members


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from EQT portfolio page.

    The portfolio is rendered as an HTML table with columns:
    - Company name (link to /about/current-portfolio/{slug})
    - Sector
    - Fund
    - Market/Country
    - Entry Year
    """
    companies = []
    seen_names = set()

    soup = BeautifulSoup(html, "html.parser")

    # Portfolio data is in table rows
    for row in soup.select("tr"):
        tds = row.find_all("td")
        if len(tds) < 2:
            continue

        # First td should have company link
        link = tds[0].find("a", href=True)
        if not link:
            continue

        href = link.get("href", "")

        # Skip fund pages, divestments, and navigation links
        if "/funds/" in href:
            continue
        if href.endswith("/divestments") or href.endswith("/funds"):
            continue
        if "/about/current-portfolio/" not in href:
            continue

        name = link.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip navigation/filter text
        skip_words = ["divestments", "funds", "load more", "filter", "clear", "overview"]
        if any(skip in name.lower() for skip in skip_words):
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector from second td
        sector = None
        if len(tds) > 1:
            sector_text = tds[1].get_text(strip=True)
            if sector_text and len(sector_text) < 50:
                sector = sector_text

        # Get fund from third td (if exists)
        fund = None
        if len(tds) > 2:
            fund_link = tds[2].find("a")
            if fund_link:
                fund = fund_link.get_text(strip=True)

        # Get market/country from fourth td (if exists)
        market = None
        if len(tds) > 3:
            market_text = tds[3].get_text(strip=True)
            if market_text and len(market_text) < 50:
                market = market_text

        # Build profile URL
        profile_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": profile_url,
            "description": None,
            "status": "current",  # Portfolio page entries
            "fund": fund,
            "market": market,
            "confidence": 0.95,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from EQT news page.

    Structure: Next.js rendered with semantic <article> elements
    - Title in <h3>
    - Date in <time> element (ISO 8601 datetime attribute)
    - URL from <a> href to /news/[slug]
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Month name to number mapping for fallback date parsing
    month_map = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12"
    }

    # Strategy 1: Parse semantic article elements
    for article in soup.find_all("article"):
        # Get title from h3
        h3 = article.find("h3")
        if not h3:
            continue

        title = h3.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_key = title.lower()[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Get date from <time> element
        date = None
        time_el = article.find("time")
        if time_el:
            # Try ISO format first (datetime attribute)
            datetime_attr = time_el.get("datetime")
            if datetime_attr and len(datetime_attr) >= 10:
                date = datetime_attr[:10]  # "2025-05-20T15:30:18Z" → "2025-05-20"
            else:
                # Fallback: parse display text "May 20, 2025" or "January 29, 2026"
                date_text = time_el.get_text(strip=True)
                match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", date_text)
                if match:
                    month_name, day, year = match.groups()
                    month_num = month_map.get(month_name.lower(), "01")
                    date = f"{year}-{month_num}-{day.zfill(2)}"

        # Get URL from link
        url = None
        link = article.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and "/news/" in href:
                url = urljoin(base_url, href)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    # Strategy 2: Fallback to link-based extraction if no articles found
    if not news:
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if "/news/" not in href or href.endswith("/news/") or href.endswith("/news"):
                continue

            h3 = link.find("h3")
            if not h3:
                continue

            title = h3.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            title_key = title.lower()[:50]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            url = urljoin(base_url, href)

            news.append({
                "title": title,
                "url": url,
                "date": None,
                "summary": None,
                "confidence": 0.75,
            })

    return news


EXTRACTORS = {
    "team": extract_team,
    "portfolio": extract_portfolio,
    "news": extract_news,
}
