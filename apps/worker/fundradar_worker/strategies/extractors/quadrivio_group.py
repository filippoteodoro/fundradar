"""Site-specific extractors for quadriviogroup.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.quadriviogroup.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/it/fondi/industry-4-0-fund/portfolio",
    "team": "/it/about/people",
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Quadrivio Group portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Portfolio cards use article.cm-azienda-partecipata-card-3
    for item in soup.select("article.cm-azienda-partecipata-card-3"):
        # Get company name from h2.cm-azienda-partecipata-card-3__title
        name_el = item.select_one("h2.cm-azienda-partecipata-card-3__title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip government programs and non-company entries
        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "nuova sabatini", "sabatini", "incentivo",
            "agevolazione", "bando", "contributo",
        ]):
            continue

        # Get description from div.cm-azienda-partecipata-card-3__abstract
        description = None
        desc_el = item.select_one("div.cm-azienda-partecipata-card-3__abstract")
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        # Get status from link path - /exit/ indicates exited companies
        status = "current"
        link_el = item.select_one("a[href]")
        if link_el:
            href = link_el.get("href", "")
            if "/exit/" in href:
                status = "exited"

        # Note: The portfolio cards don't contain actual company website URLs
        # Only internal detail page links - website is set to None per extraction guidelines
        companies.append({
            "name": name,
            "sector": None,  # Subtitle is typically empty on this site
            "website": None,  # Actual company URLs would require fetching detail pages
            "description": description,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Quadrivio Group people page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Team members are in article.cm-card-persona-1
    for item in soup.select("article.cm-card-persona-1"):
        # Get name from div.cm-card-persona-1__nome
        name_el = item.select_one("div.cm-card-persona-1__nome")
        if not name_el:
            continue

        # Name is in ALL CAPS, convert to title case
        name_raw = name_el.get_text(strip=True)
        if not name_raw or len(name_raw) < 3:
            continue
        name = name_raw.title()

        # Get title/role from div.cm-card-persona-1__ruolo
        title = None
        title_el = item.select_one("div.cm-card-persona-1__ruolo")
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo URL from img.cm-card-persona-1__img
        photo_url = None
        img = item.select_one("img.cm-card-persona-1__img")
        if img:
            src = img.get("data-src") or img.get("src")
            if src and "placeholder" not in src:
                photo_url = urljoin(base_url, src)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if any(k in title_lower for k in ["ceo", "founder", "president", "chairman"]):
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"
            elif "board" in title_lower or "consigliere" in title_lower:
                role = "board"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract press releases from Quadrivio Group press releases page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Press releases are in article.cm-comunicato-stampa-teaser
    for item in soup.select("article.cm-comunicato-stampa-teaser"):
        # Get title from h2 a
        title_el = item.select_one("h2 a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL
        url = None
        href = title_el.get("href")
        if href:
            url = urljoin(base_url, href)

        # Get date from div.cm-comunicato-stampa-teaser__data (format: DD.MM.YYYY)
        date = None
        date_el = item.select_one(".cm-comunicato-stampa-teaser__data")
        if date_el:
            date = date_el.get_text(strip=True)

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
