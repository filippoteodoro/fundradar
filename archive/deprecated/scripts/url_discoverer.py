#!/usr/bin/env python3
"""
URL discoverer for fund websites.

Finds portfolio/team/news page URLs for all funds by analyzing
navigation links and common URL patterns.

Usage:
    python url_discoverer.py
    python url_discoverer.py --limit 20
    python url_discoverer.py --fund-id 21-invest
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin

sys.path.insert(0, str(Path(__file__).parent))

from fundradar_worker.playwright_fetcher import PlaywrightFetcher, FetchOptions, PLAYWRIGHT_AVAILABLE

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DB_FILE = DATA_DIR / "db.json"
OUTPUT_FILE = DATA_DIR / "site_configs" / "fund_urls.json"

# URL patterns by type (ordered by likelihood)
URL_PATTERNS = {
    "portfolio": [
        # Italian patterns
        "/investimenti",
        "/portafoglio",
        "/partecipazioni",
        "/le-nostre-aziende",
        "/aziende-partecipate",
        "/fondi-investimenti",
        # English patterns
        "/portfolio",
        "/investments",
        "/companies",
        "/portfolio-companies",
        "/our-companies",
        "/equity-investments",
        "/our-investments",
        "/participations",
    ],
    "team": [
        # Italian patterns
        "/team",
        "/chi-siamo",
        "/il-team",
        "/persone",
        "/professionisti",
        "/la-squadra",
        "/gruppo",
        # English patterns
        "/people",
        "/our-team",
        "/about-us",
        "/about",
        "/who-we-are",
        "/management",
        "/leadership",
    ],
    "news": [
        # Italian patterns
        "/news",
        "/notizie",
        "/comunicati",
        "/comunicati-stampa",
        "/rassegna-stampa",
        "/media",
        # English patterns
        "/press",
        "/press-releases",
        "/newsroom",
        "/media-room",
        "/updates",
        "/insights",
        "/blog",
    ]
}

# Known good URLs for priority funds (from TEST_SITES in test_extractors.py)
KNOWN_URLS = {
    "21-invest": {
        "portfolio": "https://www.21invest.com/en/investments/",
        "team": "https://www.21invest.com/en/who-we-are/",
        "needs_scroll": True,
    },
    "fondoitaliano": {
        "portfolio": "https://www.fondoitaliano.it/investimenti/",
        "team": "https://www.fondoitaliano.it/persone/",
        "news": "https://www.fondoitaliano.it/press/",
    },
    "alcedo": {
        "portfolio": "https://www.alcedo.it/fondi_private_equity/",
        "team": "https://www.alcedo.it/team_alcedo_sgr/",
        "news": "https://www.alcedo.it/news/",
    },
    "progressio": {
        "portfolio": "https://www.progressiosgr.it/investments/",
        "team": "https://www.progressiosgr.it/team/",
        "news": "https://www.progressiosgr.it/news/",
    },
    "greenarrow-capital": {
        "portfolio": "https://www.greenarrow-capital.com/investimenti/",
        "news": "https://www.greenarrow-capital.com/media/",
    },
    "clessidra": {
        "portfolio": "https://www.clessidragroup.it/soluzioni/private-equity/fondi-investimenti/",
        "team": "https://www.clessidragroup.it/gruppo/team/",
        "news": "https://www.clessidragroup.it/news/",
        "needs_scroll": True,
    },
}


@dataclass
class DiscoveredUrl:
    """A discovered URL with confidence."""
    url: str
    confidence: float  # 0.0-1.0
    source: str  # "link", "pattern", "known"
    verified: bool = False


@dataclass
class FundUrls:
    """URLs for a fund."""
    fund_id: str
    fund_name: str
    website: str | None
    portfolio: DiscoveredUrl | None = None
    team: DiscoveredUrl | None = None
    news: DiscoveredUrl | None = None
    needs_scroll: bool = False
    homepage_error: str | None = None
    discovered_at: str | None = None


def extract_navigation_links(html: str, base_url: str) -> list[dict]:
    """Extract navigation links from HTML with context."""
    links = []

    # Parse base URL
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # Find all anchor tags with href
    link_pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    matches = re.findall(link_pattern, html, re.IGNORECASE | re.DOTALL)

    for href, text in matches:
        # Skip non-http links
        if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
            continue

        # Normalize URL
        if href.startswith('//'):
            full_url = f"{parsed.scheme}:{href}"
        elif href.startswith('/'):
            full_url = f"{base}{href}"
        elif href.startswith('http'):
            full_url = href
        else:
            full_url = urljoin(base_url, href)

        # Only keep same-domain links
        link_parsed = urlparse(full_url)
        if link_parsed.netloc != parsed.netloc:
            continue

        # Clean text
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        clean_text = re.sub(r'\s+', ' ', clean_text)

        links.append({
            "url": full_url,
            "text": clean_text.lower(),
            "path": link_parsed.path.lower().rstrip('/'),
        })

    return links


def match_url_to_type(
    links: list[dict],
    url_type: str,
) -> DiscoveredUrl | None:
    """Find best matching URL for a type from discovered links."""
    patterns = URL_PATTERNS.get(url_type, [])

    # First pass: exact pattern match in path
    for link in links:
        path = link["path"]
        for pattern in patterns:
            if pattern in path:
                return DiscoveredUrl(
                    url=link["url"],
                    confidence=0.9,
                    source="link",
                )

    # Second pass: text content match
    type_keywords = {
        "portfolio": ["portfolio", "investimenti", "investments", "companies", "aziende", "partecipazioni"],
        "team": ["team", "chi siamo", "about", "persone", "people", "management"],
        "news": ["news", "press", "media", "comunicati", "notizie"],
    }
    keywords = type_keywords.get(url_type, [])

    for link in links:
        text = link["text"]
        for keyword in keywords:
            if keyword in text:
                return DiscoveredUrl(
                    url=link["url"],
                    confidence=0.7,
                    source="link",
                )

    return None


def generate_pattern_urls(base_url: str, url_type: str) -> list[DiscoveredUrl]:
    """Generate candidate URLs from common patterns."""
    patterns = URL_PATTERNS.get(url_type, [])
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    candidates = []
    for i, pattern in enumerate(patterns[:5]):  # Try top 5 patterns
        url = f"{base}{pattern}/"
        # Higher confidence for earlier patterns
        confidence = 0.5 - (i * 0.05)
        candidates.append(DiscoveredUrl(
            url=url,
            confidence=confidence,
            source="pattern",
        ))

    return candidates


async def discover_fund_urls(
    fetcher: PlaywrightFetcher,
    fund: dict,
) -> FundUrls:
    """Discover URLs for a single fund."""
    fund_id = fund["id"]
    result = FundUrls(
        fund_id=fund_id,
        fund_name=fund["name"],
        website=fund.get("website"),
    )

    # Check for known URLs first
    if fund_id in KNOWN_URLS:
        known = KNOWN_URLS[fund_id]
        if known.get("portfolio"):
            result.portfolio = DiscoveredUrl(
                url=known["portfolio"],
                confidence=1.0,
                source="known",
                verified=True,
            )
        if known.get("team"):
            result.team = DiscoveredUrl(
                url=known["team"],
                confidence=1.0,
                source="known",
                verified=True,
            )
        if known.get("news"):
            result.news = DiscoveredUrl(
                url=known["news"],
                confidence=1.0,
                source="known",
                verified=True,
            )
        result.needs_scroll = known.get("needs_scroll", False)
        result.discovered_at = datetime.now(timezone.utc).isoformat()
        return result

    if not result.website:
        result.homepage_error = "No website URL"
        result.discovered_at = datetime.now(timezone.utc).isoformat()
        return result

    # Fetch homepage
    try:
        options = FetchOptions(
            wait_for_network_idle=True,
            network_idle_timeout=15000,
        )
        fetch_result = await fetcher.fetch(result.website, options=options)

        if fetch_result.error:
            result.homepage_error = fetch_result.error
            result.discovered_at = datetime.now(timezone.utc).isoformat()
            return result

        if not fetch_result.html:
            result.homepage_error = "No HTML content"
            result.discovered_at = datetime.now(timezone.utc).isoformat()
            return result

        html = fetch_result.html

    except Exception as e:
        result.homepage_error = str(e)
        result.discovered_at = datetime.now(timezone.utc).isoformat()
        return result

    # Extract navigation links
    links = extract_navigation_links(html, result.website)
    print(f"  Found {len(links)} navigation links")

    # Match URLs for each type
    result.portfolio = match_url_to_type(links, "portfolio")
    result.team = match_url_to_type(links, "team")
    result.news = match_url_to_type(links, "news")

    # Fall back to pattern-based URLs if not found
    if not result.portfolio:
        patterns = generate_pattern_urls(result.website, "portfolio")
        if patterns:
            result.portfolio = patterns[0]  # Use first pattern

    if not result.team:
        patterns = generate_pattern_urls(result.website, "team")
        if patterns:
            result.team = patterns[0]

    if not result.news:
        patterns = generate_pattern_urls(result.website, "news")
        if patterns:
            result.news = patterns[0]

    result.discovered_at = datetime.now(timezone.utc).isoformat()
    return result


async def run_discovery(
    limit: int | None = None,
    fund_id: str | None = None,
) -> dict:
    """Run URL discovery on all funds."""

    # Load fund database
    with open(DB_FILE) as f:
        db = json.load(f)

    funds = db.get("funds", [])
    print(f"Loaded {len(funds)} funds from database")

    # Filter to specific fund if requested
    if fund_id:
        funds = [f for f in funds if f["id"] == fund_id]
        if not funds:
            print(f"Fund not found: {fund_id}")
            return {}

    # Sort by AUM (prioritize larger funds)
    funds.sort(key=lambda f: f.get("aum_eur") or 0, reverse=True)

    if limit:
        funds = funds[:limit]
        print(f"Limited to {len(funds)} funds")

    # Load existing results
    existing = {}
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            existing = json.load(f)

    results = existing.copy()

    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright not available")
        return results

    async with PlaywrightFetcher() as fetcher:
        for i, fund in enumerate(funds):
            print(f"\n[{i+1}/{len(funds)}] {fund['name']} ({fund['id']})")

            try:
                fund_urls = await discover_fund_urls(fetcher, fund)

                # Convert to dict for JSON
                url_dict = {
                    "fund_name": fund_urls.fund_name,
                    "website": fund_urls.website,
                }

                if fund_urls.portfolio:
                    url_dict["portfolio"] = fund_urls.portfolio.url
                    url_dict["portfolio_confidence"] = fund_urls.portfolio.confidence
                    url_dict["portfolio_source"] = fund_urls.portfolio.source

                if fund_urls.team:
                    url_dict["team"] = fund_urls.team.url
                    url_dict["team_confidence"] = fund_urls.team.confidence
                    url_dict["team_source"] = fund_urls.team.source

                if fund_urls.news:
                    url_dict["news"] = fund_urls.news.url
                    url_dict["news_confidence"] = fund_urls.news.confidence
                    url_dict["news_source"] = fund_urls.news.source

                if fund_urls.needs_scroll:
                    url_dict["needs_scroll"] = True

                if fund_urls.homepage_error:
                    url_dict["error"] = fund_urls.homepage_error

                url_dict["discovered_at"] = fund_urls.discovered_at

                results[fund["id"]] = url_dict

                # Show discovered URLs
                if fund_urls.portfolio:
                    print(f"  Portfolio: {fund_urls.portfolio.url} ({fund_urls.portfolio.source})")
                if fund_urls.team:
                    print(f"  Team: {fund_urls.team.url} ({fund_urls.team.source})")
                if fund_urls.news:
                    print(f"  News: {fund_urls.news.url} ({fund_urls.news.source})")
                if fund_urls.homepage_error:
                    print(f"  Error: {fund_urls.homepage_error}")

                # Save progress
                OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(OUTPUT_FILE, "w") as f:
                    json.dump(results, f, indent=2)

            except Exception as e:
                print(f"  ERROR: {e}")

    return results


def print_summary(results: dict):
    """Print discovery summary."""
    total = len(results)
    with_portfolio = sum(1 for r in results.values() if r.get("portfolio"))
    with_team = sum(1 for r in results.values() if r.get("team"))
    with_news = sum(1 for r in results.values() if r.get("news"))
    with_error = sum(1 for r in results.values() if r.get("error"))

    print("\n" + "=" * 60)
    print("URL DISCOVERY SUMMARY")
    print("=" * 60)
    print(f"Total funds: {total}")
    print(f"With portfolio URL: {with_portfolio} ({100*with_portfolio/total:.1f}%)")
    print(f"With team URL: {with_team} ({100*with_team/total:.1f}%)")
    print(f"With news URL: {with_news} ({100*with_news/total:.1f}%)")
    print(f"With errors: {with_error} ({100*with_error/total:.1f}%)")
    print(f"\nResults saved to: {OUTPUT_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Discover URLs for fund websites")
    parser.add_argument("--limit", type=int, help="Limit number of funds")
    parser.add_argument("--fund-id", help="Discover URLs for specific fund")
    args = parser.parse_args()

    print("=" * 60)
    print("Fundradar URL Discovery")
    print("=" * 60)

    results = asyncio.run(run_discovery(
        limit=args.limit,
        fund_id=args.fund_id,
    ))

    if results:
        print_summary(results)


if __name__ == "__main__":
    main()
