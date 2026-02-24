"""Site-specific extractors for hf.com (Hellman & Friedman).

Hellman & Friedman is a PE firm (~$115B AUM, HQ San Francisco) focused on
large-cap buyouts in technology, financial services, healthcare, and insurance.
Italian deal: TeamSystem (cloud ERP, acquired 2016).

Portfolio at /portfolio/, news at /news/, team at /people/.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "hf.com"

URLS = {
    "portfolio": "/portfolio/",
    "team": None,
    "news": "/news/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from H&F portfolio page.

    H&F uses a grid of company logos in div.portgrid elements. Company names
    are in the alt attribute of img tags (format: "Company Name - Hellman Friedman").
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Primary: company logos in portfolio grid
    for grid_item in soup.select("div.portgrid"):
        img = grid_item.select_one("img[alt]")
        if not img:
            continue

        alt = img.get("alt", "").strip()
        if not alt:
            continue

        # Strip " - Hellman Friedman" suffix from alt text
        name = alt
        for suffix in [" - Hellman Friedman", " - Hellman & Friedman", " - H&F"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()
                break

        if not name or len(name) < 2 or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get link to company detail page
        link = grid_item.select_one("a[href]")
        detail_url = urljoin(base_url, link.get("href", "")) if link else None

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": "current",
            "confidence": 0.90,
            "detail_page_url": detail_url,
        })

    # Fallback: links to individual company pages
    if not companies:
        for link in soup.select("a[href*='/portfolio/']"):
            href = link.get("href", "")
            if href.rstrip("/") == "/portfolio" or "/page/" in href:
                continue
            text = link.get_text(strip=True)
            if not text or len(text) < 3 or text.lower() in seen:
                continue
            if text.lower() in ("portfolio", "back", "view all"):
                continue
            seen.add(text.lower())
            companies.append({
                "name": text,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.75,
            })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from H&F news page."""
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
