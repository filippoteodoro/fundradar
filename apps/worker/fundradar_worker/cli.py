"""
Fundradar Worker CLI.

Command-line interface for scraping operations and configuration validation.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fundradar_worker.domain_policies import DomainPolicyRegistry
from fundradar_worker.fetcher import fetch_url
from fundradar_worker.enrichment import FundEnricher
from fundradar_worker.baseline import (
    generate_baselines_for_fixtures,
    run_regression_tests,
    format_regression_report,
)
from fundradar_worker.health_report import (
    generate_health_report,
    format_health_report,
    save_health_report,
)
from fundradar_worker.circuit_breaker import (
    get_circuit_registry,
    CircuitConfig,
    CircuitState,
)
from fundradar_worker.rate_limiter import get_rate_limiter


def cmd_generate_baselines(args):
    """Generate regression test baselines from fixtures."""
    project_root = Path(__file__).parent.parent
    fixtures_dir = project_root / "tests" / "fixtures"
    baselines_dir = project_root / "tests" / "baselines"

    if not fixtures_dir.exists():
        print(f"Fixtures directory not found: {fixtures_dir}")
        return 1

    print(f"Generating baselines from: {fixtures_dir}")
    print(f"Output directory: {baselines_dir}")
    print(f"Overwrite: {args.overwrite}")
    print()

    baselines = generate_baselines_for_fixtures(
        fixtures_dir,
        baselines_dir,
        overwrite=args.overwrite,
    )

    print(f"\nGenerated {len(baselines)} baselines:")
    for b in baselines:
        print(f"  - {b.fixture_name}: {b.company_count} companies ({b.extraction_method or 'none'})")

    return 0


def cmd_health_report(args):
    """Generate scraping health report."""
    project_root = Path(__file__).parent.parent.parent.parent
    data_dir = project_root / "data" / "derived"
    db_path = project_root / "data" / "db.json"

    print("Generating health report...")
    print()

    report = generate_health_report(data_dir, db_path)

    # Format and print
    text_report = format_health_report(report, verbose=args.verbose)
    print(text_report)

    # Save if requested
    if args.output:
        output_path = Path(args.output)
        save_health_report(report, output_path)
        print(f"\nSaved JSON report to: {output_path}")

    # Output JSON if requested
    if args.json:
        print("\nJSON Output:")
        from dataclasses import asdict
        json_data = {
            "generated_at": report.generated_at,
            "total_funds": report.total_funds,
            "funds_with_website": report.funds_with_website,
            "funds_checked": report.funds_checked,
            "overall_success_rate": report.overall_success_rate,
            "total_companies_extracted": report.total_companies_extracted,
            "total_signals_generated": report.total_signals_generated,
            "error_summary": report.error_summary,
            "coverage_gaps_count": len(report.coverage_gaps),
        }
        print(json.dumps(json_data, indent=2))

    return 0


def cmd_check_regression(args):
    """Run regression tests against baselines."""
    project_root = Path(__file__).parent.parent
    fixtures_dir = project_root / "tests" / "fixtures"
    baselines_dir = project_root / "tests" / "baselines"

    if not baselines_dir.exists() or not list(baselines_dir.glob("*.baseline.json")):
        print("No baselines found. Run 'generate-baselines' first.")
        return 1

    print("Running regression tests...")
    print()

    diffs, all_passed = run_regression_tests(fixtures_dir, baselines_dir)

    # Print report
    report = format_regression_report(diffs)
    print(report)

    if args.json:
        print("\nJSON Output:")
        json_output = []
        for d in diffs:
            json_output.append({
                "fixture": d.fixture_name,
                "passed": d.passed,
                "message": d.message,
                "company_count_diff": d.company_count_diff,
                "added": d.added_companies,
                "removed": d.removed_companies,
            })
        print(json.dumps(json_output, indent=2))

    return 0 if all_passed else 1


def cmd_list_errors(args):
    """List domains with errors, open circuits, or backoff status."""
    project_root = Path(__file__).parent.parent.parent.parent
    state_path = project_root / "data" / "derived" / "circuit_state.json"

    # Get circuit registry
    config = CircuitConfig.from_env()
    registry = get_circuit_registry(config, state_path)

    # Get all circuit stats
    all_stats = registry.get_all_stats()
    summary = registry.get_summary()

    # Filter by status if requested
    if args.status:
        status = args.status.lower()
        all_stats = [s for s in all_stats if s.state == status]

    # Sort by failures (most failures first)
    all_stats.sort(key=lambda s: s.total_failures, reverse=True)

    if args.json:
        from dataclasses import asdict
        output = {
            "summary": summary,
            "circuits": [asdict(s) for s in all_stats],
        }
        print(json.dumps(output, indent=2))
        return 0

    # Text output
    print("Circuit Breaker Status")
    print("=" * 60)
    print()
    print(f"Total circuits: {summary['total_circuits']}")
    print(f"  Open:      {summary['open_circuits']}")
    print(f"  Half-open: {summary['half_open_circuits']}")
    print(f"  Closed:    {summary['closed_circuits']}")
    print(f"\nTotal failures: {summary['total_failures']}")
    print(f"Total successes: {summary['total_successes']}")
    print()

    if not all_stats:
        print("No circuits tracked yet.")
        return 0

    # Show circuits with issues (open or with failures)
    problem_circuits = [s for s in all_stats if s.state != "closed" or s.total_failures > 0]

    if not problem_circuits:
        print("All circuits are healthy.")
        return 0

    print("Domains with errors or issues:")
    print("-" * 60)

    for stat in problem_circuits[:args.limit]:
        status_icon = {
            "open": "🔴",
            "half_open": "🟡",
            "closed": "🟢",
        }.get(stat.state, "⚪")

        print(f"\n{status_icon} {stat.domain}")
        print(f"   State: {stat.state}")
        print(f"   Consecutive failures: {stat.consecutive_failures}")
        print(f"   Total failures: {stat.total_failures}")
        print(f"   Total successes: {stat.total_successes}")

        if stat.last_failure_at:
            print(f"   Last failure: {stat.last_failure_at}")
        if stat.opened_at:
            print(f"   Circuit opened: {stat.opened_at}")

    remaining = len(problem_circuits) - args.limit
    if remaining > 0:
        print(f"\n... and {remaining} more (use --limit to show more)")

    return 0


def cmd_reset_backoff(args):
    """Reset circuit breaker and backoff for a domain."""
    domain = args.domain

    if not domain and not args.all:
        print("Error: Either provide a domain or use --all to reset all domains")
        return 1

    project_root = Path(__file__).parent.parent.parent.parent
    state_path = project_root / "data" / "derived" / "circuit_state.json"
    backoff_path = project_root / "data" / "derived" / "domain_backoff.json"

    # Reset circuit breaker
    config = CircuitConfig.from_env()
    registry = get_circuit_registry(config, state_path)

    if args.all:
        print("Resetting all circuits...")
        registry.reset_all()
        domains_reset = list(registry._circuits.keys())
        print(f"Reset {len(domains_reset)} circuits")
    else:
        print(f"Resetting circuit for: {domain}")
        registry.reset(domain)
        domains_reset = [domain]

    # Also reset backoff state if it exists
    if backoff_path.exists():
        try:
            with open(backoff_path) as f:
                backoff_data = json.load(f)

            modified = False
            if args.all:
                if "domains" in backoff_data:
                    count = len(backoff_data["domains"])
                    backoff_data["domains"] = {}
                    modified = True
                    print(f"Reset backoff for {count} domains")
            else:
                if "domains" in backoff_data and domain in backoff_data["domains"]:
                    del backoff_data["domains"][domain]
                    modified = True
                    print(f"Reset backoff for: {domain}")

            if modified:
                with open(backoff_path, "w") as f:
                    json.dump(backoff_data, f, indent=2)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Warning: Could not reset backoff state: {e}")

    if args.json:
        output = {
            "action": "reset",
            "domains": domains_reset,
            "success": True,
        }
        print(json.dumps(output, indent=2))
    else:
        print("\nDone. Domain(s) will be retried on next scrape.")

    return 0


def cmd_scrape_fund(args):
    """Scrape a specific fund and output results."""
    slug = args.slug
    dry_run = args.dry_run

    project_root = Path(__file__).parent.parent.parent.parent
    db_path = project_root / "data" / "db.json"

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    # Load fund data
    with open(db_path) as f:
        db = json.load(f)

    funds = db.get("funds", [])
    fund = None
    for f in funds:
        if f.get("slug") == slug:
            fund = f
            break

    if not fund:
        print(f"Fund not found: {slug}")
        print(f"\nAvailable funds (first 20):")
        for f in funds[:20]:
            print(f"  - {f.get('slug')}")
        return 1

    website = fund.get("website", "")
    if not website:
        print("No website URL found for fund")
        return 1

    if dry_run:
        print("[DRY RUN MODE - No data will be written]")
        print()

    print(f"Scraping fund: {fund.get('name')}")
    print(f"Website: {website}")
    print()

    # Check circuit breaker status
    state_path = project_root / "data" / "derived" / "circuit_state.json"
    config = CircuitConfig.from_env()
    registry = get_circuit_registry(config, state_path)

    from urllib.parse import urlparse
    domain = urlparse(website).netloc
    circuit = registry.get_circuit(domain)
    circuit_state = circuit.state

    print(f"Circuit state for {domain}: {circuit_state.value}")

    if circuit_state == CircuitState.OPEN:
        print("WARNING: Circuit is open (site has been failing). Use --force to scrape anyway.")
        if not args.force:
            return 1

    # Use the monitor to check the fund
    from fundradar_worker.monitor import WebsiteMonitor, MonitoredUrl

    data_dir = project_root / "data" / "derived"
    monitor = WebsiteMonitor(data_dir)

    # Create monitored URL
    monitored = MonitoredUrl(
        url=website,
        fund_slug=slug,
        fund_name=fund.get("name", slug),
        page_type="home",
        category="HOME",
    )

    # Check the URL
    print("\nFetching and analyzing website...")
    signals = monitor.check_url(monitored, skip_backoff=True)

    # Record success/failure in circuit breaker
    if signals is not None:
        registry.record_success(domain)
    else:
        registry.record_failure(domain)
        signals = []

    print(f"\nSignals generated: {len(signals)}")

    if args.json:
        output = {
            "fund_slug": slug,
            "fund_name": fund.get("name"),
            "website": website,
            "dry_run": dry_run,
            "circuit_state": circuit_state.value,
            "signals_count": len(signals),
            "signals": signals,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        for signal in signals:
            print(f"  - [{signal['signal_type']}] {signal['title']}")

    if dry_run:
        print("\n[DRY RUN] Signals not saved to database")
    elif signals:
        # In non-dry-run mode, signals are already saved by the monitor
        print(f"\nSignals saved to: {data_dir / 'detected_signals.json'}")

    return 0


def cmd_linkedin_posts(args):
    """Scrape LinkedIn posts for funds."""
    from fundradar_worker.linkedin import (
        ApifyClient, ApifyConfig,
        LinkedInPostsScraper,
        PostClassifier,
    )
    from fundradar_worker.data_writer import SignalRecord, get_data_writer

    project_root = Path(__file__).parent.parent.parent.parent
    db_path = project_root / "data" / "db.json"
    data_dir = project_root / "data" / "derived" / "linkedin"

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    # Load fund data
    with open(db_path) as f:
        db = json.load(f)

    funds = db.get("funds", [])

    # Filter to specific fund if provided
    if args.fund:
        funds = [f for f in funds if f.get("slug") == args.fund]
        if not funds:
            print(f"Fund not found: {args.fund}")
            return 1

    # Build LinkedIn URLs (generate from website domain if not available)
    companies = []
    for fund in funds[:args.limit]:
        slug = fund.get("slug")
        name = fund.get("name", slug)
        website = fund.get("website", "")

        # Try to generate LinkedIn URL from website domain
        if website:
            from urllib.parse import urlparse
            domain = urlparse(website).netloc.replace("www.", "")
            linkedin_url = f"https://www.linkedin.com/company/{domain.split('.')[0]}"
        else:
            linkedin_url = None

        if linkedin_url:
            companies.append({
                "slug": slug,
                "name": name,
                "linkedin_url": linkedin_url,
            })

    if not companies:
        print("No companies with LinkedIn URLs found")
        return 1

    print(f"Scraping posts for {len(companies)} companies...")
    print(f"Max posts per company: {args.max_posts}")

    if args.dry_run:
        print("\n[DRY RUN] Would scrape:")
        for c in companies:
            print(f"  - {c['name']}: {c['linkedin_url']}")
        return 0

    try:
        config = ApifyConfig.from_env()
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    client = ApifyClient(config)
    scraper = LinkedInPostsScraper(client, data_dir)
    classifier = PostClassifier(min_confidence=0.5)

    all_posts = []
    for company in companies:
        print(f"\nScraping: {company['name']}...")
        posts = scraper.scrape_company_posts(
            company_url=company["linkedin_url"],
            company_slug=company["slug"],
            company_name=company["name"],
            max_posts=args.max_posts,
            save_raw=True,
        )
        all_posts.extend(posts)
        print(f"  Got {len(posts)} posts")

    # Save all posts
    scraper.save_posts(all_posts)

    # Classify and generate signals
    print(f"\nClassifying {len(all_posts)} posts...")
    classified = classifier.classify_batch(all_posts, filter_unknown=True)
    print(f"Found {len(classified)} signal-worthy posts")

    # Convert to signals
    signals = classifier.to_signal_records(classified)

    if args.json:
        print(json.dumps({
            "posts_scraped": len(all_posts),
            "signals_found": len(signals),
            "signals": signals[:10],  # First 10
        }, indent=2))
    else:
        for sig in signals[:20]:
            print(f"  [{sig['signal_type']}] {sig['title']}")

    # Save signals to linkedin_signals.json
    signals_path = data_dir / "linkedin_signals.json"
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(signals_path, "w") as f:
        json.dump({
            "generated_at": signals[0]["observed_at"] if signals else None,
            "signal_count": len(signals),
            "signals": signals,
        }, f, indent=2)

    print(f"\nSaved {len(signals)} signals to {signals_path}")
    return 0


def cmd_linkedin_people(args):
    """Scrape LinkedIn people data for funds."""
    from fundradar_worker.linkedin import (
        ApifyClient, ApifyConfig,
        LinkedInPeopleScraper,
        PeopleStatsCalculator,
    )

    project_root = Path(__file__).parent.parent.parent.parent
    db_path = project_root / "data" / "db.json"
    data_dir = project_root / "data" / "derived" / "linkedin"

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    # Load fund data
    with open(db_path) as f:
        db = json.load(f)

    funds = db.get("funds", [])

    # Filter to specific fund if provided
    if args.fund:
        funds = [f for f in funds if f.get("slug") == args.fund]
        if not funds:
            print(f"Fund not found: {args.fund}")
            return 1

    # Build LinkedIn URLs
    companies = []
    for fund in funds[:args.limit]:
        slug = fund.get("slug")
        name = fund.get("name", slug)
        website = fund.get("website", "")

        if website:
            from urllib.parse import urlparse
            domain = urlparse(website).netloc.replace("www.", "")
            linkedin_url = f"https://www.linkedin.com/company/{domain.split('.')[0]}"
        else:
            linkedin_url = None

        if linkedin_url:
            companies.append({
                "slug": slug,
                "name": name,
                "linkedin_url": linkedin_url,
            })

    if not companies:
        print("No companies with LinkedIn URLs found")
        return 1

    print(f"Scraping people data for {len(companies)} companies...")
    print(f"Top profiles per company: {args.top_profiles}")

    if args.dry_run:
        print("\n[DRY RUN] Would scrape:")
        for c in companies:
            print(f"  - {c['name']}: {c['linkedin_url']}")
        return 0

    try:
        config = ApifyConfig.from_env()
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    client = ApifyClient(config)
    scraper = LinkedInPeopleScraper(client, data_dir)
    stats_calculator = PeopleStatsCalculator(data_dir)

    all_employees = []
    all_profiles = []
    fund_data = []

    for company in companies:
        print(f"\nScraping: {company['name']}...")

        employees, profiles = scraper.scrape_top_employees(
            company_url=company["linkedin_url"],
            company_slug=company["slug"],
            company_name=company["name"],
            num_profiles=args.top_profiles,
            save_raw=True,
        )

        all_employees.extend(employees)
        all_profiles.extend(profiles)

        fund_data.append({
            "slug": company["slug"],
            "name": company["name"],
            "employees": employees,
            "profiles": profiles,
        })

        print(f"  Employees: {len(employees)}, Profiles: {len(profiles)}")

    # Save raw data
    scraper.save_employees(all_employees)
    scraper.save_profiles(all_profiles)

    # Calculate and save stats
    print(f"\nCalculating stats for {len(fund_data)} funds...")
    all_stats = stats_calculator.calculate_batch(fund_data)
    stats_calculator.save_stats(all_stats)

    # Generate summary
    summary = stats_calculator.generate_summary_report(all_stats)

    if args.json:
        print(json.dumps({
            "funds_scraped": len(fund_data),
            "total_employees": len(all_employees),
            "total_profiles": len(all_profiles),
            "summary": summary,
        }, indent=2))
    else:
        print(f"\nSummary:")
        print(f"  Funds: {summary.get('fund_count', 0)}")
        print(f"  Total employees tracked: {summary.get('total_employees_tracked', 0)}")
        print(f"  New hires (6mo): {summary.get('hiring', {}).get('total_new_hires_6mo', 0)}")
        bg = summary.get("background_totals", {})
        print(f"  IB background: {bg.get('investment_banking', 0)}")
        print(f"  PE background: {bg.get('private_equity', 0)}")
        print(f"  Consulting: {bg.get('consulting', 0)}")

    print(f"\nSaved to {data_dir}/")
    return 0


def cmd_linkedin_test(args):
    """Test LinkedIn scraping with a single company."""
    from fundradar_worker.linkedin import ApifyClient, ApifyConfig

    print("Testing Apify connection...")

    try:
        config = ApifyConfig.from_env()
        print(f"API token configured: {config.api_token[:8]}...")
    except ValueError as e:
        print(f"Error: {e}")
        print("\nTo configure Apify:")
        print("  export APIFY_API_TOKEN='your_token_here'")
        return 1

    if not args.url:
        print("\nConnection test successful!")
        print("To test scraping, provide a LinkedIn URL:")
        print("  python -m fundradar_worker.cli linkedin-test --url https://www.linkedin.com/company/investindustrial")
        return 0

    client = ApifyClient(config)

    print(f"\nTesting URL: {args.url}")

    if "company" in args.url:
        print("Detected company URL, scraping company profile...")
        result = client.scrape_company_profile(args.url)
    else:
        print("Detected profile URL, scraping individual profile...")
        result = client.scrape_profile(args.url)

    if result.error:
        print(f"Error: {result.error}")
        return 1

    print(f"Status: {result.status}")
    print(f"Duration: {result.duration_secs:.1f}s")
    print(f"Estimated cost: ${result.cost_usd:.4f}")
    print(f"Items returned: {len(result.items)}")

    if result.items and args.json:
        print("\nData:")
        print(json.dumps(result.items[0], indent=2)[:2000])

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Fundradar Worker CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape a fund (dry run first)
  python -m fundradar_worker.cli scrape-fund investindustrial --dry-run
  python -m fundradar_worker.cli scrape-fund investindustrial

  # View errors and circuit breaker status
  python -m fundradar_worker.cli list-errors
  python -m fundradar_worker.cli list-errors --status open --json

  # Reset a failing domain
  python -m fundradar_worker.cli reset-backoff example.com
  python -m fundradar_worker.cli reset-backoff --all

  # Generate health report
  python -m fundradar_worker.cli health-report --verbose
  python -m fundradar_worker.cli health-report --json --output report.json

  # Regression testing
  python -m fundradar_worker.cli generate-baselines
  python -m fundradar_worker.cli check-regression

  # LinkedIn scraping (requires APIFY_API_TOKEN env var)
  python -m fundradar_worker.cli linkedin-test
  python -m fundradar_worker.cli linkedin-test --url https://www.linkedin.com/company/investindustrial
  python -m fundradar_worker.cli linkedin-posts --fund investindustrial --dry-run
  python -m fundradar_worker.cli linkedin-posts --limit 5 --max-posts 10
  python -m fundradar_worker.cli linkedin-people --fund investindustrial --dry-run
  python -m fundradar_worker.cli linkedin-people --limit 10 --top-profiles 5
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scrape-fund command
    scrape_parser = subparsers.add_parser(
        "scrape-fund",
        help="Scrape a specific fund by slug",
    )
    scrape_parser.add_argument("slug", help="Fund slug (e.g., investindustrial)")
    scrape_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze site but don't save any data",
    )
    scrape_parser.add_argument(
        "--force",
        action="store_true",
        help="Scrape even if circuit breaker is open",
    )
    scrape_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    scrape_parser.set_defaults(func=cmd_scrape_fund)

    # list-errors command
    errors_parser = subparsers.add_parser(
        "list-errors",
        help="List domains with errors or open circuits",
    )
    errors_parser.add_argument(
        "--status",
        choices=["open", "half_open", "closed"],
        help="Filter by circuit state",
    )
    errors_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of domains to show (default: 20)",
    )
    errors_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    errors_parser.set_defaults(func=cmd_list_errors)

    # reset-backoff command
    reset_parser = subparsers.add_parser(
        "reset-backoff",
        help="Reset circuit breaker and backoff for a domain",
    )
    reset_parser.add_argument(
        "domain",
        nargs="?",
        help="Domain to reset (e.g., example.com)",
    )
    reset_parser.add_argument(
        "--all",
        action="store_true",
        help="Reset all domains",
    )
    reset_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    reset_parser.set_defaults(func=cmd_reset_backoff)

    # generate-baselines command
    baseline_gen_parser = subparsers.add_parser(
        "generate-baselines",
        help="Generate regression test baselines from fixtures",
    )
    baseline_gen_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing baselines",
    )
    baseline_gen_parser.set_defaults(func=cmd_generate_baselines)

    # check-regression command
    regression_parser = subparsers.add_parser(
        "check-regression",
        help="Run regression tests against baselines",
    )
    regression_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    regression_parser.set_defaults(func=cmd_check_regression)

    # health-report command
    health_parser = subparsers.add_parser(
        "health-report",
        help="Generate scraping health report",
    )
    health_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    health_parser.add_argument("--verbose", "-v", action="store_true", help="Include detailed domain breakdown")
    health_parser.add_argument("--output", "-o", help="Save JSON report to file")
    health_parser.set_defaults(func=cmd_health_report)

    # linkedin-posts command
    linkedin_posts_parser = subparsers.add_parser(
        "linkedin-posts",
        help="Scrape LinkedIn posts for funds",
    )
    linkedin_posts_parser.add_argument(
        "--fund",
        help="Specific fund slug to scrape (optional)",
    )
    linkedin_posts_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of funds to scrape (default: 10)",
    )
    linkedin_posts_parser.add_argument(
        "--max-posts",
        type=int,
        default=10,
        help="Maximum posts per company (default: 10)",
    )
    linkedin_posts_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be scraped without making API calls",
    )
    linkedin_posts_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    linkedin_posts_parser.set_defaults(func=cmd_linkedin_posts)

    # linkedin-people command
    linkedin_people_parser = subparsers.add_parser(
        "linkedin-people",
        help="Scrape LinkedIn people data for funds",
    )
    linkedin_people_parser.add_argument(
        "--fund",
        help="Specific fund slug to scrape (optional)",
    )
    linkedin_people_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of funds to scrape (default: 10)",
    )
    linkedin_people_parser.add_argument(
        "--top-profiles",
        type=int,
        default=5,
        help="Number of full profiles to scrape per fund (default: 5)",
    )
    linkedin_people_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be scraped without making API calls",
    )
    linkedin_people_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    linkedin_people_parser.set_defaults(func=cmd_linkedin_people)

    # linkedin-test command
    linkedin_test_parser = subparsers.add_parser(
        "linkedin-test",
        help="Test LinkedIn scraping connection and API",
    )
    linkedin_test_parser.add_argument(
        "--url",
        help="LinkedIn URL to test (company or profile)",
    )
    linkedin_test_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    linkedin_test_parser.set_defaults(func=cmd_linkedin_test)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
