"""Site-specific extractors for www.f2isgr.it (F2i SGR - Fondi Italiani per le Infrastrutture)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.f2isgr.it"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/en/portfolio/index.html",
    "team": "/en/team/team.html",
    "news": "/en/media/press-releases/index.html",
}
_LOGO_RE = re.compile(r"\blog[oa]\b", re.I)
_SKIP_RE = re.compile(
    r"^(?:immagine|image|swdes|logo)\d*$|"
    r"\.(jpg|jpeg|png|gif|svg|webp)$",
    re.I,
)


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from F2i SGR portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Companies are in section.section elements, organized by sector (h2)
    for section in soup.select("section.section"):
        h2 = section.select_one("h2")
        sector = h2.get_text(strip=True) if h2 else None

        for article in section.select("article.str__article"):
            h3 = article.select_one("h3")
            if not h3:
                continue

            name = h3.get_text(strip=True)
            if not name or name.lower() in seen:
                continue
            # Skip logo references and image artifacts
            if _LOGO_RE.search(name) or _SKIP_RE.search(name):
                continue

            seen.add(name.lower())

            companies.append({
                "name": name,
                "sector": sector,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.9,
            })

    # Strategy 2: Fallback - look for portfolio links
    if not companies:
        for link in soup.find_all("a", href=re.compile(r"/portfolio/investimenti/[^/]+\.html")):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if not text or len(text) <= 3 or text.lower() in seen:
                continue
            if _LOGO_RE.search(text) or _SKIP_RE.search(text):
                continue
            seen.add(text.lower())
            companies.append({
                "name": text,
                "sector": None,
                "website": urljoin(base_url, href),
                "description": None,
                "status": "current",
                "confidence": 0.80,
            })

    # Strategy 3: Generic card fallback
    if not companies:
        for card in soup.find_all(class_=re.compile(r"card|portfolio|invest", re.I)):
            heading = card.find(["h2", "h3", "h4"])
            if heading:
                name = heading.get_text(strip=True)
                if not name or len(name) <= 2 or name.lower() in seen:
                    continue
                if _LOGO_RE.search(name) or _SKIP_RE.search(name):
                    continue
                seen.add(name.lower())
                companies.append({
                    "name": name,
                    "sector": None,
                    "website": None,
                    "description": None,
                    "status": "current",
                    "confidence": 0.65,
                })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from F2i SGR news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Look for news article elements
    for article in soup.select("article, .news-item, [class*='news']"):
        title_el = article.find(["h2", "h3", "h4"])
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        # Get link
        url = None
        link = article.find("a", href=True)
        if link:
            url = urljoin(base_url, link.get("href", ""))

        # Get date
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
