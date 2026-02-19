"""Site-specific extractors for www.yarpa.it (Yarpa Investimenti SGR).

Fund-of-funds model. No company-level portfolio.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.yarpa.it"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": "/le-persone/",
    "news": "/press/",
}

_ITALIAN_MONTHS = {
    "gennaio": "01",
    "febbraio": "02",
    "marzo": "03",
    "aprile": "04",
    "maggio": "05",
    "giugno": "06",
    "luglio": "07",
    "agosto": "08",
    "settembre": "09",
    "ottobre": "10",
    "novembre": "11",
    "dicembre": "12",
}


def _clean_text(value: str | None) -> str | None:
    """Normalize whitespace and strip."""
    if not value:
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _extract_date_iso(raw: str | None) -> str | None:
    """Parse common date formats (including Italian month names) to YYYY-MM-DD."""
    value = _clean_text(raw)
    if not value:
        return None

    iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if iso_match:
        return iso_match.group(0)

    dmy_num = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", value)
    if dmy_num:
        day, month, year = dmy_num.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    dmy_it = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", value, re.IGNORECASE)
    if dmy_it:
        day, month_name, year = dmy_it.groups()
        month = _ITALIAN_MONTHS.get(month_name.lower())
        if month:
            return f"{year}-{month}-{day.zfill(2)}"

    return None


def _infer_role(title: str | None) -> str | None:
    """Map Yarpa titles to generic role categories."""
    if not title:
        return None

    t = title.lower()
    if any(
        kw in t
        for kw in [
            "amministratore delegato",
            "ceo",
            "founder",
            "presidente",
            "vice presidente",
            "managing partner",
            "partner",
        ]
    ):
        return "partner"

    if any(
        kw in t
        for kw in [
            "direttore",
            "director",
            "head",
            "responsabile",
            "portfolio manager",
        ]
    ):
        return "manager"

    if any(kw in t for kw in ["analyst", "associate"]):
        return "associate"

    if any(kw in t for kw in ["sindaco", "collegio", "board", "amministratore"]):
        return "board"

    return None


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Yarpa team page.

    Current layout uses Team Showcase cards (`figure.tpstyle-img-*`) with:
    - h3: name
    - h5: title
    - optional profile image/link
    """
    soup = BeautifulSoup(html, "html.parser")
    members: list[dict] = []
    seen_keys: set[str] = set()

    cards = soup.select("figure.tpstyle-img-7, figure[class*='tpstyle-img-']")

    for card in cards:
        name_anchor = card.select_one("figcaption h3 a[href]")
        name_el = name_anchor or card.select_one("figcaption h3, h3")
        name = _clean_text(name_el.get_text(" ", strip=True) if name_el else None)
        if not name or len(name) < 4 or len(name.split()) < 2:
            continue
        if name.lower() in {"le persone", "press", "yarpa"}:
            continue

        profile_url = None
        if name_anchor:
            href = (name_anchor.get("href") or "").strip()
            if href:
                profile_url = urljoin(base_url, href)

        dedupe_key = (profile_url or name).lower()
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        title_el = card.select_one("figcaption h5, h5, .position, .title, .role")
        title = _clean_text(title_el.get_text(" ", strip=True) if title_el else None)

        linkedin = None
        linkedin_el = card.select_one("a[href*='linkedin.com']")
        if linkedin_el:
            linkedin = _clean_text(linkedin_el.get("href"))

        photo_url = None
        img = card.select_one("img")
        if img:
            src = (
                img.get("nitro-lazy-src")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("src")
            )
            src = _clean_text(src)
            if src and not src.startswith("data:image/"):
                photo_url = urljoin(base_url, src)

        members.append(
            {
                "name": name,
                "title": title,
                "role": _infer_role(title),
                "linkedin": linkedin,
                "email": None,
                "photo_url": photo_url,
                "confidence": 0.90,
            }
        )

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract press/news items from Yarpa press page.

    Current layout uses Elementor post cards (`article.elementor-post`).
    Includes a detail-page fallback when a single article page is provided.
    """
    soup = BeautifulSoup(html, "html.parser")
    news: list[dict] = []
    seen_urls: set[str] = set()

    cards = soup.select("article.elementor-post")
    for card in cards:
        title_link = card.select_one(".elementor-post__title a[href]")
        if not title_link:
            title_link = card.select_one("h2 a[href], h3 a[href]")
        if not title_link:
            continue

        title = _clean_text(title_link.get_text(" ", strip=True))
        if not title or len(title) < 8:
            continue

        href = _clean_text(title_link.get("href"))
        if not href:
            continue
        url = urljoin(base_url, href)
        url_key = url.lower()
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)

        date_el = card.select_one(".elementor-post-date, time, .date, [datetime]")
        date_raw = None
        if date_el:
            date_raw = date_el.get("datetime") or date_el.get_text(" ", strip=True)
        date = _extract_date_iso(date_raw) or _clean_text(date_raw)

        summary = None
        summary_el = card.select_one(".elementor-post__excerpt p, .elementor-post__excerpt, .excerpt, p")
        if summary_el:
            summary = _clean_text(summary_el.get_text(" ", strip=True))
            if summary and summary.lower().startswith(title.lower()):
                summary = _clean_text(summary[len(title):].lstrip(" :|-"))
            if summary:
                summary = summary[:300]

        news.append(
            {
                "title": title,
                "url": url,
                "date": date,
                "summary": summary,
                "confidence": 0.92,
            }
        )

    if news:
        return news

    # Detail page fallback (e.g., /press/<article>/)
    title_el = soup.select_one("h1.entry-title, h1.elementor-heading-title, h1")
    title = _clean_text(title_el.get_text(" ", strip=True) if title_el else None)
    if title and len(title) >= 12:
        date_raw = None
        date_el = soup.select_one("time, .elementor-post-date, .date, [datetime]")
        if date_el:
            date_raw = date_el.get("datetime") or date_el.get_text(" ", strip=True)
        if not date_raw:
            modified_meta = soup.find("meta", attrs={"property": "article:modified_time"})
            if modified_meta:
                date_raw = modified_meta.get("content")

        summary = None
        summary_el = soup.select_one(".entry-content p, .elementor-widget-text-editor p, article p")
        if summary_el:
            summary = _clean_text(summary_el.get_text(" ", strip=True))
            if summary:
                summary = summary[:300]

        return [
            {
                "title": title,
                "url": base_url,
                "date": _extract_date_iso(date_raw) or _clean_text(date_raw),
                "summary": summary,
                "confidence": 0.85,
            }
        ]

    return []


EXTRACTORS = {
    "team": extract_team,
    "news": extract_news,
}
