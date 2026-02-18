"""Site-specific extractors for bluegemcp.com (BlueGem).

Portfolio structure:
- Squarespace site with company logos as images
- Images have mouseover effects (logo -> company image)
- Company names can be extracted from image URLs/filenames
- Sections: Fund III, Fund II, Realised
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote

DOMAIN = "www.bluegemcp.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio",
    "team": "/team",
    "news": "/news",
}
def _clean_company_name(raw_name: str) -> str | None:
    """Extract clean company name from image filename."""
    # Decode URL encoding
    name = unquote(raw_name)

    # First, remove PC_LOGO prefix pattern (do this before skip check)
    name = re.sub(r"^PC[_ ]?LOGO[_ ]+\d+[_ ]+", "", name, flags=re.IGNORECASE)

    # Skip non-company images (check after removing PC_LOGO prefix)
    skip_patterns = [
        "SOLID", "PRI ", "CNC", "IC logo", "Header", "footer",
        "BLUEGEM", "background", "banner", "Combined"
    ]
    if any(skip.lower() in name.lower() for skip in skip_patterns):
        return None

    # Remove common suffixes
    name = re.sub(r"\d+$", "", name)  # Trailing numbers
    name = re.sub(r"[-_]?v\d+.*$", "", name, flags=re.IGNORECASE)  # Version numbers

    # Clean up separators
    name = name.replace("+", " ").replace("_", " ").replace("-", " ")

    # Collapse multiple spaces
    name = " ".join(name.split())

    # Skip if too short or looks like a generic name
    if len(name) < 2 or name.lower() in ["v", "logo", "image"]:
        return None

    return name.strip().title()


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from BlueGem portfolio page.

    Companies are displayed as logo images. Names are extracted from
    the image src URLs. Status is determined by section headers.

    Structure:
    - Fund III section: current portfolio
    - Fund II section: current portfolio
    - Realised section: exited companies
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Track current section (Fund III, Fund II, Realised)
    current_status = "current"

    # Skip patterns for non-company images
    skip_patterns = [
        "SOLID", "Logo", "logo", "PRI", "CNC", "IC logo", "IC%20logo",
        "banner", "Header", "footer", "background", "BLUEGEM"
    ]

    # Find all relevant elements in document order
    for element in soup.find_all(["h2", "img"]):
        # Check for section headers
        if element.name == "h2":
            text = element.get_text(strip=True).lower()
            if "realised" in text or "realized" in text or "exited" in text:
                current_status = "exited"
            elif "fund" in text:
                current_status = "current"
            continue

        # Process images
        if element.name == "img":
            src = element.get("src", "") or element.get("data-src", "")
            # Include both squarespace URL patterns
            if not src or ("squarespace" not in src and "static1." not in src):
                continue

            # Skip non-company images
            if any(skip in src for skip in skip_patterns):
                continue

            # Extract filename from URL - handle both patterns:
            # 1. static1.squarespace.com/.../timestamp/filename.ext
            # 2. images.squarespace-cdn.com/.../filename.ext
            raw_name = None
            match = re.search(r"/(\d+)/([^/]+)\.(?:jpg|png|jpeg)(?:\?|$| )", src, re.IGNORECASE)
            if match:
                # For timestamp URLs, the filename is the second group
                raw_name = match.group(2)
            else:
                # Try simpler pattern
                match = re.search(r"/([^/]+)\.(?:jpg|png|jpeg)(?:\?|$)", src, re.IGNORECASE)
                if match:
                    raw_name = match.group(1)

            if not raw_name:
                continue
            name = _clean_company_name(raw_name)

            if not name or name.lower() in seen_names:
                continue

            seen_names.add(name.lower())

            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "status": current_status,
                "confidence": 0.85,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from BlueGem team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for team member patterns
    for el in soup.select(".sqs-block-content, .team-member, [class*='team']"):
        # Find name - typically in bold or heading
        for name_el in el.select("strong, b, h3, h4, h5"):
            name = name_el.get_text(strip=True)
            if not name or len(name) < 3 or len(name) > 50:
                continue

            # Skip section headers
            if any(skip in name.lower() for skip in ["bluegem", "team", "partner", "company"]):
                continue

            # Check if it looks like a person name (2+ words, no special chars)
            words = name.split()
            if len(words) < 2 or any(c.isdigit() for c in name):
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # Try to find title (next sibling or parent's next text)
            title = None
            next_el = name_el.find_next_sibling()
            if next_el:
                title = next_el.get_text(strip=True)
                if len(title) > 100:
                    title = None

            # Get photo if available
            photo_url = None
            parent = name_el.find_parent(["div", "article", "section"])
            if parent:
                img = parent.find("img")
                if img:
                    src = img.get("src") or img.get("data-src")
                    if src:
                        photo_url = urljoin(base_url, src)

            members.append({
                "name": name,
                "title": title,
                "role": "partner" if title and "partner" in title.lower() else None,
                "linkedin": None,
                "email": None,
                "photo_url": photo_url,
                "confidence": 0.75,
            })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/blog items from BlueGem news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # News items are in article.blog-item elements (Squarespace blog)
    for item in soup.select(".blog-item"):
        # Get title from h1 a
        title_el = item.select_one("h1 a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL
        url = None
        href = title_el.get("href")
        if href:
            url = urljoin(base_url, href)

        # Get date from time.blog-date (format: DD/MM/YYYY)
        date = None
        date_el = item.select_one("time.blog-date")
        if date_el:
            date = date_el.get_text(strip=True)

        # Get excerpt from .blog-excerpt
        summary = None
        excerpt_el = item.select_one(".blog-excerpt")
        if excerpt_el:
            summary = excerpt_el.get_text(strip=True)
            if summary and len(summary) > 300:
                summary = summary[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary if summary else None,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
