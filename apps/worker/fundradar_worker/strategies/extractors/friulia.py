"""Site-specific extractors for friulia.it."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.friulia.it"



# URL paths — verified against live site
URLS = {
    "portfolio": "/it/partecipate",
    "team": None,
    "news": "/it/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Friulia partecipate page.

    Structure: .card-subsidiary-company cards containing:
    - .company > .fw-bold: company name
    - .sector > .fw-bold: sector
    - a.link--absolute: detail page link
    - .logo with background-image style: logo URL
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all company cards
    for card in soup.select(".card-subsidiary-company"):
        # Extract company name from .company > .fw-bold
        name_el = card.select_one(".company .fw-bold")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue

        # Skip non-company entries (unions, associations, section headers)
        if any(skip in name_lower for skip in [
            "cisl", "cgil", "uil", "sindacato", "first cisl",
            "società partecipate", "partecipate",
        ]):
            continue

        seen_names.add(name_lower)

        # Extract sector from .sector > .fw-bold
        sector = None
        sector_el = card.select_one(".sector .fw-bold")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Extract detail page link from a.link--absolute
        website = None
        link_el = card.select_one("a.link--absolute[href]")
        if link_el:
            href = link_el.get("href", "")
            if href and "/partecipate/" in href:
                website = urljoin(base_url, href)

        # Extract logo URL from .logo background-image style
        logo_url = None
        logo_el = card.select_one(".logo")
        if logo_el:
            style = logo_el.get("style", "")
            match = re.search(r"url\(['\"]?([^'\"]+)['\"]?\)", style)
            if match:
                logo_path = match.group(1)
                if not logo_path.startswith("http://i.delex"):  # Skip placeholder
                    logo_url = urljoin(base_url, logo_path)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "logo_url": logo_url,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Friulia team page.

    Structure: Staff member cards with h3 names and p titles.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for h3 elements containing names
    for h3 in soup.find_all("h3"):
        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip navigation items and common headings
        name_lower = name.lower()
        if any(skip in name_lower for skip in ["menu", "chi siamo", "team", "contatti", "news", "partecipate"]):
            continue

        # Skip duplicates
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find title in nearby p element
        title = None
        parent = h3.find_parent(["div", "li", "article", "section"])
        if parent:
            for p in parent.find_all("p"):
                text = p.get_text(strip=True)
                # Title should be short and descriptive
                if text and len(text) < 100 and not text.startswith("staff."):
                    title = text
                    break

        # If no title found, look at next sibling
        if not title:
            next_el = h3.find_next_sibling(["p", "span", "div"])
            if next_el:
                text = next_el.get_text(strip=True)
                if text and len(text) < 100:
                    title = text

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["president", "amministratore", "direttore generale"]):
                role = "partner"
            elif "direttore" in title_lower:
                role = "director"
            elif "responsabile" in title_lower:
                role = "manager"
            elif any(r in title_lower for r in ["analista", "analyst", "specialist"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from Friulia news page.

    Structure: Articles with date (e.g., "26 Gennaio 2026"), title, description.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Italian date pattern
    date_pattern = re.compile(r"(\d{1,2})\s+(Gennaio|Febbraio|Marzo|Aprile|Maggio|Giugno|Luglio|Agosto|Settembre|Ottobre|Novembre|Dicembre)\s+(\d{4})", re.I)

    # Look for news card containers
    for card in soup.select(".card-news"):
        # Find the news article link
        link = card.select_one("a.link--absolute[href]")
        if not link:
            continue

        href = link.get("href", "")
        if "/it/news/" not in href or href == "/it/news/":
            continue

        # Get title from link's title attribute or .content .title div
        title = link.get("title", "")
        if not title:
            title_el = card.select_one(".content .title")
            if title_el:
                title = title_el.get_text(strip=True)

        if not title or len(title) < 10:
            continue

        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Build full URL
        url = urljoin(base_url, href)

        # Extract date from .date div
        date = None
        date_el = card.select_one(".date")
        if date_el:
            date_text = date_el.get_text(strip=True)
            match = date_pattern.search(date_text)
            if match:
                day, month, year = match.groups()
                # Convert Italian month to number
                months = {
                    "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
                    "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
                    "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12"
                }
                month_num = months.get(month.lower(), "01")
                date = f"{year}-{month_num}-{day.zfill(2)}"

        # Get summary from .excerpt div
        summary = None
        excerpt_el = card.select_one(".excerpt")
        if excerpt_el:
            summary = excerpt_el.get_text(strip=True)
            if summary and len(summary) > 300:
                summary = summary[:300]

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
