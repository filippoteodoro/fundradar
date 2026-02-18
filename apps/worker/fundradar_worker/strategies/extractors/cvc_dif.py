"""Site-specific extractors for cvcdif.com (CVC DIF, infrastructure strategy of CVC).

URL structure changed in 2025/2026:
  - /investments → /infrastructure/investments
  - /management → /about-us/our-team
  - /en/news → /news-insights

The investments page is paginated (9 per page, 4 pages, ~30 total).
The extractor only sees page 1 HTML (9 companies) since it receives static HTML.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re


DOMAIN = "www.cvcdif.com"


URLS = {
    "portfolio": "/infrastructure/investments",
    "team": "/about-us/our-team",
    "news": "/news-insights",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from CVC DIF investments page.

    Structure: a.card.is-regular elements with h3 for name, span.tag for sector/fund.
    Only page 1 (9 of ~30 companies) is available from static HTML.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    for card in soup.select("a.card.is-regular"):
        name_el = card.select_one("h3")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get sector and fund from tags
        sector = None
        fund = None
        tags = card.select("span.tag")
        for tag in tags:
            tag_text = tag.get_text(strip=True)
            if "DIF" in tag_text.upper():
                fund = tag_text
            else:
                sector = tag_text

        # Get logo/image URL
        logo_url = None
        img = card.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                logo_url = urljoin(base_url, src)
        if not logo_url:
            source = card.select_one("picture source")
            if source:
                srcset = source.get("srcset", "")
                if srcset:
                    logo_url = urljoin(base_url, srcset.split()[0])

        companies.append({
            "name": name,
            "sector": sector.title() if sector else None,
            "website": None,
            "description": f"Fund: {fund}" if fund else None,
            "logo_url": logo_url,
            "status": "current",
            "confidence": 0.85,
        })

    # Fallback: try to extract from embedded JSON data in script tags
    if not companies:
        for script in soup.select("script"):
            text = script.string or ""
            if "totalItems" not in text or len(text) < 500:
                continue
            # Unescape double-escaped JSON
            unescaped = text.replace('\\"', '"')
            # Extract company names and sectors from modal data
            items = re.findall(
                r'"modal":\{"title":\{"value":"([^"]+)"\}.*?"sector":"([^"]+)"',
                unescaped,
            )
            for name, sector in items:
                if name.lower() in seen:
                    continue
                seen.add(name.lower())
                companies.append({
                    "name": name,
                    "sector": sector.title(),
                    "website": None,
                    "description": None,
                    "logo_url": None,
                    "status": "current",
                    "confidence": 0.80,
                })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from CVC DIF team page.

    Structure: accordion-item elements with h3 for name, .content.is-large for title.
    Also has quote cards with .quote-quotee for testimonials.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    _SKIP = {
        "join our team", "linkedin", "looking for something?",
        "cvc dif", "disclaimer", "useful links",
    }

    # Executive committee members in accordion items
    for accordion in soup.select(".accordion-item"):
        name_el = accordion.select_one("h3")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or name.lower() in seen or name.lower() in _SKIP:
            continue
        seen.add(name.lower())

        title = None
        title_el = accordion.select_one(".content.is-large")
        if title_el:
            title = title_el.get_text(strip=True)

        role = None
        if title:
            tl = title.lower()
            if "managing partner" in tl or "head of" in tl:
                role = "partner"
            elif any(x in tl for x in ["chief", "cio", "cro", "cfo"]):
                role = "c-level"
            elif "partner" in tl:
                role = "partner"
            elif "director" in tl:
                role = "director"
            elif "executive committee" in tl:
                role = "executive"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "confidence": 0.85,
        })

    # Also extract from quote cards (testimonials section)
    for card in soup.select(".card.is-quote"):
        quotee = card.select_one(".quote-quotee")
        if not quotee:
            continue
        spans = quotee.select("span.content")
        if len(spans) < 2:
            continue

        name = spans[0].get_text(strip=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        title = spans[1].get_text(strip=True) if len(spans) > 1 else None
        role = None
        if title:
            tl = title.lower()
            if "director" in tl:
                role = "director"
            elif "associate" in tl:
                role = "associate"
            elif "analyst" in tl:
                role = "analyst"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "confidence": 0.80,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from CVC DIF news & insights page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_urls = set()

    for link in soup.select('a[href*="/news-insights/"]'):
        href = link.get("href", "")
        if not href or href.rstrip("/") == "/news-insights":
            continue

        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        text = link.get_text(strip=True)
        if not text or len(text) < 20:
            h3 = link.select_one("h3")
            if h3:
                text = h3.get_text(strip=True)
        if not text or len(text) < 20:
            continue

        date = None
        date_match = re.match(r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", text)
        if date_match:
            date = date_match.group(1)
            title = text[len(date):].strip()
        else:
            title = text

        title = re.sub(
            r"(Transport|Energy|Digital)DIF\s+Infrastructure.*$", "", title
        ).strip()

        if len(title) < 20:
            continue

        news.append({
            "title": title,
            "url": full_url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
