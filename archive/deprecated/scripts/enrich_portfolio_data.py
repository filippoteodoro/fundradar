#!/usr/bin/env python3
"""
Enrich portfolio entries with missing sector AND headquarters using OpenAI API.

Batches companies together and asks for both fields in one call to minimize tokens.
Only uses GPT knowledge (no web search) — cheapest possible approach.

Usage:
    python apps/worker/scripts/enrich_portfolio_data.py [--dry-run] [--limit N] [--slug SLUG]

Reads OPENAI_API_KEY from .env file.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv, dotenv_values

try:
    from openai import OpenAI
except ImportError:
    print("Error: openai package not installed.")
    print("Install with: pip install openai python-dotenv")
    sys.exit(1)

# ── Paths ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH, override=False)
if ENV_PATH.exists() and not os.environ.get("OPENAI_API_KEY"):
    env_vars = dotenv_values(ENV_PATH)
    if env_vars.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = env_vars["OPENAI_API_KEY"]

# Add worker package to path for io_utils
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "worker"))

DATA_DIR = PROJECT_ROOT / "data" / "derived"
PORTFOLIO_FILE = DATA_DIR / "portfolio_items.json"
PROGRESS_FILE = DATA_DIR / "enrichment_data_progress.json"

# ── Config ─────────────────────────────────────────────────────────────────────

MODEL = "gpt-5-mini"
BATCH_SIZE = 25  # Large batches — simple questions, low per-company overhead
REQUESTS_PER_MINUTE = 20
DELAY_BETWEEN_REQUESTS = 60.0 / REQUESTS_PER_MINUTE

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

SECTOR_KEYWORDS = {
    "software": "Software", "saas": "Software", "cloud": "Software",
    "cybersecurity": "Software", "it services": "Technology",
    "information technology": "Technology", "tech": "Technology",
    "digital": "Technology", "artificial intelligence": "Technology",
    "fintech": "Financial Services", "banking": "Financial Services",
    "financial": "Financial Services", "payment": "Financial Services",
    "insurance": "Insurance", "insurtech": "Insurance",
    "healthcare": "Healthcare", "medical": "Healthcare",
    "health": "Healthcare", "pharma": "Biotech & Pharma",
    "biotech": "Biotech & Pharma", "life science": "Biotech & Pharma",
    "consumer": "Consumer Goods", "fmcg": "Consumer Goods",
    "retail": "Retail", "e-commerce": "Retail", "ecommerce": "Retail",
    "food": "Food & Beverage", "beverage": "Food & Beverage",
    "restaurant": "Food & Beverage", "catering": "Food & Beverage",
    "industrial": "Industrial Manufacturing",
    "manufacturing": "Industrial Manufacturing",
    "machinery": "Industrial Manufacturing",
    "automotive": "Automotive", "vehicle": "Automotive",
    "aerospace": "Aerospace & Defense", "defense": "Aerospace & Defense",
    "energy": "Energy", "oil": "Energy", "gas": "Energy",
    "renewable": "Renewable Energy", "solar": "Renewable Energy",
    "clean energy": "Renewable Energy",
    "telecom": "Telecommunications",
    "media": "Media & Entertainment", "entertainment": "Media & Entertainment",
    "gaming": "Media & Entertainment",
    "education": "Education", "edtech": "Education",
    "real estate": "Real Estate", "property": "Real Estate",
    "construction": "Construction", "building": "Construction",
    "transport": "Transportation & Logistics",
    "logistics": "Transportation & Logistics",
    "shipping": "Transportation & Logistics",
    "agriculture": "Agriculture", "agri": "Agriculture",
    "chemical": "Chemicals", "specialty chemical": "Chemicals",
    "environmental": "Environmental Services",
    "waste": "Waste Management", "recycling": "Waste Management",
    "consulting": "Professional Services",
    "professional services": "Professional Services",
    "advisory": "Professional Services",
    "hospitality": "Hospitality & Tourism", "hotel": "Hospitality & Tourism",
    "tourism": "Hospitality & Tourism", "travel": "Hospitality & Tourism",
    "fashion": "Fashion & Luxury", "luxury": "Fashion & Luxury",
    "apparel": "Fashion & Luxury",
    "packaging": "Packaging",
    "water": "Water & Utilities", "utility": "Water & Utilities",
    "utilities": "Water & Utilities",
    "mining": "Mining & Metals", "metal": "Mining & Metals",
    "steel": "Mining & Metals",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _map_to_taxonomy(raw: str | None) -> str | None:
    """Map free-text sector to canonical taxonomy."""
    if not raw:
        return None
    if raw in SECTOR_TAXONOMY:
        return raw
    lower = raw.lower()
    for kw, canonical in SECTOR_KEYWORDS.items():
        if kw in lower:
            return canonical
    return None


def _verify_url(url: str) -> bool:
    """Quick HEAD check on a URL."""
    import urllib.request
    if not url or not url.startswith("http"):
        return False
    trusted = ("wikipedia.org", "linkedin.com", "crunchbase.com", "bloomberg.com")
    if any(d in url for d in trusted):
        return True
    try:
        req = urllib.request.Request(url, method="HEAD", headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status < 400
    except Exception:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            })
            resp = urllib.request.urlopen(req, timeout=5)
            resp.read(256)
            return resp.status < 400
        except Exception:
            return False


def _verify_urls_parallel(results: list[dict]) -> None:
    """Verify sector_source_url in parallel, null out invalid ones."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    to_check = [(i, r.get("sector_source_url"))
                for i, r in enumerate(results)
                if r.get("sector_source_url") and r.get("sector")]
    if not to_check:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_verify_url, url): idx for idx, url in to_check}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                if not fut.result():
                    results[idx]["sector_source_url"] = None
            except Exception:
                results[idx]["sector_source_url"] = None


# ── Prompt ─────────────────────────────────────────────────────────────────────

SYSTEM_MSG = (
    "You classify portfolio companies of Italian PE/VC funds. "
    "Return only valid JSON, no explanation."
)


def build_prompt(companies: list[dict], fund_name: str) -> str:
    """Build a minimal-token prompt for both sector + HQ."""

    # Build compact company list — include description snippet if available
    lines = []
    for c in companies:
        parts = [c["name"]]
        if c.get("description"):
            parts.append(f"({c['description'][:80]})")
        if c.get("website"):
            parts.append(f"[{c['website']}]")
        lines.append("- " + " ".join(parts))
    company_block = "\n".join(lines)

    # Only list fields we actually need — keep sector list compact
    sectors_compact = ", ".join(SECTOR_TAXONOMY)

    # Determine which fields we need per company
    needs = []
    for c in companies:
        missing = []
        if not c.get("sector"):
            missing.append("sector")
        if not c.get("headquarters"):
            missing.append("hq")
        needs.append(f"{c['name']}: {'+'.join(missing)}")

    return f"""Fund: {fund_name}

Companies:
{company_block}

For each company, provide missing fields.
- sector: one of [{sectors_compact}] or null
- hq: city name (e.g. "Milan, Italy") or null if unknown
- sector_source_url: company website URL where sector can be confirmed, or null
Only fill fields the company is missing. If unsure, use null.

Return JSON: {{"results":[{{"company":"name","sector":"X or null","hq":"City, Country or null","sector_source_url":"url or null"}}]}}"""


# ── API Call ───────────────────────────────────────────────────────────────────

def enrich_batch(client: OpenAI, companies: list[dict], fund_name: str) -> list[dict]:
    """Call GPT to enrich a batch of companies."""
    prompt = build_prompt(companies, fund_name)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=3000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            return []

        data = json.loads(content)
        results = data.get("results", [])

        # Normalize sectors
        for r in results:
            raw_sector = r.get("sector")
            if raw_sector:
                r["sector"] = _map_to_taxonomy(raw_sector)

        return results

    except Exception as e:
        print(f"  API error: {e}")
        return []


# ── Progress ───────────────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"done": {}}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Enrich portfolio sector + HQ via OpenAI")
    parser.add_argument("--dry-run", action="store_true", help="Preview without calling API")
    parser.add_argument("--limit", type=int, default=0, help="Max API calls (0=unlimited)")
    parser.add_argument("--slug", type=str, help="Only process one fund slug")
    parser.add_argument("--sector-only", action="store_true", help="Only enrich missing sectors")
    parser.add_argument("--hq-only", action="store_true", help="Only enrich missing HQ")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        print("Error: OPENAI_API_KEY not found in .env")
        sys.exit(1)

    # Load data
    with open(PORTFOLIO_FILE) as f:
        portfolio = json.load(f)
    fund_portfolios = portfolio.get("fund_portfolios", {})

    # Load fund names
    db_path = PROJECT_ROOT / "data" / "db.json"
    fund_names = {}
    if db_path.exists():
        db = json.load(open(db_path))
        for fund in db.get("funds", []):
            fund_names[fund["slug"]] = fund.get("name", fund["slug"])

    # Load progress
    progress = load_progress()
    done = progress.get("done", {})

    # Find entries needing enrichment
    work_items = []  # (slug, [entries])
    for slug, entries in sorted(fund_portfolios.items()):
        if args.slug and slug != args.slug:
            continue

        needs_work = []
        for e in entries:
            cache_key = f"{slug}::{e.get('name', '')}"
            if cache_key in done:
                continue

            needs_sector = not e.get("sector") and not args.hq_only
            needs_hq = not e.get("headquarters") and not args.sector_only

            if needs_sector or needs_hq:
                needs_work.append(e)

        if needs_work:
            work_items.append((slug, needs_work))

    total = sum(len(e) for _, e in work_items)
    batches = sum((len(e) + BATCH_SIZE - 1) // BATCH_SIZE for _, e in work_items)
    est_minutes = batches * DELAY_BETWEEN_REQUESTS / 60

    print(f"Entries to enrich: {total} across {len(work_items)} funds")
    print(f"API calls needed:  {batches}")
    print(f"Estimated time:    ~{est_minutes:.0f} min")
    print(f"Estimated cost:    ~${batches * 0.002:.2f} (gpt-5-mini, ~500 tokens/call)")
    print()

    if args.dry_run:
        for slug, entries in work_items[:15]:
            missing_s = sum(1 for e in entries if not e.get("sector"))
            missing_h = sum(1 for e in entries if not e.get("headquarters"))
            print(f"  {slug}: {len(entries)} entries (sector:{missing_s}, hq:{missing_h})")
            for e in entries[:3]:
                print(f"    - {e.get('name')}")
            if len(entries) > 3:
                print(f"    ... +{len(entries) - 3} more")
        if len(work_items) > 15:
            print(f"  ... +{len(work_items) - 15} more funds")
        return

    # Initialize client
    client = OpenAI(api_key=api_key)
    api_calls = 0
    enriched_sectors = 0
    enriched_hqs = 0
    skipped = 0

    for fund_idx, (slug, entries) in enumerate(work_items):
        fund_name = fund_names.get(slug, slug)
        print(f"\n[{fund_idx + 1}/{len(work_items)}] {fund_name} ({slug}): {len(entries)} entries")

        for batch_start in range(0, len(entries), BATCH_SIZE):
            if args.limit and api_calls >= args.limit:
                print(f"\nReached limit ({args.limit} calls)")
                break

            batch = entries[batch_start: batch_start + BATCH_SIZE]
            results = enrich_batch(client, batch, fund_name)
            api_calls += 1

            # Index results by normalized name
            results_map = {}
            for r in results:
                rname = r.get("company", "").lower().strip()
                results_map[rname] = r

            # Verify sector source URLs
            _verify_urls_parallel(results)

            # Apply results
            for entry in batch:
                name = entry.get("name", "")
                cache_key = f"{slug}::{name}"
                r = results_map.get(name.lower().strip())

                applied = False

                if r:
                    # Sector
                    if (not entry.get("sector")
                            and r.get("sector")
                            and r.get("sector_source_url")):
                        entry["sector"] = r["sector"]
                        entry["sector_source_url"] = r["sector_source_url"]
                        enriched_sectors += 1
                        applied = True
                        print(f"  + {name} sector={r['sector']}")

                    # Headquarters
                    if not entry.get("headquarters") and r.get("hq"):
                        entry["headquarters"] = r["hq"]
                        enriched_hqs += 1
                        applied = True
                        print(f"  + {name} hq={r['hq']}")

                if not applied:
                    skipped += 1

                done[cache_key] = True

            time.sleep(DELAY_BETWEEN_REQUESTS)

            # Periodic save
            if api_calls % 5 == 0:
                save_progress(progress)
                _write_portfolio(portfolio)
                print(f"  [saved] calls={api_calls} sectors={enriched_sectors} hqs={enriched_hqs}")

        if args.limit and api_calls >= args.limit:
            break

    # Final save
    save_progress(progress)
    _write_portfolio(portfolio)
    print(f"\nDone. Sectors: +{enriched_sectors}, HQs: +{enriched_hqs}, Skipped: {skipped}, API calls: {api_calls}")


def _write_portfolio(portfolio: dict):
    """Write portfolio atomically."""
    try:
        from fundradar_worker.io_utils import safe_json_write, backup_before_write
        backup_before_write(PORTFOLIO_FILE)
        safe_json_write(PORTFOLIO_FILE, portfolio)
    except ImportError:
        # Fallback if io_utils not importable
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".json")
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(portfolio, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(PORTFOLIO_FILE))
    print(f"  Written to {PORTFOLIO_FILE}")


if __name__ == "__main__":
    main()
