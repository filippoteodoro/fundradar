"""Site-specific extractors for www.alcedo.it."""
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
import re
import logging

DOMAIN = "www.alcedo.it"


# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/fondi_private_equity/",
    "team": "/team_alcedo_sgr/",
    "news": "/stampa-news/",
}
logger = logging.getLogger(__name__)


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from alcedo.it.

    The site has company cards with:
    - Container with classes like 'col-md-6 alcedo-v 2024 in-portafoglio-2'
    - Company name in H3 heading
    - Rich info in grid_info elements (visible on hover) containing:
      Sede: location, Settore: sector, Tipo di deal: deal type,
      Quota: stake, Fatturato ingresso: revenue, website URL
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Strategy 1: Work backwards from grid_info elements (most reliable for portfolio)
    for grid_info in soup.find_all(class_=re.compile(r"grid_info", re.I)):
        info_text = grid_info.get_text(" ", strip=True)

        # Navigate up to find the container (4 levels up)
        container = grid_info
        for _ in range(4):
            if container.parent:
                container = container.parent
            else:
                break

        # Get company name from H3 in container
        name = None
        h3 = container.find("h3")
        if h3:
            name = h3.get_text(strip=True)

        if not name or len(name) < 2:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Parse structured fields using field boundaries
        sector = None
        website = None
        location = None
        deal_type = None
        description_parts = []

        # Extract Settore (sector)
        sector_match = re.search(r"Settore\s*:\s*(.+?)(?=\s*Tipo di deal\s*:|Quota\s*:|Fatturato|Status\s*:|https?://|$)", info_text, re.I)
        if sector_match:
            sector = sector_match.group(1).strip()
            if sector:
                sector = re.sub(r"\s+", " ", sector)

        # Extract Sede (location)
        sede_match = re.search(r"Sede\s*:\s*(.+?)(?=\s*Settore\s*:|Tipo di deal\s*:|Quota\s*:|Fatturato|Status\s*:|https?://|$)", info_text, re.I)
        if sede_match:
            location = sede_match.group(1).strip()

        # Extract Tipo di deal
        deal_match = re.search(r"Tipo di deal\s*:\s*(.+?)(?=\s*Quota\s*:|Fatturato|Sede\s*:|Settore\s*:|Status\s*:|https?://|$)", info_text, re.I)
        if deal_match:
            deal_type = deal_match.group(1).strip()

        # Extract website URL
        url_match = re.search(r"(https?://[^\s]+)", info_text)
        if url_match:
            website = url_match.group(1)

        # Build description from available info
        if location:
            description_parts.append(f"Sede: {location}")
        if deal_type:
            description_parts.append(f"Tipo di deal: {deal_type}")

        # Fallback: try to get website from external links in container
        if not website:
            external_link = container.find("a", href=re.compile(r"^https?://(?!.*alcedo)", re.I))
            if external_link:
                website = external_link.get("href")

        # Get logo from container
        logo_url = None
        img = container.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                logo_url = urljoin(base_url, src)

        # Build description
        description = "; ".join(description_parts) if description_parts else None

        # Determine status from structural context:
        # 1. Container CSS classes (e.g., "ceduto" class indicates exited)
        # 2. Explicit "Status:" field in the grid_info text
        status = "current"
        container_classes = " ".join(container.get("class", []))

        # Check CSS classes first (structural, most reliable)
        if "ceduto" in container_classes or "exited" in container_classes or "exit" in container_classes:
            status = "exited"
        else:
            # Check for explicit Status field in the structured info text
            status_match = re.search(r"Status\s*:\s*(\w+)", info_text, re.IGNORECASE)
            if status_match:
                status_value = status_match.group(1).lower()
                if status_value in ("ceduto", "ceduta", "exit", "exited", "realizzato"):
                    status = "exited"

        results.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "logo_url": logo_url,
            "status": status,
            "source": "alcedo_grid_info",
        })

    # Strategy 2: Fallback for member-item elements (team page structure)
    for item in soup.find_all(class_=re.compile(r"member-item", re.I)):
        name = None
        h3 = item.find("h3")
        if h3:
            name = h3.get_text(strip=True)

        if not name or len(name) < 2:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Basic extraction
        website = None
        external_link = item.find("a", href=re.compile(r"^https?://(?!.*alcedo)", re.I))
        if external_link:
            website = external_link.get("href")

        logo_url = None
        img = item.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                logo_url = urljoin(base_url, src)

        results.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": None,
            "logo_url": logo_url,
            "status": None,
            "source": "alcedo_member_item",
        })

    logger.info(f"Extracted {len(results)} companies from alcedo (with grid_info data)")
    return results


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from alcedo.it/news/.

    Structure:
    - Articles with col-md-6 col-lg-4 classes
    - Title from "Titolo:" pattern
    - Date from "Pubblicazione:" pattern (dd/mm/yyyy)
    - PDF links for source URL
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_titles = set()

    for article in soup.find_all("article"):
        text = article.get_text(" ", strip=True)

        # Extract title from "Titolo:" pattern
        title = None
        title_match = re.search(r"Titolo:\s*(.+?)(?=\s*Fonte:|Download|$)", text)
        if title_match:
            title = title_match.group(1).strip()

        if not title or len(title) < 10:
            continue

        title_key = title.lower()[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Extract date from "Pubblicazione:" pattern (dd/mm/yyyy -> yyyy-mm-dd)
        date = None
        date_match = re.search(r"Pubblicazione:\s*(\d{2})/(\d{2})/(\d{4})", text)
        if date_match:
            day, month, year = date_match.groups()
            date = f"{year}-{month}-{day}"

        # Get URL - prefer PDF link, fallback to any link in article
        url = None
        pdf_link = article.find("a", href=re.compile(r"\.pdf", re.I))
        if pdf_link:
            url = pdf_link.get("href")
        else:
            any_link = article.find("a", href=True)
            if any_link:
                url = any_link.get("href")

        if url:
            url = urljoin(base_url, url)

        results.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    logger.info(f"Extracted {len(results)} news items from alcedo")
    return results


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from alcedo.it.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Find team member items
    for item in soup.find_all(class_=re.compile(r"member-item", re.I)):
        # Get name from h3
        name = None
        h3 = item.find("h3")
        if h3:
            name = h3.get_text(strip=True)

        if not name or len(name) < 5:
            continue

        # Check if it looks like a person name
        words = name.split()
        if len(words) < 2 or len(words) > 5:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get title from p tag
        title = None
        p = item.find("p")
        if p:
            title = p.get_text(strip=True)

        # Get photo
        photo_url = None
        img = item.find("img", class_=re.compile(r"img-responsive", re.I))
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
            "source": "alcedo_members",
        })

    logger.info(f"Extracted {len(results)} team members from alcedo")
    return results


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
