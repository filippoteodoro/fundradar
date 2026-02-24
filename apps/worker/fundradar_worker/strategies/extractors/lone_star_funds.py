"""Site-specific extractors for www.lonestarfunds.com (Lone Star Funds).

Lone Star is a global PE/credit/real estate firm (~$95B AUM, HQ Dallas).
Italian deal: RadiciGroup specialty chemicals (~EUR 1B, 2025).

News at /news/. No public portfolio page (credit/distressed fund).
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.lonestarfunds.com"

URLS = {
    "portfolio": None,
    "team": None,
    "news": "/news/",
}


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Lone Star news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen = set()

    for article in soup.select(
        "article, .post, .news-item, .card, [class*='news'], [class*='press']"
    ):
        title_el = article.select_one("h2, h3, h4, .title, .heading")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen:
            continue
        if title.lower() in ("news", "press releases", "back"):
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
    "news": extract_news,
}
