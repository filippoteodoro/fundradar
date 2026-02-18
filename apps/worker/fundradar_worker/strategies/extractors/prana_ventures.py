"""Site-specific extractors for pranaventures.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re


DOMAIN = "pranaventures.it"



# URL paths — verified against live site
URLS = {
    "portfolio": "/",
    "team": None,
    "news": None,
}
# Known company name mappings from image filenames
COMPANY_NAME_MAP = {
    "getpica": "GetPica",
    "gfp": "Green Future Project",
    "daze": "Daze",
    "besafe-logo": "BeSafe",
    "aryel-logo": "Aryel",
    "sharewood": "Sharewood",
    "jet-hr": "JetHR",
    "hygge": "Hygge",
    "hercle": "Hercle",
    "factanza": "Factanza",
    "cosmico": "Cosmico",
    "otello": "Otello AI",
    "bowlpros": "BowlPros",
    "plentiness": "Plentiness",
    "ponyu": "Ponyu",
    "ring33": "Ring33",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Prana Ventures portfolio section."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Portfolio section contains company logos as images
    portfolio_section = soup.select_one("#section-portfolio")
    if not portfolio_section:
        return companies

    for img in portfolio_section.select("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if not src or "/uploads/" not in src:
            continue

        # Extract company name from image filename
        name_match = re.search(r"/([^/]+)\.(png|jpg|jpeg|webp|svg)", src.lower())
        if not name_match:
            continue

        filename = name_match.group(1)

        # Map filename to proper company name
        name = None
        for key, mapped_name in COMPANY_NAME_MAP.items():
            if key in filename.lower():
                name = mapped_name
                break

        if not name:
            # Clean up filename as company name
            name = filename.replace("-", " ").replace("_", " ").title()
            # Skip generic names
            if "progetto" in name.lower() or "logo" in name.lower():
                continue

        if name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get link if image is wrapped
        website = None
        parent_link = img.find_parent("a")
        if parent_link:
            href = parent_link.get("href", "")
            if href and "pranaventures" not in href:
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
    """Extract team members from Prana Ventures team section."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    # Team members are in elementor-icon-box-wrapper elements
    for wrapper in soup.select(".elementor-icon-box-wrapper"):
        # Get name from h3
        name_el = wrapper.select_one("h3")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get title from description
        title = None
        title_el = wrapper.select_one(".elementor-icon-box-description")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower:
                role = "partner"
            elif "cfo" in title_lower or "ceo" in title_lower or "chief" in title_lower:
                role = "c-level"
            elif "analyst" in title_lower:
                role = "analyst"
            elif "investment" in title_lower:
                role = "investment"

        # Get LinkedIn
        linkedin = None
        linkedin_el = wrapper.select_one("a[href*='linkedin.com']")
        if linkedin_el:
            linkedin = linkedin_el.get("href")

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/blog items from Prana Ventures blog page.

    Structure: h2 headings for titles, with dates in parent containers.
    URLs are found by matching title text in links.
    Date pattern: "DD Month YYYY" (Italian: "24 Maggio 2024")
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Get all h2 titles (skip page title "blog")
    h2s = [h for h in soup.select('h2')
           if h.get_text(strip=True).lower() != 'blog'
           and len(h.get_text(strip=True)) > 20]

    for h2 in h2s:
        title = h2.get_text(strip=True)
        if not title or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Find URL - search all links for matching text
        url = None
        for link in soup.find_all('a', href=True):
            if '/tutte-le-news/' in link.get('href', '') and title in link.get_text(strip=True):
                url = urljoin(base_url, link.get('href'))
                break

        # Find date - look in parent containers
        # Pattern: DD Month YYYY (Italian format)
        date = None
        container = h2.parent
        for _ in range(5):  # Go up 5 levels
            if container:
                text = container.get_text()
                date_match = re.search(
                    r'(\d{1,2}\s+(?:Gennaio|Febbraio|Marzo|Aprile|Maggio|Giugno|Luglio|Agosto|Settembre|Ottobre|Novembre|Dicembre|gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4})',
                    text
                )
                if date_match:
                    date = date_match.group(1)
                    break
                container = container.parent

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
