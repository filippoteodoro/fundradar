"""Site-specific extractors for www.deepoceancapital.it (Deep Ocean Capital SGR).

Portfolio page: https://www.deepoceancapital.it/portfolios-companies/
Uses Fusion Builder (Avada theme) with columns containing company logos and descriptions.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.deepoceancapital.it"



# URL paths — verified against live site
URLS = {
    "portfolio": "/portfolios-companies/",
    "team": None,
    "news": "/en/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Deep Ocean Capital portfolio page.

    Companies are in fusion-layout-column divs with image and description.
    Company name is extracted from the description text.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Find all columns that have both an image and a description
    for col in soup.select(".fusion-layout-column"):
        desc_el = col.select_one("p")
        if not desc_el:
            continue

        desc = desc_el.get_text(strip=True)
        if len(desc) < 20:  # Skip short text
            continue

        # Extract company name from description
        # Patterns: "CompanyName is...", "CompanyName, a spinoff...", "CompanyName develops...", etc.
        name = None
        name_match = re.match(
            r"^([A-Z][A-Za-z0-9\s\-\.]+?)(?:\s+is\s|\s+operates|\s*,|\s+develops|\s+pioneers|\s+redefin)",
            desc
        )
        if name_match:
            name = name_match.group(1).strip()

        # Special handling for FWR
        if name and name.upper() == "FWR":
            name = "Fluid Wire Robotics"
        elif "Fluid Wire Robotics" in desc and (not name or name.upper() == "FWR"):
            name = "Fluid Wire Robotics"

        if not name or len(name) < 2 or name.lower() in seen:
            continue

        seen.add(name.lower())

        # Get website link (external link, not deepoceancapital)
        website = None
        for link in col.select("a[href]"):
            href = link.get("href", "")
            if href.startswith("http") and "deepoceancapital" not in href.lower():
                website = href
                break

        companies.append({
            "name": name,
            "sector": "Deep Tech / Venture Capital",
            "website": website,
            "description": desc[:300] if desc else None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Deep Ocean Capital team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    # Look for team member sections in fusion columns
    for col in soup.select(".fusion-layout-column, .team-member, .person"):
        # Try to find name in headings
        name_el = col.select_one("h2, h3, h4, h5, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen:
            continue

        # Skip page titles
        if any(x in name.lower() for x in ["team", "portfolio", "contact", "about"]):
            continue

        seen.add(name.lower())

        # Try to get title/role
        title = None
        title_el = col.select_one(".role, .position, .title, p")
        if title_el and title_el != name_el:
            title_text = title_el.get_text(strip=True)
            if len(title_text) < 100:  # Avoid long descriptions
                title = title_text

        # Get photo URL
        photo_url = None
        img = col.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.80,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Deep Ocean Capital news page.

    Structure: .fusion-layout-column containers with:
    - Title: h2
    - Date: first h3
    - Source: second h3
    - URL: external link (a[href] not containing 'deepoceancapital')
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all fusion columns
    for col in soup.select('.fusion-layout-column'):
        # Get title from h2
        h2 = col.select_one('h2')
        if not h2:
            continue

        title = h2.get_text(strip=True)
        # Skip page headers and short titles
        if 'NEWS' in title.upper() or len(title) < 10:
            continue

        if title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get date and source from h3 elements
        # Pattern: first h3 = date, second h3 = source
        date = None
        h3s = col.select('h3')
        if len(h3s) >= 1:
            date = h3s[0].get_text(strip=True)

        # Get URL from external link
        url = None
        for link in col.select('a[href]'):
            href = link.get('href', '')
            if href.startswith('http') and 'deepoceancapital' not in href:
                url = href
                break

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
