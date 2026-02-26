"""Site-specific extractors for warburgpincus.com (Warburg Pincus).

Warburg Pincus is a global growth equity firm (~$87B AUM, HQ New York).
Investments page at /investments/, news at /news/.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
import re

DOMAIN = "warburgpincus.com"

URLS = {
    "portfolio": "/investments/",
    "team": None,
    "news": "/news/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Warburg Pincus investments page."""
    if "/investments" not in (base_url or "").lower():
        return []

    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()
    hard_skip = {
        "unity advisory",
        "community fibre",
        "skip to main content",
        "skip companies list",
    }

    # Primary extraction: cards are link-only (logo image + href slug), not text headings.
    for link in soup.select("a.investment--link[href*='/investments/']"):
        href = link.get("href", "")
        if not href:
            continue
        parsed_path = urlparse(href).path.strip("/")
        parts = [p for p in parsed_path.split("/") if p]
        if "investments" not in parts:
            continue
        try:
            slug = parts[parts.index("investments") + 1]
        except Exception:
            continue
        slug = unquote(slug).strip("/")
        if not slug:
            continue
        name = re.sub(r"[_\-]+", " ", slug).strip()
        if not name:
            continue
        # Title-case tokenized slugs while keeping 2-3 letter acronyms uppercase.
        words = []
        for w in name.split():
            if len(w) <= 3 and w.isalpha():
                words.append(w.upper())
            else:
                words.append(w.capitalize())
        name = " ".join(words).strip()
        name_key = name.lower().strip(" .")
        if not name or len(name) < 2 or name_key in seen:
            continue
        if name_key in (
            "investments", "portfolio", "back", "view all",
            "warburg pincus", "our investments",
        ):
            continue
        if name_key in hard_skip or re.search(r"unity\W*advisory", name_key):
            continue
        seen.add(name_key)
        card = link.find_parent(class_=re.compile(r"\binvestment\b"))
        sector = None
        if card and card.get("data-sectors"):
            sectors = [s.strip() for s in card.get("data-sectors", "").split(",") if s.strip()]
            if sectors:
                sector = ", ".join(s.replace("-", " ").title() for s in sectors)

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": None,
            "status": "current",
            "confidence": 0.92,
        })

    # Fallback for structural changes where link cards are not available.
    if companies:
        return companies

    for item in soup.select(
        "article, .portfolio-item, .investment, .card, .company, "
        "[class*='portfolio'], [class*='investment'], [class*='company']"
    ):
        heading = item.select_one("h2, h3, h4, .name, .title")
        if not heading:
            continue
        name = heading.get_text(strip=True)
        name_key = name.lower().strip(" .")
        if not name or len(name) < 2 or name_key in seen:
            continue
        if name_key in hard_skip or re.search(r"unity\W*advisory", name_key):
            continue
        seen.add(name_key)
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
    """Extract news from Warburg Pincus news page."""
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
