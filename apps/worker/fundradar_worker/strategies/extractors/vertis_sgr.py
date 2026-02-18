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

    for strong in soup.find_all("strong"):
        name = strong.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        parts = name.split()
        if len(parts) < 2:
            continue

        if any(skip in name.lower() for skip in [
            "vertis", "team", "portfolio", "scopri", "investment",
            "risk", "compliance", "administration", "aml"
        ]):
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        title = None
        parent = strong.find_parent(["div", "p", "section"])
        if parent:
            full_text = parent.get_text(" ", strip=True)
            if name in full_text:
                after_name = full_text.split(name, 1)[-1].strip()
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

        role = None
        if title:
            tl = title.lower()
            if any(r in tl for r in ["ceo", "founder", "partner", "managing"]):
                role = "partner"
            elif any(r in tl for r in ["director", "head"]):
                role = "director"
            elif any(r in tl for r in ["manager", "principal"]):
                role = "manager"
            elif any(r in tl for r in ["analyst", "associate", "assistant"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
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
