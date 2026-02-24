"""Site-specific extractors for www.silverlake.com (Silver Lake).

Silver Lake is a tech-focused PE firm (~$116B AUM, HQ Menlo Park). Major Italian
deals include Facile.it (majority stake) and TeamSystem (strategic minority).

Portfolio at /portfolio/, news at /news/.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.silverlake.com"

URLS = {
    "portfolio": "/portfolio/",
    "team": None,
    "news": "/news/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Silver Lake portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    for item in soup.select(
        "article, .portfolio-item, .company, .card, .grid-item, "
        "[class*='portfolio'], [class*='company'], li"
    ):
        heading = item.select_one("h2, h3, h4, .name, .title, strong")
        if not heading:
            continue

        name = heading.get_text(strip=True)
        if not name or len(name) < 2 or name.lower() in seen:
            continue
        if name.lower() in (
            "portfolio", "our portfolio", "investments", "back",
            "silver lake", "view all", "current", "realized",
        ):
            continue
        seen.add(name.lower())

        website = None
        link = item.select_one("a[href^='http']")
        if link and "silverlake.com" not in link.get("href", ""):
            website = link.get("href")

        description = None
        desc_el = item.select_one("p, .description, .excerpt")
        if desc_el and desc_el != heading:
            text = desc_el.get_text(strip=True)
            if len(text) > 15:
                description = text[:500]

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description,
            "status": "current",
            "confidence": 0.85,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Silver Lake news page."""
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
