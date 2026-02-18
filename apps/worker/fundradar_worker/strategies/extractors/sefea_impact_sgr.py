"""Site-specific extractors for sefeaimpact.it (Sefea Impact SGR).

Sefea Impact SGR is an Italian SGR focused on social impact investing,
particularly through their Social Impact Fund (Fondo SI).

NOTE: The fund page lists impact investment categories and team members,
NOT portfolio company names. Aggressive filtering is needed to prevent
Italian category labels and person names from appearing as portfolio entries.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.sefeaimpact.it"

# URL paths for monitoring
URLS = {
    "portfolio": "/fondo-si-social-impact/",
    "team": "/chi-siamo-sefea-impact/",
    "news": None,  # No dedicated news page found
}

# Italian impact category labels that appear as headings on the fund page.
# These are NOT portfolio companies — they're investment theme descriptions.
_SEFEA_GARBAGE = {
    # Known ALL CAPS Italian category labels
    "agricoltura sociale", "housing sociale", "inclusione socio-lavorativa",
    "rigenerazione urbana", "educazione e formazione", "servizi socio-sanitari",
    "turismo sostenibile", "efficienza energetica", "economia circolare",
    "cooperazione internazionale", "finanza sociale", "microcredito",
    "cooperazione sociale", "inserimento lavorativo",
    # Navigation / section labels
    "società partecipate", "partecipate", "il fondo", "strategia",
    "il team", "team", "contatti", "chi siamo", "documenti",
    "investimenti", "portfolio", "obiettivi", "mission",
    "impatto sociale", "impatto", "risultati", "governance",
}

# Pattern to detect person names (2-3 capitalized words, typical Italian names)
_PERSON_NAME_RE = re.compile(
    r'^[A-Z][a-z]+\s+(?:(?:di|de|del|della|dello|degli|delle|dal|dalla|dei|da|lo|la|le|li|al)\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?$'
)

# Pattern to detect ALL CAPS Italian phrases (category labels)
_ALL_CAPS_ITALIAN_RE = re.compile(r'^[A-Z\s\-\'\u00C0-\u00FF]{5,}$')


def _is_sefea_garbage(name: str) -> bool:
    """Check if a name is a garbage entry (category label or person name)."""
    name_stripped = name.strip()
    name_lower = name_stripped.lower()

    # Exact match against known garbage
    if name_lower in _SEFEA_GARBAGE:
        return True

    # ALL CAPS Italian phrases (category labels like "AGRICOLTURA SOCIALE")
    if _ALL_CAPS_ITALIAN_RE.match(name_stripped) and len(name_stripped.split()) >= 2:
        return True

    # Person names (2-3 capitalized words)
    if _PERSON_NAME_RE.match(name_stripped):
        return True

    # Short generic Italian words
    if name_lower in {"impatto", "strategia", "obiettivi", "mission", "governance",
                       "documenti", "risultati", "il fondo", "fondo si"}:
        return True

    return False


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio investments from Sefea Impact fund page.

    Includes aggressive filtering for Italian category labels and person names
    that the page structure exposes as headings.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for investment/project cards
    for item in soup.select(".portfolio-item, .investment-card, article, .card, .et_pb_blurb"):
        name_el = item.select_one("h2, h3, h4, .name, .title, .et_pb_blurb_title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Skip navigation items
        if any(skip in name_lower for skip in [
            "sefea", "fondo", "social impact", "menu", "home", "contatti"
        ]):
            continue

        # Skip garbage entries (category labels, person names)
        if _is_sefea_garbage(name):
            continue

        website = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "sefea" not in href.lower():
                website = href

        sector = "Social Impact"  # Sefea focuses on social impact

        description = None
        desc_el = item.select_one("p, .description, .summary, .et_pb_blurb_description")
        if desc_el:
            description = desc_el.get_text(strip=True)[:300]

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",
            "confidence": 0.80,
        })

    # Fallback: look for project names in headings
    if not companies:
        for heading in soup.find_all(["h2", "h3", "h4"]):
            name = heading.get_text(strip=True)
            if not name or len(name) < 3 or len(name) > 80:
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue

            if any(skip in name_lower for skip in [
                "sefea", "fondo", "impact", "social", "chi siamo", "contatti", "sgr"
            ]):
                continue

            # Skip garbage entries (category labels, person names)
            if _is_sefea_garbage(name):
                continue

            seen_names.add(name_lower)
            companies.append({
                "name": name,
                "sector": "Social Impact",
                "website": None,
                "description": None,
                "status": "current",  # Portfolio page entries
                "confidence": 0.70,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Sefea Impact about page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select(".team-member, .person, article, .et_pb_team_member, .et_pb_blurb"):
        name_el = item.select_one("h2, h3, h4, .name, .et_pb_team_member_name, .et_pb_blurb_title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or len(name.split()) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        if any(skip in name_lower for skip in ["team", "sefea", "chi siamo"]):
            continue

        title = None
        title_el = item.select_one(".title, .role, .position, p, .et_pb_team_member_position")
        if title_el and title_el != name_el:
            title = title_el.get_text(strip=True)

        photo_url = None
        img = item.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.80,
        })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
