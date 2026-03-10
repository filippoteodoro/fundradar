"""
Batch scraper for LinkedIn people data.

Processes all funds in batches with progress tracking and cost monitoring.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from ..io_utils import safe_json_write
from ..paths import PROJECT_ROOT

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Pricing constants (harvestapi actor)
PRICE_ACTOR_START = 0.02
PRICE_FULL_PROFILE = 0.008

# Global mega-funds where LinkedIn returns thousands of global employees.
# Their Italy teams are tiny fractions of total headcount, making scraping impractical.
MEGA_FUNDS_TO_SKIP = {
    "blackstone",  # Global HQ NY, LinkedIn returns 50k+ global employees
    "kkr",  # Global HQ NY, LinkedIn returns 10k+ global employees
    "apollo",  # 3k+ global, multi_strategy, NY HQ
    "ares-management",  # 3k+ global, multi_strategy, LA HQ
    "macquarie",  # 20k+ global, infra, London HQ
    "towerbrook",  # 500+ global, PE, NY HQ
    "ardian",  # 4k+ global, Paris HQ — Italy team is tiny fraction, manual profiles preferred
    "carlyle",  # 2k+ global, Washington HQ — already have manual profiles
    "eqt",  # 2k+ global, Stockholm HQ — already have manual profiles
    "permira",  # 500+ global, London HQ — already have manual profiles
    "advent-international",  # 500+ global, Boston HQ — already have manual profiles
    "bain-capital",  # 10k+ global, Boston HQ — already have manual profiles
    "partners-group",  # 1.5k+ global, Zug HQ — already have manual profiles
    "h-i-g-capital",  # 1k+ global, Miami HQ — already have manual profiles
    "apax-partners",  # 500+ global, London HQ — already have manual profiles
    "bridgepoint",  # 500+ global, London HQ — already have manual profiles
    "pai-partners",  # 500+ global, Paris HQ — already have manual profiles
}

# Non-Italian European funds whose LinkedIn pages return predominantly non-Italy staff.
# The priority_ranker gives these Italy HQ bonus because AIFI records their Italian branch
# address — but their global LinkedIn team is mostly Paris/London/Amsterdam.
# Scraping 25 profiles yields ~1-3 Italy-based people: not worth the Apify budget.
# Add manual profiles to manual_profiles.json instead if Italy team coverage is needed.
FOREIGN_FUNDS_TO_SKIP = {
    "montefiore",       # Paris HQ, ~100 global employees, Italy team tiny fraction
    "bc-partners",      # London HQ, ~200 global employees, Italy team tiny fraction
    "cinven",           # London/Luxembourg HQ, ~300 global, Italy team tiny fraction
    "argos-wityu",      # Paris/Luxembourg HQ, ~50 global, Italy team tiny fraction
    "charme-capital",   # London/Jersey HQ, Italy connections but non-Italian team
    "rivean-capital",   # Amsterdam HQ, ~150 global, Italy team tiny fraction
    "sagard",           # Paris/Canada HQ, ~200 global, Italy team tiny fraction
    "andera-partners",  # Paris HQ, VC, Italy team tiny fraction
    "eiffel",           # Paris HQ, infrastructure, Italy team tiny fraction
    "sofinnova-partners",  # Paris HQ, biotech VC, Italy team tiny fraction
    "portobello-capital",  # Madrid HQ, Spain-focused, minimal Italy team
    "capza",            # Paris HQ, mid-market, Italy team tiny fraction
    "muzinich-co",      # London HQ, credit, Italy team tiny fraction
    "eurazeo",          # Paris HQ, ~500 global, Italy team small fraction
    "astorg",           # Paris/Luxembourg HQ, Italy team tiny fraction
    "abenex",           # Paris HQ, France-focused, Italy team tiny fraction
    "apheon",           # Belgium HQ, Benelux-focused, Italy team tiny fraction
    "perwyn",           # London HQ, Italy team tiny fraction
    "oakley-capital",   # London HQ, ~100 global, Italy investments but London team
    "unigrains",        # Paris HQ, France-focused agri fund
    "ring-capital",     # Paris HQ, French VC, Italy team tiny fraction
}


@dataclass
class ScrapeProgress:
    """Track scraping progress."""

    started_at: str
    completed_funds: list[str]
    failed_funds: list[str]
    skipped_mega_funds: list[str]  # Global mega-funds skipped intentionally
    total_profiles: int
    total_cost_usd: float
    last_fund: str | None


def load_progress(progress_path: Path) -> ScrapeProgress | None:
    """Load existing progress if available."""
    if progress_path.exists():
        with open(progress_path) as f:
            data = json.load(f)
            # Handle backwards compatibility for old progress files
            if "skipped_mega_funds" not in data:
                data["skipped_mega_funds"] = []
            # Remove any extra fields not in dataclass
            valid_fields = {f.name for f in ScrapeProgress.__dataclass_fields__.values()}
            data = {k: v for k, v in data.items() if k in valid_fields}
            return ScrapeProgress(**data)
    return None


def save_progress(progress: ScrapeProgress, progress_path: Path):
    """Save progress to file."""
    safe_json_write(progress_path, asdict(progress))


def scrape_fund_employees(
    company_url: str,
    api_token: str,
    max_employees: int = 50,
    use_basic_actor: bool = True,
) -> tuple[list[dict], float, str | None]:
    """
    Scrape employees for a single fund.

    Args:
        use_basic_actor: If True, use apimaestro actor (unlimited, headline-only data).
                         If False, use harvestapi actor (10 runs/month, full experience+education).

    Returns:
        Tuple of (profiles, cost_usd, error_message)
    """
    base_url = "https://api.apify.com/v2"

    if use_basic_actor:
        # apimaestro: unlimited runs, free (pure compute), headline-only data
        actor_id = "cIdqlEvw6afc1do1p"
        input_data = {
            "identifier": company_url,
            "max_employees": max_employees,
        }
    else:
        # harvestapi: 10 runs/month on free Apify plan, rich data (experience+education)
        actor_id = "harvestapi~linkedin-company-employees"
        input_data = {
            "companies": [company_url],
            "maxItems": max_employees,
            "outputType": "full",
        }

    # Start the actor
    run_url = f"{base_url}/acts/{actor_id}/runs?token={api_token}"

    try:
        response = requests.post(run_url, json=input_data, timeout=30)
        response.raise_for_status()
        run_data = response.json()["data"]
        run_id = run_data["id"]
        dataset_id = run_data["defaultDatasetId"]
    except Exception as e:
        return [], 0.0, f"Failed to start actor: {e}"

    # Poll for completion (max 5 minutes)
    status_url = f"{base_url}/actor-runs/{run_id}?token={api_token}"
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > 300:
            return [], PRICE_ACTOR_START, "Timeout waiting for actor"

        try:
            response = requests.get(status_url, timeout=30)
            response.raise_for_status()
            run_info = response.json()["data"]
            status = run_info.get("status")

            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                break

            time.sleep(5)
        except Exception as e:
            logger.warning(f"Error checking status: {e}")
            time.sleep(5)

    if status != "SUCCEEDED":
        return [], PRICE_ACTOR_START, f"Actor ended with status: {status}"

    # Get results
    items_url = f"{base_url}/datasets/{dataset_id}/items?token={api_token}"
    try:
        response = requests.get(items_url, timeout=30)
        response.raise_for_status()
        profiles = response.json()
    except Exception as e:
        return [], PRICE_ACTOR_START, f"Failed to get results: {e}"

    # Calculate cost
    # apimaestro: charges only compute units (negligible, ~$0.001/run) — no per-profile fee
    # harvestapi: charges PRICE_ACTOR_START + PRICE_FULL_PROFILE per profile
    charged = run_info.get("chargedEventCounts", {})
    full_profiles = charged.get("full-profile", 0)
    if use_basic_actor:
        # Compute-unit cost only: CU * $0.004 (Apify free plan rate)
        compute_units = run_info.get("stats", {}).get("computeUnits", 0)
        cost = round(compute_units * 0.004, 4)
    else:
        cost = PRICE_ACTOR_START + (full_profiles * PRICE_FULL_PROFILE)

    return profiles, cost, None


def run_batch_scrape(
    funds_path: Path,
    output_dir: Path,
    api_token: str,
    max_employees: int = 50,
    batch_size: int = 10,
    max_cost_usd: float = 100.0,
    resume: bool = True,
    use_priority: bool = True,
    delay_seconds: int = 120,
    use_basic_actor: bool = True,
):
    """
    Run batch scrape of all funds.

    Args:
        funds_path: Path to fund_linkedin_urls.json
        output_dir: Directory to save results
        api_token: Apify API token
        max_employees: Max employees per fund
        batch_size: Number of funds between progress saves
        max_cost_usd: Stop if total cost exceeds this
        resume: Whether to resume from previous progress
        use_priority: Use prioritized order (important Italy funds first)
    """
    # Load funds - prefer prioritized version if available and requested
    prioritized_path = funds_path.parent / "fund_linkedin_urls_prioritized.json"
    if use_priority and prioritized_path.exists():
        print("Using prioritized fund order (important Italy funds first)")
        with open(prioritized_path) as f:
            data = json.load(f)
    else:
        with open(funds_path) as f:
            data = json.load(f)
    companies = data["companies"]

    # Load db.json slugs to filter out unmatched funds (no page to display data)
    db_path = funds_path.parent.parent.parent / "db.json"
    db_slugs: set[str] = set()
    if db_path.exists():
        with open(db_path) as f:
            db_data = json.load(f)
        db_slugs = {fund["slug"] for fund in db_data.get("funds", [])}

    # Setup output paths
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "scrape_progress.json"
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(exist_ok=True)

    # Load or create progress
    progress = None
    if resume:
        progress = load_progress(progress_path)

    if not progress:
        progress = ScrapeProgress(
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_funds=[],
            failed_funds=[],
            skipped_mega_funds=[],
            total_profiles=0,
            total_cost_usd=0.0,
            last_fund=None,
        )

    # Filter out already processed funds, mega-funds, and unmatched funds
    remaining = []
    skipped_unmatched = 0
    for c in companies:
        slug = c["slug"]
        # Skip if already processed
        if slug in progress.completed_funds or slug in progress.failed_funds:
            continue
        # Skip mega-funds and foreign-HQ funds (Italy team too small to scrape usefully)
        if slug in MEGA_FUNDS_TO_SKIP or slug in FOREIGN_FUNDS_TO_SKIP:
            if slug not in progress.skipped_mega_funds:
                progress.skipped_mega_funds.append(slug)
            continue
        # Skip entries with "note" field (e.g., search URLs that won't work)
        if c.get("note"):
            continue
        # Skip funds not in db.json (no page to display the data)
        if db_slugs and slug not in db_slugs:
            skipped_unmatched += 1
            continue
        remaining.append(c)

    print(f"Total funds in file: {len(companies)}")
    print(f"Mega-funds skipped: {len(progress.skipped_mega_funds)}")
    print(f"Not in db.json (skipped): {skipped_unmatched}")
    print(f"Already processed: {len(progress.completed_funds)}")
    print(f"Failed: {len(progress.failed_funds)}")
    print(f"Remaining to scrape: {len(remaining)}")
    print(f"Current cost: ${progress.total_cost_usd:.2f}")
    print(f"Max cost budget: ${max_cost_usd:.2f}")
    print()

    # Process in batches
    for i, company in enumerate(remaining):
        slug = company["slug"]
        name = company["name"]
        linkedin_url = company["linkedin_url"]

        # Check cost budget
        if progress.total_cost_usd >= max_cost_usd:
            print(f"\nCost budget exceeded (${progress.total_cost_usd:.2f} >= ${max_cost_usd:.2f})")
            break

        print(f"[{i+1}/{len(remaining)}] Scraping {name}...")
        print(f"  URL: {linkedin_url}")

        profiles, cost, error = scrape_fund_employees(
            linkedin_url, api_token, max_employees, use_basic_actor=use_basic_actor
        )

        progress.total_cost_usd += cost
        progress.last_fund = slug

        if error:
            print(f"  ERROR: {error}")
            progress.failed_funds.append(slug)
        elif len(profiles) == 0:
            # 0 profiles = LinkedIn rate limited the actor. Do NOT mark as completed —
            # mark as failed so it can be retried in a future session.
            print(f"  WARNING: 0 profiles returned — likely LinkedIn rate limit. Marking as failed for retry.")
            progress.failed_funds.append(slug)
        else:
            print(f"  Got {len(profiles)} profiles (cost: ${cost:.3f})")
            progress.completed_funds.append(slug)
            progress.total_profiles += len(profiles)

            # Save raw profiles
            raw_path = raw_dir / f"{slug}_employees.json"
            safe_json_write(raw_path, profiles)

        # Save progress every batch_size funds
        if (i + 1) % batch_size == 0:
            save_progress(progress, progress_path)
            print(f"\n  Progress saved. Total cost: ${progress.total_cost_usd:.2f}\n")

        # Delay between funds to avoid LinkedIn rate limiting.
        # HarvestAPI recommends distributing requests evenly across hours (not bursting).
        # Default 120s = scraping 8 funds takes ~16 minutes, well within hourly limits.
        if i < len(remaining) - 1 and delay_seconds > 0:
            print(f"  Waiting {delay_seconds}s before next fund (rate limit protection)...")
            time.sleep(delay_seconds)

    # Final save
    save_progress(progress, progress_path)

    print("\n" + "=" * 60)
    print("SCRAPE COMPLETE")
    print("=" * 60)
    print(f"Total funds processed: {len(progress.completed_funds)}")
    print(f"Mega-funds skipped: {len(progress.skipped_mega_funds)}")
    print(f"Total failed: {len(progress.failed_funds)}")
    print(f"Total profiles scraped: {progress.total_profiles}")
    print(f"Total cost: ${progress.total_cost_usd:.2f}")

    return progress


if __name__ == "__main__":
    import argparse
    from fundradar_worker.linkedin.priority_ranker import create_prioritized_linkedin_urls

    parser = argparse.ArgumentParser(description="Batch scrape LinkedIn employee data")
    parser.add_argument("--max-employees", type=int, default=50, help="Max employees per fund")
    parser.add_argument("--max-cost", type=float, default=100.0, help="Max total cost in USD")
    parser.add_argument("--batch-size", type=int, default=10, help="Save progress every N funds")
    parser.add_argument("--no-resume", action="store_true", help="Start fresh instead of resuming")
    parser.add_argument("--no-priority", action="store_true", help="Don't use priority ranking (scrape in file order)")
    parser.add_argument("--delay", type=int, default=30, help="Seconds to wait between funds (default: 30 for apimaestro, use 180 for harvestapi)")
    parser.add_argument("--rich", action="store_true", help="Use harvestapi actor (rich data: experience+education, but 10 runs/month limit). Default: apimaestro (unlimited, headline-only)")
    args = parser.parse_args()

    # Get API token
    api_token = os.environ.get("APIFY_API_TOKEN")
    if not api_token:
        print("Error: APIFY_API_TOKEN environment variable required")
        exit(1)

    # Paths
    funds_path = PROJECT_ROOT / "data" / "derived" / "linkedin" / "fund_linkedin_urls.json"
    output_dir = PROJECT_ROOT / "data" / "derived" / "linkedin"

    # Generate prioritized list before running (if using priority)
    if not args.no_priority:
        print("Generating prioritized fund order...")
        create_prioritized_linkedin_urls(project_root)
        print()

    run_batch_scrape(
        funds_path=funds_path,
        output_dir=output_dir,
        api_token=api_token,
        max_employees=args.max_employees,
        batch_size=args.batch_size,
        max_cost_usd=args.max_cost,
        resume=not args.no_resume,
        use_priority=not args.no_priority,
        delay_seconds=args.delay,
        use_basic_actor=not args.rich,
    )
