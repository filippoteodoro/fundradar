"""Site-specific extractors for mittel.it."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.mittel.it"



# URL paths for monitoring - verified against live site Feb 2026
# Note: /investments does NOT exist; actual equity page is Italian URL
URLS = {
    "portfolio": "/prodotti-e-servizi/investimenti-in-equity/",
    "team": "/management",
    "news": "/en/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Mittel equity investments page.

    Structure (verified Feb 2026):
    - Page at /prodotti-e-servizi/investimenti-in-equity/
    - Container class: partecipazioniintrotabs (NOT partecipazioniintrotab2)
    - Companies are <a> tags linking to external company websites, wrapping <img> elements
    - Image alt text may be empty; fallback to domain name extraction
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_urls = set()

    # Try multiple container class patterns
    containers = soup.select("div.partecipazioniintrotabs, div.partecipazioniintrotab2, div.partecipazioniintrotab")
    if not containers:
        # Fallback: look for the section containing external links
        containers = [soup]

    for container in containers:
        for link in container.select("a[href]"):
            href = link.get("href", "").strip()
            if not href:
                continue

            # Skip internal Mittel links
            if "mittel.it" in href.lower():
                continue
            # Must be an external URL (company website)
            if not href.startswith("http"):
                continue

            # Skip duplicates
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Try to get company name from image alt text
            name = None
            img = link.select_one("img")
            if img:
                alt = img.get("alt", "").strip()
                if alt and len(alt) > 2:
                    # Skip section headings and navigation text
                    alt_lower = alt.lower()
                    if any(skip in alt_lower for skip in [
                        "investimenti", "equity", "portfolio", "partecipazioni",
                        "menu", "home", "back", "investment", "view all",
                    ]):
                        continue
                    name = alt

            # Fallback: extract company name from URL domain
            if not name:
                domain = href.replace("https://", "").replace("http://", "").replace("www.", "")
                domain_name = domain.split("/")[0].split(".")[0]
                if len(domain_name) > 2:
                    name = domain_name.replace("-", " ").title()

            if not name or len(name) < 2:
                continue

            companies.append({
                "name": name,
                "sector": None,
                "website": href,
                "description": None,
                "status": "current",
                "confidence": 0.85,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract board members from Mittel governance page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Board members are in table.memberstable
    table = soup.select_one("table.memberstable")
    if not table:
        return members

    for row in table.select("tr"):
        cells = row.select("td")
        if len(cells) < 2:
            continue

        # First cell is name, second is title
        name = cells[0].get_text(strip=True)
        title = cells[1].get_text(strip=True)

        if not name or len(name) < 3:
            continue

        # Get CV link if available
        cv_url = None
        cv_link = row.select_one("a[href*='.pdf']")
        if cv_link:
            cv_url = cv_link.get("href", "")

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "presidente" in title_lower:
                role = "partner"
            elif "vice presidente" in title_lower:
                role = "partner"
            elif "consigliere delegato" in title_lower or "ceo" in title_lower:
                role = "partner"
            elif "consigliere" in title_lower:
                role = "board"
            elif "direttore" in title_lower:
                role = "director"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract press releases from Mittel news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []

    # News items are in div.postitem
    for item in soup.select("div.postitem"):
        # Get title from h2 > a
        title_link = item.select_one("div.post-content h2 a")
        if not title_link:
            continue

        title = title_link.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        url = title_link.get("href", "")
        if url:
            url = urljoin(base_url, url)

        # Get date from calendar elements
        date = None
        month_el = item.select_one("div.post-month")
        day_el = item.select_one("div.post-day")
        year_el = item.select_one("div.post-year")

        if month_el and day_el and year_el:
            month = month_el.get_text(strip=True)
            day = day_el.get_text(strip=True)
            year = year_el.get_text(strip=True)
            date = f"{day} {month} {year}"

        # Get PDF attachment URL if available
        pdf_url = None
        pdf_link = item.select_one("div.post-attachment a[href*='.pdf']")
        if pdf_link:
            pdf_url = pdf_link.get("href", "")

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
