"""Site-specific extractors for www.eiffel-ig.com (Eiffel Investment Group).

French investment group. No public company-level portfolio.
"""
import json
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.eiffel-ig.com"


# URL paths — verified against live site patterns.
# Eiffel uses a Frontity/SSR app with embedded state; route both FR/EN pages.
URLS = {
    "portfolio": None,
    "team": ["/en/group/team/", "/groupe/equipe/"],
    "news": ["/en/news/", "/actualites/"],
}

_PUBLIC_DOMAINS = ("https://www.eiffel-ig.com", "https://eiffel-ig.com")
_ADMIN_DOMAINS = ("https://admin.eiffel-ig.com", "https://eng.admin.eiffel-ig.com")


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(value.split()).strip()
    return text or None


def _to_public_url(url: str | None, base_url: str) -> str | None:
    """Normalize URLs and map admin domains to the public domain."""
    if not url:
        return None
    resolved = urljoin(base_url, url.strip())
    for admin in _ADMIN_DOMAINS:
        if resolved.startswith(admin):
            return resolved.replace(admin, _PUBLIC_DOMAINS[0], 1)
    return resolved


def _parse_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    if "T" in raw and len(raw) >= 10:
        return raw[:10]
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    return None


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return _clean_text(text)


def _extract_frontity_state(html: str) -> dict | None:
    """Parse Frontity state JSON if present."""
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__FRONTITY_CONNECT_STATE__")
    if not script or not script.string:
        return None
    try:
        state = json.loads(script.string)
    except json.JSONDecodeError:
        return None
    return state if isinstance(state, dict) else None


def _collect_by_post_type(obj, post_type: str, out: list[dict]) -> None:
    """Recursively collect dictionaries with matching post_type."""
    if isinstance(obj, dict):
        if obj.get("post_type") == post_type:
            out.append(obj)
        for value in obj.values():
            _collect_by_post_type(value, post_type, out)
        return
    if isinstance(obj, list):
        for value in obj:
            _collect_by_post_type(value, post_type, out)


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from Eiffel Frontity state.

    Primary source is embedded state (`post_type == "articles"`).
    """
    items: list[dict] = []
    seen: set[str] = set()

    state = _extract_frontity_state(html)
    if state:
        article_nodes: list[dict] = []
        _collect_by_post_type(state, "articles", article_nodes)

        for node in article_nodes:
            title = _clean_text(node.get("post_title"))
            if not title or len(title) < 8:
                continue

            url = _to_public_url(node.get("link") or node.get("guid"), base_url)
            if not url and node.get("post_name"):
                url = _to_public_url(f"/articles/{node.get('post_name')}/", base_url)
            key = f"{title.lower()}::{(url or '').lower()}"
            if key in seen:
                continue
            seen.add(key)

            date = _parse_iso_date(node.get("post_date") or node.get("post_date_gmt"))
            summary = _strip_html(node.get("post_excerpt") or node.get("post_content"))
            if summary:
                summary = summary[:300]

            items.append(
                {
                    "title": title,
                    "url": url,
                    "date": date,
                    "summary": summary,
                    "confidence": 0.88,
                }
            )

    if items:
        return items

    # Fallback: generic card/article parsing if Frontity state is unavailable.
    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select("article, .post, .news-item, .entry"):
        link = card.select_one("h2 a[href], h3 a[href], a[href]")
        if not link:
            continue
        title = _clean_text(link.get_text(" ", strip=True))
        if not title or len(title) < 8:
            continue
        url = _to_public_url(link.get("href"), base_url)
        key = f"{title.lower()}::{(url or '').lower()}"
        if key in seen:
            continue
        seen.add(key)

        date = None
        date_el = card.select_one("time, .date, [datetime]")
        if date_el:
            date = _parse_iso_date(date_el.get("datetime") or date_el.get_text(" ", strip=True))
        summary_el = card.select_one(".excerpt, .summary, p")
        summary = _clean_text(summary_el.get_text(" ", strip=True) if summary_el else None)
        if summary:
            summary = summary[:300]

        items.append(
            {
                "title": title,
                "url": url,
                "date": date,
                "summary": summary,
                "confidence": 0.70,
            }
        )
    return items


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Eiffel Frontity state.

    Primary source is embedded state (`post_type == "teammembers"`).
    """
    members: list[dict] = []
    seen: set[str] = set()

    state = _extract_frontity_state(html)
    if state:
        team_nodes: list[dict] = []
        _collect_by_post_type(state, "teammembers", team_nodes)

        for node in team_nodes:
            name = _clean_text(node.get("post_title"))
            if not name or len(name.split()) < 2:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            acf = node.get("acf") if isinstance(node.get("acf"), dict) else {}
            title = _clean_text(
                acf.get("job_title")
                or acf.get("position")
                or acf.get("role")
            )
            linkedin = _to_public_url(acf.get("linkedin"), base_url)
            email = _clean_text(acf.get("email"))
            photo = None
            image = acf.get("image")
            if isinstance(image, dict):
                photo = _to_public_url(image.get("url"), base_url)

            members.append(
                {
                    "name": name,
                    "title": title,
                    "role": None,
                    "linkedin": linkedin,
                    "email": email,
                    "photo_url": photo,
                    "confidence": 0.88,
                }
            )

    if members:
        return members

    # Fallback: generic heading-based team parsing.
    soup = BeautifulSoup(html, "html.parser")
    for heading in soup.select("h2, h3, .member-name, .team-name"):
        name = _clean_text(heading.get_text(" ", strip=True))
        if not name or len(name.split()) < 2:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        container = heading.find_parent(["article", "div", "section"]) or heading
        title = None
        title_el = container.select_one(".position, .title, .role, h4, p")
        if title_el:
            title = _clean_text(title_el.get_text(" ", strip=True))
            if title and title.lower() == name.lower():
                title = None
        linkedin_el = container.select_one("a[href*='linkedin.com']")
        linkedin = _to_public_url(linkedin_el.get("href"), base_url) if linkedin_el else None

        members.append(
            {
                "name": name,
                "title": title,
                "role": None,
                "linkedin": linkedin,
                "email": None,
                "photo_url": None,
                "confidence": 0.65,
            }
        )
    return members


EXTRACTORS = {
    "team": extract_team,
    "news": extract_news,
}
