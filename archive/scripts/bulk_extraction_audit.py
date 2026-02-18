#!/usr/bin/env python3
"""
Bulk extraction audit for all Fundradar funds.

Discovers URLs and tests extraction quality for all funds in db.json.
"""

import asyncio
import json
import logging
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).parent))

from fundradar_worker.playwright_fetcher import PlaywrightFetcher, FetchOptions
from fundradar_worker.strategy_orchestrator import StrategyOrchestrator
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# URL patterns to discover
PORTFOLIO_PATTERNS = [
    '/portfolio', '/investments', '/investimenti', '/companies',
    '/our-companies', '/partecipazioni', '/aziende', '/fondi',
    '/our-business/portfolio', '/invest/portfolio'
]
TEAM_PATTERNS = [
    '/team', '/people', '/chi-siamo', '/about-us', '/about',
    '/who-we-are', '/persone', '/management', '/leadership',
    '/our-team', '/the-team'
]
NEWS_PATTERNS = [
    '/news', '/media', '/press', '/comunicati', '/newsroom',
    '/press-releases', '/insights', '/publications'
]


@dataclass
class FundResult:
    fund_id: str
    fund_name: str
    website: str
    portfolio_url: str | None = None
    portfolio_count: int = 0
    portfolio_quality: float = 0.0
    team_url: str | None = None
    team_count: int = 0
    team_quality: float = 0.0
    news_url: str | None = None
    news_count: int = 0
    news_quality: float = 0.0
    overall_quality: float = 0.0
    error: str | None = None
    status: str = "pending"  # pending, success, partial, failed, blocked


def calculate_quality(total: int, high_conf: int, med_conf: int, low_conf: int) -> float:
    """Calculate quality score from confidence distribution."""
    if total == 0:
        return 0.0
    conf_score = (high_conf * 1.0 + med_conf * 0.7 + low_conf * 0.3) / total
    return min(100.0, conf_score * 80 + 10)  # Base 10 points for finding items


async def discover_urls(fetcher: PlaywrightFetcher, base_url: str) -> dict:
    """Discover portfolio, team, and news URLs from a fund's website."""
    result = {"portfolio": None, "team": None, "news": None}

    try:
        # Fetch homepage
        res = await fetcher.fetch(base_url, FetchOptions(wait_for_network_idle=True))
        if not res.html or res.error:
            return result

        # Check for 403/blocked
        if "403" in res.html[:1000] or "forbidden" in res.html[:1000].lower():
            return result

        soup = BeautifulSoup(res.html, "html.parser")

        # Find all links
        links = {}
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").lower()
            text = a.get_text(strip=True).lower()
            full_url = urljoin(base_url, a.get("href", ""))

            # Portfolio
            if not result["portfolio"]:
                for pattern in PORTFOLIO_PATTERNS:
                    if pattern in href or any(k in text for k in ["portfolio", "investment", "compan", "partecip"]):
                        result["portfolio"] = full_url
                        break

            # Team
            if not result["team"]:
                for pattern in TEAM_PATTERNS:
                    if pattern in href or any(k in text for k in ["team", "people", "chi siamo", "about us"]):
                        result["team"] = full_url
                        break

            # News
            if not result["news"]:
                for pattern in NEWS_PATTERNS:
                    if pattern in href or any(k in text for k in ["news", "press", "media", "comunicat"]):
                        result["news"] = full_url
                        break

        # Try common URL patterns if not found
        domain = urlparse(base_url).netloc
        base = f"https://{domain}"

        if not result["portfolio"]:
            for pattern in PORTFOLIO_PATTERNS[:4]:
                result["portfolio"] = base + pattern
                break

        if not result["team"]:
            for pattern in TEAM_PATTERNS[:4]:
                result["team"] = base + pattern
                break

    except Exception as e:
        logger.warning(f"Error discovering URLs for {base_url}: {e}")

    return result


async def test_extraction(fetcher: PlaywrightFetcher, orchestrator: StrategyOrchestrator,
                          url: str, data_type: str) -> tuple[int, float, int, int, int]:
    """Test extraction for a single URL. Returns (count, quality, high, med, low)."""
    try:
        res = await fetcher.fetch(url, FetchOptions(
            wait_for_network_idle=True,
            scroll_to_bottom=True,
            max_scrolls=10
        ))

        if not res.html or res.error:
            return 0, 0.0, 0, 0, 0

        # Check for error pages
        if "403" in res.html[:1000] or "404" in res.html[:1000]:
            return 0, 0.0, 0, 0, 0

        items = []
        if data_type == "portfolio":
            items = orchestrator.extract_portfolio(res.html, url)
        elif data_type == "team":
            items = orchestrator.extract_team(res.html, url)
        elif data_type == "news":
            items = orchestrator.extract_news(res.html, url)

        if not items:
            return 0, 0.0, 0, 0, 0

        # Calculate confidence distribution
        high = sum(1 for i in items if i.confidence > 0.8)
        med = sum(1 for i in items if 0.5 <= i.confidence <= 0.8)
        low = sum(1 for i in items if i.confidence < 0.5)

        quality = calculate_quality(len(items), high, med, low)

        return len(items), quality, high, med, low

    except Exception as e:
        logger.warning(f"Error testing {url}: {e}")
        return 0, 0.0, 0, 0, 0


async def process_fund(fetcher: PlaywrightFetcher, orchestrator: StrategyOrchestrator,
                       fund: dict) -> FundResult:
    """Process a single fund - discover URLs and test extraction."""
    result = FundResult(
        fund_id=fund["id"],
        fund_name=fund["name"],
        website=fund.get("website", "")
    )

    website = fund.get("website", "")
    if not website or website.startswith("mailto:") or website == "-":
        result.status = "failed"
        result.error = "No valid website"
        return result

    # Ensure https
    if not website.startswith("http"):
        website = "https://" + website
    elif website.startswith("http://"):
        website = website.replace("http://", "https://")

    result.website = website

    try:
        # Discover URLs
        urls = await discover_urls(fetcher, website)

        # Test portfolio
        if urls["portfolio"]:
            result.portfolio_url = urls["portfolio"]
            count, quality, _, _, _ = await test_extraction(
                fetcher, orchestrator, urls["portfolio"], "portfolio"
            )
            result.portfolio_count = count
            result.portfolio_quality = quality

        # Test team
        if urls["team"]:
            result.team_url = urls["team"]
            count, quality, _, _, _ = await test_extraction(
                fetcher, orchestrator, urls["team"], "team"
            )
            result.team_count = count
            result.team_quality = quality

        # Test news
        if urls["news"]:
            result.news_url = urls["news"]
            count, quality, _, _, _ = await test_extraction(
                fetcher, orchestrator, urls["news"], "news"
            )
            result.news_count = count
            result.news_quality = quality

        # Calculate overall quality
        scores = []
        if result.portfolio_quality > 0:
            scores.append(result.portfolio_quality)
        if result.team_quality > 0:
            scores.append(result.team_quality)
        if result.news_quality > 0:
            scores.append(result.news_quality)

        if scores:
            result.overall_quality = sum(scores) / len(scores)
            result.status = "success" if result.overall_quality >= 70 else "partial"
        else:
            result.status = "failed"
            result.error = "No data extracted"

    except Exception as e:
        result.status = "failed"
        result.error = str(e)[:100]

    return result


async def run_audit(funds: list[dict], max_concurrent: int = 3) -> list[FundResult]:
    """Run extraction audit on all funds."""
    results = []
    orchestrator = StrategyOrchestrator()

    async with PlaywrightFetcher() as fetcher:
        # Process in batches
        for i in range(0, len(funds), max_concurrent):
            batch = funds[i:i + max_concurrent]
            batch_num = i // max_concurrent + 1
            total_batches = (len(funds) + max_concurrent - 1) // max_concurrent

            print(f"\nBatch {batch_num}/{total_batches} - Processing {len(batch)} funds...")

            tasks = [process_fund(fetcher, orchestrator, fund) for fund in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    result = FundResult(
                        fund_id=batch[j]["id"],
                        fund_name=batch[j]["name"],
                        website=batch[j].get("website", ""),
                        status="failed",
                        error=str(result)[:100]
                    )

                results.append(result)

                # Print progress
                status_icon = "✓" if result.status == "success" else "◐" if result.status == "partial" else "✗"
                print(f"  {status_icon} {result.fund_name[:30]:<30} P:{result.portfolio_count:>3} T:{result.team_count:>3} N:{result.news_count:>3} Q:{result.overall_quality:>5.1f}%")

            # Small delay between batches
            await asyncio.sleep(1)

    return results


def main():
    # Load funds
    db_path = Path(__file__).parent.parent.parent / "data" / "db.json"
    with open(db_path) as f:
        db = json.load(f)

    all_funds = db["funds"]

    # Filter to funds with valid websites
    funds_to_test = [
        f for f in all_funds
        if f.get("website") and not f["website"].startswith("mailto:") and f["website"] != "-"
    ]

    print("=" * 70)
    print("BULK EXTRACTION AUDIT")
    print("=" * 70)
    print(f"Total funds: {len(all_funds)}")
    print(f"Funds with websites: {len(funds_to_test)}")
    print()

    # Run audit
    results = asyncio.run(run_audit(funds_to_test))

    # Calculate statistics
    success = [r for r in results if r.status == "success"]
    partial = [r for r in results if r.status == "partial"]
    failed = [r for r in results if r.status == "failed"]

    portfolio_scores = [r.portfolio_quality for r in results if r.portfolio_quality > 0]
    team_scores = [r.team_quality for r in results if r.team_quality > 0]
    news_scores = [r.news_quality for r in results if r.news_quality > 0]
    overall_scores = [r.overall_quality for r in results if r.overall_quality > 0]

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Successful (≥70%):  {len(success):>3} funds")
    print(f"Partial (<70%):     {len(partial):>3} funds")
    print(f"Failed:             {len(failed):>3} funds")
    print()
    print("AVERAGE QUALITY SCORES")
    print("-" * 40)
    if portfolio_scores:
        print(f"Portfolio: {sum(portfolio_scores)/len(portfolio_scores):.1f}% ({len(portfolio_scores)} funds)")
    if team_scores:
        print(f"Team:      {sum(team_scores)/len(team_scores):.1f}% ({len(team_scores)} funds)")
    if news_scores:
        print(f"News:      {sum(news_scores)/len(news_scores):.1f}% ({len(news_scores)} funds)")
    if overall_scores:
        print(f"Overall:   {sum(overall_scores)/len(overall_scores):.1f}% ({len(overall_scores)} funds)")

    # Save results
    output_path = Path(__file__).parent.parent.parent / "data" / "derived" / "bulk_extraction_audit.json"
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_funds": len(all_funds),
        "tested_funds": len(funds_to_test),
        "summary": {
            "successful": len(success),
            "partial": len(partial),
            "failed": len(failed),
            "portfolio_avg": sum(portfolio_scores)/len(portfolio_scores) if portfolio_scores else 0,
            "team_avg": sum(team_scores)/len(team_scores) if team_scores else 0,
            "news_avg": sum(news_scores)/len(news_scores) if news_scores else 0,
            "overall_avg": sum(overall_scores)/len(overall_scores) if overall_scores else 0,
        },
        "results": [asdict(r) for r in results]
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {output_path}")

    # Print top and bottom performers
    sorted_results = sorted([r for r in results if r.overall_quality > 0],
                           key=lambda x: x.overall_quality, reverse=True)

    if sorted_results:
        print("\n" + "=" * 70)
        print("TOP 20 PERFORMERS")
        print("-" * 70)
        for r in sorted_results[:20]:
            print(f"{r.fund_name[:35]:<35} {r.overall_quality:>6.1f}%  P:{r.portfolio_count:>3} T:{r.team_count:>3} N:{r.news_count:>3}")

        print("\n" + "=" * 70)
        print("BOTTOM 10 (excluding failed)")
        print("-" * 70)
        for r in sorted_results[-10:]:
            print(f"{r.fund_name[:35]:<35} {r.overall_quality:>6.1f}%  P:{r.portfolio_count:>3} T:{r.team_count:>3} N:{r.news_count:>3}")


if __name__ == "__main__":
    main()
