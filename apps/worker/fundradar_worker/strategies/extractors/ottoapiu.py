"""Site-specific extractors for www.ottoapiu.it (8a+ Investimenti SGR).

Site uses Avada/Fusion Builder with Bootstrap modals for team bios.
Team page: /chi-siamo/persone/
Products page: /prodotti/
Stories page: /storie-di-impresa/

Plain HTTP works fine — no Playwright needed.
"""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

DOMAIN = "www.ottoapiu.it"


# URL paths for monitoring — verified against url_status.json
URLS = {
    "portfolio": "/prodotti/",
    "team": "/chi-siamo/persone/",
    "news": None,
}
logger = logging.getLogger(__name__)

# Role slug -> Italian title mapping for image-filename extraction
_ROLE_SLUG_MAP = {
    "presidente": "Presidente",
    "vice-presidente": "Vice Presidente",
    "amministratore-delegato": "Amministratore Delegato",
    "direttore-generale": "Direttore Generale",
    "responsabile-risk-management": "Responsabile Risk Management",
    "responsabile-clientela-diretta": "Responsabile Clientela Diretta",
    "responsabile-clientela": "Responsabile Clientela",
    "responsabile-compliance": "Responsabile Compliance",
    "gestore": "Gestore",
}

# Role slug patterns -> normalized role category
_ROLE_CATEGORY_MAP = [
    (["presidente", "amministratore", "delegato"], "partner"),
    (["direttore", "vice-presidente"], "director"),
    (["responsabile", "head"], "manager"),
    (["gestore", "analyst", "analista"], "associate"),
    (["sindaco", "consigliere"], "board"),
]


def _role_from_image_filename(src: str) -> str | None:
    """Extract role from image filename like marco-bartolomei_presidente-600x750.jpg."""
    filename = src.rsplit("/", 1)[-1] if "/" in src else src
    match = re.search(r"_([a-z][a-z0-9-]+?)(?:-\d+x\d+)?\.(?:jpg|png|webp)", filename)
    if not match:
        return None
    slug = match.group(1)
    # Try exact mapping first
    if slug in _ROLE_SLUG_MAP:
        return _ROLE_SLUG_MAP[slug]
    # Otherwise titlecase the slug
    return slug.replace("-", " ").title()


def _classify_role(title: str | None) -> str | None:
    """Classify Italian title into a normalized role category."""
    if not title:
        return None
    title_lower = title.lower()
    for keywords, category in _ROLE_CATEGORY_MAP:
        if any(k in title_lower for k in keywords):
            return category
    return None


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from the /chi-siamo/persone/ page.

    Structure:
    - Each person lives in a div.modal-content > div.modal-header > h3.modal-title
    - Photo is in a table.modalePersone inside div.modal-body
    - Role is encoded in the image filename (e.g. _presidente-600x750.jpg)
    - Section headers (Persone chiave, CdA, Collegio Sindacale) are h3 inside
      div.fusion-title, NOT inside modal-header — we skip those.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names: set[str] = set()

    for modal in soup.find_all("div", class_="modal-content"):
        header = modal.find("div", class_="modal-header")
        if not header:
            continue

        h3 = header.find("h3", class_="modal-title")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Extract photo and role from image
        photo_url = None
        title = None
        body = modal.find("div", class_="modal-body")
        if body:
            img = body.find("img")
            if img:
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    photo_url = urljoin(base_url, src)
                    title = _role_from_image_filename(src)

        role = _classify_role(title)

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.92,
        })

    logger.info(f"Extracted {len(members)} team members from ottoapiu")
    return members


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract fund products from the /prodotti/ page.

    8a+ is an SGR — their 'portfolio' is investment fund products,
    not portfolio companies. Structure:
    - Section h3 headers: OICVM, Comparti SICAV, Gestione portafogli, FIA
    - Individual fund names in h4 tags
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names: set[str] = set()

    # Section headers and junk we want to skip
    skip_patterns = {"i nostri prodotti", "prodotti", "menu", "contatti", "scopri"}
    max_name_len = 60  # Skip taglines caught as h4

    current_section = None

    for heading in soup.find_all(["h3", "h4"]):
        text = heading.get_text(strip=True)
        if not text or len(text) < 2:
            continue

        text_lower = text.lower()

        # h3 = section header (fund category)
        if heading.name == "h3":
            if text_lower not in skip_patterns:
                current_section = text
            continue

        # h4 = individual fund name
        if heading.name == "h4":
            if text_lower in skip_patterns or len(text) > max_name_len:
                continue
            if text_lower in seen_names:
                continue
            seen_names.add(text_lower)

            # Look for a detail link
            website = None
            parent_link = heading.find_parent("a", href=True)
            if parent_link:
                href = parent_link.get("href", "")
                if href and "/prodotti/" in href:
                    website = urljoin(base_url, href)

            # Description from nearby paragraph
            description = None
            parent = heading.find_parent("div")
            if parent:
                for p in parent.find_all("p"):
                    p_text = p.get_text(strip=True)
                    if p_text and len(p_text) > 20 and p_text.lower() != text_lower:
                        description = p_text[:300]
                        break

            companies.append({
                "name": text,
                "sector": current_section or "Investment Fund",
                "website": website,
                "description": description,
                "status": "current",
                "confidence": 0.85,
            })

    logger.info(f"Extracted {len(companies)} products from ottoapiu")
    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract stories from the /storie-di-impresa/ page.

    Structure:
    - Each story is an h2 wrapping or near an <a> tag
    - Stories are about portfolio companies (investment stories)
    - Date may be in the URL pattern /YYYY/MM/DD/slug/
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles: set[str] = set()

    skip_patterns = {"storie di impresa", "menu", "contatti", "8a+", "scopri"}
    date_from_url = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")

    for h2 in soup.find_all("h2"):
        title = h2.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in skip_patterns or title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Get URL
        url = None
        link = h2.find("a", href=True) or h2.find_parent("a", href=True)
        if link:
            url = urljoin(base_url, link.get("href", ""))

        # Extract date from URL
        date = None
        if url:
            match = date_from_url.search(url)
            if match:
                date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

        # Description from nearby paragraph
        summary = None
        parent = h2.find_parent("div", class_=lambda c: c and "column" in str(c).lower()) if h2 else None
        if parent:
            for p in parent.find_all("p"):
                p_text = p.get_text(strip=True)
                if p_text and len(p_text) > 20 and p_text.lower() != title_lower:
                    summary = p_text[:300]
                    break

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.80,
        })

    logger.info(f"Extracted {len(news)} stories from ottoapiu")
    return news


EXTRACTORS = {
    "team": extract_team,
    "portfolio": extract_portfolio,
    "news": extract_news,
}
