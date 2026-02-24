"""Site-specific extractors for www.azzurracapital.com (Azzurra Capital).

Azzurra Capital is a PE firm (~€600M AUM, HQ Luxembourg, Milan office).
Italian portfolio: Nextchem (MAIRE), Gruppo Desa (Chanteclair), Lucart Group,
DMX Pharma, Marval.

Portfolio at /portfolio/, news/media at /media/.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.azzurracapital.com"

URLS = {
    "portfolio": "/portfolio/",
    "team": "/team/",
    "news": "/media/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Azzurra Capital portfolio page.

    Azzurra uses WordPress + Elementor with a Loop Grid. Portfolio items are
    article.type-portfolio elements with h2/h3 company name headings.
    Currently 5 companies: Nextchem, DMX Pharma, Marval, Lucart Group, Gruppo Desa.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Primary: articles in the Elementor loop grid
    for article in soup.select("article.type-portfolio, article[class*='portfolio']"):
        heading = article.select_one("h2, h3, h4")
        if not heading:
            continue

        name = heading.get_text(strip=True)
        if not name or len(name) < 2 or name.lower() in seen:
            continue
        if name.lower() in (
            "portfolio", "our portfolio", "back", "view all",
            "azzurra capital", "investments", "asia fund",
        ):
            continue
        seen.add(name.lower())

        detail_url = None
        link = article.select_one("a[href]")
        if link:
            detail_url = urljoin(base_url, link.get("href", ""))

        description = None
        desc_el = article.select_one("p, .description, .excerpt")
        if desc_el and desc_el != heading:
            text = desc_el.get_text(strip=True)
            if len(text) > 15:
                description = text[:500]

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": description,
            "status": "current",
            "confidence": 0.90,
            "detail_page_url": detail_url,
        })

    # Fallback: headings that look like company names in main content
    if not companies:
        main = soup.select_one("main, .site-content, #content, .entry-content")
        if main:
            for heading in main.select("h2, h3"):
                name = heading.get_text(strip=True)
                if not name or len(name) < 2 or name.lower() in seen:
                    continue
                if name.lower() in (
                    "portfolio", "our portfolio", "azzurra capital",
                    "asia fund", "about us", "team", "media", "contact",
                ):
                    continue
                if len(name) > 80:
                    continue
                seen.add(name.lower())
                companies.append({
                    "name": name,
                    "sector": None,
                    "website": None,
                    "description": None,
                    "status": "current",
                    "confidence": 0.75,
                })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Azzurra Capital team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    for item in soup.select(
        ".team-member, .person, .card, article, "
        "[class*='team'], [class*='person'], [class*='member']"
    ):
        name_el = item.select_one("h2, h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen:
            continue
        if any(skip in name.lower() for skip in ["team", "about", "contact"]):
            continue
        seen.add(name.lower())

        title = None
        title_el = item.select_one(".title, .position, .role, p")
        if title_el and title_el != name_el:
            title = title_el.get_text(strip=True)

        linkedin = None
        for a in item.select("a[href*='linkedin']"):
            linkedin = a.get("href")
            break

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": None,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from Azzurra Capital media page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen = set()

    for article in soup.select("article, .post, .news-item, .card, .media-item"):
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
    "team": extract_team,
    "news": extract_news,
}
