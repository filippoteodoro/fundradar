"""Site-specific extractors for www.icgam.com (ICG / Intermediate Capital Group).

ICG is a global alternative asset manager (~€113B AUM, HQ London) with strategies
spanning structured capital, private debt, PE secondaries, credit, and real assets.
Italian office in Milan (Corso Giacomo Matteotti 3).

News at /news-insights-analysis/. No public portfolio page (credit/secondaries fund).
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.icgam.com"

URLS = {
    "portfolio": None,
    "team": None,
    "news": "/news-insights-analysis/",
}


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/insights from ICG news page."""
    import re

    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen = set()

    for article in soup.select(
        "article, .post, .news-item, .card, .insight-card, "
        "[class*='news'], [class*='article'], [class*='insight']"
    ):
        title_el = article.select_one("h2, h3, h4, .title, .heading")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen:
            continue
        if title.lower() in ("news", "insights", "analysis", "load more", "view all"):
            continue
        # Skip concatenated hero copy (e.g., "We invest globally.We grow ...")
        if title.count(".") >= 2 and not re.search(r"\.\s", title):
            continue
        seen.add(title.lower())

        url = None
        link = article.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))
        # Real news cards always have a navigable article URL.
        if not url or url.rstrip("/") == base_url.rstrip("/"):
            continue

        date = None
        date_el = article.select_one("time, .date, [datetime], .published")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        summary = None
        summary_el = article.select_one("p, .excerpt, .summary, .description")
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
