"""Site-specific extractors for auroragrowthcapital.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.auroragrowthcapital.it"


# URL paths — verified against live site
URLS = {
    "portfolio": "/?page_id=3191",
    "team": None,
    "news": None,
}
# Known company name mappings from image filenames
COMPANY_NAME_MAPPINGS = {
    # Current investments
    "genetic": "Genetic",
    "eurmoda": "Eurmoda",
    "cazampa": "Ca' Zampa",
    "club del sole": "Club del Sole",
    "dierre": "Dierre",
    "finlogic": "Finlogic",
    "promo pharma": "Promo Pharma",
    "farmo": "Farmo",
    "comet": "Comet",
    "eng": "ENG",
    "phse": "PHSE",
    "amut": "AMUT",
    # Realised investments
    "exacer": "Exacer",
    "bluvet": "Bluvet",
    "veneta": "Veneta Cucine",
    "dbagroup": "dba Group",
    "ligabue": "Ligabue",
    "sira": "Sira Industrie",
    "elco": "Elco",
    "forgitalgroup": "Forgital Group",
    "lapatria": "La Patria",
    "rigoni": "Rigoni di Asiago",
    "mesgo": "Mesgo",
    "sanlorenzo": "Sanlorenzo Yachts",
    "megadyne": "Megadyne",
    "true star": "True Star Group",
    "ien": "IEN",
    "gmm": "GMM",
    "surgital": "Surgital",
    "brugola": "Brugola OEB",
    "bat": "BAT",
    "labomar": "Labomar",
}


def _extract_name_from_filename(filename: str) -> str | None:
    """Extract company name from logo filename."""
    if not filename:
        return None

    # Remove extension
    name = re.sub(r"\.(png|jpg|jpeg|gif|webp).*", "", filename, flags=re.I)

    # Remove common suffixes and artifacts
    name = re.sub(r"[-_]?(logo|LOGO|Logo)[-_]?", " ", name)
    name = re.sub(r"[-_]?transparent[-_]?", "", name, flags=re.I)
    name = re.sub(r"[-_]?removebg[-_]?preview[-_]?", "", name, flags=re.I)
    name = re.sub(r"[-_]?basic[-_]?", "", name, flags=re.I)
    name = re.sub(r"[-_]?new[-_]?", "", name, flags=re.I)

    # Remove size suffixes like 1300x520 or 300x300
    name = re.sub(r"[-_]?\d+x\d+[-_]?", "", name)

    # Remove WordPress timestamp suffixes like e1717768409937
    name = re.sub(r"[-_]?e\d{10,}[-_]?", "", name)

    # Replace separators with spaces
    name = re.sub(r"[-_]+", " ", name)

    # Remove trailing/leading numbers
    name = re.sub(r"^\d+\s*", "", name)
    name = re.sub(r"\s*\d+$", "", name)

    # Clean up whitespace
    name = re.sub(r"\s+", " ", name).strip()

    if not name or len(name) < 2:
        return None

    # Check known mappings
    name_lower = name.lower()
    for key, mapped_name in COMPANY_NAME_MAPPINGS.items():
        if key in name_lower:
            return mapped_name

    # Title case the name
    return name.title()


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Aurora Growth Capital news page.

    News items are displayed in DataTables with title, date, and PDF download links.
    Two sections: "Aurora Activity" and "Corporate News".
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all table rows containing news items
    for row in soup.select("tr.__dt_row"):
        # Extract title
        title_cell = row.select_one("td.__dt_col_title")
        if not title_cell:
            continue

        title_el = title_cell.select_one("strong")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Extract date
        date = None
        date_cell = row.select_one("td.__dt_col_publish_date")
        if date_cell:
            date_el = date_cell.select_one("span.__dt_publish_date")
            if date_el:
                date = date_el.get_text(strip=True)  # Format: DD-MM-YYYY

        # Extract URL from download link
        url = None
        link_cell = row.select_one("td.__dt_col_download_link")
        if link_cell:
            link = link_cell.select_one("a[data-downloadurl]")
            if link:
                url = link.get("data-downloadurl")

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    return news


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Aurora Growth Capital.

    Companies are displayed as logo images.
    - Current investments: uses .panel-grid-cell
    - Realised investments: uses .crp-tile gallery
    Company names are extracted from image filenames.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Determine status based on page
    is_realised = "page_id=3026" in base_url or "realised" in base_url.lower()
    status = "exited" if is_realised else "current"

    # Find all images in panel-grid-cells (current investments page)
    for cell in soup.select(".panel-grid-cell"):
        img = cell.select_one("img[src]")
        if not img:
            continue

        src = img.get("src", "")
        if not src:
            continue

        # Skip header/footer logos and stats images
        if "AuroraG" in src or "icon" in src.lower() or "ci_" in src:
            continue

        # Get filename from src
        filename = src.split("/")[-1] if "/" in src else src

        # Extract company name from filename
        name = _extract_name_from_filename(filename)
        if not name:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": status,
            "confidence": 0.80,
        })

    # Find all images in crp-tile gallery (realised investments page)
    for tile in soup.select(".crp-tile"):
        img = tile.select_one("img[src]")
        if not img:
            continue

        src = img.get("src", "")
        if not src or "/uploads/" not in src:
            continue

        # Skip Aurora logos
        if "Aurora" in src:
            continue

        # Get filename from src
        filename = src.split("/")[-1] if "/" in src else src

        # Extract company name from filename
        name = _extract_name_from_filename(filename)
        if not name:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": status,
            "confidence": 0.75,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "news": extract_news,
}
