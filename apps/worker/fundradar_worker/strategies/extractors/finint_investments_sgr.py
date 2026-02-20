"""Site-specific extractors for finintinvestments.com.

Note: Finint Investments is an SGR (asset management company) that manages
various funds (Real Estate, Infrastructure, Private Capital, NPE, Public Markets).
They don't have a traditional portfolio company page - investments are made
through their managed funds.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.finintinvestments.com"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": ["/it/chi-siamo/management-team.php", "/it/chi-siamo/storia.php"],
    "news": "/it/press/comunicati-stampa.php",
}


def _smart_title_token(token: str) -> str:
    """Title-case a token while preserving apostrophes/hyphens."""
    parts = re.split(r"([-'’])", token.lower())
    out: list[str] = []
    for part in parts:
        if part in {"-", "'", "’"}:
            out.append(part)
        elif part:
            out.append(part[0].upper() + part[1:])
    return "".join(out)


def _normalize_person_name(raw: str) -> str:
    """Normalize whitespace/punctuation and convert all-caps names."""
    name = " ".join(raw.split()).strip()
    name = re.sub(r"[.,;:]+$", "", name)
    name = re.sub(r"'+$", "", name)
    if name.isupper():
        name = " ".join(_smart_title_token(tok) for tok in name.split())
    return name


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract management team members from Finint Investments team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names: set[str] = set()

    # Primary and fallback team-card containers.
    cards = soup.select("div.ancestor-team-collapse div.item-team")
    if not cards:
        cards = soup.select(".item-team-wrap .item-team, .item-team")

    for item in cards:
        name = None

        text_div = item.select_one("div.text p, .text p")
        if text_div:
            name_el = text_div.select_one("strong")
            if name_el:
                name = name_el.get_text(strip=True)

        if not name:
            name_el = item.select_one(".name, h3, h4")
            if name_el:
                name = name_el.get_text(strip=True)

        if not name:
            continue

        name = _normalize_person_name(name)
        if len(name) < 3 or len(name.split()) < 2:
            continue

        # Skip organization-like labels.
        lower_name = name.lower()
        if any(token in lower_name for token in ("s.p.a", "s.r.l", "group", "investments", "finint")):
            continue

        key = lower_name
        if key in seen_names:
            continue
        seen_names.add(key)

        title = None
        if text_div:
            full_text = text_div.get_text(separator=" ", strip=True)
            title = full_text.replace(name, "").strip() or None
        if not title:
            title_el = item.select_one(".role, .title, .position")
            if title_el:
                title = title_el.get_text(" ", strip=True) or None
        if title and len(title) > 200:
            title = title[:200]

        # Get photo URL
        photo_url = None
        img = item.select_one("div.photo img, img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "amministratore delegato" in title_lower or "ceo" in title_lower:
                role = "partner"
            elif "direttore generale" in title_lower:
                role = "partner"
            elif "vicedirettore" in title_lower:
                role = "partner"
            elif "consigliere delegato" in title_lower:
                role = "board"
            elif "direttore" in title_lower:
                role = "director"
            elif "responsabile" in title_lower or "head" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "analyst" in title_lower or "associate" in title_lower:
                role = "associate"

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
    """Extract news articles from Finint Investments news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles: set[str] = set()

    def _iso_date(raw: str | None) -> str | None:
        if not raw:
            return None
        text = raw.strip()
        m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
        if not m:
            return text or None
        d, mth, y = m.groups()
        return f"{y}-{mth.zfill(2)}-{d.zfill(2)}"

    # Primary: press releases table.
    for row in soup.select("table.table-press tr"):
        title_el = row.select_one("td.title a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        url = None
        href = title_el.get("href", "").strip()
        if href and not href.startswith("#"):
            url = urljoin(base_url, href)

        # Skip placeholder "download" anchors without a real URL.
        if not url:
            continue

        date = _iso_date(row.select_one("td.date").get_text(strip=True) if row.select_one("td.date") else None)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.92,
        })

        # Cap to avoid flooding old historical press items in one run.
        if len(news) >= 40:
            break

    if news:
        return news

    # Fallback: homepage/news slider blocks.
    for item in soup.select("section.sn_info_news .news_item, section.sn_news div.news_item"):
        title_el = item.select_one("div.title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        url = None
        link = item.select_one("a.btn-arrow")
        if link:
            href = link.get("href", "").strip()
            if href and not href.startswith("#"):
                url = urljoin(base_url, href)

        date = _iso_date(item.select_one("div.date").get_text(strip=True) if item.select_one("div.date") else None)
        summary = None
        desc_el = item.select_one("div.description")
        if desc_el:
            summary = desc_el.get_text(" ", strip=True)
            if len(summary) > 300:
                summary = summary[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.90,
        })

    return news


# Note: Finint Investments manages funds (RE, Infrastructure, Private Capital, NPE)
# rather than direct equity investments with portfolio companies.
# Individual fund investments are behind a disclaimer/login wall.
EXTRACTORS = {
    "team": extract_team,
    "news": extract_news,
}
