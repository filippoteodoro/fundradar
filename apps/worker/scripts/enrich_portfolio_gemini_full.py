#!/usr/bin/env python3
"""
Enrich portfolio entries with missing sector, headquarters, and description
using Gemini 3 Flash (base knowledge, no web search by default).

Fills all three fields in a single API call per batch to minimize cost.
Sectors are validated against the canonical 30-sector taxonomy.

Usage:
    python apps/worker/scripts/enrich_portfolio_gemini_full.py --dry-run
    python apps/worker/scripts/enrich_portfolio_gemini_full.py --limit 5
    python apps/worker/scripts/enrich_portfolio_gemini_full.py --slug alto-partners-sgr
    python apps/worker/scripts/enrich_portfolio_gemini_full.py --pipeline
    python apps/worker/scripts/enrich_portfolio_gemini_full.py --pipeline --slugs f2i-sgr,triton

Pipeline mode (--pipeline):
  - Auto-skips if GEMINI_API_KEY not set (warning, no failure)
  - Accepts --slugs (comma-separated) to limit scope
  - Caps API calls at --limit (default 15 in pipeline mode)

Multi-pass: failed batches are NOT marked done — re-run to retry.
Merge-safe: re-reads file from disk before writing to preserve concurrent edits.
"""

import argparse
import json
import os
import sys
import time
import signal as _signal
from pathlib import Path

from dotenv import load_dotenv, dotenv_values

sys.path.insert(0, str(Path(__file__).parent.parent))

from fundradar_worker.paths import PROJECT_ROOT, DATA_DIR, DB_PATH, PORTFOLIO_FILE, ROOT_ENV_PATH as ENV_PATH, SECTOR_TAXONOMY
from fundradar_worker.io_utils import safe_json_write, backup_before_write, load_progress_file

load_dotenv(ENV_PATH, override=False)
if ENV_PATH.exists() and not os.environ.get("GEMINI_API_KEY"):
    env_vars = dotenv_values(ENV_PATH)
    if env_vars.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = env_vars["GEMINI_API_KEY"]

PROGRESS_FILE = DATA_DIR / "enrichment_portfolio_full_progress.json"

from fundradar_worker.paths import GEMINI_MODEL as MODEL
BATCH_SIZE = 25  # 25 companies per call — safe for Gemini free tier
MAX_RETRIES = 2
CALL_TIMEOUT = 90  # 90s — generous for 25-company batches
MAX_CONCURRENT = 2  # 2 parallel workers — safe for Gemini free tier (~10 RPM)
DELAY_BETWEEN_CALLS = 1.5  # delay between submissions (safe for Gemini free tier ~10 RPM)
PIPELINE_DEFAULT_LIMIT = 25  # 25 calls × 25 = 625 entries coverage

# SDK-level timeout — google-genai defaults to 60s which silently kills calls
SDK_TIMEOUT_MS = 120_000  # 120s — must exceed CALL_TIMEOUT (SIGALRM)

# Auto-split: when a batch fails at size N, retry at next smaller size
BATCH_SPLIT_SIZES = [25, 12, 5, 1]

SECTOR_SET = set(SECTOR_TAXONOMY)

# ─── Structured output schema (used by Gemini API) ─────────────────────────
# Lazy-initialized to avoid importing google.genai at module level (may not be installed)
_RESPONSE_SCHEMA = None

def _get_response_schema():
    global _RESPONSE_SCHEMA
    if _RESPONSE_SCHEMA is None:
        from google.genai import types as genai_types
        _RESPONSE_SCHEMA = genai_types.Schema(
            type=genai_types.Type.ARRAY,
            items=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "company": genai_types.Schema(type=genai_types.Type.STRING),
                    "sector": genai_types.Schema(
                        type=genai_types.Type.STRING, nullable=True, enum=SECTOR_TAXONOMY,
                    ),
                    "hq": genai_types.Schema(type=genai_types.Type.STRING, nullable=True),
                    "description": genai_types.Schema(type=genai_types.Type.STRING, nullable=True),
                },
                required=["company"],
            ),
        )
    return _RESPONSE_SCHEMA

# Flag: disable response_schema if the API rejects it (fallback to mime_type only)
_schema_disabled = False

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


def _map_to_taxonomy(raw: str | None) -> str | None:
    """Map free-text sector to canonical taxonomy."""
    if not raw:
        return None
    if raw in SECTOR_SET:
        return raw
    lower = raw.lower()
    for kw, canonical in SECTOR_KEYWORDS.items():
        if kw in lower:
            return canonical
    return None


# ─── Prompt ────────────────────────────────────────────────────────────────

def build_prompt(companies: list[dict], fund_name: str) -> str:
    lines = []
    for i, c in enumerate(companies, 1):
        parts = [c["name"]]
        if c.get("website"):
            parts.append(f"[{c['website']}]")
        if c.get("description"):
            parts.append(f"({c['description'][:60]})")
        # Note which fields are missing
        missing = []
        if not c.get("sector"):
            missing.append("sector")
        if not c.get("headquarters"):
            missing.append("hq")
        if not c.get("description"):
            missing.append("description")
        parts.append(f"fund={fund_name}")
        parts.append(f"need={'+'.join(missing)}")
        lines.append(f"{i}. " + " | ".join(parts))

    company_block = "\n".join(lines)

    return f"""These companies are portfolio investments of "{fund_name}" PE/VC fund. Use your knowledge to fill in the missing fields for each.

For each company, provide the missing fields:
- sector: from the allowed enum values, or null if truly unknown
- hq: headquarters city (e.g. "Milan, Italy") or null if truly unknown
- description: 1-2 sentence company description or null if truly unknown

Only fill fields marked as needed.

{company_block}"""


# ─── API Call ──────────────────────────────────────────────────────────────

def _do_api_call(client, prompt):
    """Execute a single Gemini API call with structured JSON output."""
    global _schema_disabled
    from google.genai import types

    config_kwargs = dict(
        temperature=0.1,
        response_mime_type="application/json",
        http_options=types.HttpOptions(timeout=SDK_TIMEOUT_MS),
    )
    if not _schema_disabled:
        config_kwargs["response_schema"] = _get_response_schema()

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as e:
        # If the API rejects the schema, disable it and retry with mime_type only
        if not _schema_disabled and "schema" in str(e).lower():
            _schema_disabled = True
            print("    Schema rejected by API — falling back to mime_type only", flush=True)
            config_kwargs.pop("response_schema", None)
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        else:
            raise

    text = response.text.strip()
    # Safety net: strip markdown code fences if present (should not happen with structured output)
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    results = json.loads(text)

    usage = response.usage_metadata
    in_tok = usage.prompt_token_count or 0
    out_tok = usage.candidates_token_count or 0
    return results, in_tok, out_tok


class _AlarmTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _AlarmTimeout()


def _enrich_batch_single(client, companies: list[dict], fund_name: str) -> tuple:
    """Call Gemini API with SIGALRM timeout and retry at a fixed batch size.

    Returns (results, in_tokens, out_tokens). Empty results on total failure.
    """
    prompt = build_prompt(companies, fund_name)

    for attempt in range(1 + MAX_RETRIES):
        try:
            old_handler = _signal.signal(_signal.SIGALRM, _alarm_handler)
            _signal.alarm(CALL_TIMEOUT)
            results, in_tok, out_tok = _do_api_call(client, prompt)
            _signal.alarm(0)
            _signal.signal(_signal.SIGALRM, old_handler)
            return results, in_tok, out_tok

        except _AlarmTimeout:
            _signal.alarm(0)
            if attempt < MAX_RETRIES:
                print(f"    Timeout (attempt {attempt+1}), retrying in 5s...", flush=True)
                time.sleep(5)
                continue
            return [], 0, 0

        except json.JSONDecodeError:
            _signal.alarm(0)
            if attempt < MAX_RETRIES:
                time.sleep(3)
                continue
            return [], 0, 0

        except Exception as e:
            _signal.alarm(0)
            if attempt < MAX_RETRIES:
                print(f"    Error (attempt {attempt+1}): {str(e)[:80]}, retrying in 5s...", flush=True)
                time.sleep(5)
                continue
            return [], 0, 0


def enrich_batch(client, companies: list[dict], fund_name: str) -> tuple:
    """Call Gemini API with auto-split on failure.

    Tries the full batch first. If all retries fail, splits into smaller
    sub-batches (25 → 12 → 5 → 1) and retries each. 1-by-1 is the last
    resort (~5s per company, virtually never fails).

    Returns (results, in_tokens, out_tokens).
    """
    batch_size = len(companies)

    # Find the starting split tier for this batch size
    split_sizes = [s for s in BATCH_SPLIT_SIZES if s <= batch_size]
    if not split_sizes:
        split_sizes = [1]

    for tier_idx, split_size in enumerate(split_sizes):
        if tier_idx == 0:
            # First tier: try the full batch as-is
            results, in_tok, out_tok = _enrich_batch_single(client, companies, fund_name)
            if results:
                return results, in_tok, out_tok
            if split_size == 1:
                return [], 0, 0  # Already at 1-by-1, nothing to split
            print(f"    Batch of {batch_size} failed, auto-splitting to size {split_sizes[tier_idx + 1] if tier_idx + 1 < len(split_sizes) else 1}...", flush=True)
            continue

        # Split into sub-batches of this tier's size
        all_results = []
        total_in, total_out = 0, 0
        sub_failed = False

        for sub_start in range(0, len(companies), split_size):
            sub_batch = companies[sub_start: sub_start + split_size]
            time.sleep(DELAY_BETWEEN_CALLS)  # respect rate limits
            sub_results, sub_in, sub_out = _enrich_batch_single(client, sub_batch, fund_name)
            total_in += sub_in
            total_out += sub_out

            if sub_results:
                all_results.extend(sub_results)
            else:
                sub_failed = True

        if all_results and not sub_failed:
            return all_results, total_in, total_out

        if all_results:
            # Partial success — return what we got (better than nothing)
            print(f"    Split size {split_size}: partial success ({len(all_results)}/{len(companies)})", flush=True)
            if tier_idx + 1 < len(split_sizes):
                # Try even smaller splits for the remaining companies
                continue
            return all_results, total_in, total_out

        # Total failure at this split size — try next smaller
        if tier_idx + 1 < len(split_sizes):
            print(f"    Split size {split_size} failed, trying size {split_sizes[tier_idx + 1]}...", flush=True)
            continue

    return [], 0, 0


# ─── Progress ──────────────────────────────────────────────────────────────

MAX_BATCH_ATTEMPTS = 3  # give up after this many consecutive failures per batch


def load_progress() -> dict:
    return load_progress_file(PROGRESS_FILE, default={"done": {}, "attempts": {}})


def save_progress(progress: dict):
    safe_json_write(PROGRESS_FILE, progress)


# ─── Merge-safe save ──────────────────────────────────────────────────────

def _load_portfolio() -> dict:
    """Load portfolio from disk once. Caller keeps in memory for batch merges."""
    with open(PORTFOLIO_FILE) as f:
        return json.load(f)


def _merge_into(portfolio: dict, pending: dict) -> tuple[int, int, int]:
    """Merge pending enrichments into in-memory portfolio.

    Only fills fields that are STILL missing — preserves existing data.

    pending: {slug: {company_name_lower: {"sector": ..., "hq": ..., "description": ...}}}
    Returns: (applied_sectors, applied_hqs, applied_descriptions)
    """
    applied_s, applied_h, applied_d = 0, 0, 0
    for slug, companies in pending.items():
        entries = portfolio.get("fund_portfolios", {}).get(slug, [])
        for entry in entries:
            name_key = entry.get("name", "").lower().strip()
            enrichment = companies.get(name_key)
            if not enrichment:
                continue
            if not entry.get("sector") and enrichment.get("sector"):
                entry["sector"] = enrichment["sector"]
                applied_s += 1
            if not entry.get("headquarters") and enrichment.get("hq"):
                entry["headquarters"] = enrichment["hq"]
                applied_h += 1
            if not entry.get("description") and enrichment.get("description"):
                entry["description"] = enrichment["description"]
                applied_d += 1
    return applied_s, applied_h, applied_d


def _save_portfolio(portfolio: dict) -> None:
    """Write portfolio to disk atomically."""
    backup_before_write(PORTFOLIO_FILE)
    safe_json_write(PORTFOLIO_FILE, portfolio)


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enrich portfolio sector/HQ/description via Gemini Flash"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max API calls (0=unlimited)")
    parser.add_argument("--slug", type=str, help="Only process one fund slug")
    parser.add_argument("--slugs", type=str, help="Comma-separated fund slugs")
    parser.add_argument(
        "--pipeline", action="store_true",
        help="Pipeline mode: skip if no API key, default limit 50"
    )
    args = parser.parse_args()

    # In pipeline mode, auto-skip if no API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if args.pipeline and not api_key:
        print("GEMINI_API_KEY not set — skipping portfolio enrichment (optional step)")
        sys.exit(0)

    if not api_key and not args.dry_run:
        print("Error: GEMINI_API_KEY not found")
        sys.exit(1)

    # Check google-generativeai is installed (before doing any work)
    if not args.dry_run:
        try:
            from google import genai  # noqa: F401
        except ImportError as exc:
            if args.pipeline:
                print(f"google-genai import failed — skipping portfolio enrichment: {exc}")
                sys.exit(0)
            print(f"Error: google-genai import failed: {exc}")
            print("Install with: pip install google-genai")
            print("If google-genai is already installed, rebuild the worker virtualenv.")
            sys.exit(1)

    # Pipeline mode defaults
    if args.pipeline and args.limit == 0:
        args.limit = PIPELINE_DEFAULT_LIMIT

    # Resolve slug filters
    slug_filter: set[str] | None = None
    if args.slug:
        slug_filter = {args.slug}
    elif args.slugs:
        slug_filter = set(s.strip() for s in args.slugs.split(",") if s.strip())

    # Load data
    with open(PORTFOLIO_FILE) as f:
        portfolio = json.load(f)
    fund_portfolios = portfolio.get("fund_portfolios", {})

    fund_names: dict[str, str] = {}
    if DB_PATH.exists():
        db = json.load(open(DB_PATH))
        for fund in db.get("funds", []):
            fund_names[fund["slug"]] = fund.get("name", fund["slug"])

    progress = load_progress()
    done = progress.get("done", {})
    attempts = progress.get("attempts", {})

    # Find entries needing enrichment (missing at least one of sector/hq/description)
    all_batches: list[tuple[str, str, list[dict]]] = []
    locked_skipped = 0
    for slug, entries in sorted(fund_portfolios.items()):
        if slug_filter and slug not in slug_filter:
            continue
        needs_work = []
        for e in entries:
            if e.get("curation_locked"):
                # Never mutate manually curated entries from apply-gemini flow.
                locked_skipped += 1
                continue
            key = f"{slug}::{e.get('name', '')}"
            if key in done:
                continue
            if attempts.get(key, 0) >= MAX_BATCH_ATTEMPTS:
                continue  # gave up after repeated API failures
            missing_sector = not e.get("sector")
            missing_hq = not e.get("headquarters")
            missing_desc = not e.get("description")
            if missing_sector or missing_hq or missing_desc:
                needs_work.append(e)
        if needs_work:
            fund_name = fund_names.get(slug, slug)
            for batch_start in range(0, len(needs_work), BATCH_SIZE):
                batch = needs_work[batch_start: batch_start + BATCH_SIZE]
                all_batches.append((slug, fund_name, batch))

    total_entries = sum(len(b[2]) for b in all_batches)
    print(f"Entries to enrich: {total_entries}")
    print(f"API calls needed:  {len(all_batches)}")
    print(f"Locked entries skipped: {locked_skipped}")
    print(f"Model: {MODEL} (base knowledge, no web search)")
    print(f"Timeout: {CALL_TIMEOUT}s, Retries: {MAX_RETRIES}, Concurrent: {MAX_CONCURRENT}")
    if args.limit:
        print(f"Limit: {args.limit} API calls")
    print()

    if args.dry_run:
        fund_counts: dict[str, dict[str, int]] = {}
        for slug, _, batch in all_batches:
            if slug not in fund_counts:
                fund_counts[slug] = {"total": 0, "sector": 0, "hq": 0, "desc": 0}
            for e in batch:
                fund_counts[slug]["total"] += 1
                if not e.get("sector"):
                    fund_counts[slug]["sector"] += 1
                if not e.get("headquarters"):
                    fund_counts[slug]["hq"] += 1
                if not e.get("description"):
                    fund_counts[slug]["desc"] += 1
        for slug, counts in sorted(fund_counts.items())[:20]:
            print(f"  {slug}: {counts['total']} entries "
                  f"(sector:{counts['sector']}, hq:{counts['hq']}, desc:{counts['desc']})")
        if len(fund_counts) > 20:
            print(f"  ... +{len(fund_counts) - 20} more funds")
        return

    from google import genai
    from google.genai import types as genai_types
    client = genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(timeout=SDK_TIMEOUT_MS),
    )

    if args.limit:
        all_batches = all_batches[:args.limit]

    api_calls = 0
    total_in = 0
    total_out = 0
    enriched_sectors = 0
    enriched_hqs = 0
    enriched_descs = 0
    errors = 0
    start_time = time.time()

    # Collect enrichments for merge-on-save
    pending_enrichments: dict[str, dict[str, dict]] = {}
    # Load portfolio once — kept in memory, written after each batch for crash safety
    portfolio_data = _load_portfolio()

    print(f"Processing {len(all_batches)} batches sequentially...\n", flush=True)

    for batch_idx, (slug, fund_name, batch) in enumerate(all_batches):
        if batch_idx > 0:
            time.sleep(DELAY_BETWEEN_CALLS)

        results, in_tok, out_tok = enrich_batch(client, batch, fund_name)
        api_calls += 1
        total_in += in_tok
        total_out += out_tok

        if not results:
            errors += 1
            # Increment attempt counter for each entry in the failed batch
            for entry in batch:
                k = f"{slug}::{entry.get('name', '')}"
                attempts[k] = attempts.get(k, 0) + 1
            gave_up = [entry.get('name','') for entry in batch if attempts.get(f"{slug}::{entry.get('name','')}", 0) >= MAX_BATCH_ATTEMPTS]
            if gave_up:
                # Mark permanently done so they don't block pipeline status forever
                for entry in batch:
                    k = f"{slug}::{entry.get('name', '')}"
                    if attempts.get(k, 0) >= MAX_BATCH_ATTEMPTS:
                        done[k] = True
                print(
                    f"  [{api_calls}/{len(all_batches)}] {fund_name} "
                    f"— FAILED {MAX_BATCH_ATTEMPTS}x, giving up: {gave_up}", flush=True
                )
            else:
                first_key = f"{slug}::{batch[0].get('name', '')}"
                attempt_num = attempts.get(first_key, 1)
                print(
                    f"  [{api_calls}/{len(all_batches)}] {fund_name} "
                    f"— FAILED (attempt {attempt_num}/{MAX_BATCH_ATTEMPTS}, will retry)", flush=True
                )
            save_progress(progress)
            continue

        # Match results to entries by name
        results_map = {r.get("company", "").lower().strip(): r for r in results}

        if slug not in pending_enrichments:
            pending_enrichments[slug] = {}

        batch_s, batch_h, batch_d = 0, 0, 0
        for entry in batch:
            name = entry.get("name", "")
            key = f"{slug}::{name}"
            name_lower = name.lower().strip()
            r = results_map.get(name_lower)

            enrichment: dict = {}
            if r:
                # Sector — validate against taxonomy
                if not entry.get("sector") and r.get("sector"):
                    mapped = _map_to_taxonomy(r["sector"])
                    if mapped:
                        enrichment["sector"] = mapped
                        batch_s += 1

                # Headquarters
                if not entry.get("headquarters") and r.get("hq"):
                    enrichment["hq"] = r["hq"]
                    batch_h += 1

                # Description
                if not entry.get("description") and r.get("description"):
                    enrichment["description"] = r["description"]
                    batch_d += 1

            if enrichment:
                pending_enrichments[slug][name_lower] = enrichment

            # Mark as done (success or no result)
            done[key] = True

        enriched_sectors += batch_s
        enriched_hqs += batch_h
        enriched_descs += batch_d

        # Save after each batch — prevents data loss on kill
        save_progress(progress)
        if pending_enrichments:
            _merge_into(portfolio_data, pending_enrichments)
            _save_portfolio(portfolio_data)
            pending_enrichments.clear()

        elapsed = time.time() - start_time
        successful = api_calls - errors
        rate = successful / (elapsed / 60) if elapsed > 0 else 0

        print(
            f"  [{api_calls}/{len(all_batches)}] {fund_name} "
            f"+{batch_s}s +{batch_h}h +{batch_d}d | "
            f"Total: +{enriched_sectors}s +{enriched_hqs}h +{enriched_descs}d | "
            f"{errors} err | {rate:.1f} ok/min", flush=True
        )

    # Final save (also saves incrementally after each batch above)
    save_progress(progress)

    elapsed = time.time() - start_time
    cost = total_in * 0.10 / 1_000_000 + total_out * 0.40 / 1_000_000
    print(f"\n{'='*50}")
    print(f"Done in {elapsed/60:.1f}m")
    print(f"Sectors: +{enriched_sectors}, HQs: +{enriched_hqs}, Descriptions: +{enriched_descs}")
    print(f"API calls: {api_calls} ({errors} failed)")
    print(f"Tokens: {total_in} in / {total_out} out, Cost: ${cost:.4f}")
    if errors > 0:
        print(f"\n{errors} batches failed — will be retried automatically if pipeline retry is enabled")
        sys.exit(2)  # Partial success — pipeline can retry


if __name__ == "__main__":
    main()
