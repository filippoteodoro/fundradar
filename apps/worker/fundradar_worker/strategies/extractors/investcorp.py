"""Site-specific extractors for www.investcorp.com (Investcorp).

Investcorp is a global alternative investment firm (~$62B AUM, HQ Manama, Bahrain).
Very active in Italy: CloudCare, Corneliani, Vivaticket, Sababa Security, Epipoli,
plus Italian RE and NPL portfolios.

News at /category/news/. No dedicated public portfolio page.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.investcorp.com"

URLS = {
    "portfolio": None,
    "team": None,
    "news": "/category/news/",
}


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from Investcorp news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen = set()

    for article in soup.select(
        "article, .post, .news-item, .card, [class*='news'], [class*='post']"
    ):
        title_el = article.select_one("h2, h3, h4, .title, .entry-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen:
            continue
        if title.lower() in ("news", "press releases", "back", "load more"):
            continue
        seen.add(title.lower())

        url = None
        link = title_el.select_one("a[href]") or article.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        date = None
        date_el = article.select_one("time, .date, [datetime], .entry-date")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        summary = None
        summary_el = article.select_one("p, .excerpt, .summary, .entry-summary")
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
    "news": extract_news,
}
