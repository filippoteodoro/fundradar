"""Site-specific extractors for www.fvssgr.it (FVS SGR).

FVS SGR uses a Next.js frontend with portfolio cards displayed in a grid.
Each card contains company name, sector, metadata (location, year, stake, status), and website.
"""
import re
from bs4 import BeautifulSoup
from fundradar_worker.date_utils import MONTH_NAMES as _MONTH_NAMES
from urllib.parse import urljoin

DOMAIN = "www.fvssgr.it"

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/fondi",
    "team": "/team",
    "news": "/notizie",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from FVS SGR portfolio page.

    Structure:
    - div.group.relative.flex: container for each company card
    - h5: company name
    - p.text-sm.font-bold.uppercase: sector (follows h5)
    - a[target="_blank"]: company website link
    - Nested p tags with metadata: Sede, Anno investimento, Quota, Status
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Portfolio cards are div elements with these classes
    for item in soup.select("div.group.relative.flex"):
        # Get company name from h5
        name_el = item.select_one("h5")
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

        # Get sector from the p tag that follows h5
        sector = None
        sector_el = name_el.find_next_sibling("p")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Get website from external link
        website = None
        link = item.select_one("a[target='_blank']")
        if link:
            href = link.get("href", "")
            if href.startswith("http"):
                website = href

        # Extract metadata from nested p tags
        status = "current"
        description_parts = []

        # Find metadata div with p tags containing "Sede:", "Anno:", etc.
        for p in item.select("p"):
            text = p.get_text(strip=True)
            if ":" in text:
                key, val = text.split(":", 1)
                key = key.strip()
                val = val.strip()

                if key == "Status":
                    # Check explicit status field values
                    val_lower = val.lower()
                    if val_lower in ("ceduta", "ceduto", "exited", "exit", "divested"):
                        status = "exited"
                    elif val_lower in ("in portafoglio", "current", "portfolio", "attivo"):
                        status = "current"
                elif key == "Sede":
                    description_parts.append(f"Location: {val}")
                elif key == "Anno investimento":
                    description_parts.append(f"Investment year: {val}")
                elif key == "Quota":
                    description_parts.append(f"Stake: {val}")

        description = "; ".join(description_parts) if description_parts else None

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": status,
            "confidence": 0.85,
        })

    return companies

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from FVS SGR /notizie page.

    Structure:
    - h2 > a: article title and link
    - time: date (e.g. "15 dic 2025")
    - p: summary text (before "Leggi" link)
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Italian month abbreviations for date parsing

    for h2 in soup.find_all("h2"):
        link = h2.find("a", href=True)
        if not link:
            continue

        href = link.get("href", "")
        if "/notizie/" not in href:
            continue

        title = link.get_text(strip=True)

        # Strip curly quotes
        title = title.replace("\u2018", "'").replace("\u2019", "'")
        title = title.replace("\u201c", '"').replace("\u201d", '"')

        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = urljoin(base_url, href)

        # Find date from nearby time element
        date = None
        parent = h2.find_parent(["div", "article", "section"])
        if parent:
            time_el = parent.find("time")
            if time_el:
                date_text = time_el.get_text(strip=True).lower()
                # Parse "15 dic 2025" format
                m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", date_text)
                if m:
                    day, month_abbr, year = m.groups()
                    month_num = month_map.get(month_abbr)
                    if month_num:
                        date = f"{year}-{month_num}-{day.zfill(2)}"

        # Skip non-news content: outsourcing inquiries, job postings, internship offers
        if re.search(
            r"\b(?:outsourcing|affidamento\s+in\s+outsourcing|indagine\s+esplorativa|"
            r"manifestazion[ei]\s+di\s+interesse|procedura\s+di\s+selezione|"
            r"offerta\s+di\s+stage|avvia\s+(?:la\s+)?selezione|"
            r"ricerca\s+(?:una?\s+)?risors[ae])\b",
            title_lower,
        ):
            continue

        # Find summary from p element (exclude "Leggi" links)
        summary = None
        if parent:
            for p in parent.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 20 and text.lower() not in ("leggi", "continua a leggere"):
                    # Truncate long summaries to ~200 chars
                    if len(text) > 220:
                        trimmed = text[:200]
                        last_space = trimmed.rfind(" ")
                        summary = (trimmed[:last_space] if last_space > 100 else trimmed) + "..."
                    else:
                        summary = text
                    break

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
    "news": extract_news,
}
