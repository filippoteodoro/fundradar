"""Site-specific extractors for vertis.it.

Vertis SGR is a Naples-based VC/PE firm with multiple fund vintages (VV2-VV7, Vertis Capital).
Portfolio page shows logo grid organized by fund. Company detail pages have rich metadata
(sector, description, location, website) but we only scrape the overview page.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.vertis.it"


URLS = {
    "portfolio": "/portfolio/",
    "team": "/team/",
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Vertis portfolio page.

    Structure: <a href="/portfolio/{slug}/"><img alt="Company | Partecipata Vertis SGR"></a>
    Names come from img alt text (preferred) or URL slug fallback.
    All companies shown on the portfolio page are current investments.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        if "/portfolio/" not in href:
            continue
        if href.rstrip("/").endswith("/portfolio"):
            continue

        match = re.search(r"/portfolio/([^/]+)/?", href)
        if not match:
            continue

        slug = match.group(1)

        # Get name from img alt text (format: "Company | Partecipata Vertis SGR")
        name = None
        img = link.find("img")
        if img:
            alt = img.get("alt", "")
            if alt and "|" in alt:
                name = alt.split("|")[0].strip()
            elif alt and len(alt) > 2 and len(alt) < 80:
                name = alt.strip()

        # Fallback to slug-based name
        if not name or len(name) < 2:
            name = slug.replace("-", " ").title()

        # Clean up name
        name = re.sub(r"\s*\|\s*Partecipata.*", "", name).strip()
        name = re.sub(r"\s*logo$", "", name, flags=re.I).strip()

        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Build detail page URL
        detail_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": None,
            "website": detail_url,
            "description": None,
            "status": "current",
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Vertis SGR team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    def _clean(text: str | None) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def _role_from_title(title: str | None) -> str | None:
        if not title:
            return None
        tl = title.lower()
        if any(r in tl for r in ["ceo", "founder", "partner", "managing"]):
            return "partner"
        if any(r in tl for r in ["director", "head"]):
            return "director"
        if any(r in tl for r in ["manager", "principal", "advisor"]):
            return "manager"
        if any(r in tl for r in ["analyst", "associate", "assistant"]):
            return "associate"
        return None

    # Primary structure (current live layout): cards under .team-l-info rows.
    for card in soup.select(".team-l-info .wpb_column, .team-l-info .uncol"):
        name_el = card.select_one(".uncode_text_column.text-lead p")
        name = _clean(name_el.get_text(" ", strip=True) if name_el else None)
        if not name or len(name) < 3:
            continue
        if len(name.split()) < 2:
            continue

        lower_name = name.lower()
        if any(skip in lower_name for skip in [
            "vertis", "team", "portfolio", "scopri", "investment",
            "risk", "compliance", "administration", "aml", "cookies",
        ]):
            continue
        if lower_name in seen_names:
            continue
        seen_names.add(lower_name)

        title = None
        title_block = card.select_one(".uncode_text_column.text-small")
        if title_block:
            lines = []
            for p in title_block.select("p"):
                text = _clean(p.get_text(" ", strip=True))
                if not text or text in {"-", "–"}:
                    continue
                lines.append(text)
            if lines:
                title = " ".join(lines)
                title = re.sub(r"\bSCOPRI\b.*", "", title, flags=re.I).strip()
                if len(title) > 200:
                    title = title[:200]

        photo_url = None
        img = card.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title or None,
            "role": _role_from_title(title),
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    if members:
        return members

    # Fallback for older page versions that used <strong> names.
    for strong in soup.find_all("strong"):
        name = _clean(strong.get_text(strip=True))
        if not name or len(name) < 3:
            continue
        if len(name.split()) < 2:
            continue
        if any(skip in name.lower() for skip in [
            "vertis", "team", "portfolio", "scopri", "investment",
            "risk", "compliance", "administration", "aml",
        ]):
            continue
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        title = None
        parent = strong.find_parent(["div", "p", "section"])
        if parent:
            full_text = _clean(parent.get_text(" ", strip=True))
            if name in full_text:
                after_name = _clean(full_text.split(name, 1)[-1])
                if after_name and len(after_name) < 100:
                    after_name = re.sub(r"\bSCOPRI\b.*", "", after_name, flags=re.I).strip()
                    if after_name:
                        title = after_name

        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": _role_from_title(title),
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


EXTRACTORS = {
    "team": extract_team,
    "portfolio": extract_portfolio,
}
