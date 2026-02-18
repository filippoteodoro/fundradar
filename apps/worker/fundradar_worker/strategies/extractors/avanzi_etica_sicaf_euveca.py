"""Site-specific extractors for aimpact.org (Avanzi Etica Sicaf EuVECA)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.aimpact.org"



# URL paths — verified against url_status.json
URLS = {
    "portfolio": "/portafoglio",
    "team": None,
    "news": "/en/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from a|impact portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Each portfolio item is in div.box-portfolio
    for item in soup.select("div.box-portfolio"):
        # Get company name from Italian title
        name_el = item.select_one("div.titolo-portfolio.italiano")
        if not name_el:
            # Fallback to any titolo-portfolio
            name_el = item.select_one("div.titolo-portfolio")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Get detail page URL
        website = None
        link_el = item.select_one("a[href]")
        if link_el:
            href = link_el.get("href", "")
            if href:
                website = urljoin(base_url, href)

        # Get logo image
        img = item.select_one("img.img-fluid")
        logo_url = None
        if img:
            src = img.get("src")
            if src:
                logo_url = urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": "Impact Investing",  # All are impact investments
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from a|impact chi-siamo page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find the Italian governance section
    italiano_divs = soup.select("div.italiano")

    for div in italiano_divs:
        current_section = None

        # Iterate through all elements to track sections
        for el in div.find_all(["h4", "p"]):
            # Track which section we're in based on h4 headers
            if el.name == "h4":
                section_text = el.get_text(strip=True).lower()
                if "consiglio di amministrazione" in section_text:
                    current_section = "board_of_directors"
                elif "collegio sindacale" in section_text:
                    current_section = "audit_board"
                elif "advisory" in section_text:
                    current_section = "advisory"
                continue

            # Process paragraph elements
            if el.name != "p":
                continue

            # Look for bold or strong tags containing names
            name_el = el.find(["b", "strong"])
            if not name_el:
                continue

            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            # Skip if already seen (avoid duplicates)
            if name in seen_names:
                continue
            seen_names.add(name)

            # Get the full text and extract title after the name
            full_text = el.get_text(strip=True)
            title = None
            role = None

            # Title is usually after comma
            if "," in full_text:
                parts = full_text.split(",", 1)
                if len(parts) > 1:
                    title = parts[1].strip()

            # Determine role based on section and title
            if current_section == "board_of_directors":
                if title:
                    title_lower = title.lower()
                    if "amministratore delegato" in title_lower or "ceo" in title_lower:
                        role = "partner"
                    elif "presidente" in title_lower:
                        role = "partner"
                    else:
                        role = "board"
                else:
                    role = "board"
            elif current_section == "audit_board":
                role = "board"
            elif current_section == "advisory":
                role = "advisor"
            else:
                # Fallback role detection
                if title:
                    title_lower = title.lower()
                    if "amministratore delegato" in title_lower or "ceo" in title_lower:
                        role = "partner"
                    elif "presidente" in title_lower:
                        role = "partner"
                    else:
                        role = "board"

            members.append({
                "name": name,
                "title": title,
                "role": role,
                "linkedin": None,
                "email": None,
                "photo_url": None,
                "confidence": 0.85,
            })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from a|impact news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []

    # News items use same structure as portfolio: div.box-portfolio
    for item in soup.select("div.box-portfolio"):
        # Get the parent link
        link = item.find_parent("a") or item.select_one("a[href]")

        # Get title from h4 inside Italian title div
        title_div = item.select_one("div.titolo-portfolio.italiano")
        if not title_div:
            continue

        title_el = title_div.select_one("h4")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # Get date from Italian date div
        date = None
        date_el = title_div.select_one("div.data.italiano")
        if date_el:
            date = date_el.get_text(strip=True)

        # Get summary from Italian span
        summary = None
        summary_el = title_div.select_one("span.italiano p")
        if summary_el:
            summary = summary_el.get_text(strip=True)[:300]

        # Get article URL
        url = None
        if link:
            href = link.get("href", "")
            if href:
                url = urljoin(base_url, href)

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
