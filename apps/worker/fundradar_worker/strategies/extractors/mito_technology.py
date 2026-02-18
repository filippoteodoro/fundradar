"""Site-specific extractors for mitotech.eu."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

DOMAIN = "mitotech.eu"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Mito Technology homepage."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Portfolio section contains links with images
    portfolio = soup.select_one("#portfolio")
    if not portfolio:
        return companies

    for a in portfolio.select('a[href*="/portfolio-companies"]'):
        # Get company name from image alt text
        img = a.select_one("img[alt]")
        if not img:
            continue

        name = img.get("alt", "").strip()
        if not name or name == "Image" or name.lower() in seen:
            continue

        seen.add(name.lower())
        href = a.get("href", "")
        detail_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": None,
            "website": detail_url,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from MITO Technology LinkedIn feed widget.

    The news section (#news) uses an Elfsight widget that embeds
    LinkedIn newsletter posts from "MITO Insights". Posts are
    dynamically loaded but rendered in the HTML.

    Structure:
    - Widget: div[data-app="eapps-linkedin-feed"]
    - Post containers: .CardContainer-sc-1afuoaq-0
    - Post text: .ShortenedText__ShortenedTextComponent-sc-1x39ulp-1
    - Preview title: .PreviewLink__Title-sc-1f0n847-3 (linked article title)
    - Date: .DateTime__Time-sc-120o31o-0

    Note: The Elfsight widget doesn't expose direct LinkedIn post URLs
    in the static HTML, so we use the base URL as source.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_keys = set()

    # Find the LinkedIn feed widget
    widget = soup.select_one('[data-app="eapps-linkedin-feed"]')
    if not widget:
        return news

    # Extract posts from card containers
    containers = widget.select('.CardContainer-sc-1afuoaq-0')

    for container in containers:
        # Get post text
        text_elem = container.select_one('.ShortenedText__ShortenedTextComponent-sc-1x39ulp-1')
        post_text = text_elem.get_text(strip=True) if text_elem else None

        # Get preview title (if post links to an article)
        title_elem = container.select_one('.PreviewLink__Title-sc-1f0n847-3')
        preview_title = title_elem.get_text(strip=True) if title_elem else None

        # Use preview title as title if available, otherwise use first 100 chars of text
        if preview_title:
            title = preview_title
        elif post_text:
            title = post_text[:100]
        else:
            continue

        # Skip if title is too short
        if not title or len(title) < 20:
            continue

        # Get date
        date_elem = container.select_one('.DateTime__Time-sc-120o31o-0')
        date_str = date_elem.get_text(strip=True) if date_elem else None

        # Parse date to ISO format if possible
        date = None
        if date_str:
            try:
                # Try parsing "November 12, 2025" format
                if ',' in date_str:
                    parsed = datetime.strptime(date_str, "%B %d, %Y")
                    date = parsed.strftime("%Y-%m-%d")
                # Handle "January 28" (no year) - assume current year
                else:
                    current_year = datetime.now().year
                    parsed = datetime.strptime(f"{date_str}, {current_year}", "%B %d, %Y")
                    date = parsed.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                # Keep original date string if parsing fails
                date = date_str

        # Create dedup key from title and date
        dedup_key = f"{title[:50].lower()}_{date_str or ''}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        # Combine post text and preview title for summary
        summary = None
        if post_text and preview_title:
            # If we have both, use post text as summary
            summary = post_text[:300]
        elif post_text and not preview_title:
            # If only post text, use it beyond the title
            summary = post_text[100:400] if len(post_text) > 100 else None

        news.append({
            "title": title,
            "url": base_url,  # LinkedIn feed widget doesn't expose direct post URLs
            "date": date,
            "summary": summary,
            "confidence": 0.80,  # Lower confidence due to widget-based extraction
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "news": extract_news,
}
