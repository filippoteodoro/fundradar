"""Site-specific extractors for www.greenarrow-capital.com."""
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
import re
import logging

DOMAIN = "www.greenarrow-capital.com"


# URL paths — verified against live site
URLS = {
    "portfolio": "/en/investments-divestments-private-equity-eng/",
    "team": None,
    "news": None,
}
logger = logging.getLogger(__name__)


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Green Arrow Capital investments page.

    Structure: Visual Composer vc_column_container elements.
    - Section headers in h4: "IN PORTFOLIO – GAPEF 3", "REALISED GAPEF 3"
    - Company name in first <strong> that isn't a section header
    - Description follows the company name
    - Website link as external <a> (e.g., "XXX website" or "Website")
    - Status derived from section: "IN PORTFOLIO" = current, "REALISED" = exited
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Section header patterns to skip
    _RE_SECTION = re.compile(
        r"^(IN PORTFOLIO|REALISED|PRIVATE EQUITY|DIRECT LENDING)",
        re.IGNORECASE,
    )

    # Track current section for status
    current_status = "current"

    for col in soup.find_all(class_=re.compile(r'vc_column_container', re.I)):
        col_text = col.get_text(" ", strip=True)

        # Check if this column is just a section header
        h4 = col.find("h4")
        if h4:
            h4_text = h4.get_text(strip=True)
            if "REALISED" in h4_text.upper():
                current_status = "exited"
            elif "IN PORTFOLIO" in h4_text.upper():
                current_status = "current"

        # Find company name from first strong tag that isn't a section header
        name = None
        for strong in col.find_all("strong"):
            text = strong.get_text(strip=True)
            if not text or len(text) < 2:
                continue
            if _RE_SECTION.match(text):
                continue
            name = text.rstrip(" .")
            break

        if not name or len(name) < 3 or len(name) > 60:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Skip non-company text
        if name_key in ("private equity investments", "direct lending investments"):
            continue

        # Find external website link
        website = None
        for a in col.find_all("a", href=True):
            href = a.get("href", "")
            if href.startswith("http") and "greenarrow" not in href.lower():
                website = href
                break

        if not website:
            continue

        # Get description from column text
        description = None
        # Text between company name and link text
        desc_match = re.search(
            re.escape(name) + r'\s+(.+?)(?:\s+(?:Website|Sito web)|\s*$)',
            col_text, re.DOTALL
        )
        if desc_match:
            desc = desc_match.group(1).strip()
            if len(desc) > 20:
                description = desc[:500]

        # Detect "Sold in YYYY" for explicit exit
        status = current_status
        if re.search(r"Sold in \d{4}", col_text):
            status = "exited"

        results.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description,
            "status": status,
            "confidence": 0.85,
        })

    return results


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from greenarrow-capital.com top-management page.

    Structure: Team members in H3/H4 headings that contain person names (First Last format).
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Find headings that look like person names
    for h in soup.find_all(["h3", "h4"]):
        text = h.get_text(strip=True)
        if not text or len(text) > 60:
            continue

        # Skip all-caps headers (like "TOP MANAGEMENT")
        if text.upper() == text:
            continue

        # Check if it looks like a person name (2+ words, each capitalized)
        words = text.split()
        if len(words) < 2:
            continue

        # Basic name validation
        if not all(w[0].isupper() for w in words if w):
            continue

        name_key = text.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Try to find LinkedIn link nearby
        linkedin = None
        parent = h.parent
        if parent:
            linkedin_el = parent.find("a", href=re.compile(r"linkedin\.com", re.I))
            if linkedin_el:
                linkedin = linkedin_el.get("href")

        # Try to find photo
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        results.append({
            "name": text,
            "title": None,  # Titles not visible on this page
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "source": "greenarrow_team",
        })

    logger.info(f"Extracted {len(results)} team members from greenarrow")
    return results


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from greenarrow-capital.com media page.

    Structure:
    - News items in w-grid-item-h containers
    - Title in h2 with usg_post_title_1 class
    - Date in time element with datetime attribute
    - Link in w-grid-item-anchor or in title h2
    - Content snippet in usg_post_content_1
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_titles = set()

    # Find news items
    items = soup.find_all(class_=lambda c: c and "w-grid-item-h" in c)

    for item in items:
        # Get title
        title_el = item.find(class_=lambda c: c and "post_title" in c)
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_key = title.lower()[:100]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Get URL
        url = None
        anchor = item.find(class_="w-grid-item-anchor")
        if anchor:
            url = anchor.get("href")
        if not url:
            link = title_el.find("a")
            if link:
                url = link.get("href")
        if url:
            url = urljoin(base_url, url)

        # Get date from time element
        date = None
        time_el = item.find("time")
        if time_el:
            # Prefer datetime attribute (ISO format)
            datetime_attr = time_el.get("datetime")
            if datetime_attr:
                date = datetime_attr[:10]  # Just the date part
            else:
                date = time_el.get_text(strip=True)

        # Get content snippet
        summary = None
        content_el = item.find(class_=lambda c: c and "post_content" in c)
        if content_el:
            summary = content_el.get_text(strip=True)[:300]

        # Try to detect deal type from title/content
        deal_type = None
        text = (title + " " + (summary or "")).lower()
        if any(word in text for word in ["acquisizione", "acquisito", "acquisition", "acquires"]):
            deal_type = "acquisition"
        elif any(word in text for word in ["investimento", "investment", "invested"]):
            deal_type = "investment"
        elif any(word in text for word in ["exit", "cessione", "vendita", "disinvest"]):
            deal_type = "exit"
        elif any(word in text for word in ["nomina", "appointment", "entra", "joins"]):
            deal_type = "hiring"
        elif any(word in text for word in ["fundraising", "raccolta", "fund", "fondo"]):
            deal_type = "fund_news"

        # Calculate confidence based on data richness
        confidence = 0.90  # Base high confidence
        if url:
            confidence += 0.03
        if date:
            confidence += 0.02
        if deal_type:
            confidence += 0.02

        results.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "deal_type": deal_type,
            "source": "greenarrow_media",
            "confidence": min(confidence, 0.97),
        })

    logger.info(f"Extracted {len(results)} news items from greenarrow")
    return results


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
