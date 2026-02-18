"""Site-specific extractors for higeurope.com.

H.I.G. Capital European website with well-structured team and portfolio pages.
Team members have names, titles, and photos in card format.
Portfolio companies show status (active/realized), logos, and descriptions.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.higeurope.com"



# URL paths — verified against live site (higeurope.com)
URLS = {
    "portfolio": "/portfolio/",
    "team": "/team/",
    "news": "/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from H.I.G. Europe portfolio page.

    Structure:
    - .portfolio--item contains each company
    - Has 'active' or 'realized' in class for status
    - h4 inside .portfolio--item-content has company name
    - p inside .portfolio--item-content has description
    - .portfolio--item-logo img has logo
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for item in soup.select(".portfolio--item"):
        # Get company name from h4 in content area
        content = item.select_one(".portfolio--item-content")
        if not content:
            continue

        name_el = content.select_one("h4")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Determine status from class
        classes = " ".join(item.get("class", []))
        if "realized" in classes:
            status = "exited"
        else:
            status = "current"

        # Get description from first p tag (skip "Learn More" links)
        description = None
        for p in content.select("p"):
            text = p.get_text(strip=True)
            if text and text != "Learn More" and len(text) > 10:
                description = text[:500]
                break

        # Get logo URL
        logo_url = None
        logo_img = item.select_one(".portfolio--item-logo img")
        if logo_img:
            src = logo_img.get("src")
            if src:
                logo_url = urljoin(base_url, src)

        # Get profile link
        profile_url = None
        link = item.select_one(".portfolio--item-link")
        if link:
            href = link.get("href")
            if href:
                profile_url = urljoin(base_url, href)

        # Try to extract sector from classes
        sector = None
        sector_classes = ["business-services", "consumer-retail", "healthcare",
                         "technology", "industrials", "financial-services",
                         "real-estate", "infrastructure", "direct-lending"]
        for sc in sector_classes:
            if sc in classes:
                sector = sc.replace("-", " ").title()
                break

        companies.append({
            "name": name,
            "sector": sector,
            "website": profile_url,  # HIG detail page, not company site
            "description": description,
            "status": status,
            "logo_url": logo_url,
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from H.I.G. Europe team page.

    Structure:
    - .team--item contains each member
    - .team--item-title-name has the name
    - .team--item-title-meta has the title
    - .team--item-image .lazy has data-bg for photo URL
    - .team--item-link has profile URL
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select(".team--item"):
        # Get name
        name_el = item.select_one(".team--item-title-name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip if name doesn't look like a person's name
        words = name.split()
        if len(words) < 2:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title
        title = None
        title_el = item.select_one(".team--item-title-meta")
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo URL from lazy-loaded image
        photo_url = None
        lazy_div = item.select_one(".team--item-image .lazy")
        if lazy_div:
            bg_url = lazy_div.get("data-bg")
            if bg_url:
                photo_url = urljoin(base_url, bg_url)

        # Get profile link
        profile_url = None
        link = item.select_one(".team--item-link")
        if link:
            href = link.get("href")
            if href:
                profile_url = urljoin(base_url, href)

        # Infer role from title
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower or "managing director" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "principal" in title_lower:
                role = "principal"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "analyst"

        # Infer location from item classes
        location = None
        classes = " ".join(item.get("class", []))
        locations = ["london", "milan", "hamburg", "paris", "madrid", "miami", "frankfurt"]
        for loc in locations:
            if loc in classes:
                location = loc.title()
                break

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,  # Not available on team page
            "email": None,
            "photo_url": photo_url,
            "profile_url": profile_url,
            "location": location,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/press items from H.I.G. Europe news page.

    Structure:
    - .post--item contains each news item
    - .post--item--title has the headline
    - ul.post--item--meta has date and categories (concatenated)
    - .post--item--excerpt has description
    - Wrapped in a link
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for item in soup.select(".post--item"):
        # Get title
        title_el = item.select_one(".post--item--title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL from link wrapping the item or from title link
        url = None
        link = item.find_parent("a") or item.select_one("a[href]")
        if link and link.get("href"):
            url = urljoin(base_url, link["href"])

        # Get date from meta (format: "January 29, 2026EuropeIndustrials")
        # Need to extract just the date part
        date = None
        meta_el = item.select_one("ul.post--item--meta")
        if meta_el:
            meta_text = meta_el.get_text(strip=True)
            # Date is at the beginning, followed by region/sectors
            # Extract up to first non-date word (Europe, Asia, etc.)
            import re
            date_match = re.match(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})", meta_text)
            if date_match:
                date = date_match.group(1)

        # Get excerpt/description
        summary = None
        excerpt_el = item.select_one(".post--item--excerpt")
        if excerpt_el:
            summary = excerpt_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
