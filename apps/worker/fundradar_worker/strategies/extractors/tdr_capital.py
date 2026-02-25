"""Site-specific extractors for tdrcapital.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.tdrcapital.com"

# URL paths for monitoring — verified 2026-02-25
# Portfolio page is JS-rendered; portfolio companies added manually
URLS = {
    "portfolio": None,
    "team": None,
    "news": "/news/",
}


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from TDR Capital's news page.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for article in soup.select("article, .news-item, .post, a[href*='/news/']"):
        # Get title
        title = None
        for tag in ["h2", "h3", "h4"]:
            el = article.find(tag)
            if el:
                title = el.get_text(strip=True)
                break
        if not title:
            title = article.get_text(strip=True)[:200]

        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Get URL
        url = None
        if article.name == "a":
            url = urljoin(base_url, article.get("href", ""))
        else:
            link = article.find("a", href=True)
            if link:
                url = urljoin(base_url, link["href"])

        # Get date
        date = None
        date_el = article.find("time") or article.select_one(".date, [datetime]")
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


# Note: TDR Capital's portfolio page is fully JS-rendered
# Portfolio companies are added manually to portfolio_items.json
EXTRACTORS = {
    "news": extract_news,
}
