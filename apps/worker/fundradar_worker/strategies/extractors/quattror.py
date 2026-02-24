"""Site-specific extractors for quattror.com.

QuattroR - Italian private equity firm.
Portfolio companies displayed as logo images in article elements.
Company names extracted from image alt attributes.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "quattror.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/it/portfolio-companies/",
    "team": "/it/people",
    "news": "/it/news/",
}


def _normalize_text(text: str | None) -> str:
    """Collapse whitespace and trim."""
    return re.sub(r"\s+", " ", text or "").strip()


def _role_from_title(title: str | None) -> str | None:
    """Map raw job title to normalized role bucket."""
    if not title:
        return None

    t = title.lower()
    if any(k in t for k in ("partner", "founder", "chairman", "chief executive", "ceo")):
        return "partner"
    if "principal" in t or "director" in t:
        return "director"
    if "manager" in t:
        return "manager"
    if "associate" in t or "analyst" in t:
        return "associate"
    return None


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from QuattroR portfolio page.

    Structure:
    - article.str__article contains each portfolio company
    - img inside article has company logo
    - alt attribute contains company name (e.g., " CASALASCO MONO")
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    cards = soup.select("section.mod.m09 article.str__article, .mod.m09 article.str__article")
    if not cards:
        cards = soup.select("article.str__article")

    for article in cards:
        # Portfolio cards link to /portfolio-companies/* detail pages.
        wrapper_link = article.find_parent("a", href=True)
        href = wrapper_link.get("href", "") if wrapper_link else ""
        if href and "/portfolio-companies/" not in href:
            continue

        img = article.select_one("img")
        if not img:
            continue

        alt = _normalize_text(img.get("alt", ""))
        src = img.get("src", "")

        # Skip generic/placeholder images
        if not alt or "group" in alt.lower() or len(alt) < 2:
            continue

        # Clean name - remove MONO suffix and extra whitespace
        name = re.sub(r"\s*MONO\s*$", "", alt, flags=re.IGNORECASE).strip()
        name = _normalize_text(name)

        # Convert to proper case
        # Special handling for acronyms (all caps <= 4 chars stay uppercase)
        words = name.split()
        formatted_words = []
        for word in words:
            if len(word) <= 4 and word.isupper():
                formatted_words.append(word)  # Keep acronyms
            else:
                formatted_words.append(word.title())
        name = " ".join(formatted_words)

        if not name or len(name) < 2:
            continue

        # Skip concatenated headings without spaces (e.g. "Ourportfoliocompanies")
        if " " not in name and len(name) > 15:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen:
            continue
        seen.add(name_lower)

        # Get logo URL
        logo_url = urljoin(base_url, src) if src else None

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": "current",  # Single-section portfolio page = all current
            "logo_url": logo_url,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from QuattroR people page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    cards = soup.select("div.mod.m07 article.str__article")
    if not cards:
        cards = soup.select("section#founders-partners-tab-pane article.str__article, section#team-tab-pane article.str__article")

    for card in cards:
        name_el = card.select_one("h3.str__title, h2.str__title")
        if not name_el:
            continue

        name = _normalize_text(name_el.get_text(" ", strip=True))
        if not name or len(name.split()) < 2 or len(name) > 80:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        title_el = card.select_one(".str__preview p, .str__preview")
        title = _normalize_text(title_el.get_text(" ", strip=True)) if title_el else None
        if title == "":
            title = None

        img = card.select_one(".str__figure img, img")
        photo_url = None
        if img:
            src = img.get("src") or img.get("data-src") or ""
            if src:
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": _role_from_title(title),
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.9,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from QuattroR news cards."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_titles = set()

    cards = soup.select("div.mod.m22 article.str__article")
    if not cards:
        # Fallback for minor markup changes.
        cards = [
            article for article in soup.select("article.str__article")
            if article.select_one("time") and article.select_one(".str__header .str__title")
        ]

    for card in cards:
        title_el = card.select_one(".str__header .str__title, h2.str__title")
        if not title_el:
            continue

        title = _normalize_text(title_el.get_text(" ", strip=True))
        if not title or len(title) < 20:
            continue

        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        time_el = card.select_one("time")
        date = None
        if time_el:
            date = _normalize_text(time_el.get("datetime")) or _normalize_text(time_el.get_text(" ", strip=True))

        summary_el = card.select_one(".str__preview p")
        summary = _normalize_text(summary_el.get_text(" ", strip=True)) if summary_el else ""
        if not summary:
            body_el = card.select_one(".str__body p")
            summary = _normalize_text(body_el.get_text(" ", strip=True)) if body_el else ""
        if summary == "":
            summary = None
        elif len(summary) > 500:
            summary = summary[:500]

        link_el = card.select_one(".str__footer a[href]")
        link = None
        if link_el:
            href = _normalize_text(link_el.get("href"))
            if href:
                link = urljoin(base_url, href)

        items.append({
            "title": title,
            "url": link,
            "date": date,
            "summary": summary,
            "confidence": 0.9,
        })

    return items


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
