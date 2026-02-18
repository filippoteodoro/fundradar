"""Site-specific extractors for www.progressiosgr.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import logging

DOMAIN = "www.progressiosgr.it"


# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": "/team/",
    "news": "/news-press/",
}
logger = logging.getLogger(__name__)


def _is_person_name(text: str) -> bool:
    """Check if text looks like a person name for progressio."""
    if not text or len(text) < 5:
        return False

    # Skip all-caps text (department headers)
    if text.isupper():
        return False

    # Skip department/section headers (case insensitive)
    skip_patterns = [
        "partner team", "investment team", "portfolio development",
        "finance & corporate", "corporate governance", "ir & esg",
        "hardworking", "softskills", "working", "skills",
        "finance team", "corporate team", "esg strategy"
    ]
    text_lower = text.lower()
    if any(skip in text_lower for skip in skip_patterns):
        return False

    # Skip text that contains only role words (no actual person name)
    role_words = ["partner", "team", "manager", "director", "analyst", "development"]
    words_lower = text_lower.split()
    if all(any(role in w for role in role_words) for w in words_lower):
        return False

    # Should have at least 2 words
    words = text.split()
    if len(words) < 2 or len(words) > 5:
        return False

    # First word should be capitalized (first name)
    if not words[0][0].isupper():
        return False

    # At least one word should NOT be all caps (to distinguish from "PARTNER TEAM")
    has_normal_case = any(not w.isupper() for w in words)
    if not has_normal_case:
        return False

    return True


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from progressiosgr.it team page.

    Structure:
    - Team cards in "full-team-member" class divs
    - Names are in H2 headings
    - Titles are in <p class="role"><strong>DEPT</strong> - Title</p>
    - Image in figure element
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Strategy 1: Extract from full-team-member cards (most reliable)
    cards = soup.find_all(class_=lambda c: c and "full-team-member" in " ".join(c) if isinstance(c, list) else c and "full-team-member" in c)

    for card in cards:
        h2 = card.find("h2")
        if not h2:
            continue

        name = h2.get_text(strip=True)
        if not name or len(name) < 3 or len(name) > 60:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get title from .role element specifically
        title = None
        role_el = card.find(class_="role")
        if role_el:
            role_text = role_el.get_text(strip=True)
            if "-" in role_text:
                # Extract title after the "-"
                parts = role_text.split("-")
                if len(parts) >= 2:
                    title = parts[-1].strip()
            else:
                # Some roles don't have department prefix
                title = role_text.strip()

        # Get photo from figure/img
        photo_url = None
        figure = card.find("figure")
        if figure:
            img = figure.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        results.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "source": "progressio_cards",
        })

    # Strategy 2: Also extract from image alt texts as backup
    for img in soup.find_all("img"):
        alt = img.get("alt", "").strip()
        if not alt or len(alt) < 5 or len(alt) > 60:
            continue
        if not _is_person_name(alt):
            continue

        name_key = alt.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get photo URL
        src = img.get("src") or img.get("data-src")
        photo_url = urljoin(base_url, src) if src else None

        results.append({
            "name": alt,
            "title": None,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "source": "progressio_img_alt",
        })

    # Strategy 3: Corporate governance section (h3 + h4 pattern)
    for h3 in soup.find_all("h3"):
        name = h3.get_text(strip=True)
        if not name or not _is_person_name(name):
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Look for h4 title after
        title = None
        next_h4 = h3.find_next_sibling("h4")
        if next_h4:
            title = next_h4.get_text(strip=True)

        results.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "source": "progressio_h3",
        })

    logger.info(f"Extracted {len(results)} team members from progressio")
    return results


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from progressiosgr.it investments page.

    Structure:
    - Companies are in grid cards with class "brand-dettaglio"
    - Text pattern: "CompanyNameSECTORSectorNameBUSINESS DESCRIPTIONDescription..."
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Sector mapping for normalization
    sector_map = {
        "lifestyle": "Lifestyle",
        "other": "Other",
        "industrial & mechanical": "Industrial & Mechanical",
        "digital": "Digital",
        "healthcare": "Healthcare",
        "food & beverage": "Food & Beverage",
    }

    # Find all investment cards
    for card in soup.find_all(class_=re.compile(r"brand-dettaglio", re.I)):
        text = card.get_text(strip=True)

        # Extract using the pattern: NameSECTORSectorBUSINESS DESCRIPTIONDesc
        match = re.match(
            r"^(.+?)sector([A-Za-z& ]+)business description(.+)$",
            text,
            re.IGNORECASE
        )

        if match:
            name = match.group(1).strip()
            sector = match.group(2).strip()
            description = match.group(3).strip()[:500]

            # Normalize sector
            sector_lower = sector.lower()
            sector = sector_map.get(sector_lower, sector)

            name_key = name.lower()
            if name_key in seen_names:
                continue
            seen_names.add(name_key)

            # Get logo if available
            logo_url = None
            img = card.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    logo_url = urljoin(base_url, src)

            # Get website if available
            website = None
            link = card.find("a", href=re.compile(r"^https?://(?!.*progressio)", re.I))
            if link:
                website = link.get("href")

            results.append({
                "name": name,
                "sector": sector,
                "website": website,
                "description": description,
                "logo_url": logo_url,
                "status": "current",  # Portfolio page entries
                "source": "progressio_cards",
            })

    logger.info(f"Extracted {len(results)} companies from progressio")
    return results


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from progressiosgr.it news page.

    Structure (current):
    - News cards in div.card-news__text-wrap
    - Date in span.card-news__over-head (format "DD Mese YYYY")
    - Title in h3.card-news__title
    - Link in parent <a> wrapping the card
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_titles = set()

    # Current structure: card-news cards
    cards = soup.select(".card-news__text-wrap")

    # Fallback to legacy structure
    if not cards:
        cards = soup.find_all("article", class_="archivio-news-wrap")

    for card in cards:
        # Get title from h3 (current) or h1 (legacy)
        heading = card.find(["h3", "h1"])
        if not heading:
            continue

        title = heading.get_text(separator=" ", strip=True)
        if not title or len(title) < 10:
            continue

        # Get URL from parent <a> or child <a>
        url = None
        parent_a = card.find_parent("a", href=True)
        if parent_a:
            url = parent_a.get("href")
        else:
            link = card.find("a", href=True)
            if link:
                url = link.get("href")
        if url:
            url = urljoin(base_url, url)

        # Reconstruct truncated titles from URL slug
        if title.endswith("...") and url:
            slug = url.rstrip("/").split("/")[-1]
            if slug and len(slug) > 10:
                reconstructed = slug.replace("-", " ").strip()
                if len(reconstructed) > len(title):
                    title = reconstructed[0].upper() + reconstructed[1:]

        title_key = title.lower()[:100]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Get date
        date = None
        date_el = card.find("span", class_=re.compile(r"over-head|card-news__over-head"))
        if not date_el:
            date_el = card.find("p", class_=re.compile(r"sign.*small-name|small-name", re.I))
        if date_el:
            date_text = date_el.get_text(strip=True)
            # Parse "DD Mese YYYY" or "DD - MM - YYYY"
            date_match = re.match(r"(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{4})", date_text)
            if date_match:
                day, month, year = date_match.groups()
                date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            else:
                # Italian month names
                months = {"gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
                          "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
                          "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12"}
                m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", date_text)
                if m:
                    day, month_name, year = m.groups()
                    month_num = months.get(month_name.lower())
                    if month_num:
                        date = f"{year}-{month_num}-{day.zfill(2)}"

        # Get content snippet
        summary = None
        content_el = card.find("div", class_="paragraph-text")
        if content_el:
            summary = content_el.get_text(separator=" ", strip=True)[:300]

        # Detect deal type from title/content
        deal_type = None
        text = (title + " " + (summary or "")).lower()
        if any(word in text for word in ["sells", "sale", "exit", "cessione", "vendita", "disinvest", "cede"]):
            deal_type = "exit"
        elif any(word in text for word in ["acquire", "acquisition", "acquisito", "acquisizione", "rileva"]):
            deal_type = "acquisition"
        elif any(word in text for word in ["invest", "entry", "new", "closes", "closing", "raccolta"]):
            deal_type = "investment"
        elif any(word in text for word in ["nomina", "appointment", "team"]):
            deal_type = "hiring"

        results.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "deal_type": deal_type,
            "source": "progressio_archive",
            "confidence": 0.92,
        })

    logger.info(f"Extracted {len(results)} news items from progressio")
    return results


EXTRACTORS = {
    "team": extract_team,
    "portfolio": extract_portfolio,
    "news": extract_news,
}
