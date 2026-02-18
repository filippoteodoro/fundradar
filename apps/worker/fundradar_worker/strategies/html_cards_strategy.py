"""
Extraction strategy for card-based HTML layouts.

Many websites present portfolio companies and team members in
card-based layouts with consistent structure. This strategy
extracts data using CSS selectors from site configuration.
"""

import logging
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag

from ..noise_filter import is_noise_text, is_boilerplate_element

logger = logging.getLogger(__name__)


def extract_from_html_cards(
    html: str,
    base_url: str,
    selectors: dict,
    data_type: str = "portfolio",
) -> list[dict]:
    """
    Extract data from card-based layouts using CSS selectors.

    Args:
        html: Raw HTML content
        base_url: Base URL for resolving relative links
        selectors: Dictionary of CSS selectors:
            - container: Container element selector
            - item: Individual item selector
            - name: Name/title selector (relative to item)
            - description: Description selector
            - sector: Sector/category selector
            - website: Website link selector
            - image: Image/logo selector
            - etc.
        data_type: Type of data ("portfolio" or "team")

    Returns:
        List of extracted items
    """
    if data_type == "portfolio":
        return extract_portfolio_from_cards(html, base_url, selectors)
    elif data_type == "team":
        return extract_team_from_cards(html, base_url, selectors)
    else:
        logger.warning(f"Unknown data type: {data_type}")
        return []


def extract_portfolio_from_cards(
    html: str,
    base_url: str,
    selectors: dict,
) -> list[dict]:
    """
    Extract portfolio companies from card layouts.

    Args:
        html: Raw HTML content
        base_url: Base URL for resolving links
        selectors: CSS selector configuration

    Returns:
        List of company dictionaries
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Find container if specified
    container = soup
    if selectors.get("container"):
        container_el = soup.select_one(selectors["container"])
        if container_el:
            container = container_el
        else:
            logger.debug(f"Container not found: {selectors['container']}")

    # Find items
    item_selector = selectors.get("item") or ".portfolio-item, .company-card, article"
    items = container.select(item_selector)

    if not items:
        # Fallback to common patterns
        items = _find_card_items(container, "portfolio")

    logger.debug(f"Found {len(items)} portfolio items")

    for item in items:
        if is_boilerplate_element(item):
            continue

        company = _extract_portfolio_item(item, base_url, selectors)
        if company and company.get("name"):
            results.append(company)

    # Check for exited section if selector provided
    if selectors.get("exited_section"):
        exited_container = soup.select_one(selectors["exited_section"])
        if exited_container:
            exited_items = exited_container.select(item_selector)
            for item in exited_items:
                company = _extract_portfolio_item(item, base_url, selectors)
                if company and company.get("name"):
                    company["status"] = "exited"
                    results.append(company)

    # Fallback: If no results, try extracting from headings directly
    if not results:
        results = _extract_companies_from_headings(soup, base_url)

    # Fallback 2: Try Visual Composer pattern (greenarrow style)
    if not results:
        results = _extract_companies_from_vc_columns(soup, base_url)

    logger.info(f"Extracted {len(results)} companies from HTML cards")
    return results


def _extract_companies_from_headings(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Fallback: Extract companies from h2/h3/h4 headings that look like company names.

    Used when card patterns don't work (e.g., Progressio pattern).
    """
    results = []
    seen_names = set()

    # Find all headings
    for heading in soup.find_all(["h2", "h3", "h4"]):
        text = heading.get_text(strip=True)

        # Skip noise and too short/long
        if not text or len(text) < 3 or len(text) > 60:
            continue

        if is_noise_text(text):
            continue

        # Skip common non-company patterns
        text_lower = text.lower()
        skip_patterns = [
            "invest", "portfolio", "our ", "the ", "team", "about",
            "news", "contact", "home", "menu", "navigation",
            "realizzate", "impostazioni", "private equity",
        ]
        if any(p in text_lower for p in skip_patterns):
            continue

        # Check if looks like a company name (capitalized, not too many words)
        words = text.split()
        if len(words) > 5:
            continue

        # Require at least first word to be capitalized
        if not words[0][0].isupper():
            continue

        # Dedupe
        name_key = text.lower().strip()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Look for nearby link or description
        parent = heading.parent
        link = parent.find("a", href=True) if parent else None
        website = None
        if link and link.get("href", "").startswith("http"):
            website = link["href"]

        # Try to extract sector from surrounding context
        sector = None
        if parent:
            sector = _extract_sector(parent, base_url, {})

        results.append({
            "name": text,
            "sector": sector,
            "website": website,
            "description": None,
            "logo_url": None,
            "status": None,
            "source": "html_headings",
        })

    return results


def _extract_companies_from_vc_columns(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Fallback: Extract companies from Visual Composer column layouts.

    Handles patterns like greenarrow where each company is in a vc_column_container
    with a description and "Sito web CompanyName" link.
    """
    results = []
    seen_names = set()

    # Look for VC columns with content
    for col in soup.find_all(class_=re.compile(r'vc_column_container', re.I)):
        # Check if this looks like a company entry (has a website link)
        website_link = col.find("a", href=re.compile(r'^https?://', re.I))
        if not website_link:
            continue

        href = website_link.get("href", "")

        # Skip internal links
        parsed_base = urlparse(base_url)
        parsed_href = urlparse(href)
        if parsed_base.netloc == parsed_href.netloc:
            continue

        # Try to extract company name from link text "Sito web XXX"
        link_text = website_link.get_text(strip=True)
        name = None

        if link_text.lower().startswith("sito web"):
            # Extract name after "Sito web"
            name = link_text[8:].strip()  # Remove "Sito web"
            if name and len(name) > 1:
                pass  # Keep this name
            else:
                name = None

        # If no name from link, try to get from column text
        if not name:
            col_text = col.get_text(" ", strip=True)
            # Skip section headers like "INVESTIMENTI GAPEF 3" or "REALIZZATE FONDO Q2"
            # Look for company name pattern: Capitalized words followed by description
            # Match company names that start after any all-caps section headers
            cleaned_text = re.sub(r'^[A-Z\s\d]+(?:GAPEF|FONDO|Q\d)\s+\d*\s*', '', col_text)
            match = re.match(r'^([A-Z][A-Za-z0-9&\s\-\.]+?)(?:\s+è\s+|\s+is\s+|\s+was\s+|,)', cleaned_text)
            if match:
                name = match.group(1).strip()

        if not name or len(name) < 2 or len(name) > 60:
            continue

        if is_noise_text(name):
            continue

        # Dedupe
        name_key = name.lower().strip()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Extract description from column text
        description = None
        col_text = col.get_text(" ", strip=True)
        # Remove the link text from description
        if link_text in col_text:
            description = col_text.replace(link_text, "").strip()
            if description and len(description) > 20:
                description = description[:500]
            else:
                description = None

        # Try to extract sector from the column
        sector = _extract_sector(col, base_url, {})

        # Also try to extract sector from description text
        if not sector and description:
            sector_patterns = [
                r"(?:opera|operante|attiva|leader)\s+(?:nel|nel settore|in)\s+([A-Za-z\s&/-]+?)(?:\.|,|$)",
                r"(?:settore|industry|sector):\s*([A-Za-z\s&/-]+?)(?:\.|,|$|\n)",
            ]
            for pattern in sector_patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    potential_sector = match.group(1).strip()
                    if len(potential_sector) > 2 and len(potential_sector) < 50:
                        sector = _normalize_sector(potential_sector)
                        break

        results.append({
            "name": name,
            "sector": sector,
            "website": href,
            "description": description,
            "logo_url": None,
            "status": None,
            "source": "html_vc_columns",
        })

    return results


def extract_team_from_cards(
    html: str,
    base_url: str,
    selectors: dict,
) -> list[dict]:
    """
    Extract team members from card layouts.

    Args:
        html: Raw HTML content
        base_url: Base URL for resolving links
        selectors: CSS selector configuration

    Returns:
        List of team member dictionaries
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Find container if specified
    container = soup
    if selectors.get("container"):
        container_el = soup.select_one(selectors["container"])
        if container_el:
            container = container_el

    # Find items
    item_selector = selectors.get("item") or ".team-member, .person, .member-card"
    items = container.select(item_selector)

    if not items:
        items = _find_card_items(container, "team")

    logger.debug(f"Found {len(items)} team items")

    for item in items:
        if is_boilerplate_element(item):
            continue

        member = _extract_team_item(item, base_url, selectors)
        if member and member.get("name"):
            results.append(member)

    # Fallback 1: Try people-card pattern (fondoitaliano style) - most reliable
    if not results:
        results = _extract_team_from_people_cards(soup, base_url)

    # Fallback 2: Try extracting from text patterns (Clessidra style)
    if not results:
        results = _extract_team_from_text_patterns(soup, base_url)

    # Fallback 3: Try sequential elements pattern (Progressio style)
    if not results:
        results = _extract_team_from_sequential_elements(soup, base_url)

    # Fallback 4: Try extracting from image alt text
    if not results:
        results = _extract_team_from_image_alts(soup, base_url)

    logger.info(f"Extracted {len(results)} team members from HTML cards")
    return results


def _extract_team_from_text_patterns(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Fallback: Extract team members from text patterns.

    Handles cases like Clessidra where names are in div text content.
    Looks for patterns like "Name SurnameTitle" in elements.
    """
    results = []
    seen_names = set()

    # First try: Clessidra pattern with vcex-heading-inner spans
    for heading_span in soup.find_all("span", class_=re.compile(r"vcex-heading-inner", re.I)):
        raw_name = heading_span.get_text(strip=True)
        if not raw_name:
            continue

        # Try to split concatenated name+title first
        name, title = _split_concatenated_name_title(raw_name)
        if not name and _looks_like_person_name(raw_name):
            name = raw_name
            title = None

        if name:
            name_key = name.lower()
            if name_key not in seen_names:
                seen_names.add(name_key)

                # Look for title in nearby vcex-custom-field (if not already extracted from split)
                parent = heading_span.find_parent(class_=re.compile(r"(entry|card|member)", re.I))
                if parent and not title:
                    title_el = parent.find(class_=re.compile(r"vcex-custom-field", re.I))
                    if title_el:
                        title = title_el.get_text(strip=True)

                    # Look for photo
                    photo_url = None
                    img = parent.find("img")
                    if img:
                        src = img.get("src") or img.get("data-src")
                        if src:
                            photo_url = urljoin(base_url, src)

                    # Look for LinkedIn
                    linkedin = None
                    link = parent.find("a", href=re.compile(r"linkedin", re.I))
                    if link:
                        linkedin = link.get("href")
                else:
                    photo_url = None
                    linkedin = None

                results.append({
                    "name": name,
                    "title": title,
                    "role": None,
                    "linkedin": linkedin,
                    "email": None,
                    "photo_url": photo_url,
                    "source": "html_vcex_pattern",
                })

    # If vcex pattern found results, return them
    if results:
        return results

    # Common title patterns
    title_patterns = [
        r"(?:Managing\s+)?(?:Partner|Director|Manager|Associate|Analyst|VP|Principal|Chairman|CEO|CFO|CIO|COO)",
        r"(?:Head|Chief)\s+of\s+\w+",
        r"(?:Senior|Junior)\s+\w+",
        r"General\s+Manager",
    ]
    title_regex = re.compile(r"\b(" + "|".join(title_patterns) + r")\b", re.IGNORECASE)

    # Look for elements containing names followed by titles
    for el in soup.find_all(["div", "span", "p", "li"], class_=re.compile(r"(team|member|person|staff|entry|card)", re.I)):
        text = el.get_text(strip=True)

        if not text or len(text) < 5 or len(text) > 200:
            continue

        # Try to extract name and title
        title_match = title_regex.search(text)
        if title_match:
            # Name is typically before the title
            name_part = text[:title_match.start()].strip()
            title_part = title_match.group(1).strip()

            # Validate name looks like a person's name
            if name_part and _looks_like_person_name(name_part):
                name_key = name_part.lower()
                if name_key not in seen_names:
                    seen_names.add(name_key)

                    # Look for photo in parent/siblings
                    parent = el.parent
                    photo_url = None
                    if parent:
                        img = parent.find("img")
                        if img:
                            src = img.get("src") or img.get("data-src")
                            if src:
                                photo_url = urljoin(base_url, src)

                    # Look for LinkedIn
                    linkedin = None
                    link = el.find("a", href=re.compile(r"linkedin", re.I))
                    if not link and parent:
                        link = parent.find("a", href=re.compile(r"linkedin", re.I))
                    if link:
                        linkedin = link.get("href")

                    results.append({
                        "name": name_part,
                        "title": title_part,
                        "role": None,
                        "linkedin": linkedin,
                        "email": None,
                        "photo_url": photo_url,
                        "source": "html_text_patterns",
                    })

    return results


def _extract_team_from_people_cards(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Extract team members from people-card styled elements.

    Handles sites like fondoitaliano with class patterns like:
    - people-card, people-card__name, people-card__role
    """
    results = []
    seen_names = set()

    # Find people cards
    cards = soup.find_all(class_=re.compile(r'people-card(?!__)', re.I))

    for card in cards:
        # Try to find name element
        name_el = card.find(class_=re.compile(r'people-card__name|person-name|member-name', re.I))
        name = name_el.get_text(strip=True) if name_el else None

        if not name or not _looks_like_person_name(name):
            continue

        # Find role/title
        role_el = card.find(class_=re.compile(r'people-card__role|person-role|member-role|member-title', re.I))
        title = role_el.get_text(strip=True) if role_el else None

        # Dedupe
        name_key = name.lower().strip()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get photo from image
        photo_url = None
        img = card.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Check for LinkedIn link
        linkedin = None
        link = card.find("a", href=re.compile(r"linkedin", re.I))
        if link:
            linkedin = link.get("href")

        results.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "source": "html_people_cards",
        })

    return results


def _extract_team_from_image_alts(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Fallback: Extract team members from image alt text.

    Handles sites where team member names are only in image alt attributes.
    """
    results = []
    seen_names = set()

    for img in soup.find_all("img"):
        alt = img.get("alt", "").strip()
        if not alt:
            continue

        # Try to extract a person name from alt text
        # Common patterns:
        # - "Company Name FirstName LastName" (skip company prefix)
        # - "FirstName LastName"
        # - "FirstName LastName Title"

        words = alt.split()
        if len(words) < 2:
            continue

        # Skip if it contains common non-name patterns
        alt_lower = alt.lower()
        skip_patterns = [
            "logo", "icon", "banner", "header", "image", "photo", "picture",
            "geometric", "shape", "background", "button", "arrow", "decoration",
            "placeholder", "avatar", "default", "thumbnail", "cover"
        ]
        if any(skip in alt_lower for skip in skip_patterns):
            continue

        # Try to find person name (2-3 capitalized words)
        name = None

        # If starts with a company name prefix (often 2+ words), try to find person name after
        # Look for pattern where last 2-3 words are capitalized (person name)
        for start_idx in range(len(words) - 1):
            potential_name_words = words[start_idx:]
            if len(potential_name_words) >= 2 and len(potential_name_words) <= 4:
                # Check if all these words look like name parts
                if all(_is_name_word(w) for w in potential_name_words):
                    potential_name = " ".join(potential_name_words)
                    if _looks_like_person_name(potential_name):
                        name = potential_name
                        break

        # If didn't find at end, try the whole alt if it looks like a name
        if not name and len(words) in [2, 3, 4] and _looks_like_person_name(alt):
            name = alt

        if not name:
            continue

        # Dedupe
        name_key = name.lower().strip()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get photo URL
        photo_url = None
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if src:
            photo_url = urljoin(base_url, src)

        # Look for title/role in nearby elements
        title = None
        parent = img.parent
        if parent:
            # Check siblings or parent's text
            for sibling in parent.find_next_siblings(["p", "span", "div"])[:2]:
                text = sibling.get_text(strip=True)
                if text and len(text) < 100 and not _looks_like_person_name(text):
                    # Might be a title
                    title = text
                    break

        results.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "source": "html_image_alts",
        })

    return results


def _extract_team_from_sequential_elements(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Fallback: Extract team members from sequential element patterns.

    Handles sites like Progressio where team members are presented as:
    <img> followed by <h2/h3> name followed by <strong> title followed by <p> bio

    Without any wrapper div for each member.
    """
    results = []
    seen_names = set()

    # Find all images that look like team member photos
    for img in soup.find_all("img"):
        src = img.get("src", "")
        alt = img.get("alt", "")

        # Skip logos, icons, decorative images
        src_lower = src.lower()
        alt_lower = alt.lower()
        skip_patterns = ["logo", "icon", "banner", "decoration", "background", "pattern"]
        if any(p in src_lower or p in alt_lower for p in skip_patterns):
            continue

        # Look for person name in next headings or text elements
        name = None
        title = None
        bio = None

        # Check siblings after the image
        current = img.parent if img.parent and img.parent.name != "body" else img
        siblings = list(current.find_next_siblings())[:10]  # Look at next 10 siblings

        for sibling in siblings:
            if sibling.name in ["h2", "h3", "h4"]:
                text = sibling.get_text(strip=True)
                if text and _looks_like_person_name(text):
                    name = text
                elif text:
                    # Might be section header, stop looking
                    break
            elif sibling.name == "strong" or sibling.name == "b":
                text = sibling.get_text(strip=True)
                if text and len(text) < 100:
                    title = text
            elif sibling.name == "p":
                text = sibling.get_text(strip=True)
                if text and len(text) > 30 and len(text) < 1000:
                    if not bio:
                        bio = text[:500]
                    # Stop after finding bio
                    if name:
                        break

        # Also try: name in image alt
        if not name and alt and _looks_like_person_name(alt):
            name = alt

        # Also try: look for heading inside same parent
        if not name:
            parent = img.parent
            if parent:
                heading = parent.find(["h2", "h3", "h4", "h5"])
                if heading:
                    text = heading.get_text(strip=True)
                    if _looks_like_person_name(text):
                        name = text

                # Look for strong/bold text for title if not found
                if not title:
                    strong = parent.find(["strong", "b"])
                    if strong:
                        text = strong.get_text(strip=True)
                        if text and len(text) < 100:
                            title = text

        if not name:
            continue

        # Dedupe
        name_key = name.lower().strip()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get photo URL
        photo_url = None
        if src:
            photo_url = urljoin(base_url, src)

        results.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "bio": bio,
            "source": "html_sequential",
        })

    return results


def _is_name_word(word: str) -> bool:
    """Check if a word looks like part of a person's name."""
    if not word:
        return False
    # First letter uppercase, rest lowercase or with apostrophes
    if not word[0].isupper():
        return False
    # Allow letters, apostrophes, hyphens
    clean = word.rstrip(".,")
    return bool(re.match(r"^[A-Z][a-zA-Z'\-]+$", clean))


def _find_card_items(container: Tag, item_type: str) -> list[Tag]:
    """
    Find card items using common patterns when no selector provided.

    Args:
        container: Container element to search
        item_type: "portfolio" or "team"

    Returns:
        List of card elements
    """
    if item_type == "portfolio":
        patterns = [
            # Specific patterns first
            ".grid-card",  # 21invest exact pattern
            "[class*='grid-card']",  # 21invest pattern variations
            "[class*='portfolio-item']",
            "[class*='portfolio-card']",
            "[class*='company-card']",
            "[class*='investment-card']",
            # Generic patterns
            "[class*='portfolio']",
            "[class*='company']",
            "[class*='investment']",
            "[class*='investimenti']",  # Italian
            "article",
            ".grid > div",
            "li[class]",  # Only li with classes to avoid nav items
        ]
    else:  # team
        patterns = [
            # Specific patterns first
            ".wpex-post-cards-entry",  # Clessidra exact pattern
            "[class*='wpex-post-cards-entry']",  # Clessidra variations
            ".team-member",
            ".member-card",
            ".person-card",
            "[class*='team-member']",
            "[class*='team-card']",
            # Generic patterns
            "[class*='team']",
            "[class*='member']",
            "[class*='person']",
            "[class*='staff']",
            "[class*='card'][class*='entry']",
            ".grid > div",
        ]

    for pattern in patterns:
        try:
            items = container.select(pattern)
            if items and len(items) >= 2:  # Expect at least 2 items
                return items
        except Exception:
            continue

    return []


def _extract_portfolio_item(
    item: Tag,
    base_url: str,
    selectors: dict,
) -> dict:
    """
    Extract portfolio company data from a card element.

    Args:
        item: Card element
        base_url: Base URL for resolving links
        selectors: CSS selectors for fields

    Returns:
        Company dictionary
    """
    company = {
        "name": None,
        "sector": None,
        "website": None,
        "description": None,
        "logo_url": None,
        "status": None,
        "source": "html_cards",
    }

    # Extract name
    name_sel = selectors.get("name") or "h2, h3, h4, .title, .name, .company-name"
    company["name"] = _extract_text(item, name_sel)

    # If no name from selector, try image alt
    if not company["name"]:
        img = item.find("img")
        if img and img.get("alt"):
            alt = img["alt"].strip()
            if len(alt) > 2 and not is_noise_text(alt):
                company["name"] = alt

    # If still no name, try extracting from URL path (21invest pattern)
    # URLs like /en/forno-d-asolo/ -> "Forno D Asolo"
    if not company["name"]:
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            # Extract company name from URL path
            name_from_url = _extract_name_from_url(href)
            if name_from_url:
                company["name"] = name_from_url

    # Extract sector (enhanced with multiple strategies)
    company["sector"] = _extract_sector(item, base_url, selectors)

    # Extract website
    website_sel = selectors.get("website") or "a[target='_blank'], a[href*='http']"
    website_link = item.select_one(website_sel)
    if website_link and website_link.get("href"):
        href = website_link["href"]
        if href.startswith("http") and base_url not in href:
            company["website"] = href

    # Extract description
    desc_sel = selectors.get("description") or ".description, .summary, .excerpt, p"
    company["description"] = _extract_text(item, desc_sel, max_length=500)

    # Extract logo
    image_sel = selectors.get("image") or "img"
    img = item.select_one(image_sel)
    if img:
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if src:
            company["logo_url"] = urljoin(base_url, src)

    # Check for exit indicators
    item_text = item.get_text().lower()
    item_classes = " ".join(item.get("class", [])).lower()

    if any(word in item_text or word in item_classes for word in ["exit", "past", "former", "divest"]):
        company["status"] = "exited"

    return company


def _extract_sector(item: Tag, base_url: str, selectors: dict) -> str | None:
    """
    Extract sector/industry from a portfolio item using multiple strategies.

    Strategies (in order of priority):
    1. CSS selectors for sector-related classes
    2. Data attributes (data-sector, data-category, data-industry)
    3. Text patterns like "Sector: X" or "Industry: Y"
    4. Badge/tag elements
    5. URL path extraction (e.g., /portfolio/technology/company)
    6. Parent container category

    Args:
        item: Card element
        base_url: Base URL
        selectors: CSS selectors config

    Returns:
        Sector string or None
    """
    # Strategy 1: CSS selectors (expanded list)
    sector_selectors = [
        selectors.get("sector") or "",
        ".sector",
        ".industry",
        ".category",
        ".tag",
        ".settore",  # Italian
        ".categoria",  # Italian
        ".badge",
        "[class*='sector']",
        "[class*='industry']",
        "[class*='category']",
        "[class*='tag-']",
        ".meta-category",
        ".post-category",
        ".entry-category",
        "span.label:not(.w-btn-label)",  # Exclude Visual Composer button labels
        ".chip",
        ".pill",
    ]

    for sel in sector_selectors:
        if not sel:
            continue
        try:
            for s in sel.split(","):
                s = s.strip()
                if not s:
                    continue
                el = item.select_one(s)
                if el:
                    text = el.get_text(strip=True)
                    if text and len(text) > 1 and len(text) < 100 and not is_noise_text(text):
                        # Skip button labels and common navigation text
                        text_lower = text.lower()
                        button_labels = ["sito web", "website", "visit site", "visita", "scopri", "leggi", "read more", "more info"]
                        if any(label in text_lower for label in button_labels):
                            continue
                        # Skip if looks like a name or navigation item
                        if not _looks_like_company_name(text):
                            return _normalize_sector(text)
        except Exception:
            continue

    # Strategy 2: Data attributes
    data_attrs = ["data-sector", "data-category", "data-industry", "data-type", "data-tag"]
    for attr in data_attrs:
        value = item.get(attr)
        if value and len(value) > 1 and len(value) < 100:
            return _normalize_sector(value)

    # Also check parent for data attributes
    parent = item.parent
    if parent:
        for attr in data_attrs:
            value = parent.get(attr)
            if value and len(value) > 1 and len(value) < 100:
                return _normalize_sector(value)

    # Strategy 3: Text patterns like "Sector: X" or "Settore: Y"
    item_text = item.get_text(" ", strip=True)
    sector_patterns = [
        r"(?:Sector|Industry|Settore|Industria|Category|Categoria):\s*([A-Za-z\s&,/-]+?)(?:\.|,|$|\n)",
        r"(?:Sector|Industry|Settore|Industria)[\s:]+([A-Z][a-zA-Z\s&/-]+?)(?:\s{2,}|$|\n)",
    ]

    for pattern in sector_patterns:
        match = re.search(pattern, item_text, re.IGNORECASE)
        if match:
            sector = match.group(1).strip()
            if len(sector) > 2 and len(sector) < 80:
                return _normalize_sector(sector)

    # Strategy 4: Look for small text elements that might be tags/badges
    for el in item.find_all(["span", "div", "a"], class_=True):
        classes = " ".join(el.get("class", [])).lower()
        # Skip Visual Composer button labels
        if "w-btn-label" in classes:
            continue
        if any(kw in classes for kw in ["tag", "badge", "label", "chip", "category", "sector"]):
            text = el.get_text(strip=True)
            if text and len(text) > 2 and len(text) < 50:
                # Skip button labels and common navigation text
                text_lower = text.lower()
                button_labels = ["sito web", "website", "visit site", "visita", "scopri", "leggi", "read more", "more info"]
                if any(label in text_lower for label in button_labels):
                    continue
                if not is_noise_text(text) and not _looks_like_company_name(text):
                    return _normalize_sector(text)

    # Strategy 5: Extract from URL path
    links = item.find_all("a", href=True)
    for link in links:
        href = link.get("href", "")
        sector_from_url = _extract_sector_from_url(href)
        if sector_from_url:
            return sector_from_url

    # Strategy 6: Check if item is nested in a sector-categorized container
    # Look up to 3 levels of parents for section headers
    current = item
    for _ in range(3):
        parent = current.parent
        if not parent:
            break

        # Check for section header before this element
        prev_heading = parent.find_previous_sibling(["h2", "h3", "h4"])
        if prev_heading:
            heading_text = prev_heading.get_text(strip=True)
            if heading_text and len(heading_text) < 50:
                # Check if it's a sector name (not a generic section title)
                sector_keywords = [
                    "technology", "healthcare", "industrial", "consumer", "financial",
                    "energia", "tecnologia", "sanità", "manifatturiero", "servizi",
                    "food", "retail", "manufacturing", "services", "software"
                ]
                heading_lower = heading_text.lower()
                if any(kw in heading_lower for kw in sector_keywords):
                    return _normalize_sector(heading_text)

        current = parent

    return None


def _extract_sector_from_url(href: str) -> str | None:
    """
    Extract sector from URL path.

    Handles patterns like:
    - /portfolio/technology/company-name
    - /investments/healthcare/
    - /settore/manifatturiero/

    Args:
        href: URL or path

    Returns:
        Sector string or None
    """
    if not href:
        return None

    path = urlparse(href).path if href.startswith("http") else href

    # Common sector path patterns
    sector_path_indicators = [
        "sector", "industry", "settore", "categoria", "category", "type"
    ]

    segments = [s.lower() for s in path.split("/") if s]

    for i, segment in enumerate(segments):
        if segment in sector_path_indicators and i + 1 < len(segments):
            # Next segment is likely the sector
            sector_slug = segments[i + 1]
            return _normalize_sector(sector_slug.replace("-", " ").replace("_", " "))

    # Also check for known sector names in the path
    known_sectors = {
        "technology": "Technology",
        "tech": "Technology",
        "software": "Software",
        "healthcare": "Healthcare",
        "health": "Healthcare",
        "sanita": "Healthcare",
        "industrial": "Industrial",
        "industriale": "Industrial",
        "manufacturing": "Manufacturing",
        "manifatturiero": "Manufacturing",
        "consumer": "Consumer",
        "retail": "Retail",
        "food": "Food & Beverage",
        "food-beverage": "Food & Beverage",
        "financial": "Financial Services",
        "fintech": "Fintech",
        "energia": "Energy",
        "energy": "Energy",
        "services": "Services",
        "servizi": "Services",
        "media": "Media",
        "entertainment": "Entertainment",
        "education": "Education",
        "logistics": "Logistics",
        "transportation": "Transportation",
    }

    for segment in segments:
        if segment in known_sectors:
            return known_sectors[segment]

    return None


def _normalize_sector(sector: str) -> str:
    """Normalize sector string."""
    if not sector:
        return None

    # Title case and clean up
    sector = sector.strip()
    sector = re.sub(r'\s+', ' ', sector)  # Normalize whitespace

    # Don't title-case if it's already properly formatted
    if not sector.isupper() and not sector.islower():
        return sector

    return sector.title()


def _looks_like_company_name(text: str) -> bool:
    """Check if text looks like a company name rather than a sector."""
    if not text:
        return False

    # Company name indicators
    company_suffixes = ["spa", "srl", "ltd", "inc", "llc", "sa", "ag", "s.p.a.", "s.r.l."]
    text_lower = text.lower()

    if any(text_lower.endswith(suffix) or f" {suffix}" in text_lower for suffix in company_suffixes):
        return True

    # If all words are capitalized and short, might be a company
    words = text.split()
    if len(words) <= 3 and all(w[0].isupper() for w in words if w):
        # But check if it's a known sector
        sector_words = [
            "technology", "healthcare", "industrial", "consumer", "financial",
            "services", "software", "retail", "manufacturing", "food", "energy"
        ]
        if any(sw in text_lower for sw in sector_words):
            return False
        return True

    return False


def _split_concatenated_name_title(text: str) -> tuple[str | None, str | None]:
    """
    Split concatenated name and title text like "Nicolas VagnerInvestor Relations".

    This handles cases where HTML elements have name and title text run together
    without proper separation (common in JS-rendered sites).

    Returns:
        Tuple of (name, title) or (None, None) if splitting fails
    """
    if not text or len(text) < 5:
        return None, None

    # Common title starter words - these will be detected even when concatenated
    # without space (e.g., "VagnerInvestor" -> split at "Investor")
    title_starter_words = [
        "Managing", "Partner", "Director", "Manager", "Associate", "Analyst",
        "Principal", "Chairman", "Founder", "Senior", "Junior", "Chief", "Head",
        "President", "CEO", "CFO", "CIO", "COO", "CMO", "CTO", "General",
        "Investment", "Investor", "Portfolio", "Operating", "Advisory", "Vice",
        "Board", "Officer", "Executive", "Amministratore", "Direttore",
        "Responsabile", "Socio", "Presidente"
    ]

    # Build regex that matches title words even when concatenated to previous text
    # Finds where a lowercase letter is followed by uppercase title word
    # Note: Don't use IGNORECASE as we need to detect the case boundary
    title_words_pattern = "|".join(title_starter_words)
    concat_pattern = re.compile(
        r"([a-z])(" + title_words_pattern + r")"
    )

    # Find where a name ends and title begins (lowercase followed by Title word)
    match = concat_pattern.search(text)
    if match:
        # Split right before the title word starts
        split_pos = match.start() + 1  # After the lowercase letter
        name_part = text[:split_pos].strip()
        title_part = text[split_pos:].strip()

        # Validate name looks like a person name
        if _looks_like_person_name(name_part):
            return name_part, title_part

    # Also try matching full title patterns with optional whitespace
    title_starters = [
        r"(?:Managing\s*)?(?:Partner|Director|Manager|Associate|Analyst|Principal|Chairman|Founder)",
        r"(?:Senior|Junior)\s*(?:Partner|Director|Manager|Associate|Analyst|VP|Principal)",
        r"(?:Chief|Head)\s*(?:of\s*)?(?:\w+\s*)?(?:Officer|Partner|Director|Manager)",
        r"(?:Vice\s*)?President",
        r"CEO|CFO|CIO|COO|CMO|CTO",
        r"General\s*(?:Partner|Manager)",
        r"Investment\s*(?:Manager|Director|Analyst)",
        r"Investor\s*Relations",
        r"Portfolio\s*(?:Manager|Director)",
        r"Operating\s*Partner",
        r"Advisory\s*(?:Board|Partner)",
    ]

    title_regex = re.compile(r"(" + "|".join(title_starters) + r")", re.IGNORECASE)

    match = title_regex.search(text)
    if match:
        split_pos = match.start()
        if split_pos > 3:  # Ensure there's at least some name before title
            name_part = text[:split_pos].strip()
            title_part = text[split_pos:].strip()

            # Validate name looks like a person name
            if _looks_like_person_name(name_part):
                return name_part, title_part

    return None, None


def _extract_team_item(
    item: Tag,
    base_url: str,
    selectors: dict,
) -> dict:
    """
    Extract team member data from a card element.

    Args:
        item: Card element
        base_url: Base URL for resolving links
        selectors: CSS selectors for fields

    Returns:
        Team member dictionary
    """
    member = {
        "name": None,
        "title": None,
        "role": None,
        "linkedin": None,
        "email": None,
        "photo_url": None,
        "source": "html_cards",
    }

    # Extract name
    name_sel = selectors.get("name") or "h2, h3, h4, .name, .person-name"
    raw_name = _extract_text(item, name_sel)

    # Always try to split concatenated name+title first (e.g., "Nicolas VagnerInvestor Relations")
    # This handles JS-rendered sites that concatenate text without separators
    if raw_name:
        split_name, split_title = _split_concatenated_name_title(raw_name)
        if split_name:
            member["name"] = split_name
            if split_title:
                member["title"] = split_title
        elif _looks_like_person_name(raw_name):
            member["name"] = raw_name

    # Extract title (if not already extracted from concatenated text)
    if not member["title"]:
        title_sel = selectors.get("title") or ".title, .position, .job-title, .role"
        member["title"] = _extract_text(item, title_sel)

    # Extract role/department
    role_sel = selectors.get("role") or ".role, .department, .team"
    member["role"] = _extract_text(item, role_sel)

    # Extract LinkedIn
    linkedin_sel = selectors.get("linkedin") or "a[href*='linkedin'], .linkedin"
    linkedin_link = item.select_one(linkedin_sel) if linkedin_sel else None
    if linkedin_link and linkedin_link.get("href"):
        href = linkedin_link["href"]
        if "linkedin" in href.lower():
            member["linkedin"] = href

    # Extract email
    email_link = item.select_one("a[href^='mailto:']")
    if email_link:
        href = email_link["href"]
        member["email"] = href.replace("mailto:", "").split("?")[0]

    # Extract photo
    image_sel = selectors.get("image") or "img"
    img = item.select_one(image_sel) if image_sel else None
    if img:
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if src:
            member["photo_url"] = urljoin(base_url, src)

    return member


def _extract_text(item: Tag, selector: str | None, max_length: int = 200) -> str | None:
    """
    Extract text from an element using CSS selector.

    Args:
        item: Parent element
        selector: CSS selector (can be comma-separated), or None
        max_length: Maximum text length

    Returns:
        Extracted text or None
    """
    if not selector:
        return None

    # Try each selector
    for sel in selector.split(","):
        sel = sel.strip()
        try:
            el = item.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                if text and len(text) > 1 and not is_noise_text(text):
                    return text[:max_length]
        except Exception:
            continue

    return None


def _extract_name_from_url(href: str) -> str | None:
    """
    Extract company name from URL path.

    Handles patterns like:
    - /en/forno-d-asolo/ -> "Forno D Asolo"
    - /portfolio/dl-software/ -> "Dl Software"
    - /investments/apaczka/ -> "Apaczka"

    Args:
        href: URL or path

    Returns:
        Extracted company name or None
    """
    if not href:
        return None

    # Parse the path
    path = urlparse(href).path if href.startswith("http") else href

    # Split by / and get meaningful segments
    segments = [s for s in path.split("/") if s and len(s) > 1]

    # Skip common non-company segments
    skip_segments = {"en", "it", "portfolio", "investments", "companies", "investimenti", "team", "about"}

    for segment in reversed(segments):  # Start from the end
        if segment.lower() in skip_segments:
            continue

        # Check if segment looks like a company slug (has letters, maybe hyphens)
        if re.match(r'^[a-z0-9][a-z0-9\-]+[a-z0-9]$', segment, re.I):
            # Convert slug to name: forno-d-asolo -> Forno D Asolo
            name = segment.replace("-", " ").replace("_", " ")
            # Title case each word
            name = " ".join(word.capitalize() for word in name.split())

            # Skip if too short or looks like noise
            if len(name) > 2 and not is_noise_text(name):
                return name

    return None


def _looks_like_person_name(text: str) -> bool:
    """
    Check if text looks like a person's name.

    Args:
        text: Text to check

    Returns:
        True if text appears to be a person's name
    """
    if not text or len(text) < 3 or len(text) > 60:
        return False

    words = text.split()
    if len(words) < 2 or len(words) > 5:
        return False

    # Check if words look like name parts
    for word in words:
        word_clean = word.rstrip(".,")
        if not word_clean:
            continue
        # First letter should be uppercase
        if not word_clean[0].isupper():
            return False
        # Should be mostly letters
        if not re.match(r"^[A-Za-z\'-]+\.?$", word_clean):
            return False

    # Filter out common non-name patterns
    text_lower = text.lower()
    noise_words = [
        "cookie", "privacy", "contact", "about", "news",
        "our", "read", "more", "learn", "view", "see", "all"
    ]
    if any(noise in text_lower for noise in noise_words):
        return False

    # Filter out text that is ONLY a department/section header (e.g., "Portfolio Management")
    # But allow names like "Nicolas Vagner" even if followed by role words
    section_only_patterns = [
        r"^(?:portfolio|investment|advisory|executive|management)\s+(?:team|board|committee|management)$",
        r"^(?:senior|junior)\s+(?:management|team|staff)$",
    ]
    for pattern in section_only_patterns:
        if re.match(pattern, text_lower):
            return False

    return True
