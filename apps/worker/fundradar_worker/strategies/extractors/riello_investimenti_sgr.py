"""Site-specific extractors for rielloinvestimenti.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.rielloinvestimenti.it"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio.html",
    "team": "/struttura.html",
    "news": "/press.html",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Riello Investimenti portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Each portfolio item is in a div.isotope-item with fund type class
    for item in soup.select("div.isotope-item"):
        # Get company name from span.thumb-info-inner
        name_el = item.select_one("span.thumb-info-inner")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Get fund name from span.thumb-info-type
        fund_name = None
        fund_el = item.select_one("span.thumb-info-type")
        if fund_el:
            fund_name = fund_el.get_text(strip=True)

        # CSS classes indicate fund type (equity/debt/vent), not company sector
        sector = None

        # Get detail page URL
        website = None
        link_el = item.select_one("a[href]")
        if link_el:
            href = link_el.get("href", "")
            if href and not href.startswith("#"):
                website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": fund_name,  # Store fund name as description
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Riello Investimenti team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Team members are in col-lg-3 col-sm-6 divs containing span.thumb-info
    for col in soup.select("div.col-lg-3.col-sm-6"):
        # Look for the name in h5.thumb-info-inner
        name_el = col.select_one("h5.thumb-info-inner")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Get title from span.thumb-info-type
        title = None
        title_el = col.select_one("span.thumb-info-type")
        if title_el:
            # Use separator to handle <br> tags properly
            title = title_el.get_text(separator=" ", strip=True)
            # Clean up multiple spaces
            title = " ".join(title.split())

        # Get photo URL
        photo_url = None
        img = col.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower or "founder" in title_lower or "presidente" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower:
                role = "associate"
            elif "consigliere" in title_lower:
                role = "board"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/press releases from Riello Investimenti press page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []

    # News items use same structure as portfolio: div.portfolio-item
    for item in soup.select("div.portfolio-item"):
        # Get all thumb-info-type spans - first is date, second is title
        type_spans = item.select("span.thumb-info-type")
        if len(type_spans) < 2:
            continue

        date_text = type_spans[0].get_text(strip=True)
        title = type_spans[1].get_text(strip=True)

        if not title or len(title) < 5:
            continue

        # Get article URL
        url = None
        link = item.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href and not href.startswith("#"):
                url = urljoin(base_url, href)

        # Parse date (format: "16 dicembre 2025")
        date = None
        if date_text:
            # Keep as-is for now, could parse to ISO format
            date = date_text

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.90,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
