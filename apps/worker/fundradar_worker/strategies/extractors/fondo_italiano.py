"""Site-specific extractors for www.fondoitaliano.it."""
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
import re
import logging

DOMAIN = "www.fondoitaliano.it"


# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/investimenti-diretti/",
    "team": "/persone/",
    "news": "/comunicati-e-rassegna/",
}
logger = logging.getLogger(__name__)


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from fondoitaliano.it.

    Uses Bricks builder with specific element patterns.
    Structure:
    - Main cards have class "investimento-card-small" (not sub-elements)
    - Company name in h2/h3/h4 inside heading element
    - Sector in "investimento-card-small__settore" element
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Strategy 1: Look for investimento-card-small blocks (main card containers)
    # This is more specific than matching any "investimento-card" which also matches sub-elements
    for card in soup.find_all(class_=re.compile(r"investimento-card-small$", re.I)):
        # Skip if this is a sub-element (footer, heading, settore, media-wrapper)
        classes = " ".join(card.get("class", []))
        if any(sub in classes for sub in ["__footer", "__heading", "__settore", "__media"]):
            continue

        # Get company name from heading element with clickable-parent
        name = None
        heading_container = card.find(class_=re.compile(r"investimento-card.*__heading", re.I))
        if heading_container:
            h_tag = heading_container.find(["h2", "h3", "h4"])
            if h_tag:
                name = h_tag.get_text(strip=True)

        # Fallback: any heading in the card
        if not name:
            heading = card.find(["h2", "h3", "h4"])
            if heading:
                name = heading.get_text(strip=True)

        if not name or len(name) < 2 or len(name) > 80:
            continue

        # Skip navigation items
        if any(skip in name.lower() for skip in ["home", "menu", "cookie", "privacy"]):
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get sector from the specific settore element
        sector = None
        sector_el = card.find(class_=re.compile(r"investimento-card.*__settore", re.I))
        if sector_el:
            sector = sector_el.get_text(strip=True)
        else:
            # Fallback: look for text-basic elements, skipping dates and fund names
            for text_el in card.find_all(class_=re.compile(r"brxe-text-basic", re.I)):
                text = text_el.get_text(strip=True)
                # Skip fund names (FIAF, FIPEC, FITEC, FICC)
                if re.match(r"^(FIAF|FIPEC|FITEC|FICC)(\s+[IV]+)?$", text, re.I):
                    continue
                # Skip dates (months)
                if re.match(r"^(Gennaio|Febbraio|Marzo|Aprile|Maggio|Giugno|Luglio|Agosto|Settembre|Ottobre|Novembre|Dicembre)\s+\d{4}$", text, re.I):
                    continue
                # Skip labels
                if text.lower() in ["data investimento", "data", "investimento", "settore"]:
                    continue
                if text and 3 < len(text) < 60:
                    sector = text
                    break

        # Get website
        website = None
        external_link = card.find("a", href=re.compile(r"^https?://(?!.*fondoitaliano)", re.I))
        if external_link:
            website = external_link.get("href")

        # Get logo
        logo_url = None
        img = card.find("img")
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if src:
                logo_url = urljoin(base_url, src)

        results.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "logo_url": logo_url,
            "status": "current",  # Portfolio page entries
            "source": "fondoitaliano_cards",
        })

    # Strategy 2: Fallback - Look for Bricks blocks with company info
    for block in soup.find_all(class_=re.compile(r"brxe-block", re.I)):
        # Skip if it's an investimento-card (already processed)
        if any("investimento-card" in c for c in block.get("class", [])):
            continue

        # Get company name
        name = None
        heading = block.find(["h2", "h3", "h4"])
        if heading:
            name = heading.get_text(strip=True)

        if not name:
            # Try from image alt
            img = block.find("img")
            if img:
                name = img.get("alt", "").strip()

        if not name or len(name) < 2 or len(name) > 80:
            continue

        # Skip navigation items
        if any(skip in name.lower() for skip in ["home", "menu", "cookie", "privacy"]):
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get sector from the specific settore element
        sector = None
        sector_el = block.find(class_=re.compile(r"settore", re.I))
        if sector_el:
            sector = sector_el.get_text(strip=True)
        else:
            for text_el in block.find_all(class_=re.compile(r"brxe-text-basic", re.I)):
                text = text_el.get_text(strip=True)
                # Skip fund names
                if re.match(r"^(FIAF|FIPEC|FITEC|FICC)(\s+[IV]+)?$", text, re.I):
                    continue
                # Skip dates
                if re.match(r"^(Gennaio|Febbraio|Marzo|Aprile|Maggio|Giugno|Luglio|Agosto|Settembre|Ottobre|Novembre|Dicembre)\s+\d{4}$", text, re.I):
                    continue
                if text and 3 < len(text) < 60:
                    sector = text
                    break

        # Get logo
        logo_url = None
        img = block.find("img")
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if src:
                logo_url = urljoin(base_url, src)

        results.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": None,
            "logo_url": logo_url,
            "status": "current",  # Portfolio page entries
            "source": "fondoitaliano_bricks",
        })

    logger.info(f"Extracted {len(results)} companies from fondoitaliano")
    return results


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from fondoitaliano.it team page.

    Structure (Bricks builder):
    - Cards are <a> tags with class "people-card" and "x-slider_slide"
    - Name in element with class "people-card__name"
    - Title/role in element with class "people-card__role"
    - Photo in img inside "people-card__media" element
    - Card href links to detail page like /team/person-name/
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Find people-card containers (they are <a> tags with both classes)
    cards = soup.find_all(
        lambda tag: tag.name == "a" and
        tag.get("class") and
        any("people-card" in c for c in tag.get("class", [])) and
        any("x-slider_slide" in c for c in tag.get("class", []))
    )

    for card in cards:
        # Get name
        name_el = card.find(class_=lambda c: c and "people-card__name" in c)
        if not name_el:
            continue
        name = name_el.get_text(strip=True)

        if not name or len(name) < 3 or len(name) > 80:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get title/role
        title = None
        role_el = card.find(class_=lambda c: c and "people-card__role" in c)
        if role_el:
            title = role_el.get_text(strip=True)

        # Get photo URL
        photo_url = None
        media_el = card.find(class_=lambda c: c and "people-card__media" in c)
        if media_el:
            img = media_el.find("img")
            if img:
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if src:
                    photo_url = urljoin(base_url, src)

        # Get detail page URL
        detail_url = card.get("href")
        if detail_url:
            detail_url = urljoin(base_url, detail_url)

        # Calculate confidence: high because structure is very consistent
        confidence = 0.90  # Base high confidence for structured data
        if title:
            confidence += 0.03
        if photo_url:
            confidence += 0.02
        confidence = min(confidence, 0.95)

        results.append({
            "name": name,
            "title": title,
            "role": None,  # Could be derived from title
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "detail_url": detail_url,
            "confidence": confidence,
            "source": "fondoitaliano_people_cards",
        })

    logger.info(f"Extracted {len(results)} team members from fondoitaliano")
    return results


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from fondoitaliano.it press page.

    Uses Bricks builder with rassegna-wide-card structure.
    Each card has: title, date, URL, and sometimes a PDF link.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_urls = set()

    # Find all rassegna-wide-card items
    cards = soup.find_all(class_=re.compile(r"rassegna-wide-card$", re.I))
    logger.debug(f"Found {len(cards)} rassegna-wide-card items")

    for card in cards:
        # Get title from heading
        title_el = card.find(class_=re.compile(r"rassegna-wide-card__heading", re.I))
        if not title_el:
            title_el = card.find(["h2", "h3", "h4"])
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Get URL from heading link
        url = None
        link = title_el.find("a", href=True)
        if link:
            url = link.get("href")
        if not url:
            link = card.find("a", href=True)
            if link:
                url = link.get("href")

        # Skip duplicates
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        # Get date
        date = None
        date_el = card.find(class_=re.compile(r"rassegna-wide-card__date|date", re.I))
        if date_el:
            date_raw = date_el.get_text(strip=True)
            # Parse DD/MM/YYYY format
            date_match = re.match(r"(\d{2})/(\d{2})/(\d{4})", date_raw)
            if date_match:
                day, month, year = date_match.groups()
                date = f"{year}-{month}-{day}"
            else:
                date = date_raw

        # Classify deal type from title
        deal_type = None
        title_lower = title.lower()
        if any(w in title_lower for w in ["acqui", "invest", "enter"]):
            deal_type = "investment"
        elif any(w in title_lower for w in ["sell", "exit", "cede"]):
            deal_type = "exit"
        elif any(w in title_lower for w in ["fundrais", "launch", "close"]):
            deal_type = "fundraise"

        # High confidence for structured extraction
        confidence = 0.85
        if url:
            confidence += 0.05
        if date:
            confidence += 0.05

        results.append({
            "title": title,
            "url": url,
            "date": date,
            "description": None,  # No description in cards
            "deal_type": deal_type,
            "confidence": min(confidence, 0.95),
            "source": "fondoitaliano_news_cards",
        })

    logger.info(f"Extracted {len(results)} news items from fondoitaliano")
    return results


def extract_company_detail(html: str, url: str) -> dict:
    """
    Extract company details from fondoitaliano.it company page.

    Fondo Italiano uses modals or separate pages for company details.
    Structure may include:
    - Full description
    - Investment date
    - Sector information
    - Company website

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

    # Fondo Italiano uses Bricks builder - look for content blocks
    # The company detail might be in a modal or dedicated page

    # Try to find the main content area
    content_selectors = [
        ".brxe-container",
        ".brxe-block",
        ".company-detail",
        ".investimento-detail",
        "main",
        "article",
    ]

    main_content = None
    for selector in content_selectors:
        main_content = soup.select_one(selector)
        if main_content:
            break

    if not main_content:
        main_content = soup.body or soup

    # Extract description from paragraphs or text blocks
    description_parts = []
    for el in main_content.find_all(["p", "div"]):
        # Skip elements with specific classes that are not descriptions
        el_classes = " ".join(el.get("class", []))
        if any(skip in el_classes.lower() for skip in ["nav", "menu", "footer", "header", "button"]):
            continue

        text = el.get_text(strip=True)
        if len(text) > 80:  # Substantial text
            # Skip fund names and labels
            if not re.match(r"^(FIAF|FIPEC|FITEC|FICC)", text, re.I):
                description_parts.append(text)

    if description_parts:
        result["description"] = " ".join(description_parts[:3])[:1000]

    # Extract sector
    full_text = main_content.get_text(" ", strip=True)

    # Look for settore label
    settore_match = re.search(r"settore[:\s]+([^<\n]+?)(?:\.|$|Data|Fondo)", full_text, re.IGNORECASE)
    if settore_match:
        sector = settore_match.group(1).strip()
        if 3 < len(sector) < 60:
            result["sector"] = sector

    # Look in specific elements
    if not result["sector"]:
        sector_el = soup.find(class_=re.compile(r"settore", re.I))
        if sector_el:
            text = sector_el.get_text(strip=True)
            if 3 < len(text) < 60:
                result["sector"] = text

    # Extract investment date
    date_patterns = [
        r"(?:data investimento|investment date)[:\s]+([A-Za-z]+\s+\d{4}|\d{4})",
        r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(\d{4})",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            if match.lastindex == 2:
                result["investment_date"] = f"{match.group(1)} {match.group(2)}"
            else:
                result["investment_date"] = match.group(1)
            break

    # Extract headquarters
    sede_match = re.search(r"sede[:\s]+([A-Za-z\s,]+?)(?:\.|$|Settore|Data)", full_text, re.IGNORECASE)
    if sede_match:
        result["headquarters"] = sede_match.group(1).strip()[:100]

    # Extract external website
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if href.startswith("http") and "fondoitaliano" not in href.lower():
            link_text = link.get_text(strip=True).lower()
            if any(word in link_text for word in ["sito", "website", "visita", "www"]):
                result["website"] = href
                break

    logger.info(f"Extracted fondoitaliano detail for {url}: desc={bool(result['description'])}, sector={result['sector']}")
    return result


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
    "company_detail": extract_company_detail,
}
