"""Site-specific extractors for stirlingsquare.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.stirlingsquare.com"

# URL paths for monitoring — verified 2026-02-25
URLS = {
    "portfolio": "/investments",
    "team": None,
    "news": "/news",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Stirling Square's investments page.

    The page lists investments with sector, core geographies, fund name,
    investment/exit dates, and status (In Portfolio / Realised / Partially).
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Try to find investment cards/sections
    # The page uses generic HTML without strong semantic markup
    for heading in soup.find_all(["h2", "h3"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 2 or len(name) > 80:
            continue

        # Skip section headings
        if name.lower() in ["investments", "current portfolio", "realised",
                            "our investments", "portfolio", "in portfolio"]:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Try to find surrounding context for metadata
        parent = heading.find_parent(["div", "section", "article"])
        sector = None
        status = None
        country = None

        if parent:
            text = parent.get_text(" ", strip=True).lower()

            # Look for status indicators
            if "realised" in text or "realized" in text:
                status = "exited"
            elif "in portfolio" in text:
                status = "current"

            # Look for sector after "sector" label
            for p in parent.find_all("p"):
                p_text = p.get_text(strip=True)
                if p_text and len(p_text) < 80 and p_text.lower() != name_lower:
                    if not sector and any(kw in p_text.lower()
                                          for kw in ["services", "technology",
                                                     "industrial", "healthcare",
                                                     "software", "environmental"]):
                        sector = p_text

        # Get link if heading is inside an anchor
        detail_url = None
        link = heading.find_parent("a")
        if link:
            detail_url = urljoin(base_url, link.get("href", ""))

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": None,
            "status": status,
            "detail_page_url": detail_url,
            "confidence": 0.80,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Stirling Square's news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for article in soup.select("article, .news-item, .post"):
        title = None
        for tag in ["h2", "h3", "h4"]:
            el = article.find(tag)
            if el:
                title = el.get_text(strip=True)
                break

        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = None
        link = article.find("a", href=True)
        if link:
            url = urljoin(base_url, link["href"])

        date = None
        date_el = article.find("time") or article.select_one(".date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        summary = None
        p = article.find("p")
        if p:
            summary = p.get_text(strip=True)[:300]

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
