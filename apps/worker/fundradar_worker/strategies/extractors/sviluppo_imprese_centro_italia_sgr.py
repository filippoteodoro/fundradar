"""Site-specific extractors for fondisici.it (SICI SGR)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin


DOMAIN = "www.fondisici.it"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/come-investiamo/",  # Investment approach with portfolio
    "team": "/chi-siamo/",
    "news": "/portafoglio/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from SICI SGR page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Portfolio companies are in elementor-portfolio-item__title elements
    for title_el in soup.select("h3.elementor-portfolio-item__title"):
        name = title_el.get_text(strip=True)
        if not name or name.lower() in seen:
            continue

        # Skip strategy/section headings (not company names)
        name_upper = name.upper()
        if any(skip in name_upper for skip in [
            "ESIGENZE", "CARATTERISTICHE", "VANTAGGI", "DELL'IMPRESA",
            "OPERAZIONE", "COME INVESTIAMO", "STRATEGIA", "INVESTIMENTO",
        ]):
            continue

        seen.add(name.lower())

        # Get detail URL from parent link
        detail_url = None
        parent_link = title_el.find_parent("a")
        if parent_link:
            href = parent_link.get("href")
            if href:
                detail_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
            "detail_url": detail_url,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from SICI SGR team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    # Team members are in elementor-image-box-wrapper elements
    for wrapper in soup.select(".elementor-image-box-wrapper"):
        # Get name from h4.elementor-image-box-title
        name_el = wrapper.select_one("h4.elementor-image-box-title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        # Skip non-person entries
        if not name or name.lower() in seen or name.lower() in ["contatti", "seguici su", "download area", "link utili"]:
            continue
        seen.add(name.lower())

        # Get title from p.elementor-image-box-description
        title = None
        title_el = wrapper.select_one("p.elementor-image-box-description")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "direttore generale" in title_lower or "general director" in title_lower:
                role = "c-level"
            elif "vice direttore" in title_lower:
                role = "vp"
            elif "senior" in title_lower:
                role = "senior"
            elif "manager" in title_lower:
                role = "manager"
            elif "analyst" in title_lower or "analista" in title_lower:
                role = "analyst"
            elif "administration" in title_lower or "segreteria" in title_lower:
                role = "admin"

        # Get LinkedIn from link
        linkedin = None
        link = name_el.select_one("a[href*='linkedin.com']")
        if link:
            linkedin = link.get("href")

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "confidence": 0.85,
        })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
