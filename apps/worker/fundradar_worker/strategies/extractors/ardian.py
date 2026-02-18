"""Site-specific extractors for ardian.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.ardian.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/expertise/our-portfolio",
    "team": None,  # No public team page
    "news": ["/news-insights/press-releases", "/news-insights"],
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Ardian portfolio page.

    Structure:
    - Case study banners: .banner.type-bg-casestudy with company name before |
    - Logo grid: .list-investment-preview-logo img elements
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # 1. Extract from case study banners (featured investments with descriptions)
    for case in soup.select(".banner.type-bg-casestudy"):
        text = case.get_text(strip=True)
        # Pattern: "Case studyCompanyName | Description..."
        if "|" in text:
            parts = text.split("|")
            if len(parts) >= 2:
                company_part = parts[0].replace("Case study", "").strip()
                description = parts[1].strip()[:500]

                if not company_part or len(company_part) < 2:
                    continue

                name_lower = company_part.lower()
                if name_lower in seen_names:
                    continue
                seen_names.add(name_lower)

                # Get logo from the case study
                logo_url = None
                img = case.select_one("img")
                if img:
                    src = img.get("src") or img.get("data-src")
                    if src:
                        logo_url = urljoin(base_url, src)

                companies.append({
                    "name": company_part,
                    "sector": None,
                    "website": None,
                    "description": description,
                    "logo_url": logo_url,
                    "status": "current",  # Portfolio page entries
                    "confidence": 0.85,
                })

    # 2. Extract from logo grid (portfolio company logos)
    logo_section = soup.select_one(".list-investment-preview-logo")
    if logo_section:
        for img in logo_section.select("img"):
            src = img.get("src", "")
            if not src:
                continue

            # Extract company name from filename
            filename = src.split("/")[-1].split("?")[0]

            # Clean up filename to get company name
            name = filename
            # Remove file extensions first (case-insensitive, handle double extensions)
            name = re.sub(r"\.(?:jpg|jpeg|png|gif|webp|svg)$", "", name, flags=re.IGNORECASE)
            # Remove common logo-related suffixes (case insensitive)
            name_lower = name.lower()
            for suffix in ["logo", "-off", "_off", "_0", "-0"]:
                if suffix in name_lower:
                    idx = name_lower.find(suffix)
                    name = name[:idx] + name[idx + len(suffix):]
                    name_lower = name.lower()
            # Handle URL encoding
            name = name.replace("%2B", " & ").replace("%20", " ")
            # Replace separators with spaces
            name = name.replace("_", " ").replace("-", " ")
            name = name.strip()

            # Final check: reject if still contains a dot (likely a filename remnant)
            if "." in name:
                continue

            # Capitalize properly
            if name.isupper() or name.islower():
                name = name.title()

            if not name or len(name) < 2:
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # Get full image URL
            logo_url = urljoin(base_url, src) if src else None

            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "logo_url": logo_url,
                "status": "current",  # Portfolio page entries
                "confidence": 0.85,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Ardian.

    Note: The /team page 404s, so this tries to extract any available info.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Try to find any person cards/listings
    for element in soup.find_all(["h3", "h4"]):
        name = element.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip section headings
        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "talent", "career", "join", "diversity", "inclusion",
            "contact", "menu", "ardian"
        ]):
            continue

        # Check if it looks like a person's name (basic heuristic)
        # Names usually have 2+ words and capital letters
        words = name.split()
        if len(words) < 2:
            continue
        if not all(w[0].isupper() for w in words if w):
            continue

        # Skip duplicates
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Try to find title
        title = None
        parent = element.find_parent(["div", "li", "article"])
        if parent:
            for p in parent.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) < 100 and text.lower() != name_lower:
                    title = text
                    break

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.70,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from Ardian press releases and news & insights pages.

    Press releases page uses item_list_press_release_small class items
    with <a> links to /news-insights/press-releases/[slug].
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    months = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12"
    }
    date_pattern = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)

    # Strategy 1: Press release items (on /news-insights/press-releases)
    # Look for links to individual press releases
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/news-insights/press-releases/" not in href:
            continue
        # Skip the listing page itself
        if href.rstrip("/").endswith("press-releases"):
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["press releases", "filter", "menu", "read more"]):
            continue

        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = urljoin(base_url, href)

        # Find date from parent container
        date = None
        parent = link.find_parent(["div", "li", "article"])
        if parent:
            text = parent.get_text(" ", strip=True)
            match = date_pattern.search(text)
            if match:
                day, month_name, year = match.groups()
                month_num = months.get(month_name.lower(), "01")
                date = f"{year}-{month_num}-{day.zfill(2)}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    # Strategy 2: Heading-based extraction (fallback for /news-insights)
    if not news:
        for h3 in soup.find_all(["h3", "h2"]):
            title = h3.get_text(strip=True)
            if not title or len(title) < 15:
                continue

            title_lower = title.lower()
            if any(skip in title_lower for skip in ["news", "insights", "filter", "menu", "contact"]):
                continue

            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)

            url = None
            parent = h3.find_parent("a", href=True)
            if parent:
                url = urljoin(base_url, parent.get("href", ""))
            else:
                a = h3.find("a", href=True)
                if a:
                    url = urljoin(base_url, a.get("href", ""))

            date = None
            container = h3.find_parent(["div", "article", "li"])
            if container:
                match = date_pattern.search(container.get_text())
                if match:
                    day, month_name, year = match.groups()
                    month_num = months.get(month_name.lower(), "01")
                    date = f"{year}-{month_num}-{day.zfill(2)}"

            news.append({
                "title": title,
                "url": url,
                "date": date,
                "summary": None,
                "confidence": 0.80,
            })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
