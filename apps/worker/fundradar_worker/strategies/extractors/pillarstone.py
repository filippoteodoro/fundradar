"""Site-specific extractors for pillarstone.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.pillarstone.com"



# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/portafoglio/",
    "team": "/team/",
    "news": "/newsroom/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Pillarstone portfolio page.

    Structure: Bootstrap collapse components with data-anchor attributes.
    Companies: Fi.Nav, RSCT, Bluwater, CSM Italy, Magicland, Premuda, Sirti, etc.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Known company name mappings for cleaner output
    name_corrections = {
        "bluwater-s-p-a": "Bluwater S.p.A.",
        "csm-italy-s-r-l": "CSM Italy S.r.l.",
        "magicland-s-p-a": "MagicLand S.p.A.",
        "premuda-s-p-a": "Premuda S.p.A.",
        "sirti-s-p-a": "Sirti S.p.A.",
    }

    # Look for elements with data-anchor attributes (collapse triggers)
    # Use CSS selector since find_all with attrs dict doesn't work well with hyphenated attrs
    for el in soup.select("[data-anchor]"):
        anchor = el.get("data-anchor", "")
        if not anchor:
            continue

        # Skip fund vehicle entries — not portfolio companies
        if anchor in {"fi-nav-fund", "rsct-fund"}:
            continue

        # Use corrected name or fallback to title case
        name = name_corrections.get(anchor)
        if not name:
            name = anchor.replace("-", " ").replace("_", " ").title()
            # Clean up Italian company suffixes
            name = re.sub(r'\bS P A\b', 'S.p.A.', name, flags=re.IGNORECASE)
            name = re.sub(r'\bS R L\b', 'S.r.l.', name, flags=re.IGNORECASE)

        # Try to find better name from images
        img = el.find("img")
        if img:
            alt = img.get("alt", "").strip()
            if alt and len(alt) > 1:
                name = alt

        # Skip incomplete or invalid names
        if not name or len(name) < 3 or name.lower() in ["none", "well", "fund"]:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find corresponding content section
        content_id = f"#{anchor}"
        content = soup.find(id=anchor)

        description = None
        website = None

        if content:
            # Get description from paragraphs
            for p in content.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 30:
                    description = text[:500]
                    break

            # Get website link
            for link in content.find_all("a", href=True):
                href = link.get("href", "")
                if href.startswith("http") and "pillarstone" not in href.lower():
                    website = href
                    break

        companies.append({
            "name": name,
            "sector": "Turnaround",
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    # Fallback: extract from h3/h4 headings if no data-anchor found
    if not companies:
        for heading in soup.find_all(["h3", "h4"]):
            name = heading.get_text(strip=True)
            if not name or len(name) < 2:
                continue

            name_lower = name.lower()
            if any(skip in name_lower for skip in ["portfolio", "pillarstone", "menu"]):
                continue

            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",  # Portfolio page entries
                "confidence": 0.70,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Pillarstone team page.

    Structure: .team-card with h3 names and h6 titles.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for team cards
    for card in soup.find_all(class_="team-card"):
        # Get name from h3
        h3 = card.find("h3")
        if not h3:
            continue

        # Names may have <br> between first and last name
        # Extract text parts separately and join with spaces
        name_parts = []
        for content in h3.children:
            if hasattr(content, 'name') and content.name == 'br':
                continue
            text = content.get_text(strip=True) if hasattr(content, 'get_text') else str(content).strip()
            if text:
                name_parts.append(text)
        name = " ".join(name_parts)
        name = " ".join(name.split())  # Clean up any extra whitespace

        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from h6
        title = None
        h6 = card.find("h6")
        if h6:
            title = h6.get_text(strip=True)

        # Get photo
        photo_url = None
        img = card.find("img")
        if img:
            src = img.get("src") or img.get("data-lazy-src") or img.get("data-src")
            if src and not src.startswith("data:"):
                photo_url = urljoin(base_url, src)

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["chairman", "ceo", "chief"]):
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    # Fallback: look for h3 names if no team-card found
    if not members:
        for h3 in soup.find_all("h3"):
            for br in h3.find_all("br"):
                br.replace_with(" ")
            name = h3.get_text(strip=True)
            name = " ".join(name.split())

            if not name or len(name) < 3:
                continue

            words = name.split()
            if len(words) < 2:
                continue

            name_lower = name.lower()
            if any(skip in name_lower for skip in ["team", "pillarstone", "menu"]):
                continue

            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # Find title from h6
            title = None
            parent = h3.find_parent("div")
            if parent:
                h6 = parent.find("h6")
                if h6:
                    title = h6.get_text(strip=True)

            members.append({
                "name": name,
                "title": title,
                "role": None,
                "linkedin": None,
                "email": None,
                "photo_url": None,
                "confidence": 0.80,
            })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from Pillarstone newsroom page.

    Structure: h3 elements with links to /comunicato-stampa/ or /aggiornamento/.
    The page uses entry-meta for dates and categories.
    Categories: Comunicato Stampa (press releases), Aggiornamento (updates).
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_urls = set()

    # Primary extraction: Look for h3 > a links pointing to news pages
    for h3 in soup.find_all("h3"):
        link = h3.find("a", href=True)
        if not link:
            continue

        href = link.get("href", "")
        # Filter for actual news article URLs
        if not any(x in href for x in ["/comunicato-stampa/", "/aggiornamento/"]):
            continue

        url = href if href.startswith("http") else urljoin(base_url, href)

        # Skip duplicates
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Get title - clean up any date/category text that got concatenated
        title = link.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Try to find associated metadata (date, category) nearby
        date = None
        category = None

        # Look for entry-meta sibling or nearby element
        parent = h3.find_parent("div") or h3.find_parent("article")
        if parent:
            # Look for date
            date_elem = parent.find(class_="entry-date")
            if not date_elem:
                # Try to find date pattern in text
                import re
                date_match = re.search(r'\d{1,2}\s+\w+\s+\d{4}', parent.get_text())
                if date_match:
                    date = date_match.group(0)
            else:
                date = date_elem.get_text(strip=True)

            # Look for category links
            for cat_link in parent.find_all("a", href=True):
                cat_href = cat_link.get("href", "")
                if "/categoria/" in cat_href:
                    category = cat_link.get_text(strip=True)
                    break

        # Infer category from URL if not found
        if not category:
            if "/comunicato-stampa/" in url:
                category = "Comunicato Stampa"
            elif "/aggiornamento/" in url:
                category = "Aggiornamento"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "category": category,
            "summary": None,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
