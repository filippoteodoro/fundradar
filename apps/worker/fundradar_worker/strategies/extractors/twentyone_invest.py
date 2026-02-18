"""Site-specific extractors for www.21invest.com."""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

DOMAIN = "www.21invest.com"


# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/en/investments/",
    "team": "/en/who-we-are/",
    "news": None,
}
logger = logging.getLogger(__name__)


def extract_company_detail(html: str, url: str) -> dict:
    """
    Extract company details from 21invest.com company page.

    Pages are at /en/company-name/ and contain:
    - Full description text
    - Sector information
    - Sometimes headquarters/location
    - External website link

    Args:
        html: Page HTML content
        url: Page URL

    Returns:
        Dict with: description, headquarters, investment_date, website, sector
    """
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "url": url,
        "success": True,
        "description": None,
        "headquarters": None,
        "investment_date": None,
        "investment_thesis": None,
        "website": None,
        "sector": None,
    }

    # Check for 21invest's soft error pages
    # These show "That's an error" in the h1 but return HTTP 200
    h1 = soup.find("h1")
    if h1:
        h1_text = h1.get_text(strip=True).lower()
        if "error" in h1_text or "continue to explore" in h1_text:
            result["success"] = False
            result["error"] = "Page not found (soft 404)"
            return result

    # Extract main description - usually in main content area
    # 21invest uses a clean layout with company info in main section
    main_content = soup.find("main") or soup.find("article") or soup.find(class_=re.compile(r"content|main", re.I))

    if main_content:
        # Look for paragraph text (description)
        paragraphs = main_content.find_all("p")
        description_parts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            # Skip very short or navigation-like text
            if len(text) > 50 and not any(skip in text.lower() for skip in ["cookie", "privacy", "contact"]):
                description_parts.append(text)

        if description_parts:
            result["description"] = " ".join(description_parts[:3])[:1000]  # First 3 paragraphs, max 1000 chars

    # Extract sector from tags or labels - be careful about noise
    # Only extract from main content, not from cookie dialogs
    full_text = main_content.get_text(" ", strip=True) if main_content else ""

    # Skip common noise phrases
    noise_phrases = ["cookie", "privacy", "menu", "navigation", "accept", "decline"]

    sector_patterns = [
        (r"settore[:\s]+([^<\n.]+)", 1),
        (r"sector[:\s]+([^<\n.]+)", 1),
        (r"industry[:\s]+([^<\n.]+)", 1),
    ]
    for pattern, group in sector_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            sector = match.group(group).strip()
            # Validate sector - skip if it looks like noise
            if 3 < len(sector) < 60 and not any(n in sector.lower() for n in noise_phrases):
                result["sector"] = sector
                break

    # Also check for tag elements within main content
    if not result["sector"] and main_content:
        for tag_class in ["tag", "sector-tag", "category"]:
            tag_el = main_content.find(class_=re.compile(tag_class, re.I))
            if tag_el:
                text = tag_el.get_text(strip=True)
                if 3 < len(text) < 60 and not any(n in text.lower() for n in noise_phrases):
                    result["sector"] = text
                    break

    # Extract headquarters/location
    location_patterns = [
        (r"(?:sede|headquarters|head office|location)[:\s]+([A-Za-z\s,]+?)(?:\.|$|<|\n)", 1),
        (r"(?:based in|headquartered in)\s+([A-Za-z\s,]+?)(?:\.|$|<|\n)", 1),
    ]
    for pattern, group in location_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            location = match.group(group).strip()
            if len(location) < 100:
                result["headquarters"] = location
                break

    # Extract external website link - look in main content only
    # Skip cookie, privacy, google links
    skip_domains = ["cookie", "google", "privacy", "21invest", "datocms"]
    search_area = main_content if main_content else soup

    for link in search_area.find_all("a", href=True):
        href = link.get("href", "")
        if not href.startswith("http"):
            continue

        # Skip internal and cookie/tracking links
        href_lower = href.lower()
        if any(skip in href_lower for skip in skip_domains):
            continue

        link_text = link.get_text(strip=True)

        # Look for website links - domain-like text or explicit website labels
        if re.match(r"^[a-z0-9-]+\.[a-z]{2,}$", link_text.lower()):
            # Text looks like a domain (e.g., "fornodasolo.it")
            result["website"] = href
            break
        elif any(word in link_text.lower() for word in ["sito", "website", "visit", "visita"]):
            result["website"] = href
            break

    # Extract investment date/year
    year_patterns = [
        (r"(?:anno|year|data)[:\s]+(\d{4})", 1),
        (r"(?:invested|investment)[:\s]+.*?(\d{4})", 1),
        (r"dal\s+(\d{4})", 1),  # Italian "from YEAR"
    ]
    for pattern, group in year_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            year = match.group(group)
            if 1990 < int(year) < 2030:
                result["investment_date"] = year
                break

    logger.info(f"Extracted 21invest detail for {url}: desc={bool(result['description'])}, sector={result['sector']}, hq={result['headquarters']}")
    return result


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from 21invest.com.

    Structure:
    - Companies are in grid cards
    - Company names in link text or headings
    - Often linked to detail pages like /en/company-name/
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Strategy 1: Find all internal links that look like company pages
    company_link_pattern = re.compile(r"/en/([a-z0-9-]+)/$", re.I)

    skip_paths = {
        "who-we-are", "manifesto", "investments", "contact-us",
        "compliance", "legal-disclamer", "careers", "privacy",
        "cookie-policy", "shared-value", "21-invest-italy",
        "21-invest-france", "21-invest-poland"
    }

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        match = company_link_pattern.search(href)
        if match:
            slug = match.group(1)
            if slug in skip_paths:
                continue

            # Convert slug to name
            name = slug.replace("-", " ").title()
            if "D " in name:
                name = name.replace("D ", "d'")  # Fix Italian articles

            name_key = name.lower()
            if name_key in seen_names:
                continue
            seen_names.add(name_key)

            # Try to get sector from nearby elements
            sector = None
            parent = link.parent
            if parent:
                sector_el = parent.find(class_=re.compile(r"tag|sector|category", re.I))
                if sector_el:
                    sector = sector_el.get_text(strip=True)

            # Get logo if available
            logo_url = None
            img = link.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    logo_url = urljoin(base_url, src)

            # Construct detail page URL from the link
            detail_url = urljoin(base_url, href)

            results.append({
                "name": name,
                "sector": sector,
                "website": None,
                "description": None,
                "logo_url": logo_url,
                "status": "current",  # Portfolio page entries
                "source": "21invest_links",
                "detail_page_url": detail_url,
            })

    # Strategy 2: Look for grid cards with company info
    for card in soup.find_all(class_=re.compile(r"grid-card|investment-card|portfolio-card", re.I)):
        # Get name from heading
        heading = card.find(["h2", "h3", "h4"])
        name = heading.get_text(strip=True) if heading else None

        if not name:
            # Try image alt
            img = card.find("img")
            if img:
                name = img.get("alt", "").strip()

        if not name or len(name) < 2 or len(name) > 80:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        results.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "logo_url": None,
            "status": "current",  # Portfolio page entries
            "source": "21invest_cards",
        })

    logger.info(f"Extracted {len(results)} companies from 21invest")
    return results


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from 21invest.com who-we-are page.

    Structure:
    - Members are in grid-card elements
    - grid-card__title contains the name
    - grid-card__subtitle contains the title/role
    - grid-card__links-container contains the office (21 Invest - Italy/France)
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Find all grid-card elements
    for card in soup.find_all(class_=re.compile(r"^grid-card$", re.I)):
        content = card.find(class_=re.compile(r"grid-card__content", re.I))
        if not content:
            continue

        # Get name from title
        name = None
        title_el = content.find(class_=re.compile(r"grid-card__title", re.I))
        if title_el:
            name = title_el.get_text(strip=True)

        if not name or len(name) < 3 or len(name) > 60:
            continue

        # Check it looks like a name (at least 2 words)
        words = name.split()
        if len(words) < 2:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get role from subtitle
        title = None
        subtitle_el = content.find(class_=re.compile(r"grid-card__subtitle", re.I))
        if subtitle_el:
            title = subtitle_el.get_text(strip=True)

        # Get office/department from links-container (e.g., "21 Invest - Italy")
        department = None
        links_el = content.find(class_=re.compile(r"grid-card__links-container", re.I))
        if links_el:
            department = links_el.get_text(strip=True)

        # Combine title and department if we have both
        if title and department:
            title = f"{title} ({department})"
        elif department and not title:
            title = department

        # Get photo URL from image wrapper
        photo_url = None
        img_wrapper = card.find(class_=re.compile(r"grid-card__image", re.I))
        if img_wrapper:
            # Look for background image style or img tag
            img = img_wrapper.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        # Get LinkedIn if available
        linkedin = None
        linkedin_link = card.find("a", href=re.compile(r"linkedin", re.I))
        if linkedin_link:
            linkedin = linkedin_link.get("href")

        results.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "source": "21invest_grid_card",
        })

    logger.info(f"Extracted {len(results)} team members from 21invest")
    return results


EXTRACTORS = {
    "company_detail": extract_company_detail,
    "portfolio": extract_portfolio,
    "team": extract_team,
}
