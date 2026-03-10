"""Site-specific extractors for charmecapitalpartners.com."""
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re

DOMAIN = "www.charmecapitalpartners.com"

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/funds",
    "team": None,
    "news": "/news",
}
# Known non-company domains to exclude
EXCLUDED_DOMAINS = {
    "charmecapitalpartners.com", "google.com", "allaboutcookies.org",
    "fca.org.uk", "register.fca.org.uk", "joerns.co.uk",
    "facebook.com", "linkedin.com", "twitter.com", "instagram.com",
    "youtube.com",
    # Acquirers/co-investors — NOT Charme portfolio companies
    "tata.com", "tatacommunications.com",
    "medtronic.com",
    "ima.it", "imagroup.com",
    "livingbridge.com",
    # Poltrona Frau Group subsidiaries (Charme invested in the group, not these separately)
    "cassina.com", "cappellini.com",
}

# Reject image alt text, logo refs, pixel dimensions, CSS class names
_GARBAGE_RE = re.compile(
    r"logo|^\d|px$|\d{2,}px|\bimage\b|"
    r"\.(jpg|jpeg|png|gif|svg|webp)$",
    re.I,
)

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Charme Capital Partners funds page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_domains = set()

    # Find all external links that look like company websites
    for a in soup.select("a[href^='http']"):
        href = a.get("href", "")

        # Parse the URL
        try:
            parsed = urlparse(href)
            domain = parsed.netloc.lower().replace("www.", "")
        except Exception:
            continue

        # Skip excluded domains
        if any(exc in domain for exc in EXCLUDED_DOMAINS):
            continue

        # Skip if already seen this domain
        if domain in seen_domains:
            continue
        seen_domains.add(domain)

        # Always derive name from domain (more reliable than link text
        # which often contains image alt text or garbled CSS class names)
        name_parts = domain.split(".")[0]
        name = name_parts.replace("-", " ").replace("_", " ").title()

        if not name or len(name) < 2 or len(name) > 60:
            continue

        # Skip names that look like garbage
        if _GARBAGE_RE.search(name):
            continue

        companies.append({
            "name": name,
            "sector": None,
            "website": href,
            "description": None,
            "status": "current",
            "confidence": 0.80,
        })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members - not implemented for this site."""
    return []

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Charme Capital Partners news page.

    Structure:
    - h5 elements containing <a> links to news articles
    - Date in nearby text (DD Month YYYY format)
    """
    from urllib.parse import urljoin

    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Month name to number mapping

    # Find h5 elements with news links
    for h5 in soup.find_all("h5"):
        link = h5.find("a", href=True)
        if not link:
            continue

        href = link.get("href", "")
        if not href or not href.startswith("/news/"):
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_key = title.lower()[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        url = urljoin(base_url, href)

        # Look for date in sibling or parent text
        date = None
        parent = h5.find_parent(["div", "article", "li", "section"])
        if parent:
            text = parent.get_text(" ", strip=True)
            # Pattern: DD Month YYYY
            date_match = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
            if date_match:
                day, month_name, year = date_match.groups()
                month_num = _MONTH_NAMES.get(month_name.lower(), "01")
                if month_num:
                    date = f"{year}-{month_num}-{day.zfill(2)}"

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
