"""Site-specific extractors for capza.co."""
import json
import re
from bs4 import BeautifulSoup
from fundradar_worker.date_utils import MONTH_NAMES as _MONTH_NAMES
from urllib.parse import urljoin

DOMAIN = "www.capza.co"

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/companies-listing",
    "team": "/teams/",
    "news": "/newsroom/",
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from CAPZA teams page.

    Structure: <li> elements with:
    - <h3> for name
    - <p> for city, title, expertise
    - <a href="linkedin..."> for LinkedIn
    - <img> for photo
    - <script type="application/json"> with embedded data
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # First try to extract from embedded JSON scripts
    for script in soup.find_all("script", type="application/json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and "firstname" in data:
                firstname = data.get("firstname", "")
                lastname = data.get("lastname", "")
                name = f"{firstname} {lastname}".strip()

                if not name or len(name) < 3:
                    continue

                name_lower = name.lower()
                if name_lower in seen_names:
                    continue
                seen_names.add(name_lower)

                members.append({
                    "name": name,
                    "title": data.get("job_title") or data.get("title"),
                    "role": None,
                    "linkedin": data.get("linkedin"),
                    "email": data.get("email"),
                    "photo_url": data.get("photo") or data.get("image"),
                    "confidence": 0.90,
                })
        except (json.JSONDecodeError, TypeError):
            continue

    # If no JSON found, fall back to HTML parsing
    if not members:
        for li in soup.find_all("li"):
            # Look for h3 with name
            h3 = li.find("h3")
            if not h3:
                continue

            name = h3.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            # Skip non-name content
            if any(skip in name.lower() for skip in ["menu", "filter", "search", "contact"]):
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # Extract title from <p> elements
            title = None
            city = None
            paragraphs = li.find_all("p")
            for i, p in enumerate(paragraphs):
                text = p.get_text(strip=True)
                if text:
                    # First p is often city, second is title
                    if i == 0 and len(text) < 30:
                        city = text
                    elif i == 1 or (i == 0 and len(text) > 30):
                        title = text
                        break

            # Combine city with title if needed
            if city and title:
                title = f"{title} ({city})"
            elif city and not title:
                title = None  # Just city isn't useful as title

            # Extract LinkedIn
            linkedin = None
            for link in li.find_all("a", href=True):
                href = link.get("href", "")
                if "linkedin.com" in href:
                    linkedin = href
                    break

            # Extract photo
            photo_url = None
            for img in li.find_all("img"):
                src = img.get("src") or img.get("data-src")
                # Skip logo/icon images
                if src and "logo" not in src.lower() and "icon" not in src.lower():
                    if not src.startswith("data:"):  # Skip placeholder data URIs
                        photo_url = urljoin(base_url, src)
                        break

            # Determine role from title
            role = None
            if title:
                title_lower = title.lower()
                if any(r in title_lower for r in ["partner", "managing director", "ceo", "founder"]):
                    role = "partner"
                elif any(r in title_lower for r in ["director", "head of"]):
                    role = "director"
                elif any(r in title_lower for r in ["manager", "vp", "vice president"]):
                    role = "manager"
                elif any(r in title_lower for r in ["analyst", "associate", "assistant"]):
                    role = "associate"

            members.append({
                "name": name,
                "title": title,
                "role": role,
                "linkedin": linkedin,
                "email": None,
                "photo_url": photo_url,
                "confidence": 0.85,
            })

    return members

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from CAPZA companies listing.

    Structure:
    - ul#ajaxresults contains all companies
    - Each li.flex.in is a company card
    - .name has the company name
    - .list.expertise span has the fund type
    - .list.country span has the country
    - .text p has the description
    - figure img has the logo
    - a.link has the website
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all company cards in the results list
    for li in soup.select("ul#ajaxresults li.flex"):
        # Get company name from .name element
        name_el = li.select_one(".name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue

        # Skip single generic sector words (filter tags, not company names)
        if name_lower in {"services", "technology", "healthcare", "retail",
                          "industrial", "consumer", "media", "financial",
                          "energy", "infrastructure"}:
            continue

        seen_names.add(name_lower)

        # Get sector/expertise
        sector = None
        expertise_el = li.select_one(".list.expertise span")
        if expertise_el:
            sector = expertise_el.get_text(strip=True)

        # Get country
        country = None
        country_el = li.select_one(".list.country span")
        if country_el:
            country = country_el.get_text(strip=True)

        # Get description
        description = None
        desc_el = li.select_one(".text p")
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        # Get website
        website = None
        link_el = li.select_one("a.link")
        if link_el:
            website = link_el.get("href")

        # Get logo URL
        logo_url = None
        img = li.select_one("figure img")
        if img:
            src = img.get("src")
            if src:
                logo_url = urljoin(base_url, src)

        # Get investment year
        year = None
        year_el = li.select_one(".list.investment span")
        if year_el:
            year = year_el.get_text(strip=True)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "logo_url": logo_url,
            "country": country,
            "year": year,
            "confidence": 0.85,
        })

    return companies

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from CAPZA newsroom page.

    Structure: ul#ajaxresults contains li items, each with:
    - h2 for title
    - a[href] for link
    - div.date with children:
      - div.month (actually day number)
      - span.day (actually month abbreviation, e.g. "Feb'")
      - span.year (year)
    - div.text for summary
    Falls back to URL slug extraction if structure not found.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_urls = set()

    # Month abbreviation mapping (CAPZA uses trailing apostrophe, e.g. "Feb'")

    # Strategy 1: Parse structured listing from ul#ajaxresults
    results_list = soup.select_one("ul#ajaxresults")
    if results_list:
        for li in results_list.find_all("li", recursive=False):
            # Get title from div.title-news (primary) or h2 (fallback)
            title = None
            title_el = li.select_one("div.title-news")
            if title_el:
                title = title_el.get_text(separator=" ", strip=True)
            if not title:
                h2 = li.find("h2")
                if h2:
                    title = h2.get_text(separator=" ", strip=True)
            if not title or len(title) < 10:
                continue

            # Get URL from "Read more" link
            url = None
            link = li.select_one("a.btn[href]")
            if not link:
                link = li.find("a", href=True)
            if link:
                url = urljoin(base_url, link.get("href", ""))
                if url in seen_urls:
                    continue
                seen_urls.add(url)

            # Get date from div.date structure
            date = None
            date_div = li.select_one("div.date")
            if date_div:
                day_el = date_div.select_one("div.month")  # confusingly named: holds day number
                month_el = date_div.select_one("span.day")  # confusingly named: holds month abbrev
                year_el = date_div.select_one("span.year")
                if day_el and month_el and year_el:
                    day_text = day_el.get_text(strip=True)
                    month_text = month_el.get_text(strip=True).rstrip("'").lower()
                    year_text = year_el.get_text(strip=True)
                    month_num = month_map.get(month_text[:3])
                    if month_num and day_text.isdigit() and year_text.isdigit():
                        date = f"{year_text}-{month_num}-{day_text.zfill(2)}"

            # Get summary from div.experpt (note: typo in actual HTML)
            summary = None
            summary_el = li.select_one("div.experpt")
            if not summary_el:
                summary_el = li.select_one("div.text")
            if summary_el:
                summary = summary_el.get_text(strip=True)[:300]

            news.append({
                "title": title,
                "url": url,
                "date": date,
                "summary": summary,
                "confidence": 0.85,
            })

    # Strategy 2: Fall back to URL slug extraction
    if not news:
        for link in soup.select('a[href*="/news/"]'):
            href = link.get('href', '')
            if not href.startswith(('https://capza.co/news/', 'http://capza.co/news/', '/news/')):
                continue

            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            match = re.search(r'/news/([^/]+)/?$', href)
            if not match:
                continue

            slug = match.group(1)
            title = slug.replace('-', ' ').replace('_', ' ')
            title = ' '.join(word.capitalize() for word in title.split())

            if len(title) < 20:
                continue

            news.append({
                "title": title,
                "url": full_url,
                "date": None,
                "summary": None,
                "confidence": 0.80,
            })

    return news

EXTRACTORS = {
    "team": extract_team,
    "portfolio": extract_portfolio,
    "news": extract_news,
}
