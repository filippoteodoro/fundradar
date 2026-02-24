"""Site-specific extractors for www.platinumequity.com (Platinum Equity).

Platinum Equity is a PE firm (~$50B AUM, HQ Beverly Hills) focused on buyouts.
Italian portfolio: Polli (pesto/food, 2024), De Wave Group (marine furniture),
Fantini Group (wine).

Portfolio at /our-companies/, news at /our-news/.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.platinumequity.com"

URLS = {
    "portfolio": "/our-companies/",
    "team": None,
    "news": "/our-news/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Platinum Equity companies page.

    Platinum Equity uses an Elementor-based layout. Company logos are img tags
    with company names in the alt attribute. Only ~20 of 50+ companies are
    in the static HTML (the rest require JS "See all" click).
    """
    import re

    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Primary: extract company names from img alt attributes
    for img in soup.select("img[alt]"):
        alt = img.get("alt", "").strip()
        if not alt or len(alt) < 3:
            continue

        # Clean common suffixes
        name = alt
        name = re.sub(r'\s*[-–]\s*logo\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+logo\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*[-–]\s*Platinum\s+Equity\s*$', '', name, flags=re.IGNORECASE)
        name = name.strip()

        if not name or len(name) < 3 or name.lower() in seen:
            continue

        # Skip generic alt text
        skip = (
            "platinum equity", "logo", "icon", "image", "hero",
            "banner", "background", "our companies", "companies",
            "see all", "contact", "arrow", "menu",
        )
        if name.lower() in skip:
            continue
        if re.match(r'^(logo|icon|img|image)\b', name, re.IGNORECASE):
            continue
        if len(name) > 80:
            continue

        seen.add(name.lower())

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": "current",
            "confidence": 0.85,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from Platinum Equity news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen = set()

    for article in soup.select("article, .post, .news-item, .card"):
        title_el = article.select_one("h2, h3, h4, .title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen:
            continue
        seen.add(title.lower())

        url = None
        link = article.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        date = None
        date_el = article.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        summary = None
        summary_el = article.select_one("p, .excerpt, .summary")
        if summary_el and summary_el != title_el:
            summary = summary_el.get_text(strip=True)[:300]

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
    "news": extract_news,
}
