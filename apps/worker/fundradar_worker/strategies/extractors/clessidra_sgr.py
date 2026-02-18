"""Site-specific extractors for www.clessidragroup.it (Clessidra Private Equity SGR).

Portfolio page: https://www.clessidragroup.it/soluzioni/private-equity/fondi-investimenti/
Companies are displayed with logo images (alt="logo {CompanyName}") and also
in structured portfolio cards linking to /portfolio/{company-slug}/ detail pages.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.clessidragroup.it"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/soluzioni/private-equity/fondi-investimenti/",
    "team": "/gruppo/team/",
    "news": "/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Clessidra investments page.

    Strategy 1: Logo images with alt="logo {CompanyName}"
    Strategy 2: Links to /portfolio/{company}/ detail pages
    Strategy 3: Structured cards with company metadata (Azienda label)
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    def add_company(name: str, website: str = None, sector: str = None,
                    detail_url: str = None, status: str = None,
                    source: str = "clessidra_logos") -> bool:
        """Add a company if not already seen."""
        if not name or len(name) < 2 or name.lower() in seen:
            return False
        # Skip generic/nav items
        skip = ["clessidra", "clessidra group", "italiano", "inglese",
                "portafoglio", "portfolio", "home", "menu",
                "strategie", "investimento", "scopri di più",
                "scopri di piu", "leggi tutto", "read more",
                "continua a leggere"]
        if name.lower() in skip or any(s in name.lower() for s in [
            "strategie", "investimento", "investment",
            "scopri di", "leggi tutto", "read more",
        ]):
            return False
        seen.add(name.lower())
        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "detail_page_url": detail_url,
            "status": status,
            "confidence": 0.85,
            "source": source,
        })
        return True

    # Strategy 1: Find all logo images - pattern is alt="logo {CompanyName}"
    for img in soup.select("img[alt]"):
        alt = img.get("alt", "").strip()
        if not alt.lower().startswith("logo "):
            continue

        name = alt[5:].strip()  # Remove "logo " prefix

        # Try to get link from parent anchor
        website = None
        parent_link = img.find_parent("a")
        if parent_link:
            href = parent_link.get("href", "")
            if href and not href.startswith("#") and "clessidra" not in href.lower():
                website = urljoin(base_url, href)

        add_company(name, website=website)

    # Strategy 2: Links to portfolio detail pages
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/portfolio/" not in href:
            continue
        if href.rstrip("/").endswith("/portfolio"):
            continue

        name = link.get_text(strip=True)
        if not name:
            img = link.find("img")
            if img:
                name = (img.get("alt") or "").replace("logo ", "").strip()

        if not name or len(name) < 2 or len(name) > 80:
            continue

        detail_url = urljoin(base_url, href)
        add_company(name, detail_url=detail_url, source="clessidra_portfolio_links")

    # Strategy 3: Look for company names in structured text near "Azienda" labels
    for el in soup.find_all(string=re.compile(r"Azienda", re.I)):
        parent = el.find_parent(["div", "td", "li", "span", "dt"])
        if not parent:
            continue
        # The company name is typically in a sibling or nearby element
        next_el = parent.find_next_sibling()
        if next_el:
            name = next_el.get_text(strip=True)
            if name and 2 < len(name) < 80:
                add_company(name, source="clessidra_azienda_label")

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Clessidra team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    # Look for team member cards/items
    for item in soup.select(".team-member, .person, .member, article"):
        # Try to find name
        name_el = item.select_one("h2, h3, h4, .name, .title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen:
            continue

        seen.add(name.lower())

        # Try to get title/role
        title = None
        title_el = item.select_one(".role, .position, .job-title, p")
        if title_el and title_el != name_el:
            title = title_el.get_text(strip=True)

        # Get photo URL
        photo_url = None
        img = item.select_one("img")
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
    Extract news items from Clessidra news page.

    Structure: WordPress theme with:
    - Container: .wpex-post-cards
    - Date from .vcex-post-meta (dd/mm/yyyy format)
    - Title from .vcex-heading h3/h4
    - URL from <a> href (relative)
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all article/div elements that look like news cards
    for item in soup.find_all(["article", "div"], class_=re.compile(r"card|post|entry|vcex", re.I)):
        # Skip items without links
        link = item.find("a", href=True)
        if not link:
            continue

        href = link.get("href", "")

        # Skip navigation/category links
        if not href or href == "#" or "/category/" in href or "/tag/" in href:
            continue

        # Get title - look in heading or link text
        title = None
        heading = item.find(["h2", "h3", "h4", "h5"])
        if heading:
            title = heading.get_text(strip=True)
        if not title:
            title = link.get_text(strip=True)

        if not title or len(title) < 10:
            continue

        # Skip "Scopri di più" (read more) links
        if title.lower() in ["scopri di più", "read more", "leggi tutto", "continua"]:
            continue

        title_key = title.lower()[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Get date - look for dd/mm/yyyy pattern in meta or nearby text
        date = None
        meta = item.find(class_=re.compile(r"meta|date|time", re.I))
        text_to_search = meta.get_text(" ", strip=True) if meta else item.get_text(" ", strip=True)

        date_match = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", text_to_search)
        if date_match:
            day, month, year = date_match.groups()
            date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # Build URL
        url = urljoin(base_url, href)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
