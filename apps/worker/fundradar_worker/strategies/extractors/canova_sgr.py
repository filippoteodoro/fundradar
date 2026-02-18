"""Site-specific extractors for canovasgr.it."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "canovasgr.it"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": "/team/",
    "news": "/blog/",
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Canova SGR team page (Elementor-based)."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find all h2 headings with team member names
    headings = soup.select("h2.elementor-heading-title")

    for heading in headings:
        name = heading.get_text(strip=True)

        # Skip generic headings
        if not name or len(name) < 3 or name.lower() in ["team", "leadership", "board"]:
            continue

        # Skip duplicates
        if name in seen_names:
            continue
        seen_names.add(name)

        # Find the parent container to get related elements
        # Navigate up to find the elementor container
        container = heading.find_parent("div", class_="e-con")
        if not container:
            container = heading.find_parent("div", class_="elementor-widget")
            if container:
                container = container.find_parent("div", class_="e-con")

        title = None
        linkedin = None
        photo_url = None

        if container:
            # Find title in text-editor widget following the heading
            text_widgets = container.select("div.elementor-widget-text-editor")
            for widget in text_widgets:
                p = widget.select_one("p")
                if p:
                    text = p.get_text(strip=True)
                    # Skip if it's a long description
                    if text and len(text) < 100:
                        title = text
                        break

            # Find LinkedIn URL
            linkedin_link = container.select_one("a[href*='linkedin.com/in/']")
            if linkedin_link:
                linkedin = linkedin_link.get("href", "").split("?")[0]  # Remove query params

            # Find photo
            img = container.select_one("img[data-src], img[src]")
            if img:
                src = img.get("data-src") or img.get("src")
                if src and not src.startswith("data:"):
                    photo_url = urljoin(base_url, src)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower or "amministratore delegato" in title_lower:
                role = "partner"
            elif "consigliere" in title_lower or "presidente" in title_lower:
                role = "board"
            elif "responsabile" in title_lower or "head" in title_lower:
                role = "manager"
            elif "analyst" in title_lower or "analista" in title_lower:
                role = "associate"
            elif "key man" in title_lower:
                role = "partner"

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
    """
    Extract news/blog items from Canova SGR blog page.

    Structure: article.entry-card
    - Title: h2.entry-title a
    - URL: h2.entry-title a[href]
    - Date: time.ct-meta-element-date (Italian format: "9 Luglio 2024")
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Blog posts are in article.entry-card elements
    for article in soup.select("article.entry-card"):
        # Get title from h2.entry-title a
        title_el = article.select_one("h2.entry-title a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL
        url = None
        href = title_el.get("href")
        if href:
            url = urljoin(base_url, href)

        # Get date from time.ct-meta-element-date (Italian format)
        date = None
        date_el = article.select_one("time.ct-meta-element-date")
        if date_el:
            date = date_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    return news


# Note: Canova SGR doesn't have a dedicated portfolio page
# Their investments are announced via blog posts
EXTRACTORS = {
    "team": extract_team,
    "news": extract_news,
}
