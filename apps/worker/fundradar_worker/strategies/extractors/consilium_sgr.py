"""Site-specific extractors for consiliumsgr.com.

Consilium SGR is an Italian private equity firm focused on mid-market buyouts.
Uses US Grid plugin with specific selectors for portfolio and team.

NOTE: Team data is at /team/ not /chi-siamo/ - the URL discovery may need updating.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.consiliumsgr.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/investimenti/",
    "team": "/team/",
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Consilium SGR investments page.

    Companies are displayed in US Grid layout with .w-grid-item-h containers.
    Names use .usg_post_title_1 class.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all grid items - US Grid plugin uses w-grid-item-h
    for item in soup.select(".w-grid-item-h"):
        # Get company name from title element
        name_el = item.select_one(".usg_post_title_1")
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

        # Check for "Scopri di più" button to get detail URL
        detail_url = None
        link = item.select_one("a.usg_btn_1, a[href*='investimenti']")
        if link:
            href = link.get("href", "")
            if href and not href.startswith("#"):
                detail_url = urljoin(base_url, href)

        # Determine status - check if in "Cedute" (exited) section
        status = "current"
        parent = item.find_parent(id="us_grid_2")
        if parent:
            status = "exited"

        # Get description from content element
        description = None
        desc_el = item.select_one(".usg_post_content_1, .usg_post_content")
        if desc_el:
            description = desc_el.get_text(strip=True)
            if description:
                description = description[:500]

        # Get logo/image URL
        logo_url = None
        img_el = item.select_one(".usg_post_image_1 img, img")
        if img_el:
            src = img_el.get("src") or img_el.get("data-src")
            if src and not src.startswith("data:") and "separator" not in src:
                logo_url = urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": description,
            "logo_url": logo_url,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Consilium SGR team page.

    Team members are in US Grid layout:
    - Container: .w-grid-item-h
    - Name: .usg_post_title_1 (dark green #223D40)
    - Title: .usg_post_custom_field_1 (gold #BA9C67)
    - Images have grayscale hover effect via .imgteamanim
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find all team member grid items
    for item in soup.select(".w-grid-item-h"):
        # Get name
        name_el = item.select_one(".usg_post_title_1")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-person entries (company names, etc.)
        # Person names typically have at least one space
        if " " not in name:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title/role
        title = None
        title_el = item.select_one(".usg_post_custom_field_1")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower or "amministrator" in title_lower or "co-founder" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "analyst"
            elif "cfo" in title_lower or "chief financial" in title_lower:
                role = "executive"
            elif "administration" in title_lower or "office" in title_lower or "middle-office" in title_lower:
                role = "staff"

        # Get photo URL
        photo_url = None
        img = item.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if src and not src.startswith("data:"):
                photo_url = urljoin(base_url, src)

        # Look for LinkedIn (may not be present)
        linkedin = None
        for link in item.select("a[href*='linkedin']"):
            linkedin = link.get("href")
            break

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


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Consilium SGR news page.

    News items use similar US Grid layout with post titles and dates.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Try multiple selectors for news items
    items = soup.select(".w-grid-item-h, article.post, .news-item")

    for item in items:
        # Get title
        title = None
        title_el = item.select_one(".usg_post_title_1, .entry-title, h2, h3")
        if title_el:
            title = title_el.get_text(strip=True)

        if not title or len(title) < 5:
            continue

        # Dedupe
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Get URL
        url = None
        link = item.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href and not href.startswith("#"):
                url = urljoin(base_url, href)

        # Get date
        date = None
        date_el = item.select_one("time, .date, .usg_post_date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        # Get summary
        summary = None
        summary_el = item.select_one(".usg_post_content, .excerpt, p")
        if summary_el:
            summary = summary_el.get_text(strip=True)[:300]

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
