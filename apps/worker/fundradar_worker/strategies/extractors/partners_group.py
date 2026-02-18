"""Site-specific extractors for www.partnersgroup.com (Partners Group).

Portfolio pages use Swiper carousels with case study links across categories:
  - /en/our-investments/private-equity
  - /en/our-investments/infrastructure
  - /en/our-investments/real-estate
  - /en/our-investments/private-credit

Team page (/en/about-us/our-team) is a server-rendered HTML table
with ~160 senior team members (Managing Directors, Partners, Board).

News page (/en/news-and-views) uses Vue.js MVC for rendering.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import logging

DOMAIN = "www.partnersgroup.com"


# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": None,
    "news": ["/en/news-and-views/press-releases", "/en/news-and-views/firm-updates"],
}
logger = logging.getLogger(__name__)

# Investment category pages to scrape for portfolio companies
INVESTMENT_CATEGORIES = [
    "private-equity",
    "infrastructure",
    "real-estate",
    "private-credit",
]


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Partners Group investment pages.

    Structure (as of Jan 2026):
    - Companies in Swiper carousel slides per category page
    - Each slide: <p class="tag-lg-text"> for sector, <h2 class="h5 title"> for name,
      <h2 class="h5 year"> for year, <a aria-label="View case study about {Name}"> for link
    - The main /en/our-investments page links to category sub-pages
    - Each category shows 5-7 featured companies

    This extractor works on whichever page HTML is provided (category page or main page).
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Strategy 1: Extract from carousel case study links (aria-label pattern)
    # <a aria-label="View case study about ROSEN Group" href="/en/our-investments/...">
    for link in soup.find_all("a", attrs={"aria-label": True}):
        aria = link.get("aria-label", "")
        match = re.match(r"View case study about (.+)", aria, re.I)
        if not match:
            continue

        name = match.group(1).strip()
        if not name or len(name) < 2 or len(name) > 80:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        href = link.get("href", "")
        detail_url = urljoin(base_url, href) if href else None

        # Try to find year and sector from nearby elements in the same slide
        year = None
        sector = None
        slide = link.find_parent(class_=re.compile(r"swiper-slide"))
        if slide:
            year_el = slide.find("h2", class_=re.compile(r"\byear\b"))
            if year_el:
                year_text = year_el.get_text(strip=True)
                if re.match(r"\d{4}$", year_text):
                    year = year_text

            # Sector from tag-lg-text in the slide (e.g. "Technology", "Education")
            sector_el = slide.find("p", class_=re.compile(r"tag-lg-text"))
            if sector_el:
                sector = sector_el.get_text(strip=True)

        # Fallback: determine asset class from the URL path
        if not sector:
            if "/private-equity/" in href:
                sector = "Private Equity"
            elif "/infrastructure/" in href:
                sector = "Infrastructure"
            elif "/real-estate/" in href:
                sector = "Real Estate"
            elif "/private-credit/" in href:
                sector = "Private Credit"

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": None,
            "detail_page_url": detail_url,
            "status": "current",
            "investment_date": f"{year}-01-01" if year else None,
            "confidence": 0.90,
        })

    # Strategy 2: Fallback — find <h2 class="h5 title"> inside carousel content sections
    if not companies:
        for heading in soup.select("h2.title"):
            name = heading.get_text(strip=True)
            if not name or len(name) < 2 or len(name) > 80:
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue

            # Skip year headings (4-digit numbers)
            if re.match(r"^\d{4}$", name):
                continue

            seen_names.add(name_lower)

            # Find case study link nearby
            detail_url = None
            parent = heading.find_parent(class_=re.compile(r"swiper-slide|carousel"))
            if parent:
                case_link = parent.find("a", href=re.compile(r"/our-investments/"))
                if case_link:
                    detail_url = urljoin(base_url, case_link.get("href", ""))

            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "detail_page_url": detail_url,
                "status": "current",
                "confidence": 0.80,
            })

    # Strategy 3: Any links to /our-investments/{category}/{company-slug}
    if not companies:
        inv_pattern = re.compile(
            r"/en/our-investments/(?:private-equity|infrastructure|real-estate|private-credit)/([a-z0-9-]+)/?$",
            re.I,
        )
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            m = inv_pattern.search(href)
            if not m:
                continue

            slug = m.group(1)
            # Convert slug to name: "rosen-group" -> "Rosen Group"
            name = slug.replace("-", " ").title()

            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            detail_url = urljoin(base_url, href)

            sector = None
            if "/private-equity/" in href:
                sector = "Private Equity"
            elif "/infrastructure/" in href:
                sector = "Infrastructure"
            elif "/real-estate/" in href:
                sector = "Real Estate"
            elif "/private-credit/" in href:
                sector = "Private Credit"

            companies.append({
                "name": name,
                "sector": sector,
                "website": None,
                "description": None,
                "detail_page_url": detail_url,
                "status": "current",
                "confidence": 0.75,
            })

    logger.info(f"Extracted {len(companies)} portfolio companies from Partners Group")
    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Partners Group team page.

    Structure (as of Jan 2026):
    - Server-rendered HTML table with ~160 rows
    - Each row: <tr> with <td> cells: Name | Title | Business Unit | Location
    - Expandable detail section with biography (<h4> name, <p class="small-body"> title)
    - Executive Team section at top uses profile cards with photos
    - Board of Directors section uses profile-detail components
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Strategy 1: Table rows (main team listing)
    # <tr><td>Name</td><td>Title</td><td>Business Unit</td><td>Location</td>...</tr>
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        name = cells[0].get_text(strip=True)
        if not name or len(name) < 3 or len(name) > 80:
            continue

        # Must look like a person name (at least 2 words)
        words = name.split()
        if len(words) < 2:
            continue

        # Skip header rows
        if name.lower() in ("name", "nome", "team member"):
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from cell (may contain <br> tags)
        title_text = cells[1].get_text(" ", strip=True)
        title = title_text if title_text and len(title_text) > 2 else None

        business_unit = cells[2].get_text(strip=True) or None
        location = cells[3].get_text(strip=True) or None

        # Determine role from title
        role = _classify_role(title)

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.90,
        })

    # Strategy 2: Profile detail cards (Executive Team / Board of Directors)
    # <h3 class="h4 profile-detail__name">Name</h3>
    for name_el in soup.select("h3.profile-detail__name"):
        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Title is in <p class="tag-lg-text"> nearby
        title = None
        parent = name_el.find_parent(class_=re.compile(r"profile-detail"))
        if parent:
            title_el = parent.find("p", class_=re.compile(r"tag-lg-text"))
            if title_el:
                title = title_el.get_text(strip=True)

        # Photo from img in the profile card
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        role = _classify_role(title)

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    # Strategy 3: Fallback — h2.h6 headings used in executive/board sections
    # <h2 class="h6 mb-sm-4">Ana Campos</h2>
    for heading in soup.select("h2.h6"):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3 or len(name) > 80:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        title = None
        next_p = heading.find_next_sibling("p", class_=re.compile(r"body-sm-text"))
        if next_p:
            title = next_p.get_text(strip=True)

        role = _classify_role(title)

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.85,
        })

    logger.info(f"Extracted {len(members)} team members from Partners Group")
    return members


def _classify_role(title: str | None) -> str | None:
    """Classify a title string into a normalized role category."""
    if not title:
        return None
    t = title.lower()
    if "board" in t or "chairman" in t or "chairwoman" in t:
        return "board"
    if "partner" in t and ("managing" in t or "senior" in t):
        return "partner"
    if "partner" in t:
        return "partner"
    if "managing director" in t:
        return "director"
    if "director" in t or "head of" in t:
        return "director"
    if "vice president" in t or "vp" in t:
        return "vp"
    if "principal" in t:
        return "principal"
    if "associate" in t:
        return "associate"
    if "analyst" in t:
        return "analyst"
    return None


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from Partners Group press releases and firm updates pages.

    Press releases page is server-rendered with links to individual releases.
    Firm updates page has dated items about key events.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Date pattern: DD.MM.YYYY
    date_pattern = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")

    # Strategy 1: Links to press release detail pages
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/news-and-views/" not in href or href.rstrip("/").endswith("/news-and-views"):
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 10 or len(title) > 200:
            continue

        # Skip nav items
        if title.lower() in ("news and views", "read more", "view", "view all",
                              "press releases", "firm updates", "perspectives",
                              "in the media", "corporate news", "investment news"):
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = urljoin(base_url, href)

        # Try to find date from nearby text
        date = None
        parent = link.find_parent(["tr", "li", "div", "article"])
        if parent:
            text = parent.get_text()
            match = date_pattern.search(text)
            if match:
                day, month, year = match.groups()
                date = f"{year}-{month}-{day}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    # Strategy 2: Headings (h2/h3) that look like news titles
    if not news:
        for heading in soup.find_all(["h2", "h3", "h4"]):
            title = heading.get_text(strip=True)
            if not title or len(title) < 15 or len(title) > 200:
                continue

            title_lower = title.lower()
            if title_lower in seen_titles:
                continue
            if any(skip in title_lower for skip in ["press release", "firm update",
                                                      "news and views", "partners group"]):
                continue
            seen_titles.add(title_lower)

            url = None
            parent_link = heading.find_parent("a", href=True)
            if parent_link:
                url = urljoin(base_url, parent_link.get("href", ""))

            date = None
            parent = heading.find_parent(["div", "article", "li"])
            if parent:
                match = date_pattern.search(parent.get_text())
                if match:
                    day, month, year = match.groups()
                    date = f"{year}-{month}-{day}"

            news.append({
                "title": title,
                "url": url,
                "date": date,
                "summary": None,
                "confidence": 0.80,
            })

    logger.info(f"Extracted {len(news)} news items from Partners Group")
    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
