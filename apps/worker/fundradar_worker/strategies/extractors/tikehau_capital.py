"""Site-specific extractors for tikehaucapital.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re


DOMAIN = "www.tikehaucapital.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/en/the-company/portfolio-companies",
    "team": "/en/the-company/teams",
    "news": None,
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Tikehau Capital teams page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    # Team members are in div.bod-member elements
    for member_div in soup.select("div.bod-member"):
        # Get name from h3
        name_el = member_div.select_one("h3")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get title from designation div
        title = None
        title_el = member_div.select_one(".designation p")
        if title_el:
            # Clean up the title (may have <br> tags)
            title = " ".join(title_el.get_text(" ", strip=True).split())

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "co-founder" in title_lower or "founder" in title_lower:
                role = "founder"
            elif "chief" in title_lower or "ceo" in title_lower or "cfo" in title_lower or "coo" in title_lower:
                role = "c-level"
            elif "head of" in title_lower:
                role = "head"
            elif "chairman" in title_lower:
                role = "chairman"
            elif "director" in title_lower:
                role = "director"
            elif "partner" in title_lower:
                role = "partner"

        # Get photo URL from background-image style
        photo_url = None
        image_div = member_div.select_one(".image")
        if image_div:
            style = image_div.get("style", "")
            match = re.search(r"url\(['\"]?([^'\")\s]+)['\"]?\)", style)
            if match:
                photo_path = match.group(1)
                photo_url = urljoin(base_url, photo_path)

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "photo_url": photo_url,
            "confidence": 0.9,
        })

    return members


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Tikehau Capital portfolio page.

    Structure: .portfolio-item elements with:
    - .portfolio-title: Company name
    - .portfolio-content: Description
    - .portfolio-image img: Logo
    - .portfolio-slider-wrapper: Contains metadata (Expertise, Country, Investment date)

    Note: Page shows 12 items at a time, paginated. Use portfolio-companies URL.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    for item in soup.select(".portfolio-item"):
        # Get company name
        name_el = item.select_one(".portfolio-title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get description
        description = None
        content_el = item.select_one(".portfolio-content")
        if content_el:
            description = content_el.get_text(strip=True)[:500]

        # Get logo from background-image style
        logo_url = None
        img_div = item.select_one(".portfolio-image")
        if img_div:
            style = img_div.get("style", "")
            bg_match = re.search(r"url\(['\"]?([^'\")\s]+)['\"]?\)", style)
            if bg_match:
                logo_url = urljoin(base_url, bg_match.group(1))

        # Parse metadata from slider wrapper text
        sector = None
        country = None
        slider = item.select_one(".portfolio-slider-wrapper")
        if slider:
            text = slider.get_text(strip=True)

            # Parse expertise (sector) - pattern: "Expertise:VALUE" until "Country:"
            expertise_match = re.search(r"Expertise:([A-Za-z ]+?)Country:", text)
            if expertise_match:
                sector = expertise_match.group(1).strip()

            # Parse country - pattern: "Country:VALUE" until "/" or end
            country_match = re.search(r"Country:([A-Za-z ]+?)/", text)
            if country_match:
                country = country_match.group(1).strip()

        # Add country to description if available
        if country and description:
            description = f"Country: {country}. {description}"
        elif country:
            description = f"Country: {country}"

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": description,
            "logo_url": logo_url,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/press releases from Tikehau Capital media page.

    Structure:
    - div.media-content is the parent container for each press release
    - Contains: div.media-content-wrapper (with title) and div.links (with PDF link)
    - div.title p has the title
    - div.links a has the PDF download link
    - Dates embedded in PDF filenames (YYYYMMDD or YYYY-MM-DD format)
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all media-content containers (parent of both title and links)
    for container in soup.select("div.media-content"):
        # Get title from div.media-content-wrapper div.title p
        title_wrapper = container.select_one("div.media-content-wrapper")
        if not title_wrapper:
            continue

        title_el = title_wrapper.select_one("div.title p")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_key = title.lower()[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Get URL from sibling div.links a (PDF link)
        url = None
        date = None
        links_div = container.select_one("div.links")
        if links_div:
            link = links_div.find("a", href=True)
            if link:
                href = link.get("href", "")
                if ".pdf" in href:
                    url = urljoin(base_url, href)

                    # Extract date from filename using multiple patterns
                    # Pattern 1: YYYYMMDD at start of filename (e.g., /20250829-)
                    # Must start with 20 to be a valid year
                    date_match = re.search(r"/(20\d{2})(\d{2})(\d{2})-", href)
                    if date_match:
                        year, month, day = date_match.groups()
                        date = f"{year}-{month}-{day}"
                    else:
                        # Pattern 2: DDMMYYYY at start of filename (e.g., /11122025-)
                        date_match = re.search(r"/(\d{2})(\d{2})(20\d{2})-", href)
                        if date_match:
                            day, month, year = date_match.groups()
                            date = f"{year}-{month}-{day}"
                        else:
                            # Pattern 3: DDMMYYYY after -en- (e.g., signing-en-16122025.pdf)
                            date_match = re.search(r"-en-(\d{2})(\d{2})(20\d{2})\.pdf", href)
                            if date_match:
                                day, month, year = date_match.groups()
                                date = f"{year}-{month}-{day}"
                            else:
                                # Pattern 4: YYYY-MM-DD format (e.g., /2025-07-30-)
                                date_match = re.search(r"/(20\d{2})-(\d{2})-(\d{2})-", href)
                                if date_match:
                                    year, month, day = date_match.groups()
                                    date = f"{year}-{month}-{day}"
                                else:
                                    # Pattern 5: pr-YYYY-en folder for year-only date
                                    folder_match = re.search(r"/pr-(20\d{2})-en/", href)
                                    if folder_match:
                                        year = folder_match.group(1)
                                        date = f"{year}-01-01"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "team": extract_team,
    "portfolio": extract_portfolio,
    "news": extract_news,
}
