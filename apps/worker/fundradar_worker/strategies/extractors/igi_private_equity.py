"""Site-specific extractors for igisgr.it (IGI Private Equity)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.igisgr.it"



# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/investimenti/",
    "team": "/team/",
    "news": "/press/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from IGI investments page.

    Structure:
    - Name: h4 tag
    - Description: div.flfull
    - Link: a[href] with "Approfondisci"
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for h4 in soup.find_all("h4"):
        name = h4.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip navigation and non-company names
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        if name_lower in {"contatti", "privacy", "cookie", "investimenti", "login", "home", "team", "press"} or name_lower.startswith("investi"):
            continue
        seen_names.add(name_lower)

        # Get description from following div.flfull
        description = None
        desc_div = h4.find_next_sibling("div", class_="flfull")
        if not desc_div:
            # Try parent container
            parent = h4.find_parent()
            if parent:
                desc_div = parent.find("div", class_="flfull")
        if desc_div:
            description = desc_div.get_text(strip=True)[:500]

        # Try to extract sector from description
        sector = None
        if description:
            desc_lower = description.lower()
            if any(x in desc_lower for x in ["cuscinett", "bearing"]):
                sector = "Manufacturing - Bearings"
            elif any(x in desc_lower for x in ["scambiator", "heat exchanger"]):
                sector = "Manufacturing - Heat Exchangers"
            elif any(x in desc_lower for x in ["filtrazion", "filter"]):
                sector = "Manufacturing - Filtration"
            elif any(x in desc_lower for x in ["riduttor", "gearbox"]):
                sector = "Manufacturing - Gearboxes"
            elif any(x in desc_lower for x in ["metallurg", "metal"]):
                sector = "Manufacturing - Metalworking"
            elif any(x in desc_lower for x in ["pet", "preforme", "beverag"]):
                sector = "Manufacturing - Packaging"
            elif any(x in desc_lower for x in ["trasport", "logistic"]):
                sector = "Transportation & Logistics"
            elif any(x in desc_lower for x in ["accessibilità", "mobilità"]):
                sector = "Manufacturing - Mobility Systems"
            elif any(x in desc_lower for x in ["telecomunicazion", "cable"]):
                sector = "Telecommunications Equipment"
            elif any(x in desc_lower for x in ["movimentazione lineare", "linear"]):
                sector = "Manufacturing - Linear Motion"
            elif any(x in desc_lower for x in ["sement", "seed"]):
                sector = "Agriculture - Seeds"
            elif any(x in desc_lower for x in ["macchinari", "film", "packaging"]):
                sector = "Manufacturing - Machinery"

        # Get link to company page
        website = None
        link = h4.find_next("a", href=True)
        if link and "igisgr.it" in link.get("href", ""):
            website = urljoin(base_url, link.get("href"))

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from IGI team page.

    Structure:
    - Name: h2 tag
    - Title: h3 tag (following h2)
    - Bio: p tags
    - Photo: img with alt matching name
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for h2 in soup.find_all("h2"):
        name = h2.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-name headers
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        if any(skip in name_lower for skip in [
            "team", "partner", "storia", "investi", "contatt", "home",
            "senior", "manager", "associate", "ceo", "cfo"
        ]):
            continue

        # Check if this looks like a name (has at least 2 parts)
        parts = name.split()
        if len(parts) < 2:
            continue

        seen_names.add(name_lower)

        # Get title from following h3
        title = None
        title_el = h2.find_next_sibling("h3")
        if not title_el:
            title_el = h2.find_next("h3")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower or "cfo" in title_lower:
                role = "partner"
            elif "senior partner" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "senior" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"

        # Get photo URL
        photo_url = None
        img = soup.find("img", alt=re.compile(re.escape(name.split()[0]), re.I))
        if img and img.get("src"):
            photo_url = urljoin(base_url, img.get("src"))

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from IGI press releases page.

    Structure:
    - Container: div.dis_td or div[id^="post-"]
    - Date: span.mese (month name)
    - Title: h4 tag
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find press release items using dis_td class
    for item in soup.find_all("div", class_="dis_td"):
        # Get title from h4
        title_el = item.find("h4")
        if not title_el:
            continue

        title = title_el.get_text(separator=" ", strip=True)
        if not title or len(title) < 10:
            continue

        # Reconstruct truncated titles from URL slug
        if title.endswith("..."):
            link = item.find("a", href=True)
            if link:
                href = link.get("href", "")
                slug = href.rstrip("/").split("/")[-1]
                if slug and len(slug) > 10:
                    reconstructed = slug.replace("-", " ").strip()
                    if len(reconstructed) > len(title):
                        title = reconstructed[0].upper() + reconstructed[1:]
                        title = re.sub(r'\bs p a\b', 'S.p.A.', title, flags=re.IGNORECASE)
                        title = re.sub(r'\bs r l\b', 'S.r.l.', title, flags=re.IGNORECASE)

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Get URL from link
        url = None
        link = item.find("a", href=True)
        if link:
            url = urljoin(base_url, link.get("href", ""))

        # Get date from span.mese (month name in Italian)
        date = None
        date_el = item.find("span", class_="mese")
        if date_el:
            date = date_el.get_text(strip=True)

        # Get summary from text content (excluding title and date)
        summary = None
        # Get all text from the item excluding h4 and span.mese
        all_text = item.get_text(separator=" ", strip=True)
        if date:
            all_text = all_text.replace(date, "")
        all_text = all_text.replace(title, "")
        if all_text and len(all_text) > 20:
            summary = all_text[:300].strip()

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
