"""Site-specific extractors for www.tpg.com (TPG).

TPG is a global alternative asset management firm (~$303B AUM, HQ San Francisco)
with platforms spanning Capital, Growth, Impact, Credit, Real Estate, and Market
Solutions. Italian activity includes a Milan office and deals such as the Nexi
digital banking bid and Footballco/Calciomercato.com.

News page at /news-and-insights/news shows press releases. Portfolio page at
/portfolio lists companies across platforms. Site is Next.js (server-rendered).
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import re

DOMAIN = "www.tpg.com"

URLS = {
    "portfolio": None,
    "team": None,
    "news": "/news-and-insights/news",
}


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/press releases from TPG news page.

    TPG uses Next.js with server-side rendering. News items are embedded
    in the initial HTML via React Flight Protocol data chunks.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen = set()

    # Try to extract from Next.js Flight Protocol data
    for script in soup.select("script"):
        text = script.string or ""
        if "self.__next_f.push" not in text:
            continue
        # Look for news item patterns in the serialized data
        # Titles appear as strings in the Flight data
        for match in re.finditer(
            r'"uri"\s*:\s*"(/news-and-insights/[^"]+)".*?"date"\s*:\s*"([^"]+)".*?"title"\s*:\s*"([^"]+)"',
            text, re.DOTALL
        ):
            uri, date, title = match.groups()
            if title in seen or len(title) < 10:
                continue
            seen.add(title)

            news.append({
                "title": title,
                "url": urljoin(base_url, uri),
                "date": date[:10] if date else None,
                "summary": None,
                "confidence": 0.85,
            })

    # Fallback: parse rendered HTML
    if not news:
        for article in soup.select("article, .wp-block-post, a[href*='/news-and-insights/']"):
            heading = article.select_one("h2, h3, h4")
            if not heading:
                # If the element is an <a> with text, use it directly
                if article.name == "a":
                    title = article.get_text(strip=True)
                    href = article.get("href", "")
                else:
                    continue
            else:
                title = heading.get_text(strip=True)
                link = article.select_one("a[href]")
                href = link.get("href", "") if link else ""

            if not title or len(title) < 10 or title.lower() in seen:
                continue
            if title.lower() in ("news", "press releases", "insights", "load more"):
                continue
            seen.add(title.lower())

            url = urljoin(base_url, href) if href else None

            date = None
            time_el = article.select_one("time, [datetime]")
            if time_el:
                date = time_el.get("datetime") or time_el.get_text(strip=True)

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
