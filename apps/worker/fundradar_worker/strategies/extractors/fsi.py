"""Site-specific extractors for www.fondofsi.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.fondofsi.it"



# URL paths for monitoring - verified against live site
# Note: FSI uses Italian-language URLs; /investments does NOT exist, /investimenti/ is correct
URLS = {
    "portfolio": "/investimenti/",
    "team": "/persone/",
    "news": "/en/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from FSI /investimenti/ page.

    Structure (verified Feb 2026):
    - Investment cards contain <a> tags linking to /investimenti-fsi/{slug}/
    - Company names are in <h4> headings within the cards
    - Description snippets appear below each heading
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Navigation/garbage patterns to skip
    SKIP_LOWER = {
        "chi siamo", "come operiamo", "persone", "comunicati stampa",
        "iniziative", "il fondo", "investimenti", "sostenibilità",
        "linee guida", "esg", "video", "news", "fsi", "home",
        "contatti", "cookie", "privacy", "menu",
        "media",
    }

    # Pattern 1: Links to /investimenti-fsi/{slug}/ — the actual investment entries
    for link in soup.find_all("a", href=re.compile(r"/investimenti-fsi/[^/]+/?$")):
        # Get name from h4 inside the link, or from link text
        h4 = link.find("h4")
        if h4:
            name = h4.get_text(strip=True)
        else:
            name = link.get_text(strip=True)

        if not name or len(name) < 2 or len(name) > 80:
            continue

        name_lower = name.lower().strip()
        if name_lower in seen_names or name_lower in SKIP_LOWER:
            continue

        # Skip fund vehicle section headings like "Investimenti 2", "Investimenti 3"
        if re.match(r"^investimenti\s+\d+$", name_lower):
            continue

        # Skip UUIDs/hashes
        if re.match(r"^[0-9a-f]{8}[\s-]", name, re.I):
            continue

        seen_names.add(name_lower)

        # Get detail page URL
        detail_url = urljoin(base_url, link.get("href", ""))

        # Get description from nearby p element
        description = None
        parent = link.find_parent(["div", "article", "li"])
        if parent:
            p = parent.find("p")
            if p:
                text = p.get_text(strip=True)
                if text and len(text) > 10:
                    description = text[:500]

        companies.append({
            "name": name,
            "sector": None,
            "website": detail_url,
            "description": description,
            "status": "current",
            "confidence": 0.90,
        })

    # Pattern 2: Fallback — look for h4 headings that look like company names
    # (in case the link structure changes)
    if not companies:
        for h4 in soup.find_all("h4"):
            name = h4.get_text(strip=True)
            if not name or len(name) < 2 or len(name) > 80:
                continue

            name_lower = name.lower().strip()
            if name_lower in seen_names or name_lower in SKIP_LOWER:
                continue

            # Skip fund vehicle section headings like "Investimenti 2", "Investimenti 3"
            if re.match(r"^investimenti\s+\d+$", name_lower):
                continue

            if re.match(r"^[0-9a-f]{8}[\s-]", name, re.I):
                continue

            # Check if it has a parent link to an investment detail page
            parent_link = h4.find_parent("a", href=True)
            if not parent_link:
                continue

            href = parent_link.get("href", "")
            if "investimenti" not in href.lower():
                continue

            seen_names.add(name_lower)

            companies.append({
                "name": name,
                "sector": None,
                "website": urljoin(base_url, href),
                "description": None,
                "status": "current",
                "confidence": 0.85,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from FSI /persone/ page.

    Note: The correct team URL is /persone/, not /chi-siamo/
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Pattern 1: Employee cards with .a-employee__title-link
    for link in soup.select(".a-employee__title-link"):
        name = link.get_text(strip=True) or link.get("title", "")
        if not name or len(name) < 3:
            continue

        if name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        # Extract title - look for .a-employee__position after the link
        title = None
        position_el = link.find_next(class_="a-employee__position")
        if position_el:
            title = position_el.get_text(strip=True)

        # Extract photo URL - look for .a-employee__img-link before the link
        photo_url = None
        img_link = link.find_previous(class_="a-employee__img-link")
        if img_link:
            style = img_link.get("style", "")
            match = re.search(r"url\((.*?)\)", style)
            if match:
                photo_url = match.group(1).strip("'\"")

        # Extract profile URL
        profile_url = link.get("href")
        if profile_url:
            profile_url = urljoin(base_url, profile_url)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(x in title_lower for x in ["partner", "amministratore", "managing"]):
                role = "partner"
            elif any(x in title_lower for x in ["direttore", "director"]):
                role = "director"
            elif any(x in title_lower for x in ["principal"]):
                role = "principal"
            elif any(x in title_lower for x in ["associate"]):
                role = "associate"
            elif any(x in title_lower for x in ["analyst"]):
                role = "analyst"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    # Pattern 2: Industrial/Operating Partners listed in headings
    for heading in soup.select("h2, h3, h4"):
        heading_text = heading.get_text(strip=True).lower()
        if any(x in heading_text for x in ["industrial", "operating", "partner", "advisor"]):
            # Look for names in the following text
            next_el = heading.find_next_sibling()
            if next_el:
                text = next_el.get_text(strip=True)
                # Split by commas or newlines
                potential_names = re.split(r"[,\n]", text)
                for potential in potential_names:
                    name = potential.strip()
                    # Validate it looks like a name (2-4 words, capitalized)
                    words = name.split()
                    if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
                        if name.lower() not in seen_names:
                            seen_names.add(name.lower())
                            members.append({
                                "name": name,
                                "title": "Partner",
                                "role": "partner",
                                "linkedin": None,
                                "email": None,
                                "photo_url": None,
                                "confidence": 0.70,
                            })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from FSI media page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Pattern: Article cards
    for article in soup.select("article, .post, .news-item, .a-post-card"):
        title_el = article.select_one("h2 a, h3 a, h4 a, .entry-title a, .a-post-card__title a")
        if not title_el:
            title_el = article.select_one("h2, h3, h4, .entry-title, .a-post-card__title")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        # Extract URL
        url = None
        if title_el.name == "a":
            url = title_el.get("href")
        else:
            link = article.select_one("a[href]")
            if link:
                url = link.get("href")
        if url:
            url = urljoin(base_url, url)

        # Extract date
        date = None
        date_el = article.select_one("time, .date, .entry-date, .a-post-card__date")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        # Extract summary
        summary = None
        summary_el = article.select_one(".excerpt, .summary, .entry-summary, p")
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
