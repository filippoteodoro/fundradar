"""Site-specific extractors for www.tipspa.it (Tamburi Investment Partners / TIP).

TIP is an Italian publicly-listed investment/merchant banking firm (~€5B AUM,
HQ Milan, Borsa Italiana: TIP.MI). Portfolio data is maintained manually in
portfolio_items.json because the site is SPA-rendered for investments.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.tipspa.it"

URLS = {
    "portfolio": None,  # SPA (Next.js) — body is "Loading...", no static data
    "team": None,
    "news": "/en/page/5d24b680bac35e0a5a5eb25c",
}


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract press releases from TIP news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen = set()

    for article in soup.select("article, .post, .news-item, .card, .press-release, li"):
        title_el = article.select_one("h2, h3, h4, .title, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen:
            continue
        if title.lower() in ("press releases", "news", "back", "home"):
            continue
        seen.add(title.lower())

        url = None
        link = title_el if title_el.name == "a" else article.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        date = None
        date_el = article.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "news": extract_news,
}
