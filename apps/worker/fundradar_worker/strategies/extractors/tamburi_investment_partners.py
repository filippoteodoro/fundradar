"""Site-specific extractors for www.tipspa.it (Tamburi Investment Partners / TIP).

TIP is an Italian publicly-listed investment/merchant banking firm (~€5B AUM,
HQ Milan, Borsa Italiana: TIP.MI). Portfolio includes Moncler, Amplifon,
Interpump, Eataly, Alpitour, Bending Spoons, OVS, Engineering.

Note: TIP uses opaque hash-based URLs (e.g., /en/page/5d24b681bac35e0a5a5eb28d).
Portfolio page lists investments. News at press releases page.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.tipspa.it"

URLS = {
    "portfolio": None,  # SPA (Next.js) — body is "Loading...", no static data
    "team": None,
    "news": "/en/page/5d24b680bac35e0a5a5eb25c",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from TIP investments page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # TIP lists investments in various formats — try multiple selectors
    for item in soup.select(
        "article, .card, .portfolio-item, .investment, "
        "[class*='portfolio'], [class*='investment'], "
        ".grid-item, .item, li"
    ):
        heading = item.select_one("h2, h3, h4, .name, .title, strong, a")
        if not heading:
            continue

        name = heading.get_text(strip=True)
        if not name or len(name) < 2 or name.lower() in seen:
            continue
        if name.lower() in (
            "investments", "portfolio", "back", "view all",
            "tamburi", "tip", "home", "press releases",
            "investor relations", "contacts", "about us",
        ):
            continue
        # Skip long text blocks (descriptions, not names)
        if len(name) > 80:
            continue
        seen.add(name.lower())

        website = None
        link = item.select_one("a[href^='http']")
        if link and "tipspa.it" not in link.get("href", ""):
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
            "confidence": 0.80,
        })

    return companies


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
    "portfolio": extract_portfolio,
    "news": extract_news,
}
