"""Site-specific extractors for www.charterhouse.co.uk (Charterhouse Capital Partners).

Charterhouse is a European mid-market PE firm (~€5B AUM, HQ London). Italian deals
include DOC Generici (pharma), Nuova Castelli (cheese), and Mec3 (gelato ingredients,
sold 2025 at ~EUR 900M EV).

Portfolio at /portfolio, news at /news.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.charterhouse.co.uk"

URLS = {
    "portfolio": "/portfolio",
    "team": None,
    "news": "/news",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Charterhouse portfolio page.

    Charterhouse uses a.portfolio-module elements with company logos.
    Company names are in the alt attribute of img tags (format: "Company Logo").
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Primary: portfolio module cards with logo images
    for item in soup.select("a.portfolio-module"):
        img = item.select_one("img[alt]")
        if not img:
            continue

        alt = img.get("alt", "").strip()
        if not alt:
            continue

        # Strip " Logo" suffix from alt text
        name = alt
        if name.lower().endswith(" logo"):
            name = name[:-5].strip()

        if not name or len(name) < 2 or name.lower() in seen:
            continue
        if name.lower() in (
            "portfolio", "charterhouse", "back", "view all",
        ):
            continue
        seen.add(name.lower())

        detail_url = urljoin(base_url, item.get("href", ""))

        description = None
        desc_el = item.select_one("p, .content span")
        if desc_el:
            text = desc_el.get_text(strip=True)
            if len(text) > 15:
                description = text[:500]

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": description,
            "status": "current",
            "confidence": 0.90,
            "detail_page_url": detail_url,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from Charterhouse news page."""
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
