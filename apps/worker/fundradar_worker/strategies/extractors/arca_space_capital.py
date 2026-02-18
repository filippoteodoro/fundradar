"""Site-specific extractors for spacecapital.it (Space Capital).

Note: This fund is "Arca Space Capital" in the database but the website is spacecapital.it.
The portfolio URL is https://www.spacecapital.it/it/portfolio-investments.html
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Domain matches db.json
DOMAIN = "www.spacecapital.it"



# URL paths — verified against live site
URLS = {
    "portfolio": "/it/portfolio-investments.html",
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Space Capital portfolio investments page.

    The HTML structure uses Italian labels:
    - Settore: (Sector)
    - Data di investimento: (Investment date)
    - Stato: (Status) - "In portafoglio" = current, "Exit"/"Realizzato" = exited
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Each portfolio item is in div.mod05
    for item in soup.select("div.mod05"):
        # Get the content body
        body = item.select_one("div.cnt__body")
        if not body:
            continue

        # Find the first paragraph which contains company info
        first_p = body.find("p")
        if not first_p:
            continue

        # Extract company name from first strong tag
        name_el = first_p.find("strong")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip if this is a label (contains ":")
        if ":" in name:
            continue

        # Parse the structured info from the paragraph
        sector = None
        status = "current"
        p_text = first_p.get_text()

        # Extract sector (Italian: "Settore:" or English: "Sector:")
        sector_match = re.search(r"(?:Settore|Sector):\s*([^\n]+?)(?:\s*(?:Data|Investment|Stato|Status|$))", p_text, re.IGNORECASE)
        if sector_match:
            sector = sector_match.group(1).strip()
            # Clean up trailing labels
            for label in ["Data di investimento", "Investment date", "Stato", "Status"]:
                if label in sector:
                    sector = sector.split(label)[0].strip()

        # Extract status from explicit "Stato:" field (structured data)
        status_match = re.search(r"(?:Stato|Status):\s*([^\n]+)", p_text, re.IGNORECASE)
        if status_match:
            status_text = status_match.group(1).strip().lower()
            # Italian: "In portafoglio" = current, "Exit"/"Realizzato" = exited
            # Use explicit value matching on this structured field
            if status_text in ("exit", "exited", "realizzato", "realizzata", "sold", "uscita", "ceduto", "ceduta"):
                status = "exited"
            elif status_text.startswith("exit") or status_text.startswith("realizzat"):
                # Allow prefix match for variations like "Exit nel 2023"
                status = "exited"

        # Get description from subsequent paragraphs
        description = None
        all_p = body.find_all("p")
        if len(all_p) > 1:
            desc_parts = []
            for p in all_p[1:]:
                text = p.get_text(strip=True)
                # Skip "Scopri di più" (Discover more) links
                if text and not any(skip in text.lower() for skip in ["scopri", "discover", "leggi"]):
                    desc_parts.append(text)
            if desc_parts:
                description = " ".join(desc_parts)[:500]

        # Get company detail page URL
        website = None
        link = body.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href and "spacecapital" in href:
                website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Space Capital investment team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Each team member is in div.mod05 or div.mod05.mod05-2
    for item in soup.select("div.mod05"):
        # Get name from h2.cnt__title
        name_el = item.select_one("h2.cnt__title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Get title and bio from cnt__body
        title = None
        body = item.select_one("div.cnt__body")
        if body:
            # Title is in the first <strong> tag
            first_p = body.find("p")
            if first_p:
                strong = first_p.find("strong")
                if strong:
                    title = strong.get_text(strip=True)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "senior partner" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "associate"

        # Get photo URL
        photo_url = None
        img = item.select_one("figure img")
        if img:
            src = img.get("src") or img.get("srcset", "").split()[0]
            if src:
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
