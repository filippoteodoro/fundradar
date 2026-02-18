#!/usr/bin/env python3
"""
Enrich portfolio entries with sector classification using OpenAI API.

Reads portfolio_items.json, finds entries missing sector, uses GPT to infer
the sector from the company name + fund context, and writes back.

Usage:
    python apps/worker/scripts/enrich_portfolio_sectors.py [--dry-run] [--limit N] [--slug SLUG]

Reads OPENAI_API_KEY from .env file.
"""

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv, dotenv_values

try:
    from openai import OpenAI
except ImportError:
    print("Error: openai package not installed.")
    print("Install with: pip install openai python-dotenv")
    exit(1)

# Load environment variables
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH, override=False)
if ENV_PATH.exists() and not os.environ.get("OPENAI_API_KEY"):
    env_vars = dotenv_values(ENV_PATH)
    if env_vars.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = env_vars["OPENAI_API_KEY"]

DATA_DIR = PROJECT_ROOT / "data" / "derived"
PORTFOLIO_FILE = DATA_DIR / "portfolio_items.json"
PROGRESS_FILE = DATA_DIR / "portfolio_enrichment_progress.json"

MODEL = "gpt-5-mini"
REQUESTS_PER_MINUTE = 20
DELAY_BETWEEN_REQUESTS = 60.0 / REQUESTS_PER_MINUTE
BATCH_SIZE = 15  # Companies per API call (batch for efficiency)

# Standard sector taxonomy for consistent classification
SECTOR_TAXONOMY = [
    "Technology", "Software", "Healthcare", "Biotech & Pharma",
    "Financial Services", "Insurance", "Consumer Goods", "Retail",
    "Food & Beverage", "Industrial Manufacturing", "Automotive",
    "Aerospace & Defense", "Energy", "Renewable Energy",
    "Telecommunications", "Media & Entertainment", "Education",
    "Real Estate", "Construction", "Transportation & Logistics",
    "Agriculture", "Chemicals", "Environmental Services",
    "Professional Services", "Hospitality & Tourism",
    "Fashion & Luxury", "Packaging", "Waste Management",
    "Water & Utilities", "Mining & Metals",
]

RESPONSE_FORMAT = {"type": "json_object"}

# Mapping keywords in free-text sectors to our taxonomy
SECTOR_KEYWORDS = {
    "software": "Software",
    "saas": "Software",
    "cloud": "Software",
    "cybersecurity": "Software",
    "it services": "Technology",
    "information technology": "Technology",
    "tech": "Technology",
    "digital": "Technology",
    "artificial intelligence": "Technology",
    "ai ": "Technology",
    "data analytics": "Technology",
    "fintech": "Financial Services",
    "banking": "Financial Services",
    "financial": "Financial Services",
    "asset management": "Financial Services",
    "payment": "Financial Services",
    "insurance": "Insurance",
    "insurtech": "Insurance",
    "healthcare": "Healthcare",
    "medical": "Healthcare",
    "health": "Healthcare",
    "hospital": "Healthcare",
    "diagnostic": "Healthcare",
    "pharma": "Biotech & Pharma",
    "biotech": "Biotech & Pharma",
    "life science": "Biotech & Pharma",
    "consumer": "Consumer Goods",
    "fmcg": "Consumer Goods",
    "cosmetic": "Consumer Goods",
    "personal care": "Consumer Goods",
    "retail": "Retail",
    "e-commerce": "Retail",
    "ecommerce": "Retail",
    "food": "Food & Beverage",
    "beverage": "Food & Beverage",
    "restaurant": "Food & Beverage",
    "catering": "Food & Beverage",
    "industrial": "Industrial Manufacturing",
    "manufacturing": "Industrial Manufacturing",
    "machinery": "Industrial Manufacturing",
    "automotive": "Automotive",
    "vehicle": "Automotive",
    "aerospace": "Aerospace & Defense",
    "defense": "Aerospace & Defense",
    "defence": "Aerospace & Defense",
    "energy": "Energy",
    "oil": "Energy",
    "gas": "Energy",
    "renewable": "Renewable Energy",
    "solar": "Renewable Energy",
    "wind energy": "Renewable Energy",
    "clean energy": "Renewable Energy",
    "telecom": "Telecommunications",
    "media": "Media & Entertainment",
    "entertainment": "Media & Entertainment",
    "gaming": "Media & Entertainment",
    "publishing": "Media & Entertainment",
    "education": "Education",
    "edtech": "Education",
    "training": "Education",
    "real estate": "Real Estate",
    "property": "Real Estate",
    "construction": "Construction",
    "building": "Construction",
    "transport": "Transportation & Logistics",
    "logistics": "Transportation & Logistics",
    "shipping": "Transportation & Logistics",
    "freight": "Transportation & Logistics",
    "agriculture": "Agriculture",
    "agri": "Agriculture",
    "farming": "Agriculture",
    "chemical": "Chemicals",
    "specialty chemical": "Chemicals",
    "environmental": "Environmental Services",
    "waste": "Waste Management",
    "recycling": "Waste Management",
    "consulting": "Professional Services",
    "professional services": "Professional Services",
    "advisory": "Professional Services",
    "accounting": "Professional Services",
    "legal": "Professional Services",
    "staffing": "Professional Services",
    "human resources": "Professional Services",
    "hr ": "Professional Services",
    "payroll": "Professional Services",
    "hospitality": "Hospitality & Tourism",
    "hotel": "Hospitality & Tourism",
    "tourism": "Hospitality & Tourism",
    "travel": "Hospitality & Tourism",
    "fashion": "Fashion & Luxury",
    "luxury": "Fashion & Luxury",
    "apparel": "Fashion & Luxury",
    "packaging": "Packaging",
    "water": "Water & Utilities",
    "utility": "Water & Utilities",
    "utilities": "Water & Utilities",
    "mining": "Mining & Metals",
    "metal": "Mining & Metals",
    "steel": "Mining & Metals",
}


def _map_to_taxonomy(free_text_sector: str | None) -> str | None:
    """Map a free-text sector description to our standard taxonomy."""
    if not free_text_sector:
        return None

    # Direct match
    if free_text_sector in SECTOR_TAXONOMY:
        return free_text_sector

    lower = free_text_sector.lower()
    for keyword, standard in SECTOR_KEYWORDS.items():
        if keyword in lower:
            return standard

    return None


def build_prompt(companies: list[dict], fund_name: str, fund_slug: str) -> str:
    """Build the prompt for sector classification."""
    company_list = "\n".join(
        f"- {c['name']}" + (f" (description: {c['description'][:100]})" if c.get("description") else "")
        for c in companies
    )

    sector_list = "\n".join(f"- {s}" for s in SECTOR_TAXONOMY)

    return f"""Classify each company into a sector. The companies are portfolio investments of "{fund_name}" ({fund_slug}).

You MUST use EXACTLY one of these standard sectors (copy the text exactly):
{sector_list}

For EACH company you MUST also provide a source_url — a real, verifiable URL where the sector can be confirmed. Acceptable sources (in order of preference):
1. The company's own website (e.g. https://www.companyname.com)
2. Wikipedia page (e.g. https://en.wikipedia.org/wiki/CompanyName)
3. LinkedIn company page (e.g. https://www.linkedin.com/company/companyname)
4. Bloomberg, Crunchbase, or other business directories

If you don't recognize the company, can't determine the sector, or can't provide a real source URL, set BOTH sector and source_url to null.
Only use "high" confidence if you are certain about the company identity AND the source URL is real.

Companies to classify:
{company_list}

Return JSON object with a "results" array. Each element: {{"company": "name", "sector": "one of the sectors above or null", "source_url": "verifiable URL or null", "confidence": "high"|"medium"|"low"}}"""


def _verify_url(url: str) -> bool:
    """Check that a URL is reachable (HEAD request, follow redirects)."""
    import urllib.request

    if not url or not url.startswith("http"):
        return False

    # Known-good domains that don't need verification
    trusted = ("wikipedia.org", "linkedin.com", "crunchbase.com", "bloomberg.com")
    if any(d in url for d in trusted):
        return True

    try:
        req = urllib.request.Request(url, method="HEAD", headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status < 400
    except Exception:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })
            resp = urllib.request.urlopen(req, timeout=5)
            resp.read(256)
            return resp.status < 400
        except Exception:
            return False


def _verify_urls_parallel(results: list[dict]) -> None:
    """Verify source URLs in parallel, setting invalid ones to None."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    to_check = [(i, r.get("source_url")) for i, r in enumerate(results)
                if r.get("source_url") and r.get("sector")]

    if not to_check:
        return

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_verify_url, url): idx for idx, url in to_check}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                if not future.result():
                    results[idx]["source_url"] = None
            except Exception:
                results[idx]["source_url"] = None


def classify_batch(
    client: OpenAI, companies: list[dict], fund_name: str, fund_slug: str
) -> list[dict]:
    """Classify a batch of companies using OpenAI."""
    prompt = build_prompt(companies, fund_name, fund_slug)

    system_msg = (
        "You are a financial analyst specializing in private equity. "
        "Classify portfolio companies into industry sectors. "
        "For each company, provide a real source URL (company website, Wikipedia, LinkedIn) "
        "where the sector can be verified. Return only valid JSON."
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=4096,
            response_format=RESPONSE_FORMAT,
        )

        content = response.choices[0].message.content
        if not content:
            return []

        data = json.loads(content)
        results = data.get("results", [])

        # Normalize sectors to taxonomy
        for r in results:
            raw_sector = r.get("sector")
            if raw_sector:
                mapped = _map_to_taxonomy(raw_sector)
                r["sector"] = mapped  # None if not mappable

        return results

    except Exception as e:
        print(f"  Error: {e}")
        return []


def load_progress() -> dict:
    """Load enrichment progress to avoid re-processing."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"enriched": {}}


def save_progress(progress: dict):
    """Save enrichment progress."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Enrich portfolio sectors via OpenAI")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without calling API")
    parser.add_argument("--limit", type=int, default=0, help="Max API calls (0 = unlimited)")
    parser.add_argument("--slug", type=str, help="Only process a specific fund slug")
    parser.add_argument("--min-entries", type=int, default=3, help="Skip funds with fewer entries")
    args = parser.parse_args()

    # Load API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        print("Error: OPENAI_API_KEY not found in environment or .env file")
        exit(1)

    # Load portfolio data
    with open(PORTFOLIO_FILE) as f:
        portfolio = json.load(f)

    fund_portfolios = portfolio.get("fund_portfolios", {})

    # Load fund names from db.json
    db_path = PROJECT_ROOT / "data" / "db.json"
    fund_names = {}
    if db_path.exists():
        db = json.load(open(db_path))
        for fund in db.get("funds", []):
            fund_names[fund["slug"]] = fund.get("name", fund["slug"])

    # Load progress
    progress = load_progress()
    enriched_cache = progress.get("enriched", {})

    # Find entries needing sectors
    work_items = []  # (fund_slug, entries_needing_sector)
    for slug, entries in sorted(fund_portfolios.items()):
        if args.slug and slug != args.slug:
            continue
        if len(entries) < args.min_entries:
            continue

        needs_sector = [e for e in entries if not e.get("sector")]
        if not needs_sector:
            continue

        # Filter out already-enriched entries
        unenriched = []
        for e in needs_sector:
            cache_key = f"{slug}:{e.get('name', '')}"
            if cache_key not in enriched_cache:
                unenriched.append(e)

        if unenriched:
            work_items.append((slug, unenriched))

    total_entries = sum(len(entries) for _, entries in work_items)
    total_batches = sum((len(entries) + BATCH_SIZE - 1) // BATCH_SIZE for _, entries in work_items)
    print(f"Entries needing sector: {total_entries} across {len(work_items)} funds")
    print(f"Estimated API calls: {total_batches}")
    print(f"Estimated time: ~{total_batches * DELAY_BETWEEN_REQUESTS / 60:.1f} minutes")
    print()

    if args.dry_run:
        for slug, entries in work_items[:10]:
            print(f"  {slug}: {len(entries)} entries need sector")
            for e in entries[:3]:
                print(f"    - {e.get('name')}")
            if len(entries) > 3:
                print(f"    ... and {len(entries) - 3} more")
        if len(work_items) > 10:
            print(f"  ... and {len(work_items) - 10} more funds")
        return

    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)

    api_calls = 0
    enriched_count = 0
    skipped_count = 0

    for fund_idx, (slug, entries) in enumerate(work_items):
        fund_name = fund_names.get(slug, slug)
        print(f"\n[{fund_idx + 1}/{len(work_items)}] {fund_name} ({slug}): {len(entries)} entries")

        # Process in batches
        for batch_start in range(0, len(entries), BATCH_SIZE):
            if args.limit and api_calls >= args.limit:
                print(f"\nReached API call limit ({args.limit})")
                save_progress(progress)
                _write_portfolio(portfolio)
                print(f"\nDone. Enriched: {enriched_count}, Skipped: {skipped_count}, API calls: {api_calls}")
                return

            batch = entries[batch_start : batch_start + BATCH_SIZE]
            results = classify_batch(client, batch, fund_name, slug)
            api_calls += 1

            # Match results back to entries
            results_by_name = {}
            for r in results:
                rname = r.get("company", "").lower().strip()
                results_by_name[rname] = r

            # Verify source URLs in parallel
            _verify_urls_parallel(results)

            for entry in batch:
                name = entry.get("name", "")
                cache_key = f"{slug}:{name}"
                result = results_by_name.get(name.lower().strip())

                if (result and result.get("sector")
                        and result.get("confidence") in ("high", "medium")
                        and result.get("source_url")):
                    entry["sector"] = result["sector"]
                    entry["sector_source_url"] = result["source_url"]
                    enriched_cache[cache_key] = {
                        "sector": result["sector"],
                        "source_url": result["source_url"],
                    }
                    enriched_count += 1
                    print(f"  + {name} → {result['sector']} ({result['confidence']}) src={result['source_url']}")
                else:
                    reason = ""
                    if result and result.get("sector") and not result.get("source_url"):
                        reason = " (source URL invalid)"
                    enriched_cache[cache_key] = None  # Mark as attempted
                    skipped_count += 1
                    if reason:
                        print(f"  - {name}: skipped{reason}")

            time.sleep(DELAY_BETWEEN_REQUESTS)

            # Save progress periodically
            if api_calls % 10 == 0:
                save_progress(progress)

    # Final save
    save_progress(progress)
    _write_portfolio(portfolio)
    print(f"\nDone. Enriched: {enriched_count}, Skipped: {skipped_count}, API calls: {api_calls}")


def _write_portfolio(portfolio: dict):
    """Write portfolio back to disk atomically."""
    import tempfile

    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".json")
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, str(PORTFOLIO_FILE))
    print(f"Written to {PORTFOLIO_FILE}")


if __name__ == "__main__":
    main()
