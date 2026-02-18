"""Site-specific extractors for argos.fund (Argos Wityu).

European mid-market PE fund (€2B AUM).
Portfolio at /portfolio/ uses Elementor with logo grid.
Company names in img alt text, links to /portfolio/{slug}/.
Separate "Previous Portfolio Companies" page for exits.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "argos.wityu.fund"


# URL paths — verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": None,
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Argos /portfolio/ page.

    Structure: Elementor grid with company logos as images.
    - Company names in img alt text (e.g., "Agon Electronics - Argos")
    - Links to detail pages at /portfolio/{company-slug}/
    - Revenue figures may appear nearby (e.g., "€582 M")
    - Sector labels near company cards
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Strategy 1: Find links to portfolio detail pages
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        # Match /portfolio/{slug}/ but not /portfolio/ itself
        if "/portfolio/" not in href or href.rstrip("/").endswith("/portfolio"):
            continue
        # Skip "previous" portfolio link
        if "previous" in href.lower():
            continue
        # Skip non-company pages
        if any(kw in href.lower() for kw in ["?", "#", "page", "category", "tag"]):
            continue

        # Get company name from img alt text
        name = None
        img = link.find("img")
        if img:
            alt = (img.get("alt") or "").strip()
            if alt:
                # Clean "Company Name - Argos" format
                name = re.sub(r'\s*[-–]\s*Argos.*$', '', alt, flags=re.IGNORECASE).strip()

        # Fallback: heading text inside link
        if not name:
            for tag in ["h2", "h3", "h4", "h5"]:
                el = link.find(tag)
                if el:
                    name = el.get_text(strip=True)
                    break

        # Fallback: link text itself
        if not name:
            text = link.get_text(strip=True)
            if text and len(text) < 50 and text.lower() not in ("learn more", "read more"):
                name = text

        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Skip non-company text (nav headers, section labels)
        skip_names = {
            "portfolio", "previous portfolio companies", "argos wityu",
            "stories", "mid-market portfolio", "climate action portfolio",
            "all argos portfolio", "case studies",
        }
        if name_lower in skip_names:
            continue

        # Try to find revenue and sector from nearby text
        sector = None
        description = None
        parent = link.find_parent("div")
        if parent:
            text = parent.get_text(separator=" ", strip=True)
            # Revenue pattern: €XXX M
            revenue_match = re.search(r'€\s*[\d,]+\s*M', text)
            if revenue_match:
                description = f"Revenue: {revenue_match.group()}"

        companies.append({
            "name": name,
            "sector": sector,
            "website": urljoin(base_url, href),
            "description": description,
            "status": "current",
            "confidence": 0.85,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Argos news page.

    Structure:
    - article.elementor-post contains each news item
    - h2/h3/h4 has the title
    - a has the news article link
    - Element with "date" in class has DD/MM/YYYY format date
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all article elements (Elementor posts)
    for article in soup.find_all("article", class_=lambda x: x and "elementor-post" in str(x)):
        # Get title from heading
        title_el = article.find(["h2", "h3", "h4"])
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_key = title.lower()[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Get URL from link
        url = None
        link = article.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and href != "https://argos.fund/news/":
                url = urljoin(base_url, href)

        # Get date from date element (DD/MM/YYYY format)
        date = None
        date_el = article.find(class_=lambda x: x and "date" in str(x).lower())
        if date_el:
            date_text = date_el.get_text(strip=True)
            # Parse DD/MM/YYYY format
            date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_text)
            if date_match:
                day, month, year = date_match.groups()
                date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

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
    "news": extract_news,
}
