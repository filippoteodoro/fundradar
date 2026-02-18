"""Site-specific extractors for fieesgr.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import re

DOMAIN = "www.fieesgr.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/en/investments/",
    "team": None,
    "news": "/en/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from FIEE SGR.

    Structure:
    - Companies in H4 headings within .et_pb_blurb_container
    - Current investments: /en/investments/
    - Realized investments: /en/exit/
    - Company names end with S.r.l., S.p.A., B.V., or S.L.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Determine if this is the exit page
    page_title = soup.select_one("h1")
    is_exit_page = "/exit" in base_url.lower()
    status = "exited" if is_exit_page else "current"

    # Find main content area
    main = soup.select_one("main, #main, .main-content, article")
    if not main:
        main = soup

    # Look for h4 headings that are company names
    for h4 in main.select("h4"):
        name = h4.get_text(strip=True)
        if not name:
            continue

        # Company names have legal suffixes
        if not any(suffix in name for suffix in ["S.r.l.", "S.p.A.", "B.V.", "S.L."]):
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Skip FIEE SGR itself
        if "fiee sgr" in name_lower:
            continue

        # Try to find a link in the parent container
        website = None
        blurb = h4.find_parent(class_="et_pb_blurb_container")
        if blurb:
            link = blurb.select_one("a[href]")
            if link:
                href = link.get("href", "")
                if href and "/project/" in href:
                    website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": "Energy/Infrastructure",  # FIEE specializes in energy efficiency
            "website": website,
            "description": None,
            "status": status,
            "confidence": 0.90,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from FIEE SGR press page.

    Structure:
    - News at /press/
    - Each item has H2 > A with title + URL
    - Date appears as text after H2 (format: "2 Febbraio 2026")
    - Categories appear after date (e.g., [ETF III], [Press])
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_urls = set()

    # Italian month mapping
    italian_months = {
        'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
        'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
        'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12
    }

    # Find all H2 > A elements (news titles)
    for h2 in soup.select("h2 a[href]"):
        url = h2.get("href", "")
        if not url:
            continue

        # Make absolute URL
        url = urljoin(base_url, url)

        # Skip duplicates
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Skip non-news URLs
        if "/press/" not in url and "/20" not in url:
            continue

        title = h2.get_text(strip=True)
        if not title:
            continue

        # Look for date in nearby text
        # Date typically appears right after H2, before categories
        published_at = None
        h2_parent = h2.find_parent()
        if h2_parent:
            # Get text after H2 element
            text_after = ""
            for sibling in h2_parent.next_siblings:
                if isinstance(sibling, str):
                    text_after += sibling
                elif sibling.name:
                    text_after += sibling.get_text(strip=True)
                    break  # Stop at first element
                if len(text_after) > 100:
                    break

            # Parse Italian date format: "2 Febbraio 2026"
            date_match = re.search(r'(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(\d{4})', text_after, re.IGNORECASE)
            if date_match:
                day = int(date_match.group(1))
                month = italian_months[date_match.group(2).lower()]
                year = int(date_match.group(3))
                try:
                    published_at = datetime(year, month, day).isoformat()
                except ValueError:
                    pass

        items.append({
            "title": title,
            "url": url,
            "published_at": published_at,
            "source": "FIEE SGR Press",
            "confidence": 0.85,
        })

    return items


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "news": extract_news,
}
