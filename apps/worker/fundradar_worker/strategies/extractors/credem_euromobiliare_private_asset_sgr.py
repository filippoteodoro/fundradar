"""Site-specific extractors for www.credemeuroprivateasset.it.

Credem Euromobiliare Private Asset SGR (formerly Credem Private Equity SGR).
The public site exposes fund pages and a news index with mostly article cards.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

DOMAIN = "www.credemeuroprivateasset.it"


# URL paths verified from the live site structure.
URLS = {
    "portfolio": [
        "/it/area-investitori/fondi/credem-venture-capital",
        "/it/area-investitori/fondi/credem-venture-capital-ii",
    ],
    "team": None,
    "news": "/it/news",
}


_RE_LOGO_ALT = re.compile(r"^\s*logo[:\s-]*(.+?)\s*$", re.IGNORECASE)
_RE_STATUS_EXIT = re.compile(r"\b(?:dismess[oa]|cedut[oa]|exit|vendut[oa])\b", re.IGNORECASE)
_RE_PORTFOLIO_CONTEXT = re.compile(
    r"\b(?:investiment[oi]|partecipazion[ei]|portfolio|venture\s+capital|dismess[oa]|fondo)\b",
    re.IGNORECASE,
)
_RE_DATE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_RE_NEWS_INCLUDE = re.compile(
    r"\b(?:acquis\w+|invest\w+|partecipazion\w+|exit|cession\w+|partnership|nomina\w+|appoint\w+|hired?)\b",
    re.IGNORECASE,
)
_RE_NEWS_EXCLUDE = re.compile(
    r"\b(?:relazione|regolamento|informativa|rendiconto|bilancio|quorum|liquidazione|collocamento|sottoscrizione)\b",
    re.IGNORECASE,
)

_GENERIC_NAMES = {
    "logo",
    "news",
    "download",
    "pdf",
    "documento",
    "brochure",
    "credem",
    "euromobiliare",
    "elenco investimenti",
}


def _clean_name(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None

    logo_match = _RE_LOGO_ALT.match(text)
    if logo_match:
        text = logo_match.group(1).strip()

    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[|]+.*$", "", text).strip(" -:\t")
    if not text or len(text) < 2:
        return None
    if text.lower() in _GENERIC_NAMES:
        return None
    if re.search(r"\belenco\s+investiment[oi]\b", text, re.IGNORECASE):
        return None
    return text


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for img in soup.select("img[alt]"):
        name = _clean_name(img.get("alt", ""))
        if not name:
            continue
        name_key = name.lower()
        if name_key in seen_names:
            continue

        block = img.find_parent(["article", "section", "div", "li"])
        context = block.get_text(" ", strip=True) if block else ""
        if not context or not _RE_PORTFOLIO_CONTEXT.search(context):
            continue

        p = block.find("p") if block else None
        description = p.get_text(" ", strip=True)[:500] if p else None

        link = img.find_parent("a")
        website = urljoin(base_url, link.get("href")) if link and link.get("href") else None

        status = "exited" if _RE_STATUS_EXIT.search(context) else "current"
        confidence = 0.82 if status == "exited" else 0.78

        companies.append(
            {
                "name": name,
                "sector": None,
                "website": website,
                "description": description,
                "status": status,
                "confidence": confidence,
            }
        )
        seen_names.add(name_key)

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen = set()
    news_index_url = urljoin(base_url, "/it/news").rstrip("/")

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        url = urljoin(base_url, href)
        normalized_url = url.rstrip("/")
        if "/it/news/" not in normalized_url:
            continue
        if normalized_url == news_index_url:
            continue

        title = anchor.get_text(" ", strip=True)
        if not title or len(title) < 8:
            continue
        if _RE_NEWS_EXCLUDE.search(title):
            continue
        if not _RE_NEWS_INCLUDE.search(title):
            continue

        container = anchor.find_parent(["article", "li", "div", "section"])
        context = container.get_text(" ", strip=True) if container else title
        date_match = _RE_DATE.search(context)
        date = date_match.group(1) if date_match else None

        summary = None
        if container:
            p = container.find("p")
            if p:
                summary_candidate = p.get_text(" ", strip=True)
                if summary_candidate and summary_candidate != title:
                    summary = summary_candidate[:300]

        dedupe_key = (title.lower(), normalized_url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        news.append(
            {
                "title": title,
                "url": url,
                "date": date,
                "summary": summary,
                "confidence": 0.78,
            }
        )

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "news": extract_news,
}
