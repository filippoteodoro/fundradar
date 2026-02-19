"""Site-specific extractors for spacecapital.it (Space Capital).

Note: This fund is "Arca Space Capital" in the database but the website is spacecapital.it.
The portfolio URL is https://www.spacecapital.it/it/portfolio-investments.html
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Domain matches db.json
DOMAIN = "www.spacecapital.it"



# URL paths — verified against live site
URLS = {
    "portfolio": "/it/portfolio-investments.html",
    "team": [
        "/it/investment-team.html",
        "/it/industry-specialist.html",
    ],
    "news": [
        "/it/news/index.html",
        "/en/news/index.html",
    ],
}


_NEWS_SKIP_TITLES = {
    "news",
    "contatti",
    "contacts",
    "contact",
    "team",
    "portfolio investments",
}

_NEWS_SKIP_FRAGMENTS = ("scopri di", "read more", "leggi", "discover")

_NEWS_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|"
    r"settembre|ottobre|novembre|dicembre|january|february|march|april|may|june|"
    r"july|august|september|october|november|december)\s+\d{4})\b",
    re.IGNORECASE,
)


def _normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _is_valid_news_title(title: str) -> bool:
    normalized = _normalize_text(title)
    lower = normalized.lower()
    if not normalized or len(normalized) < 14:
        return False
    if len(normalized.split()) < 3:
        return False
    if lower in _NEWS_SKIP_TITLES:
        return False
    if any(fragment in lower for fragment in _NEWS_SKIP_FRAGMENTS):
        return False
    return True


def _extract_news_date(node) -> str | None:
    time_el = node.select_one("time")
    if time_el:
        dt = _normalize_text(time_el.get("datetime"))
        if dt:
            return dt
        txt = _normalize_text(time_el.get_text(" ", strip=True))
        if txt:
            return txt

    for date_sel in [".date", ".news-date", ".cnt__date", ".meta", ".post-meta"]:
        el = node.select_one(date_sel)
        if el:
            txt = _normalize_text(el.get_text(" ", strip=True))
            if txt:
                match = _NEWS_DATE_RE.search(txt)
                if match:
                    return match.group(0)
                return txt

    text = _normalize_text(node.get_text(" ", strip=True))
    match = _NEWS_DATE_RE.search(text)
    if match:
        return match.group(0)
    return None


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Space Capital portfolio investments page.

    The HTML structure uses Italian labels:
    - Settore: (Sector)
    - Data di investimento: (Investment date)
    - Stato: (Status) - "In portafoglio" = current, "Exit"/"Realizzato" = exited
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Each portfolio item is in div.mod05
    for item in soup.select("div.mod05"):
        # Get the content body
        body = item.select_one("div.cnt__body")
        if not body:
            continue

        # Find the first paragraph which contains company info
        first_p = body.find("p")
        if not first_p:
            continue

        # Extract company name from first strong tag
        name_el = first_p.find("strong")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip if this is a label (contains ":")
        if ":" in name:
            continue

        # Parse the structured info from the paragraph
        sector = None
        status = "current"
        p_text = first_p.get_text()

        # Extract sector (Italian: "Settore:" or English: "Sector:")
        sector_match = re.search(r"(?:Settore|Sector):\s*([^\n]+?)(?:\s*(?:Data|Investment|Stato|Status|$))", p_text, re.IGNORECASE)
        if sector_match:
            sector = sector_match.group(1).strip()
            # Clean up trailing labels
            for label in ["Data di investimento", "Investment date", "Stato", "Status"]:
                if label in sector:
                    sector = sector.split(label)[0].strip()

        # Extract status from explicit "Stato:" field (structured data)
        status_match = re.search(r"(?:Stato|Status):\s*([^\n]+)", p_text, re.IGNORECASE)
        if status_match:
            status_text = status_match.group(1).strip().lower()
            # Italian: "In portafoglio" = current, "Exit"/"Realizzato" = exited
            # Use explicit value matching on this structured field
            if status_text in ("exit", "exited", "realizzato", "realizzata", "sold", "uscita", "ceduto", "ceduta"):
                status = "exited"
            elif status_text.startswith("exit") or status_text.startswith("realizzat"):
                # Allow prefix match for variations like "Exit nel 2023"
                status = "exited"

        # Get description from subsequent paragraphs
        description = None
        all_p = body.find_all("p")
        if len(all_p) > 1:
            desc_parts = []
            for p in all_p[1:]:
                text = p.get_text(strip=True)
                # Skip "Scopri di più" (Discover more) links
                if text and not any(skip in text.lower() for skip in ["scopri", "discover", "leggi"]):
                    desc_parts.append(text)
            if desc_parts:
                description = " ".join(desc_parts)[:500]

        # Get company detail page URL
        website = None
        link = body.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href and "spacecapital" in href:
                website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Space Capital investment team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Team pages are module-based blocks with an image + body.
    for item in soup.select("div.mod05"):
        # Get name from heading
        name_el = item.select_one("h2.cnt__title, h2, h3, h4")
        if not name_el:
            continue

        name = _normalize_text(name_el.get_text(" ", strip=True))
        if not name or len(name) < 3:
            continue

        # Get title and bio from cnt__body
        title = None
        body = item.select_one("div.cnt__body")
        if body:
            # Title is in the first <strong> tag
            first_p = body.find("p")
            if first_p:
                strong = first_p.find("strong")
                if strong:
                    title = _normalize_text(strong.get_text(" ", strip=True))

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "senior partner" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "associate"

        # Get photo URL
        photo_url = None
        img = item.select_one("figure img")
        if img:
            src = img.get("src") or img.get("srcset", "").split()[0]
            if src:
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news entries from Space Capital news pages."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    main = (
        soup.select_one("main article#cnt")
        or soup.select_one("article#cnt")
        or soup.select_one("main")
        or soup
    )

    # Prefer explicit cards, then fallback to generic article blocks.
    cards = main.select(
        "article.news-item, .news-item, .news-list article, .mod05, article"
    )

    for card in cards:
        heading = card.select_one("h1, h2, h3, h4, .cnt__title, .title")
        link = None
        if heading:
            title = _normalize_text(heading.get_text(" ", strip=True))
            link = heading.select_one("a[href]") or card.select_one("a[href]")
        else:
            link = card.select_one("a[href]")
            title = _normalize_text(link.get_text(" ", strip=True)) if link else ""

        if not _is_valid_news_title(title):
            continue

        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        href = _normalize_text(link.get("href")) if link else ""
        url = urljoin(base_url, href) if href else None

        summary = None
        for paragraph in card.select("p"):
            text = _normalize_text(paragraph.get_text(" ", strip=True))
            if not text or text.lower() == title_key:
                continue
            if any(fragment in text.lower() for fragment in _NEWS_SKIP_FRAGMENTS):
                continue
            summary = text[:500]
            break

        news.append({
            "title": title,
            "url": url,
            "date": _extract_news_date(card),
            "summary": summary,
            "confidence": 0.82,
        })

    # Last-chance fallback for sparse templates.
    if not news:
        for link in main.select("a[href*='/news/']"):
            title = _normalize_text(link.get_text(" ", strip=True))
            if not _is_valid_news_title(title):
                continue
            title_key = title.lower()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            href = _normalize_text(link.get("href"))
            if not href:
                continue
            news.append({
                "title": title,
                "url": urljoin(base_url, href),
                "date": None,
                "summary": None,
                "confidence": 0.7,
            })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
