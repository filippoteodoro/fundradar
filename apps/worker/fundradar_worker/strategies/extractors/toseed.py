"""Site-specific extractors for toseed.it (ToSeed & Partners)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "toseed.it"



# URL paths — verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from ToSeed portfolio page.

    Companies are listed with their website URLs in the description.
    Company names can be extracted from the website domains.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for website links in the portfolio descriptions
    # Pattern: <a href="https://company-domain.com">website</a>
    for link in soup.select("a[href]"):
        href = link.get("href", "")
        if not href:
            continue

        # Skip non-external links and social media
        if "toseed.it" in href or "linkedin" in href or "facebook" in href:
            continue

        # Look for startup/company websites
        if re.match(r'^https?://', href):
            # Extract domain name
            domain_match = re.search(r'https?://(?:www\.)?([^/]+)', href)
            if not domain_match:
                continue

            domain = domain_match.group(1)

            # Skip common non-company domains
            if any(skip in domain for skip in ["google", "youtube", "twitter", "instagram", "wp-content"]):
                continue

            # Convert domain to company name
            # Remove TLD and convert to title case
            name_parts = domain.replace(".com", "").replace(".it", "").replace(".eu", "").replace(".tech", "")
            name_parts = name_parts.replace("-", " ").replace(".", " ")
            name = name_parts.title().strip()

            if not name or len(name) < 2 or name.lower() in seen_names:
                continue

            seen_names.add(name.lower())

            # Try to find sector info nearby
            sector = None
            parent = link.find_parent("div", class_="elementor-widget-container")
            if parent:
                text = parent.get_text()
                sector_match = re.search(r'Sector[:\s]*([^\n<]+)', text)
                if sector_match:
                    sector = sector_match.group(1).strip()

            companies.append({
                "name": name,
                "sector": sector,
                "website": href,
                "description": None,
                "status": "current",  # Portfolio page entries
                "confidence": 0.85,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from ToSeed about-us page.

    Team members are displayed with photo, name, title, description,
    and LinkedIn link in Elementor containers.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Known titles to detect (first text might be title, not name)
    known_titles = {"chairman", "ceo", "principal", "associate", "analyst",
                    "investment associate", "manager", "director"}

    # Find LinkedIn profile links and extract surrounding info
    for linkedin in soup.select("a[href*='linkedin.com/in/']"):
        linkedin_url = linkedin.get("href", "")

        # Navigate up to find the container with member info
        parent = linkedin.parent
        for _ in range(8):  # Navigate up several levels
            if not parent or not parent.name:
                break

            texts = [t.strip() for t in parent.stripped_strings]
            # We need at least name and title
            if len(texts) >= 2:
                # Check if first text looks like a name (has space = first + last name)
                # or is a title (no space, matches known title)
                first_text = texts[0]
                if " " in first_text and first_text.lower() not in known_titles:
                    # First text is likely the name
                    name = first_text
                    title = texts[1]
                elif first_text.lower() in known_titles:
                    # First text is title, need to go up one more level
                    parent = parent.parent
                    continue
                else:
                    # Single-word, might be title, keep going up
                    parent = parent.parent
                    continue

                # Skip if name looks like navigation
                if len(name) < 3 or name.lower() in ["linkedin", "menu", "home", "about", "portfolio"]:
                    parent = parent.parent
                    continue

                # Skip duplicates
                if name in seen_names:
                    break
                seen_names.add(name)

                # Find photo URL from nearby image
                photo_url = None
                img = parent.select_one("img[alt]")
                if img:
                    alt = img.get("alt", "")
                    src = img.get("src")
                    # Verify this is the right person's photo
                    if alt and src and "linkedin" not in src.lower() and \
                       (name.lower() in alt.lower() or alt.lower() in name.lower()):
                        photo_url = urljoin(base_url, src)

                # Determine role category
                role = None
                if title:
                    title_lower = title.lower()
                    if "chairman" in title_lower or "ceo" in title_lower:
                        role = "partner"
                    elif "principal" in title_lower:
                        role = "principal"
                    elif "associate" in title_lower:
                        role = "associate"
                    elif "analyst" in title_lower:
                        role = "analyst"

                members.append({
                    "name": name,
                    "title": title,
                    "role": role,
                    "linkedin": linkedin_url,
                    "email": None,
                    "photo_url": photo_url,
                    "confidence": 0.90,
                })
                break

            parent = parent.parent

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from ToSeed website."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Look for news article patterns
    for article in soup.select("article, .post, .news-item, .elementor-post"):
        title_el = article.select_one("h2, h3, h4, .entry-title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        url = None
        link = article.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        news.append({
            "title": title,
            "url": url,
            "date": None,
            "summary": None,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
