"""Site-specific extractors for starcapital.it (Star Capital SGR).

Portfolio structure:
- Companies are in .hoverBox elements on fund pages
- Image alt attribute contains company name
- Caption contains: website, investment date, sector, stake, status
- Multiple fund pages exist: fondo-ssrf, fondo-sbsrf, fondo-star-iii, fondo-star-iv
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.starcapital.it"



# URL paths for monitoring - verified against live site
# Note: Star Capital has multiple fund pages at /it/investimenti/fondo-*
URLS = {
    "portfolio": "/it/investimenti/fondo-star-iv/",
    "team": "/it/team/",
    "news": None,
}
def _extract_company_name(img_alt: str, website: str | None) -> str:
    """Extract clean company name from image alt or website domain."""
    name = img_alt.strip()

    # Clean up common patterns in alt text
    name = re.sub(r"\s*\d{4}$", "", name)  # Remove year suffix
    name = re.sub(r"\s*Da\s+Dimens.*$", "", name, flags=re.IGNORECASE)  # Remove "Da Dimens"
    name = re.sub(r"\s*V\s*\d+$", "", name, flags=re.IGNORECASE)  # Remove version numbers
    name = re.sub(r"^Logo\s*", "", name, flags=re.IGNORECASE)  # Remove "Logo" prefix
    name = re.sub(r"\s*Website$", "", name, flags=re.IGNORECASE)  # Remove "Website" suffix

    # If name looks like a filename or is too generic, try to get from website
    if website and (
        name.lower() in ["website", "logo", "holding", "last holding", "new"] or
        "tentat" in name.lower() or
        len(name) < 3
    ):
        # Extract company name from website domain
        domain = re.sub(r"^https?://", "", website).split("/")[0]
        domain = re.sub(r"^www\.", "", domain)
        domain_name = domain.split(".")[0]  # Get first part of domain
        # Convert to title case
        if len(domain_name) > 2:
            name = domain_name.replace("-", " ").replace("_", " ").title()

    # Handle special cases based on website
    if website:
        website_lower = website.lower()
        if "florence" in website_lower or "gruppoflorence" in website_lower:
            name = "Gruppo Florence"
        elif "bio.design" in website_lower:
            name = "Bio.Design"
        elif "sng.moda" in website_lower:
            name = "SNG"
        elif "starlight.lighting" in website_lower:
            name = "Starlight"
        elif "star.connect" in website_lower:
            name = "Star Connect"

    return name.strip()


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Star Capital fund pages.

    Structure: .hoverBox elements with:
    - img[alt] = company name (may need cleaning)
    - .hoverCaption = company details (website, sector, status)
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for box in soup.select(".hoverBox"):
        # Get image for company name
        img = box.select_one("img")
        if not img:
            continue

        # Parse caption for details first (we need website for name extraction)
        caption = box.select_one(".hoverCaption")
        caption_text = caption.get_text() if caption else ""

        # Extract website (Sito Internet: or Sito internet:)
        # Website ends at "Data" (next field) or whitespace
        website = None
        website_match = re.search(r"Sito\s+[Ii]nternet:\s*([^\s]+?)(?:Data|Settore|Quota|Stato|\s|$)", caption_text)
        if website_match:
            website = website_match.group(1).strip()
            if not website.startswith("http"):
                website = "https://" + website

        # Get company name
        name = _extract_company_name(img.get("alt", ""), website)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Extract sector (Settore di attività:)
        sector = None
        sector_match = re.search(r"Settore\s+di\s+attività:\s*([^Q]+?)(?:Quota|Stato|$)", caption_text, re.IGNORECASE)
        if sector_match:
            sector = sector_match.group(1).strip()
            # Reject business descriptions masquerading as sectors.
            # Real sector names are short (e.g. "Software", "Healthcare").
            # Star Capital sometimes lists a multi-word activity description here.
            if len(sector) > 50 or len(sector.split()) > 5:
                sector = None

        # Extract status from explicit "Stato dell'investimento:" field
        # Handles both straight ' and curly ' apostrophes
        status = "current"
        status_match = re.search(r"Stato\s+dell['\u2019]investimento:\s*(.+?)(?:$|\n|Sito|Settore|Data|Quota)", caption_text, re.IGNORECASE)
        if status_match:
            status_text = status_match.group(1).strip().lower()
            # Check for explicit status values from the structured field
            if status_text in ("ceduto", "ceduta", "exit", "exited", "disinvestimento", "realizzato", "realizzata", "disinvestito"):
                status = "exited"
            elif status_text.startswith("cedut") or status_text.startswith("exit") or status_text.startswith("realizzat"):
                # Allow prefix match for variations like "Ceduto nel 2023"
                status = "exited"

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Star Capital team page.

    Structure:
    - .team-member-container > .team-member
    - <img> for photo
    - <h6> for name
    - <p> for title
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find team member containers
    for container in soup.select(".team-member-container, .team-member"):
        # Look for name in h6
        h6 = container.find("h6")
        if not h6:
            continue

        name = h6.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-name headings
        if any(skip in name.lower() for skip in [
            "team", "star capital", "formazione", "esperienze", "education"
        ]):
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Extract title from first p element
        title = None
        p = container.find("p")
        if p:
            title = p.get_text(strip=True)
            # Skip if it's actually content, not title
            if title and len(title) > 100:
                title = None

        # Extract photo
        photo_url = None
        img = container.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["partner", "founder", "ceo", "amministratore"]):
                role = "partner"
            elif any(r in title_lower for r in ["director", "direttore"]):
                role = "director"
            elif any(r in title_lower for r in ["manager", "principal"]):
                role = "manager"
            elif any(r in title_lower for r in ["analyst", "associate"]):
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

    # Fallback: if no containers found, look for h6 elements directly
    if not members:
        for h6 in soup.find_all("h6"):
            name = h6.get_text(strip=True)
            if not name or len(name) < 3 or len(name) > 50:
                continue

            # Skip common non-name text
            if any(skip in name.lower() for skip in [
                "formazione", "esperienze", "education", "experience",
                "star capital", "team", "contact"
            ]):
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # Look for title in sibling
            title = None
            next_p = h6.find_next_sibling("p")
            if next_p:
                title = next_p.get_text(strip=True)
                if title and len(title) > 100:
                    title = None

            members.append({
                "name": name,
                "title": title,
                "role": None,
                "linkedin": None,
                "email": None,
                "photo_url": None,
                "confidence": 0.75,
            })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
