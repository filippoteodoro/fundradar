"""
Populate fund_urls.json with discovered URLs for all funds.

This script:
1. Reads all funds from db.json
2. Runs URL discovery for each fund to find news/portfolio/team pages
3. Updates fund_urls.json with the discovered URLs
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .url_discovery import discover_urls, DiscoveryResult


def load_funds(data_dir: Path) -> list[dict]:
    """Load all funds from db.json."""
    db_path = data_dir / "db.json"
    with open(db_path, "r") as f:
        db = json.load(f)
    return db.get("funds", [])


def load_existing_fund_urls(data_dir: Path) -> dict[str, Any]:
    """Load existing fund_urls.json."""
    fund_urls_path = data_dir / "site_configs" / "fund_urls.json"
    if fund_urls_path.exists():
        with open(fund_urls_path, "r") as f:
            return json.load(f)
    return {}


def discovery_to_fund_url_entry(
    fund: dict,
    result: DiscoveryResult,
    existing_entry: dict | None = None,
) -> dict:
    """Convert discovery result to fund_urls.json entry format."""
    entry = existing_entry.copy() if existing_entry else {}

    entry["fund_name"] = fund.get("name", fund.get("slug", "Unknown"))
    entry["website"] = fund.get("website", result.base_url)

    # Find best URL for each page type
    page_type_map = {
        "news_list": "news",
        "portfolio_list": "portfolio",
        "team_list": "team",
    }

    for discovered_type, output_key in page_type_map.items():
        # Find URLs of this type, sorted by confidence
        matching_urls = [
            u for u in result.discovered_urls
            if u.page_type == discovered_type
        ]
        matching_urls.sort(key=lambda x: -x.confidence)

        # Skip if already have a verified URL
        if existing_entry and existing_entry.get(f"{output_key}_source") == "verified":
            continue

        if matching_urls:
            best_url = matching_urls[0]
            entry[output_key] = best_url.url
            entry[f"{output_key}_confidence"] = best_url.confidence
            entry[f"{output_key}_source"] = best_url.source

    entry["discovered_at"] = datetime.now(timezone.utc).isoformat()

    return entry


def discover_fund_urls(fund: dict, timeout: int = 15) -> tuple[str, DiscoveryResult | None, str | None]:
    """
    Run URL discovery for a single fund.

    Returns:
        (slug, result, error)
    """
    slug = fund.get("slug", "")
    website = fund.get("website", "")

    if not website:
        return slug, None, "No website"

    try:
        result = discover_urls(
            base_url=website,
            entity_slug=slug,
            fetch_homepage=True,
            probe_paths=True,
            timeout=timeout,
        )
        return slug, result, None
    except Exception as e:
        return slug, None, str(e)


def run_population(
    data_dir: Path,
    limit: int | None = None,
    workers: int = 5,
    skip_existing: bool = True,
) -> dict[str, Any]:
    """
    Run URL discovery for all funds and update fund_urls.json.

    Args:
        data_dir: Path to data directory
        limit: Optional limit on number of funds to process
        workers: Number of parallel workers
        skip_existing: Skip funds already in fund_urls.json with verified URLs

    Returns:
        Updated fund_urls dict
    """
    funds = load_funds(data_dir)
    existing_fund_urls = load_existing_fund_urls(data_dir)

    print(f"Loaded {len(funds)} funds from db.json")
    print(f"Existing fund_urls.json has {len(existing_fund_urls)} entries")

    # Filter funds to process
    funds_to_process = []
    for fund in funds:
        slug = fund.get("slug", "")

        # Skip if no website
        if not fund.get("website"):
            continue

        # Optionally skip if already has good data
        if skip_existing and slug in existing_fund_urls:
            entry = existing_fund_urls[slug]
            # Skip if has all three verified URLs
            if (entry.get("news_source") == "verified" and
                entry.get("portfolio_source") == "verified" and
                entry.get("team_source") == "verified"):
                continue

        funds_to_process.append(fund)

    if limit:
        funds_to_process = funds_to_process[:limit]

    print(f"Processing {len(funds_to_process)} funds...")

    # Run discovery in parallel
    results = {}
    errors = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(discover_fund_urls, fund): fund
            for fund in funds_to_process
        }

        for i, future in enumerate(as_completed(futures)):
            fund = futures[future]
            slug, result, error = future.result()

            if error:
                errors.append((slug, error))
                print(f"  [{i+1}/{len(funds_to_process)}] {slug}: ERROR - {error}")
            elif result:
                results[slug] = result
                # Count discovered high-value URLs
                high_value = sum(
                    1 for u in result.discovered_urls
                    if u.page_type in ("news_list", "portfolio_list", "team_list")
                )
                print(f"  [{i+1}/{len(funds_to_process)}] {slug}: {high_value} high-value URLs found")

    # Update fund_urls
    updated_fund_urls = existing_fund_urls.copy()

    for slug, result in results.items():
        fund = next((f for f in funds if f.get("slug") == slug), None)
        if fund:
            existing_entry = updated_fund_urls.get(slug)
            updated_fund_urls[slug] = discovery_to_fund_url_entry(
                fund, result, existing_entry
            )

    print(f"\nProcessed {len(results)} funds successfully")
    print(f"Errors: {len(errors)}")
    print(f"Updated fund_urls.json now has {len(updated_fund_urls)} entries")

    return updated_fund_urls


def main():
    """Main entry point."""
    # Get data directory
    project_root = Path(__file__).parent.parent.parent.parent
    data_dir = project_root / "data"

    # Parse args
    limit = None
    dry_run = False
    skip_existing = True

    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--limit" and i + 1 < len(sys.argv) - 1:
            limit = int(sys.argv[i + 2])
        elif arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
        elif arg == "--dry-run":
            dry_run = True
        elif arg == "--include-existing":
            skip_existing = False
        elif arg in ("--help", "-h"):
            print("Usage: python -m fundradar_worker.populate_fund_urls [OPTIONS]")
            print("\nOptions:")
            print("  --limit N           Limit to N funds")
            print("  --dry-run           Don't save changes")
            print("  --include-existing  Re-discover URLs for all funds")
            print("  --help, -h          Show this help message")
            sys.exit(0)

    print("Fundradar URL Population")
    print("========================\n")

    # Run population
    updated_fund_urls = run_population(
        data_dir,
        limit=limit,
        skip_existing=skip_existing,
    )

    # Save results
    if not dry_run:
        output_path = data_dir / "site_configs" / "fund_urls.json"
        with open(output_path, "w") as f:
            json.dump(updated_fund_urls, f, indent=2)
        print(f"\nSaved to {output_path}")
    else:
        print("\n[DRY RUN] No changes saved")


if __name__ == "__main__":
    main()
