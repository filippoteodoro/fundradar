"""Site-specific extractors for innovative-rfk.it."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.innovative-rfk.it"



# URL paths — verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": None,
    "news": "/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Innovative-RFK portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Portfolio items are in tr.el-item within tables
    for item in soup.select("tr.el-item"):
        # Get description content
        content_el = item.select_one("div.el-content")
        if not content_el:
            continue

        content_text = content_el.get_text(strip=True)
        if not content_text:
            continue

        # Get company name from image alt or link
        name = None
        img = item.select_one("img.el-image")
        if img:
            alt = img.get("alt", "")
            if alt and len(alt) > 2:
                # Clean up logo prefixes
                name = alt.replace("Logo_", "").replace("logo_", "").replace("-", " ").strip()

        # Fallback: try to get from link text
        if not name:
            link = item.select_one("a.el-link")
            if link:
                href = link.get("href", "")
                # Extract name from domain
                if href:
                    domain = href.replace("https://", "").replace("http://", "").replace("www.", "")
                    name = domain.split("/")[0].split(".")[0].upper()

        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Get website from link
        website = None
        link = item.select_one("a.el-link[href]")
        if link:
            href = link.get("href", "")
            if href and "innovative-rfk" not in href:
                website = href

        # Parse description to extract details
        description = None
        status = "current"

        # Extract first sentence as description
        sentences = content_text.split(".")
        if sentences:
            description = sentences[0].strip()

        # Check for explicit status field or heading (avoid keyword matching on general content)
        # Look for structured pattern like "Stato: Disinvestimento" or heading "Disinvestimento:"
        status_match = re.search(r"(?:stato|status)[:\s]+(\w+)", content_text, re.IGNORECASE)
        if status_match:
            status_value = status_match.group(1).lower()
            if status_value in ("disinvestimento", "exit", "exited", "ceduto", "ceduta"):
                status = "exited"
        else:
            # Fallback: check if "Disinvestimento" appears as a label/heading (at start of text or after period)
            if re.search(r"(?:^|\.\s*)Disinvestimento\s*:", content_text, re.IGNORECASE):
                status = "exited"

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description[:300] if description else None,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Innovative-RFK about page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Team members are in div.el-item.uk-panel
    for item in soup.select("div.el-item.uk-panel"):
        # Get name from h3.el-title
        name_el = item.select_one("h3.el-title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip duplicates
        if name in seen_names:
            continue
        seen_names.add(name)

        # Get title from div.el-meta (with uk-text-primary class for team)
        title = None
        title_el = item.select_one("div.el-meta.uk-text-primary")
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo URL
        photo_url = None
        img = item.select_one("img.el-image")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "founder" in title_lower or "president" in title_lower:
                role = "partner"
            elif "ceo" in title_lower:
                role = "partner"
            elif "board" in title_lower:
                role = "board"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"

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


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from Innovative-RFK news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []

    # News items are in div.el-item.uk-panel with h3.el-title containing links
    for item in soup.select("div.el-item.uk-panel"):
        # Get title and URL from h3.el-title > a
        title_link = item.select_one("h3.el-title a")
        if not title_link:
            continue

        title = title_link.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        url = title_link.get("href", "")

        # Get date from div.el-meta (without uk-text-primary class)
        date = None
        date_el = item.select_one("div.el-meta:not(.uk-text-primary)")
        if date_el:
            date = date_el.get_text(strip=True)

        # Get summary from el-content if present
        summary = None
        content_el = item.select_one("div.el-content")
        if content_el:
            summary = content_el.get_text(strip=True)[:200]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.90,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
