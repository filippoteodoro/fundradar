"""Site-specific extractors for www.oneequity.com (One Equity Partners)."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

DOMAIN = "www.oneequity.com"

URLS = {
    "portfolio": "/portfolio/",
    "team": "/team/",
    "news": "/news/",
}

_SKIP_NAMES = {
    "portfolio",
    "team",
    "news",
    "transformational combinations",
    "work with us",
    "go back",
    "see one equity's terms of use here",
}


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    return text


def _extract_name_from_card(link) -> str:
    # Nuxt card footer has the canonical company name in the last text-paragraph node.
    footer_name = link.select_one(".tile-footer p.text-paragraph:last-of-type")
    if footer_name:
        return _clean_text(footer_name.get_text(" ", strip=True))

    # Fallbacks for potential template changes.
    heading = link.select_one("h1, h2, h3, h4")
    if heading:
        return _clean_text(heading.get_text(" ", strip=True))

    paragraph = link.select_one("p")
    if paragraph:
        return _clean_text(paragraph.get_text(" ", strip=True))

    return _clean_text(link.get_text(" ", strip=True))


def _is_noise_name(name: str) -> bool:
    n = name.lower().strip()
    if not n or n in _SKIP_NAMES:
        return True
    if len(n) < 3:
        return True
    if any(tok in n for tok in ("iframe", "cookie", "privacy", "terms", "load more")):
        return True
    return False


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio entries from One Equity's portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies: list[dict] = []
    seen: set[str] = set()

    for link in soup.select("a[href*='/portfolio/']"):
        href = (link.get("href") or "").strip()
        if not href:
            continue
        normalized_href = href.rstrip("/")
        if normalized_href.endswith("/portfolio"):
            continue

        name = _extract_name_from_card(link)
        if _is_noise_name(name):
            continue

        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        block_text = link.get_text(" ", strip=True)

        # Sector labels are not reliably structured on this page; leave null.
        sector = None

        description = None
        hq = None
        overlay = link.select_one("div[style*='background']")
        if overlay:
            overlay_ps = [p.get_text(" ", strip=True) for p in overlay.select("p")]
            overlay_ps = [_clean_text(x) for x in overlay_ps if _clean_text(x)]
            if overlay_ps:
                # Most cards use first line for short description and last line for location.
                if len(overlay_ps) >= 2:
                    description = overlay_ps[0]
                    hq = overlay_ps[-1]
                else:
                    # Single-line overlays are usually location-only.
                    hq = overlay_ps[0]

        status = None
        if re.search(r"\bcurrent\b", block_text, flags=re.IGNORECASE):
            status = "current"
        elif re.search(r"\brealized\b|\bexited\b", block_text, flags=re.IGNORECASE):
            status = "exited"

        companies.append(
            {
                "name": name,
                "sector": sector,
                "website": None,
                "description": description,
                "headquarters": hq,
                "status": status,
                "confidence": 0.82,
                "source_url": urljoin(base_url, href),
            }
        )

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from One Equity's team page."""
    soup = BeautifulSoup(html, "html.parser")
    members: list[dict] = []
    seen: set[str] = set()

    for link in soup.select("a[href*='/team/']"):
        href = (link.get("href") or "").strip()
        if not href:
            continue
        if href.rstrip("/").endswith("/team"):
            continue

        name_el = link.select_one("h1, h2, h3, h4")
        name = _clean_text(name_el.get_text(" ", strip=True) if name_el else link.get_text(" ", strip=True))
        if _is_noise_name(name):
            continue

        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        card = link.parent if getattr(link, "parent", None) else link
        title_el = card.select_one(".title, .position, .role, h5, h6") if hasattr(card, "select_one") else None
        title = _clean_text(title_el.get_text(" ", strip=True) if title_el else "") or None

        members.append(
            {
                "name": name,
                "title": title,
                "role": None,
                "linkedin": None,
                "email": None,
                "photo_url": None,
                "profile_url": urljoin(base_url, href),
                "confidence": 0.8,
            }
        )

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from One Equity's news page."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for link in soup.select("a[href*='/news/']"):
        href = (link.get("href") or "").strip()
        if not href:
            continue
        if href.rstrip("/").endswith("/news"):
            continue

        card = link.parent if getattr(link, "parent", None) else link
        title_el = link.select_one("h1, h2, h3, h4")
        title = _clean_text(title_el.get_text(" ", strip=True) if title_el else link.get_text(" ", strip=True))
        if not title or len(title) < 10:
            fallback = card.select_one("h1, h2, h3, h4") if hasattr(card, "select_one") else None
            title = _clean_text(fallback.get_text(" ", strip=True) if fallback else "")
        if not title or len(title) < 10:
            continue

        key = title.lower()
        if key in seen:
            continue
        seen.add(key)

        text = card.get_text(" ", strip=True) if hasattr(card, "get_text") else ""
        date = None
        m_date = re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", text)
        if m_date:
            date = m_date.group(0)

        items.append(
            {
                "title": title,
                "url": urljoin(base_url, href),
                "date": date,
                "summary": None,
                "confidence": 0.8,
            }
        )

    return items


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
