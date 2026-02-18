#!/usr/bin/env python3
"""
Extraction quality test suite for Fundradar scrapers.

Tests portfolio, team, and news extraction across priority sites
and generates quality scores.

Usage:
    python test_extractors.py
    python test_extractors.py --fund 21invest
    python test_extractors.py --type portfolio
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fundradar_worker.strategy_orchestrator import StrategyOrchestrator
from fundradar_worker.playwright_fetcher import PlaywrightFetcher, FetchOptions
from fundradar_worker.detail_page_fetcher import DetailPageFetcher
from fundradar_worker.strategies.site_specific import get_site_extractor

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Max companies to enrich per fund (for faster testing)
MAX_DETAIL_PAGE_ENRICHMENTS = 10


# Test configurations for priority sites
TEST_SITES = {
    "21invest": {
        "portfolio": "https://www.21invest.com/en/investments/",
        "team": "https://www.21invest.com/en/who-we-are/",  # Correct URL
        "needs_scroll": True,  # Both portfolio and team need scrolling
        "team_needs_scroll": True,
    },
    "fondo-italiano-d-investimento-sgr": {
        "portfolio": "https://www.fondoitaliano.it/investimenti/",
        "team": "https://www.fondoitaliano.it/persone/",  # Correct URL
        "news": "https://www.fondoitaliano.it/press/",
    },
    "alcedo-sgr": {
        "portfolio": "https://www.alcedo.it/fondi_private_equity/",
        "team": "https://www.alcedo.it/team_alcedo_sgr/",  # Correct URL
        "news": "https://www.alcedo.it/news/",
    },
    "progressio-sgr": {
        "portfolio": "https://www.progressiosgr.it/investments/",
        "team": "https://www.progressiosgr.it/team/",
        "news": "https://www.progressiosgr.it/news/",
    },
    "greenarrow": {
        "portfolio": "https://www.greenarrow-capital.com/investimenti/",
        "team": "https://www.greenarrow-capital.com/top-management/",
        "news": "https://www.greenarrow-capital.com/media/",
    },
    "clessidra-sgr": {
        "team": "https://www.clessidragroup.it/gruppo/team/",
        "portfolio": "https://www.clessidragroup.it/soluzioni/private-equity/fondi-investimenti/",
        "news": "https://www.clessidragroup.it/news/",
        "needs_scroll": True,
        "team_needs_scroll": True,
    },
    # === Priority Italian funds (Phase 3 - Discovered URLs) ===
    "investindustrial": {
        "portfolio": "https://www.investindustrial.com/our-business/portfolio-overview.html",
        "team": "https://www.investindustrial.com/who-we-are/People-1.html",
        "news": "https://www.investindustrial.com/publications/news.html",
    },
    "ambienta": {
        "portfolio": "https://ambientasgr.com/our-businesses/private-equity/portfolio/",
        "team": "https://ambientasgr.com/firm/team/",
        "news": "https://ambientasgr.com/search-press/type:press-coverage,press-releases/",
    },
    "cdp_venture_capital": {
        "portfolio": "https://www.cdpventurecapital.it/it/portfolio.page",
        "team": "https://www.cdpventurecapital.it/it/management.page",
        "news": "https://www.cdpventurecapital.it/it/newsroom.page",
    },
    "fsi": {
        "portfolio": "https://www.fondofsi.it/investimenti-3/",
        "team": "https://www.fondofsi.it/persone/",
        "news": "https://www.fondofsi.it/media/",
    },
    "dea_capital": {
        "portfolio": "https://www.deacapitalaf.com/investimenti/",
        "team": "https://www.deacapitalaf.com/people/team/management-team/",
        "news": "https://www.deacapitalaf.com/media/?lang=en",
    },
    "quadrivio": {
        "portfolio": "https://www.quadriviogroup.com/en/funds/lifestyle-fund/portfolio",
        "team": "https://www.quadriviogroup.com/it/about/people",
        "news": "https://www.quadriviogroup.com/en/media/press-review/lifestyle-fund",
    },
    "charme": {
        "portfolio": "https://charmecapitalpartners.com/funds",
        "team": "https://charmecapitalpartners.com/our-structure",
        "news": "https://charmecapitalpartners.com/news",
        "needs_scroll": True,
    },
    "palladio": {
        "portfolio": "https://www.pfh.eu/private-equity/",
        "team": "https://www.pfh.eu/team/",
        "news": "https://www.pfh.eu/mediapress/",
        "needs_headless": True,  # Site returns 403 without proper browser emulation
        "skip_for_now": True,  # Skip until headless mode implemented
    },
    "wise": {
        "portfolio": "https://www.wisesgr.com/en/investimenti",
        "team": "https://www.wisesgr.com/en/team",
        "news": "https://www.wisesgr.com/en/news",
    },
    "style_capital": {
        "portfolio": "https://www.stylecapital.it/style_capital_investimenti.php?lingua=1",
        "team": "https://www.stylecapital.it/chi_siamo_team.php?lingua=1",
    },
    # === Additional priority funds ===
    "oakley-capital": {
        "portfolio": "https://www.oakleycapital.com/our-companies/",
        "team": "https://www.oakleycapital.com/team/",
        "news": "https://www.oakleycapital.com/news-and-insights/",
        "needs_headless": True,  # Complex JS rendering
    },
    "alto_partners": {
        "portfolio": "https://www.altopartners.it/en/portfolio/",
        "team": "https://www.altopartners.it/en/team/",
    },
    "anthilia": {
        "portfolio": "https://privatecapital.anthilia.it/en/companies/",
        "team": "https://anthilia.it/en/anthilia/team-anthilia/",
        "news": "https://anthilia.it/en/category/news/",
    },
    "azimut_libera": {
        "portfolio": "https://www.azimutliberaimpresa.it/investimenti",
        "team": "https://www.azimutliberaimpresa.it/team",
    },
    "aksìa": {
        "portfolio": "https://aksiasgr.com/portfolio/",
        "team": "https://aksiasgr.com/team/",
        "news": "https://aksiasgr.com/insights/",
    },
}


@dataclass
class ExtractionResult:
    fund: str
    data_type: Literal["portfolio", "team", "news"]
    total_items: int
    high_confidence: int  # > 0.8
    medium_confidence: int  # 0.5 - 0.8
    low_confidence: int  # < 0.5
    quality_score: float
    items: list[dict] = field(default_factory=list)
    error: str | None = None


def calculate_quality_score(
    total: int,
    high_conf: int,
    medium_conf: int,
    low_conf: int,
    extras: dict | None = None,
) -> float:
    """
    Calculate quality score based on:
    - Base: confidence distribution (high=1.0, medium=0.7, low=0.3)
    - Bonus: rich data fields (sector, website, description for portfolio)
    """
    if total == 0:
        return 0.0

    # Base score from confidence
    conf_score = (high_conf * 1.0 + medium_conf * 0.7 + low_conf * 0.3) / total

    # Bonus for rich data
    bonus = 0.0
    if extras:
        # Portfolio bonuses
        with_sector = extras.get("with_sector", 0)
        with_website = extras.get("with_website", 0)
        with_description = extras.get("with_description", 0)

        if total > 0:
            sector_ratio = with_sector / total
            website_ratio = with_website / total
            desc_ratio = with_description / total
            bonus = (sector_ratio * 0.1 + website_ratio * 0.05 + desc_ratio * 0.05)

        # Team bonuses
        with_title = extras.get("with_title", 0)
        with_photo = extras.get("with_photo", 0)
        if total > 0:
            title_ratio = with_title / total
            photo_ratio = with_photo / total
            bonus += (title_ratio * 0.1 + photo_ratio * 0.05)

        # News bonuses
        with_url = extras.get("with_url", 0)
        with_date = extras.get("with_date", 0)
        with_deal_type = extras.get("with_deal_type", 0)
        if total > 0:
            url_ratio = with_url / total
            date_ratio = with_date / total
            deal_ratio = with_deal_type / total
            bonus += (url_ratio * 0.05 + date_ratio * 0.05 + deal_ratio * 0.1)

    return min(100.0, (conf_score * 80 + bonus * 100))


async def test_extraction(
    fund: str,
    data_type: str,
    url: str,
    needs_scroll: bool = False,
    enrich_details: bool = True,
) -> ExtractionResult:
    """Test extraction for a single fund/type combination."""
    orchestrator = StrategyOrchestrator()

    # Fetch the page
    options = FetchOptions(
        scroll_to_bottom=needs_scroll,
        max_scrolls=25 if needs_scroll else 0,
        scroll_pause_ms=1000 if needs_scroll else 0,
        wait_for_network_idle=True,
    )

    async with PlaywrightFetcher() as fetcher:
        result = await fetcher.fetch(url, options=options)

        if result.error or not result.html:
            return ExtractionResult(
                fund=fund,
                data_type=data_type,
                total_items=0,
                high_confidence=0,
                medium_confidence=0,
                low_confidence=0,
                quality_score=0.0,
                error=result.error or "No HTML content",
            )

        html = result.html
        print(f"  Fetched {len(html)} bytes")

    # Extract based on type
    items = []
    extras = {}

    if data_type == "portfolio":
        companies = orchestrator.extract_portfolio(html, url)
        print(f"  Found {len(companies)} portfolio companies")

        # Enrich with detail pages if enabled
        if enrich_details:
            companies_with_details = [c for c in companies if c.detail_page_url]
            if companies_with_details:
                print(f"  Enriching {min(len(companies_with_details), MAX_DETAIL_PAGE_ENRICHMENTS)} companies with detail pages...")
                detail_fetcher = DetailPageFetcher(use_playwright=True, max_concurrent=3)

                # Register site-specific extractors
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower()
                detail_extractor = get_site_extractor(domain, "company_detail")
                if detail_extractor:
                    detail_fetcher.register_extractor(domain, detail_extractor)

                # Limit enrichment for testing speed
                to_enrich = companies_with_details[:MAX_DETAIL_PAGE_ENRICHMENTS]
                try:
                    await detail_fetcher.enrich_portfolio(to_enrich, url, max_concurrent=3)
                finally:
                    await detail_fetcher.cleanup()

                enriched_count = sum(1 for c in to_enrich if c.sector or c.description or c.website)
                print(f"  Enriched {enriched_count} companies with additional data")

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
        extras = {
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
                "linkedin": m.linkedin,
                "confidence": m.confidence,
            }
            for m in members
        ]
        extras = {
            "with_title": sum(1 for m in members if m.title),
            "with_linkedin": sum(1 for m in members if m.linkedin),
            "with_photo": sum(1 for m in members if m.photo_url),
        }
        print(f"  Found {len(items)} team members")

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
        extras = {
            "with_url": sum(1 for n in news if n.url),
            "with_date": sum(1 for n in news if n.date),
            "with_deal_type": sum(1 for n in news if n.deal_type),
        }
        print(f"  Found {len(items)} news items")

    # Calculate confidence distribution
    high_conf = sum(1 for i in items if i.get("confidence", 0) > 0.8)
    medium_conf = sum(1 for i in items if 0.5 <= i.get("confidence", 0) <= 0.8)
    low_conf = sum(1 for i in items if i.get("confidence", 0) < 0.5)

    quality = calculate_quality_score(
        len(items), high_conf, medium_conf, low_conf, extras
    )
    print(f"  Quality Score: {quality:.1f}/100")

    return ExtractionResult(
        fund=fund,
        data_type=data_type,
        total_items=len(items),
        high_confidence=high_conf,
        medium_confidence=medium_conf,
        low_confidence=low_conf,
        quality_score=quality,
        items=items[:10],  # Store first 10 for review
    )


async def run_tests(
    funds: list[str] | None = None,
    types: list[str] | None = None,
) -> dict:
    """Run all extraction tests."""
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "portfolio": [],
        "team": [],
        "news": [],
    }

    funds_to_test = funds or list(TEST_SITES.keys())
    types_to_test = types or ["portfolio", "team", "news"]

    for fund in funds_to_test:
        if fund not in TEST_SITES:
            print(f"Unknown fund: {fund}")
            continue

        config = TEST_SITES[fund]

        for data_type in types_to_test:
            if data_type not in config:
                continue

            url = config[data_type]
            if data_type == "portfolio":
                needs_scroll = config.get("needs_scroll", False)
            elif data_type == "team":
                needs_scroll = config.get("team_needs_scroll", False)
            else:
                needs_scroll = False

            print(f"\n[{fund}] Testing {data_type} extraction...")

            try:
                result = await test_extraction(fund, data_type, url, needs_scroll)

                # Convert to dict for JSON
                result_dict = {
                    "fund": result.fund,
                    "total_companies" if data_type == "portfolio" else "total_members" if data_type == "team" else "total_items": result.total_items,
                    "high_confidence": result.high_confidence,
                    "medium_confidence": result.medium_confidence,
                    "low_confidence": result.low_confidence,
                }

                # Add type-specific fields
                if data_type == "portfolio":
                    result_dict["with_sector"] = sum(1 for i in result.items if i.get("sector"))
                    result_dict["with_website"] = sum(1 for i in result.items if i.get("website"))
                    result_dict["with_description"] = 0  # From extras
                    result_dict["current"] = sum(1 for i in result.items if i.get("status") == "current")
                    result_dict["exited"] = sum(1 for i in result.items if i.get("status") == "exited")
                    result_dict["companies"] = result.items
                elif data_type == "team":
                    result_dict["with_title"] = sum(1 for i in result.items if i.get("title"))
                    result_dict["with_linkedin"] = sum(1 for i in result.items if i.get("linkedin"))
                    result_dict["with_photo"] = 0  # From original extraction
                    result_dict["members"] = result.items
                elif data_type == "news":
                    result_dict["with_url"] = sum(1 for i in result.items if i.get("url"))
                    result_dict["with_date"] = sum(1 for i in result.items if i.get("date"))
                    result_dict["with_deal_type"] = sum(1 for i in result.items if i.get("deal_type"))
                    result_dict["items"] = result.items

                result_dict["quality_score"] = result.quality_score

                if result.error:
                    result_dict["error"] = result.error

                results[data_type].append(result_dict)

            except Exception as e:
                print(f"  Error: {e}")
                results[data_type].append({
                    "fund": fund,
                    "error": str(e),
                    "quality_score": 0.0,
                })

    # Calculate summary
    portfolio_scores = [r["quality_score"] for r in results["portfolio"] if r.get("quality_score")]
    team_scores = [r["quality_score"] for r in results["team"] if r.get("quality_score")]
    news_scores = [r["quality_score"] for r in results["news"] if r.get("quality_score")]

    results["summary"] = {
        "portfolio_avg_quality": round(sum(portfolio_scores) / len(portfolio_scores), 1) if portfolio_scores else 0,
        "team_avg_quality": round(sum(team_scores) / len(team_scores), 1) if team_scores else 0,
        "news_avg_quality": round(sum(news_scores) / len(news_scores), 1) if news_scores else 0,
        "overall_quality": round(
            (sum(portfolio_scores) + sum(team_scores) + sum(news_scores)) /
            (len(portfolio_scores) + len(team_scores) + len(news_scores))
            if (portfolio_scores or team_scores or news_scores) else 0,
            1
        ),
    }

    return results


def main():
    parser = argparse.ArgumentParser(description="Test extraction quality")
    parser.add_argument("--fund", help="Test specific fund only")
    parser.add_argument("--type", choices=["portfolio", "team", "news"], help="Test specific type only")
    parser.add_argument("--output", default="../../data/derived/extraction_test_results.json", help="Output file")
    args = parser.parse_args()

    funds = [args.fund] if args.fund else None
    types = [args.type] if args.type else None

    print("=" * 60)
    print("Fundradar Extraction Quality Tests")
    print("=" * 60)

    results = asyncio.run(run_tests(funds, types))

    # Save results
    output_path = Path(__file__).parent / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Portfolio Average Quality: {results['summary']['portfolio_avg_quality']}%")
    print(f"Team Average Quality:      {results['summary']['team_avg_quality']}%")
    print(f"News Average Quality:      {results['summary']['news_avg_quality']}%")
    print(f"Overall Quality:           {results['summary']['overall_quality']}%")
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
