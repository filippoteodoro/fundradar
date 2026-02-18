#!/usr/bin/env python3
"""
Bulk extraction tester for all Fundradar funds.

Tests extraction quality across all funds in db.json using generic extractors
and categorizes results for prioritized improvement.

Usage:
    python bulk_extraction_tester.py
    python bulk_extraction_tester.py --limit 20
    python bulk_extraction_tester.py --category pe
    python bulk_extraction_tester.py --resume
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse, urljoin
import re

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fundradar_worker.strategy_orchestrator import StrategyOrchestrator
from fundradar_worker.playwright_fetcher import PlaywrightFetcher, FetchOptions, PLAYWRIGHT_AVAILABLE
from fundradar_worker.strategies.site_specific import get_site_extractor

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DB_FILE = DATA_DIR / "db.json"
OUTPUT_FILE = DATA_DIR / "derived" / "fund_extraction_audit.json"
URLS_FILE = DATA_DIR / "site_configs" / "fund_urls.json"

# Common URL patterns for fund websites
URL_PATTERNS = {
    "portfolio": [
        "/portfolio", "/investments", "/investimenti", "/companies",
        "/portfolio-companies", "/our-companies", "/aziende",
        "/portafoglio", "/le-nostre-aziende", "/participations",
        "/partecipazioni", "/fondi-investimenti", "/equity-investments"
    ],
    "team": [
        "/team", "/people", "/chi-siamo", "/about-us", "/about",
        "/our-team", "/the-team", "/il-team", "/la-squadra",
        "/persone", "/professionisti", "/who-we-are", "/management"
    ],
    "news": [
        "/news", "/media", "/press", "/comunicati", "/rassegna-stampa",
        "/press-releases", "/newsroom", "/notizie", "/comunicati-stampa",
        "/media-room", "/updates", "/insights"
    ]
}

# Timeout settings
FETCH_TIMEOUT = 30000  # 30 seconds
DISCOVERY_TIMEOUT = 20000  # 20 seconds for homepage

# Quality thresholds
EXCELLENT_THRESHOLD = 85.0
GOOD_THRESHOLD = 60.0


@dataclass
class DiscoveredUrls:
    """URLs discovered for a fund."""
    portfolio: str | None = None
    team: str | None = None
    news: str | None = None
    homepage_ok: bool = False
    discovery_error: str | None = None


@dataclass
class ExtractionQuality:
    """Quality metrics for one extraction type."""
    url: str | None = None
    total_items: int = 0
    high_confidence: int = 0
    medium_confidence: int = 0
    low_confidence: int = 0
    quality_score: float = 0.0
    sample_items: list = field(default_factory=list)
    error: str | None = None
    extras: dict = field(default_factory=dict)


@dataclass
class FundAuditResult:
    """Full audit result for a fund."""
    fund_id: str
    fund_name: str
    website: str | None
    category: str
    aum_eur: int | None
    urls: DiscoveredUrls = field(default_factory=DiscoveredUrls)
    portfolio: ExtractionQuality = field(default_factory=ExtractionQuality)
    team: ExtractionQuality = field(default_factory=ExtractionQuality)
    news: ExtractionQuality = field(default_factory=ExtractionQuality)
    overall_score: float = 0.0
    status: str = "pending"  # pending, excellent, good, needs_work, blocked, no_website
    tested_at: str | None = None


def calculate_quality_score(
    total: int,
    high_conf: int,
    medium_conf: int,
    low_conf: int,
    extras: dict | None = None,
) -> float:
    """Calculate quality score (0-100) based on confidence and data richness."""
    if total == 0:
        return 0.0

    # Base score from confidence distribution
    conf_score = (high_conf * 1.0 + medium_conf * 0.7 + low_conf * 0.3) / total

    # Bonus for rich data fields
    bonus = 0.0
    if extras and total > 0:
        # Portfolio bonuses
        with_sector = extras.get("with_sector", 0)
        with_website = extras.get("with_website", 0)
        with_description = extras.get("with_description", 0)
        sector_ratio = with_sector / total
        website_ratio = with_website / total
        desc_ratio = with_description / total
        bonus += (sector_ratio * 0.1 + website_ratio * 0.05 + desc_ratio * 0.05)

        # Team bonuses
        with_title = extras.get("with_title", 0)
        with_photo = extras.get("with_photo", 0)
        title_ratio = with_title / total
        photo_ratio = with_photo / total
        bonus += (title_ratio * 0.1 + photo_ratio * 0.05)

        # News bonuses
        with_url = extras.get("with_url", 0)
        with_date = extras.get("with_date", 0)
        with_deal_type = extras.get("with_deal_type", 0)
        url_ratio = with_url / total
        date_ratio = with_date / total
        deal_ratio = with_deal_type / total
        bonus += (url_ratio * 0.05 + date_ratio * 0.05 + deal_ratio * 0.1)

    return min(100.0, conf_score * 80 + bonus * 100)


def categorize_fund(result: FundAuditResult) -> str:
    """Categorize fund based on extraction quality."""
    if not result.website:
        return "no_website"

    if not result.urls.homepage_ok:
        return "blocked"

    # Calculate overall score from available extractions
    scores = []
    if result.portfolio.total_items > 0:
        scores.append(result.portfolio.quality_score)
    if result.team.total_items > 0:
        scores.append(result.team.quality_score)
    if result.news.total_items > 0:
        scores.append(result.news.quality_score)

    if not scores:
        return "blocked"  # No data extracted

    avg_score = sum(scores) / len(scores)
    result.overall_score = round(avg_score, 1)

    if avg_score >= EXCELLENT_THRESHOLD:
        return "excellent"
    elif avg_score >= GOOD_THRESHOLD:
        return "good"
    else:
        return "needs_work"


async def discover_urls(
    fetcher: PlaywrightFetcher,
    website: str,
) -> DiscoveredUrls:
    """Discover portfolio/team/news URLs from fund homepage."""
    result = DiscoveredUrls()

    try:
        # Fetch homepage
        options = FetchOptions(
            wait_for_network_idle=True,
            network_idle_timeout=DISCOVERY_TIMEOUT,
        )
        fetch_result = await fetcher.fetch(website, options=options)

        if fetch_result.error:
            result.discovery_error = fetch_result.error
            return result

        if not fetch_result.html:
            result.discovery_error = "No HTML content"
            return result

        result.homepage_ok = True
        html = fetch_result.html.lower()

        # Parse base URL
        parsed = urlparse(website)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Find links in HTML
        link_pattern = r'href=["\']([^"\']+)["\']'
        links = re.findall(link_pattern, html)

        # Match against URL patterns
        for link in links:
            normalized = link.lower().rstrip('/')

            # Check portfolio patterns
            if not result.portfolio:
                for pattern in URL_PATTERNS["portfolio"]:
                    if pattern in normalized:
                        if link.startswith('http'):
                            result.portfolio = link
                        else:
                            result.portfolio = urljoin(base_url, link)
                        break

            # Check team patterns
            if not result.team:
                for pattern in URL_PATTERNS["team"]:
                    if pattern in normalized:
                        if link.startswith('http'):
                            result.team = link
                        else:
                            result.team = urljoin(base_url, link)
                        break

            # Check news patterns
            if not result.news:
                for pattern in URL_PATTERNS["news"]:
                    if pattern in normalized:
                        if link.startswith('http'):
                            result.news = link
                        else:
                            result.news = urljoin(base_url, link)
                        break

        # Try common URL patterns directly if not found via links
        if not result.portfolio:
            for pattern in URL_PATTERNS["portfolio"][:3]:  # Try top 3 patterns
                test_url = urljoin(base_url, pattern)
                # We'll test this URL exists in the extraction phase
                result.portfolio = test_url
                break

        if not result.team:
            for pattern in URL_PATTERNS["team"][:3]:
                test_url = urljoin(base_url, pattern)
                result.team = test_url
                break

    except Exception as e:
        result.discovery_error = str(e)

    return result


async def test_extraction_type(
    fetcher: PlaywrightFetcher,
    orchestrator: StrategyOrchestrator,
    url: str,
    data_type: Literal["portfolio", "team", "news"],
    fund_id: str,
) -> ExtractionQuality:
    """Test extraction for a specific data type."""
    result = ExtractionQuality(url=url)

    try:
        options = FetchOptions(
            wait_for_network_idle=True,
            network_idle_timeout=FETCH_TIMEOUT,
        )
        fetch_result = await fetcher.fetch(url, options=options)

        if fetch_result.error:
            result.error = fetch_result.error
            return result

        if not fetch_result.html:
            result.error = "No HTML content"
            return result

        html = fetch_result.html

        # Extract based on type
        if data_type == "portfolio":
            companies = orchestrator.extract_portfolio(html, url)
            items = [
                {
                    "name": c.name,
                    "sector": c.sector,
                    "website": c.website,
                    "status": c.status,
                    "confidence": c.confidence,
                }
                for c in companies
            ]
            result.extras = {
                "with_sector": sum(1 for c in companies if c.sector),
                "with_website": sum(1 for c in companies if c.website),
                "with_description": sum(1 for c in companies if c.description),
            }

        elif data_type == "team":
            members = orchestrator.extract_team(html, url)
            items = [
                {
                    "name": m.name,
                    "title": m.title,
                    "role": m.role,
                    "confidence": m.confidence,
                }
                for m in members
            ]
            result.extras = {
                "with_title": sum(1 for m in members if m.title),
                "with_photo": sum(1 for m in members if m.photo_url),
                "with_linkedin": sum(1 for m in members if m.linkedin),
            }

        elif data_type == "news":
            news = orchestrator.extract_news(html, url)
            items = [
                {
                    "title": n.title,
                    "url": n.url,
                    "date": n.date,
                    "deal_type": n.deal_type,
                    "confidence": n.confidence,
                }
                for n in news
            ]
            result.extras = {
                "with_url": sum(1 for n in news if n.url),
                "with_date": sum(1 for n in news if n.date),
                "with_deal_type": sum(1 for n in news if n.deal_type),
            }

        # Calculate confidence distribution
        result.total_items = len(items)
        result.high_confidence = sum(1 for i in items if i.get("confidence", 0) > 0.8)
        result.medium_confidence = sum(1 for i in items if 0.5 <= i.get("confidence", 0) <= 0.8)
        result.low_confidence = sum(1 for i in items if i.get("confidence", 0) < 0.5)
        result.sample_items = items[:5]  # Store first 5 for review

        result.quality_score = calculate_quality_score(
            result.total_items,
            result.high_confidence,
            result.medium_confidence,
            result.low_confidence,
            result.extras,
        )

    except Exception as e:
        result.error = str(e)

    return result


async def audit_fund(
    fetcher: PlaywrightFetcher,
    orchestrator: StrategyOrchestrator,
    fund: dict,
    skip_discovery: bool = False,
    known_urls: dict | None = None,
) -> FundAuditResult:
    """Run full extraction audit for a single fund."""
    result = FundAuditResult(
        fund_id=fund["id"],
        fund_name=fund["name"],
        website=fund.get("website"),
        category=fund.get("category", "unknown"),
        aum_eur=fund.get("aum_eur"),
    )

    if not result.website:
        result.status = "no_website"
        result.tested_at = datetime.now(timezone.utc).isoformat()
        return result

    # Use known URLs if provided, otherwise discover
    if known_urls and fund["id"] in known_urls:
        urls = known_urls[fund["id"]]
        result.urls = DiscoveredUrls(
            portfolio=urls.get("portfolio"),
            team=urls.get("team"),
            news=urls.get("news"),
            homepage_ok=True,
        )
    elif not skip_discovery:
        print(f"  Discovering URLs...")
        result.urls = await discover_urls(fetcher, result.website)
    else:
        result.urls = DiscoveredUrls(homepage_ok=False, discovery_error="Skipped")

    if not result.urls.homepage_ok:
        result.status = "blocked"
        result.tested_at = datetime.now(timezone.utc).isoformat()
        return result

    # Test each extraction type
    if result.urls.portfolio:
        print(f"  Testing portfolio: {result.urls.portfolio}")
        result.portfolio = await test_extraction_type(
            fetcher, orchestrator, result.urls.portfolio, "portfolio", fund["id"]
        )
        print(f"    Found {result.portfolio.total_items} companies (score: {result.portfolio.quality_score:.1f})")

    if result.urls.team:
        print(f"  Testing team: {result.urls.team}")
        result.team = await test_extraction_type(
            fetcher, orchestrator, result.urls.team, "team", fund["id"]
        )
        print(f"    Found {result.team.total_items} members (score: {result.team.quality_score:.1f})")

    if result.urls.news:
        print(f"  Testing news: {result.urls.news}")
        result.news = await test_extraction_type(
            fetcher, orchestrator, result.urls.news, "news", fund["id"]
        )
        print(f"    Found {result.news.total_items} items (score: {result.news.quality_score:.1f})")

    # Categorize result
    result.status = categorize_fund(result)
    result.tested_at = datetime.now(timezone.utc).isoformat()

    return result


def load_existing_results() -> dict:
    """Load existing audit results for resuming."""
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            return json.load(f)
    return {}


def load_known_urls() -> dict:
    """Load pre-configured URLs from fund_urls.json."""
    if URLS_FILE.exists():
        with open(URLS_FILE) as f:
            return json.load(f)
    return {}


async def run_bulk_audit(
    limit: int | None = None,
    category: str | None = None,
    resume: bool = False,
    min_aum: int | None = None,
) -> dict:
    """Run bulk extraction audit on all funds."""

    # Load fund database
    with open(DB_FILE) as f:
        db = json.load(f)

    funds = db.get("funds", [])
    print(f"Loaded {len(funds)} funds from database")

    # Filter by category if specified
    if category:
        funds = [f for f in funds if f.get("category") == category]
        print(f"Filtered to {len(funds)} {category} funds")

    # Filter by minimum AUM if specified
    if min_aum:
        funds = [f for f in funds if (f.get("aum_eur") or 0) >= min_aum]
        print(f"Filtered to {len(funds)} funds with AUM >= €{min_aum:,}")

    # Sort by AUM descending (prioritize larger funds)
    funds.sort(key=lambda f: f.get("aum_eur") or 0, reverse=True)

    # Apply limit
    if limit:
        funds = funds[:limit]
        print(f"Limited to {len(funds)} funds")

    # Load existing results if resuming
    existing_results = {}
    if resume:
        existing_results = load_existing_results()
        completed_ids = set(existing_results.get("funds", {}).keys())
        funds = [f for f in funds if f["id"] not in completed_ids]
        print(f"Resuming: {len(completed_ids)} already done, {len(funds)} remaining")

    # Load known URLs
    known_urls = load_known_urls()

    # Results structure
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_tested": 0,
        "funds": existing_results.get("funds", {}),
        "summary": {
            "excellent": [],
            "good": [],
            "needs_work": [],
            "blocked": [],
            "no_website": [],
        },
        "stats": {
            "portfolio_avg_quality": 0.0,
            "team_avg_quality": 0.0,
            "news_avg_quality": 0.0,
            "overall_avg_quality": 0.0,
        },
    }

    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright not available. Please install with: pip install playwright && playwright install")
        return results

    orchestrator = StrategyOrchestrator()

    async with PlaywrightFetcher() as fetcher:
        for i, fund in enumerate(funds):
            print(f"\n[{i+1}/{len(funds)}] {fund['name']} ({fund['id']})")

            try:
                audit_result = await audit_fund(
                    fetcher, orchestrator, fund,
                    known_urls=known_urls,
                )

                # Store result
                results["funds"][fund["id"]] = asdict(audit_result)
                results["total_tested"] = len(results["funds"])

                print(f"  Status: {audit_result.status} (score: {audit_result.overall_score})")

                # Save progress incrementally
                OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(OUTPUT_FILE, "w") as f:
                    json.dump(results, f, indent=2)

            except Exception as e:
                print(f"  ERROR: {e}")
                results["funds"][fund["id"]] = {
                    "fund_id": fund["id"],
                    "fund_name": fund["name"],
                    "status": "blocked",
                    "error": str(e),
                }

    # Calculate final summary
    for fund_id, audit in results["funds"].items():
        status = audit.get("status", "blocked")
        results["summary"][status].append(fund_id)

    # Calculate stats
    portfolio_scores = [
        r["portfolio"]["quality_score"]
        for r in results["funds"].values()
        if r.get("portfolio", {}).get("total_items", 0) > 0
    ]
    team_scores = [
        r["team"]["quality_score"]
        for r in results["funds"].values()
        if r.get("team", {}).get("total_items", 0) > 0
    ]
    news_scores = [
        r["news"]["quality_score"]
        for r in results["funds"].values()
        if r.get("news", {}).get("total_items", 0) > 0
    ]

    results["stats"] = {
        "portfolio_avg_quality": round(sum(portfolio_scores) / len(portfolio_scores), 1) if portfolio_scores else 0,
        "team_avg_quality": round(sum(team_scores) / len(team_scores), 1) if team_scores else 0,
        "news_avg_quality": round(sum(news_scores) / len(news_scores), 1) if news_scores else 0,
        "portfolio_count": len(portfolio_scores),
        "team_count": len(team_scores),
        "news_count": len(news_scores),
    }

    all_scores = portfolio_scores + team_scores + news_scores
    results["stats"]["overall_avg_quality"] = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0

    # Final save
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    return results


def print_summary(results: dict):
    """Print audit summary."""
    print("\n" + "=" * 70)
    print("BULK EXTRACTION AUDIT SUMMARY")
    print("=" * 70)

    summary = results.get("summary", {})
    stats = results.get("stats", {})

    print(f"\nTotal Funds Tested: {results.get('total_tested', 0)}")
    print(f"\nCategorization:")
    print(f"  Excellent (>85%):  {len(summary.get('excellent', []))} funds")
    print(f"  Good (60-85%):     {len(summary.get('good', []))} funds")
    print(f"  Needs Work (<60%): {len(summary.get('needs_work', []))} funds")
    print(f"  Blocked/Error:     {len(summary.get('blocked', []))} funds")
    print(f"  No Website:        {len(summary.get('no_website', []))} funds")

    print(f"\nQuality Scores:")
    print(f"  Portfolio Average: {stats.get('portfolio_avg_quality', 0)}% ({stats.get('portfolio_count', 0)} funds)")
    print(f"  Team Average:      {stats.get('team_avg_quality', 0)}% ({stats.get('team_count', 0)} funds)")
    print(f"  News Average:      {stats.get('news_avg_quality', 0)}% ({stats.get('news_count', 0)} funds)")
    print(f"  Overall Average:   {stats.get('overall_avg_quality', 0)}%")

    print(f"\nResults saved to: {OUTPUT_FILE}")

    # Show top needs_work funds by AUM
    if summary.get("needs_work"):
        print(f"\nTop 'needs_work' funds to prioritize:")
        needs_work_funds = [
            results["funds"][fid]
            for fid in summary["needs_work"]
            if fid in results["funds"]
        ]
        needs_work_funds.sort(key=lambda f: f.get("aum_eur") or 0, reverse=True)
        for fund in needs_work_funds[:10]:
            aum = fund.get("aum_eur") or 0
            aum_str = f"€{aum/1e6:.0f}M" if aum >= 1e6 else "N/A"
            print(f"  - {fund['fund_name']} ({aum_str}, score: {fund.get('overall_score', 0)})")


def main():
    global OUTPUT_FILE

    parser = argparse.ArgumentParser(description="Bulk extraction audit for all funds")
    parser.add_argument("--limit", type=int, help="Limit number of funds to test")
    parser.add_argument("--category", choices=["pe", "vc"], help="Filter by fund category")
    parser.add_argument("--min-aum", type=int, help="Minimum AUM in EUR to include")
    parser.add_argument("--resume", action="store_true", help="Resume from previous run")
    parser.add_argument("--output", help="Output file path")
    args = parser.parse_args()

    if args.output:
        OUTPUT_FILE = Path(args.output)

    print("=" * 70)
    print("Fundradar Bulk Extraction Audit")
    print("=" * 70)

    results = asyncio.run(run_bulk_audit(
        limit=args.limit,
        category=args.category,
        resume=args.resume,
        min_aum=args.min_aum,
    ))

    print_summary(results)


if __name__ == "__main__":
    main()
