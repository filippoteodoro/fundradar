"""Site-specific extractors for b4investimenti.it.

B4 Investimenti focuses on Italian SMEs (EUR 10-50M revenue).
Portfolio page at /investment/ uses FacetWP filtering with cards.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.b4investimenti.it"

# URL paths for monitoring - verified Feb 2026
# Note: URL changed from /investimenti/ to /investment/ in late 2025
URLS = {
    "portfolio": "/investment/",
    "team": None,
    "news": "/news/",
}

_SKIP_LOWER = {
    "b4 investimenti", "what", "who", "how", "dna b4",
    "key numbers", "il nostro team", "organi societari",
    "il club b4", "la prospettiva di b4 investimenti",
    "contatti", "home", "menu", "news", "cookie",
    "investimenti", "investment", "team", "governance",
    "esplora", "explore",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from B4 Investimenti investment page.

    Structure (verified Feb 2026):
    - Cards are <a> tags with href /investment/{company-slug}/
    - Each card has company logo, description, fund category (B4HI/B4HII/B4HIII)
    - Company name appears in nested text or can be derived from slug
    - Page uses FacetWP filtering for status (In portfolio/EXIT)
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_slugs = set()

    # Strategy 1: Find links to /investment/{slug}/ detail pages
    for link in soup.find_all("a", href=re.compile(r"/investment/[a-z]", re.I)):
        href = link.get("href", "")
        # Extract slug from URL
        slug = href.rstrip("/").split("/")[-1]
        if not slug or slug in ("investment", "investimenti"):
            continue
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Try to get name from heading inside the card
        name = None
        heading = link.find(["h2", "h3", "h4", "h5"])
        if heading:
            name = heading.get_text(strip=True)

        # Try strong/bold text as company name
        if not name:
            strong = link.find("strong")
            if strong:
                candidate = strong.get_text(strip=True)
                if candidate and 3 <= len(candidate) <= 60:
                    name = candidate

        # Fallback: derive from slug
        if not name or len(name) > 60:
            name = slug.replace("-", " ").title()
            # Clean up common slug patterns
            name = re.sub(r"\s*\d+$", "", name)  # trailing numbers

        if not name or len(name) < 2:
            continue

        name_lower = name.lower().strip()
        if name_lower in _SKIP_LOWER:
            continue

        # Detect status from page context (FacetWP "EXIT" label)
        status = "current"
        parent_text = link.get_text(separator=" ", strip=True).lower()
        if "exit" in parent_text.split():
            status = "exited"

        # Get fund category (B4HI, B4HII, B4HIII)
        sector = None
        for p in link.find_all("p"):
            text = p.get_text(strip=True)
            if re.match(r"^B4H", text):
                sector = text
                break

        # Get description
        description = None
        for p in link.find_all("p"):
            text = p.get_text(strip=True)
            if text and len(text) > 20 and not text.startswith("B4H") and text.lower() != "esplora":
                description = text[:500]
                break

        companies.append({
            "name": name,
            "sector": sector,
            "website": urljoin(base_url, href),
            "description": description,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members - not implemented for this site."""
    return []


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/press items from B4 Investimenti news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # News items: article.post__card
    for item in soup.select("article.post__card"):
        # Title in h2
        title_el = item.select_one("h2")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # URL from a[href]
        url = None
        link = item.select_one("a[href]")
        if link and link.get("href"):
            url = urljoin(base_url, link["href"])

        # Date: div.text--s.uppercase.my1 (Italian format: "Febbraio 3, 2026")
        date = None
        date_el = item.select_one("div.text--s.uppercase.my1")
        if date_el:
            date = date_el.get_text(strip=True)

        # Category/type: div.text--xs.text--tag
        category = None
        cat_el = item.select_one("div.text--xs.text--tag")
        if cat_el:
            category = cat_el.get_text(strip=True)

        # Use category as summary
        summary = category if category else None

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
