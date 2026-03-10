"""Site-specific extractors for equityclub.eu (The Equity Club)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.equityclub.eu"

# URL paths — verified against live site
URLS = {
    "portfolio": "/en/investments-details",
    "team": None,
    "news": "/en/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio investments from The Equity Club.

    Structure:
    - Company names are in h1 tags
    - Company websites are in external links (a tags with external hrefs)
    - Description follows the website link in strong/p tags
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all external company links (not equityclub)
    external_links = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if href.startswith("http") and "equityclub" not in href.lower():
            external_links.append(a)

    # Map company names to their website/description
    company_data = {}
    for link in external_links:
        # The description is usually in the next sibling strong or p tag
        parent_content = link.find_parent("div", class_="sqs-html-content")
        if parent_content:
            # Get all text after the link
            desc = None
            strong = parent_content.find("strong")
            if strong:
                desc = strong.get_text(strip=True)

            # Try to match by extracting company name from URL
            href = link.get("href", "")
            # Store both URL and description
            company_data[href] = {"website": href, "description": desc}

    # Company names are in h1 tags
    link_idx = 0
    external_urls = list(company_data.keys())

    for h1 in soup.find_all("h1"):
        name = h1.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        # Skip navigation/page titles
        if any(skip in name_lower for skip in [
            "investment", "equity club", "menu", "portfolio",
            "contact", "news", "team", "investimenti", "descrizione"
        ]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Match with external link by order
        website = None
        description = None
        if link_idx < len(external_urls):
            url = external_urls[link_idx]
            data = company_data.get(url, {})
            website = data.get("website")
            description = data.get("description")
            link_idx += 1

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description[:300] if description else None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from The Equity Club team page.

    Structure: First names only with titles like Co-CEO, Investment Director.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for strong in soup.find_all("strong"):
        name = strong.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip if name contains multiple words that look like a title
        if any(kw in name.lower() for kw in ["ceo", "director", "manager", "partner"]):
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["team", "equity", "menu", "contact"]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        title = None
        parent = strong.find_parent("div")
        if parent:
            text = parent.get_text()
            # Look for common titles
            for t in ["Co-CEO", "Investment Director", "Operating Partner", "Office Manager"]:
                if t.lower() in text.lower():
                    title = t
                    break

        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        email = None
        if parent:
            mail_link = parent.find("a", href=re.compile(r"mailto:"))
            if mail_link:
                email = mail_link.get("href", "").replace("mailto:", "")

        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "partner" in title_lower:
                role = "manager"
            elif "manager" in title_lower:
                role = "operations"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": email,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from The Equity Club.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    date_pattern = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})", re.I)

    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["news", "equity club", "menu"]):
            continue

        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            url = urljoin(base_url, parent_link.get("href", ""))

        date = None
        parent = heading.find_parent(["article", "div"])
        if parent:
            text = parent.get_text()
            match = date_pattern.search(text)
            if match:
                month, day, year = match.groups()
                month_num = _MONTH_NAMES.get(month.lower(), "01")
                date = f"{year}-{month_num}-{day.zfill(2)}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.75,
        })

    return news

EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
