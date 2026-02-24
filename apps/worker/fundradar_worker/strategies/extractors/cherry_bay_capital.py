"""Site-specific extractors for cherrybaycapital.com.

WordPress/Elementor site. Portfolio page uses alternating image widgets
(company logo + link) and text-editor widgets (description, sector, etc.).
Team page uses heading widgets (names in ALL CAPS) and text-editor widgets (titles).
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "cherrybaycapital.com"

# Verified against live site 2026-02-24
URLS = {
    "portfolio": "/cherries/",
    "team": "/about/team/",
    "news": None,
}

# Known company names mapped from logo filenames
_LOGO_NAME_MAP = {
    "poggipolini": "Poggipolini",
    "tecnomatic": "Tecnomatic",
    "awp": "AWP",
    "limolane": "Limolane",
    "mdotm": "M.dot M",
    "bs": "Bending Spoons",
    "kampos": "Kampos",
    "cutiss": "Cutiss",
}


def _extract_field(text, label):
    """Extract a labeled field value like 'Sector: Aerospace & Defence'.

    The HTML uses <b>Label</b>: value, so get_text() may insert whitespace
    or separators between the label and colon.
    """
    match = re.search(rf"{label}\s*:\s*(.+?)(?:\n|$)", text)
    return match.group(1).strip() if match else None


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from the Cherries page.

    Structure: alternating elementor widgets:
    - image.default: company logo with link to company website
    - text-editor.default: Description, Sector, Year, Deal, Status, Website
    Section headers (heading.default): 'Private Equity' and 'Tactical Investments'.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    widgets = soup.select("[data-widget_type]")

    current_section = None
    pending_logo_link = None
    pending_logo_name = None

    for w in widgets:
        wtype = w.get("data-widget_type", "")

        # Track section headers
        if wtype == "heading.default":
            text = w.get_text(strip=True)
            if text in ("Private Equity", "Tactical Investments"):
                current_section = text

        # Image widgets contain company logo + link
        elif wtype == "image.default" and current_section:
            link_el = w.select_one("a[href]")
            img_el = w.select_one("img")
            if link_el:
                href = link_el.get("href", "")
                if href and "cherrybaycapital" not in href:
                    pending_logo_link = href
                    # Try to get name from logo filename
                    pending_logo_name = None
                    if img_el:
                        src = img_el.get("src", "") or img_el.get("data-lazy-src", "")
                        fname = src.split("/")[-1].lower() if src else ""
                        # Match against known logo names
                        for key, name in _LOGO_NAME_MAP.items():
                            if fname.startswith(key):
                                pending_logo_name = name
                                break
                        # Fallback: derive from filename
                        if not pending_logo_name and "-logo" in fname.lower():
                            raw = fname.split("-logo")[0].replace("-", " ").replace("_", " ")
                            if len(raw) >= 2:
                                pending_logo_name = raw.title()

        # Text-editor widgets contain company details
        elif wtype == "text-editor.default" and current_section and pending_logo_link:
            # Extract field values from <p><b>Label</b>: value</p> elements
            paragraphs = w.select("p")
            fields = {}
            for p in paragraphs:
                p_text = p.get_text(strip=True)
                match = re.match(r"^(\w[\w\s]*?)\s*:\s*(.+)$", p_text)
                if match:
                    fields[match.group(1).strip().lower()] = match.group(2).strip()

            if "description" not in fields:
                continue

            description = fields.get("description")
            sector = fields.get("sector")
            year = fields.get("year")
            deal = fields.get("deal")
            status_raw = fields.get("status")
            website_text = fields.get("website")

            # Determine status from the labeled field
            status = None
            if status_raw:
                sl = status_raw.lower()
                if "active" in sl:
                    status = "current"
                elif "exit" in sl or "partially exited" in sl:
                    status = "exited"

            # Handle "Active, Partially Exited" -> still current
            if status_raw and "partially exited" in status_raw.lower() and "active" in status_raw.lower():
                status = "current"

            # Resolve company website
            website = pending_logo_link
            if website_text and website_text.startswith("www."):
                website = "https://" + website_text

            # Resolve company name
            name = pending_logo_name
            if not name:
                # Last resort: extract from website domain
                domain = pending_logo_link.split("//")[-1].split("/")[0]
                domain = domain.replace("www.", "")
                name = domain.split(".")[0].title()

            if name and name.lower() not in seen_names:
                seen_names.add(name.lower())
                companies.append({
                    "name": name,
                    "sector": sector,
                    "website": website,
                    "description": description,
                    "status": status,
                    "confidence": 0.90,
                })

            # Reset pending state
            pending_logo_link = None
            pending_logo_name = None

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from the team page.

    Structure: heading.default (name in ALL CAPS) followed by
    text-editor.default (title/role). The page has two sections:
    'Private Investment Office' and 'Multi Family Office'.
    Names appear twice (summary cards then detail bios) - dedup by name.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    widgets = soup.select("[data-widget_type]")

    current_section = None
    pending_name = None

    for w in widgets:
        wtype = w.get("data-widget_type", "")

        if wtype == "heading.default":
            text = w.get_text(strip=True)

            # Section headers
            if text in ("Private Investment Office", "Multi Family Office"):
                current_section = text
                pending_name = None
                continue

            # Team member names are in ALL CAPS (at least 2 words)
            if current_section and text and len(text) >= 3:
                # Filter out non-name headings
                words = text.split()
                if len(words) >= 2 and all(c.isalpha() or c in " -" for c in text):
                    # Convert ALL CAPS to Title Case
                    name = " ".join(
                        part.title() if part.isupper() and len(part) > 1 else part
                        for part in text.split()
                    )
                    # Fix fused names like "MATTIAROSSI" -> skip, we'll get proper version
                    if len(words) < 2 and len(text) > 10:
                        continue
                    pending_name = name

        elif wtype == "text-editor.default" and pending_name and current_section:
            text = w.get_text(strip=True)

            # The first text-editor after a name heading contains the title
            # e.g. "Founding Partner |Cherry Bay Capital Group"
            # or "Investment Manager |Cherry Bay Capital Private Investment Office"
            if not text or len(text) < 5:
                continue

            # Extract title (before the pipe or "Cherry Bay")
            title = text.split("|")[0].strip()
            title = title.split("Cherry Bay")[0].strip()
            if title.endswith(","):
                title = title[:-1].strip()

            name_lower = pending_name.lower()
            if name_lower not in seen_names:
                seen_names.add(name_lower)

                # Determine role category
                role = None
                if title:
                    tl = title.lower()
                    if "partner" in tl or "founder" in tl:
                        role = "partner"
                    elif "director" in tl or "head" in tl:
                        role = "director"
                    elif "manager" in tl:
                        role = "manager"
                    elif "analyst" in tl or "associate" in tl:
                        role = "associate"
                    elif "advisor" in tl:
                        role = "advisor"

                members.append({
                    "name": pending_name,
                    "title": title if title else None,
                    "role": role,
                    "linkedin": None,
                    "email": None,
                    "photo_url": None,
                    "confidence": 0.85,
                })

            pending_name = None

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
