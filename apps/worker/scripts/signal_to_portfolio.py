#!/usr/bin/env python3
"""
Convert deal/exit signals into portfolio entries.

Reads enriched signals, uses Gemini 3 Flash to extract structured company data,
deduplicates against existing portfolio, and adds new entries or updates exit status.

Usage:
    python apps/worker/scripts/signal_to_portfolio.py --dry-run
    python apps/worker/scripts/signal_to_portfolio.py --slugs cdp-venture-capital,wise-sgr
    python apps/worker/scripts/signal_to_portfolio.py --force

Pipeline mode (called from pipeline.py):
    python apps/worker/scripts/signal_to_portfolio.py --pipeline
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv, dotenv_values

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH, override=False)
if ENV_PATH.exists() and not os.environ.get("GEMINI_API_KEY"):
    env_vars = dotenv_values(ENV_PATH)
    if env_vars.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = env_vars["GEMINI_API_KEY"]

sys.path.insert(0, str(PROJECT_ROOT / "apps" / "worker"))

DATA_DIR = PROJECT_ROOT / "data" / "derived"
ENRICHED_SIGNALS_FILE = DATA_DIR / "detected_signals_enriched.json"
PORTFOLIO_FILE = DATA_DIR / "portfolio_items.json"
PROGRESS_FILE = DATA_DIR / "signal_to_portfolio_progress.json"
DB_PATH = PROJECT_ROOT / "data" / "db.json"

MODEL = "gemini-3-flash-preview"
BATCH_SIZE = 20
MAX_RETRIES = 2
CALL_TIMEOUT = 60
SDK_TIMEOUT_MS = 90_000
DELAY_BETWEEN_CALLS = 2.0

# Signal types to process
DEAL_TYPES = {"deal_announced", "exit_announced"}

# Canonical 30-sector taxonomy (same as enrich_portfolio_gemini_full.py)
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
SECTOR_SET = set(SECTOR_TAXONOMY)

# ─── Company name normalization (mirrors entity_resolver.py + data.ts) ─────

LEGAL_SUFFIXES_RE = re.compile(
    r"(?:\s+|,\s*)(?:"
    r"\bS\.?p\.?A\.?|\bS\.?r\.?l\.?|\bS\.?a\.?s\.?|\bS\.?n\.?c\.?"
    r"|\bLtd\.?|\bLLC\.?|\bInc\.?|\bGmbH\.?|\bAG\.?|\bB\.?V\.?"
    r"|\bN\.?V\.?|\bPLC\.?|\bCorp\.?|\bCorporation|\bCompany"
    r"|\bGroup|\bHolding|\bHoldings"
    r")\s*$",
    re.IGNORECASE,
)


def normalize_company_name(name: str) -> str:
    """Normalize company name for dedup matching."""
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"\s*\(.*\)", "", n)  # strip parenthetical
    n = re.sub(r"\s*logo\s*$", "", n, flags=re.IGNORECASE)
    # Repeatedly strip legal suffixes
    for _ in range(3):
        cleaned = LEGAL_SUFFIXES_RE.sub("", n).strip()
        if cleaned == n:
            break
        n = cleaned
    # Strip "technologies" at end
    n = re.sub(r"\s+technologies\s*$", "", n)
    # Non-alphanumeric to space, collapse
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return n


def compact_name(name: str) -> str:
    """Remove all spaces from normalized name."""
    return normalize_company_name(name).replace(" ", "")


def _matches_existing(new_name: str, existing_names: set[str], existing_compact: set[str]) -> bool:
    """Check if a company name matches any existing portfolio entry."""
    norm = normalize_company_name(new_name)
    if not norm:
        return False

    # 1. Exact normalized
    if norm in existing_names:
        return True

    # 2. Compact (no spaces)
    comp = norm.replace(" ", "")
    if comp in existing_compact:
        return True

    # 3. Word-boundary substring (≥5 chars) — new name inside existing or vice versa
    if len(norm) >= 5:
        for en in existing_names:
            if len(en) >= 5:
                if norm in en or en in norm:
                    return True

    return False


# ─── Source classification ─────────────────────────────────────────────────

def _get_fund_domain(fund_slug: str, funds_by_slug: dict) -> str | None:
    """Get the website domain for a fund."""
    fund = funds_by_slug.get(fund_slug)
    if not fund or not fund.get("website"):
        return None
    try:
        parsed = urlparse(fund["website"])
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return None


def classify_source(source_url: str | None, fund_domain: str | None) -> tuple[str, float]:
    """
    Classify signal source and assign confidence.

    Returns (data_source, confidence).
    """
    if not source_url:
        return "signal_rss", 0.70

    try:
        parsed = urlparse(source_url)
        source_domain = parsed.netloc.lower()
        if source_domain.startswith("www."):
            source_domain = source_domain[4:]
    except Exception:
        return "signal_rss", 0.70

    # Fund's own website = press release
    if fund_domain and source_domain == fund_domain:
        return "signal_fund_press", 0.90

    # Known industry journals
    NEWS_DOMAINS = {
        "bebeez.it", "financecommunity.it", "ilsole24ore.com",
        "startupitalia.eu", "milanofinanza.it", "reuters.com",
        "bloomberg.com", "corriere.it", "repubblica.it",
        "ansa.it", "dealflower.com", "privateequityitalia.it",
    }
    if source_domain in NEWS_DOMAINS:
        return "signal_news", 0.75

    return "signal_rss", 0.70


# ─── Gemini extraction ────────────────────────────────────────────────────

_RESPONSE_SCHEMA = None


def _get_response_schema():
    """Lazy-init Gemini structured output schema."""
    global _RESPONSE_SCHEMA
    if _RESPONSE_SCHEMA is None:
        from google.genai import types as genai_types
        _RESPONSE_SCHEMA = genai_types.Schema(
            type=genai_types.Type.ARRAY,
            items=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "signal_id": genai_types.Schema(type=genai_types.Type.STRING),
                    "target_company": genai_types.Schema(
                        type=genai_types.Type.STRING, nullable=True,
                    ),
                    "is_direct_investment": genai_types.Schema(
                        type=genai_types.Type.BOOLEAN,
                    ),
                    "action": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        enum=["investment", "exit", "other"],
                    ),
                    "sector": genai_types.Schema(
                        type=genai_types.Type.STRING, nullable=True,
                        enum=SECTOR_TAXONOMY,
                    ),
                    "headquarters": genai_types.Schema(
                        type=genai_types.Type.STRING, nullable=True,
                    ),
                    "investment_date": genai_types.Schema(
                        type=genai_types.Type.STRING, nullable=True,
                    ),
                },
                required=["signal_id", "is_direct_investment", "action"],
            ),
        )
    return _RESPONSE_SCHEMA


_schema_disabled = False


def build_prompt(fund_name: str, signals: list[dict]) -> str:
    """Build Gemini prompt for a batch of signals."""
    signal_lines = []
    for s in signals:
        parts = [
            f"id={s['id']}",
            f"type={s.get('signal_type', 'unknown')}",
            f"title={s.get('title', '')}",
        ]
        if s.get("what_changed"):
            parts.append(f"summary={s['what_changed'][:300]}")
        if s.get("published_at"):
            parts.append(f"date={s['published_at'][:10]}")
        if s.get("source_name"):
            parts.append(f"source={s['source_name']}")
        signal_lines.append(" | ".join(parts))

    signals_block = "\n".join(signal_lines)

    return f"""You are analyzing investment news signals for the PE/VC fund "{fund_name}".

For each signal, extract:
1. target_company: The company being invested in or exited from. Use the company's proper name (not the fund name). null if no specific company mentioned.
2. is_direct_investment: true if "{fund_name}" is directly investing in or exiting the target company. false if it's an add-on acquisition BY a portfolio company, or if the signal is about a different fund's deal.
3. action: "investment" if the fund is buying/investing, "exit" if the fund is selling/divesting, "other" for anything else.
4. sector: one of the allowed enum values if mentioned or clearly inferable, or null.
5. headquarters: city and country of the target company if mentioned (e.g. "Milan, Italy"), or null.
6. investment_date: date from the signal in YYYY-MM-DD format, or null.

IMPORTANT:
- "{fund_name}" is the fund we're tracking. Only mark is_direct_investment=true if THIS fund is the investor/seller.
- If the signal describes a portfolio company making an acquisition (bolt-on/add-on), set is_direct_investment=false.
- If you cannot identify a clear target company, set target_company=null.

Signals:
{signals_block}

Return a JSON array with one object per signal, matching by signal_id."""


def call_gemini(client, prompt: str) -> list[dict]:
    """Call Gemini API with structured output."""
    global _schema_disabled
    from google.genai import types

    config_kwargs = {
        "temperature": 0.1,
        "response_mime_type": "application/json",
    }
    if not _schema_disabled:
        config_kwargs["response_schema"] = _get_response_schema()

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as e:
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
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    return json.loads(text)


# ─── Progress tracking ─────────────────────────────────────────────────────

def load_progress() -> dict:
    """Load progress tracking file."""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"processed_signal_ids": [], "last_run": None, "stats": {}}


def save_progress(progress: dict):
    """Save progress tracking file."""
    from fundradar_worker.io_utils import safe_json_write
    safe_json_write(PROGRESS_FILE, progress)


# ─── Main logic ────────────────────────────────────────────────────────────

def load_funds_by_slug() -> dict:
    """Load db.json and return funds indexed by slug."""
    with open(DB_PATH) as f:
        data = json.load(f)
    return {f["slug"]: f for f in data.get("funds", []) if f.get("slug")}


def load_enriched_signals() -> list[dict]:
    """Load enriched signals file."""
    with open(ENRICHED_SIGNALS_FILE) as f:
        data = json.load(f)
    return data.get("signals", [])


def load_portfolio() -> dict:
    """Load portfolio_items.json."""
    with open(PORTFOLIO_FILE) as f:
        return json.load(f)


def save_portfolio(data: dict):
    """Save portfolio_items.json atomically."""
    from fundradar_worker.io_utils import safe_json_write, backup_before_write
    backup_before_write(PORTFOLIO_FILE)
    safe_json_write(PORTFOLIO_FILE, data)


def build_existing_names(entries: list[dict]) -> tuple[set[str], set[str]]:
    """Build normalized name sets for dedup matching."""
    norm_names = set()
    compact_names = set()
    for e in entries:
        name = e.get("name", "")
        n = normalize_company_name(name)
        if n:
            norm_names.add(n)
            compact_names.add(n.replace(" ", ""))
    return norm_names, compact_names


def process_fund_signals(
    fund_slug: str,
    fund_name: str,
    signals: list[dict],
    existing_entries: list[dict],
    fund_domain: str | None,
    client,
    dry_run: bool = False,
) -> dict:
    """
    Process signals for a single fund.

    Returns stats dict: {added: int, exits_updated: int, skipped_addon: int, skipped_existing: int, skipped_no_company: int}
    """
    stats = {
        "added": 0, "exits_updated": 0, "skipped_addon": 0,
        "skipped_existing": 0, "skipped_no_company": 0, "errors": 0,
    }

    existing_names, existing_compact = build_existing_names(existing_entries)
    # Also build a lookup by normalized name for exit status updates
    existing_by_norm: dict[str, dict] = {}
    for e in existing_entries:
        n = normalize_company_name(e.get("name", ""))
        if n:
            existing_by_norm[n] = e

    new_entries: list[dict] = []

    # Process in batches
    for batch_start in range(0, len(signals), BATCH_SIZE):
        batch = signals[batch_start:batch_start + BATCH_SIZE]
        prompt = build_prompt(fund_name, batch)

        if dry_run:
            print(f"    [dry-run] Would send {len(batch)} signals to Gemini for {fund_slug}")
            # In dry-run, just show signal titles
            for s in batch:
                print(f"      {s['id']}: {s.get('title', '')[:80]}")
            continue

        # Call Gemini with retries
        results = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                results = call_gemini(client, prompt)
                break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(f"    Retry {attempt + 1}/{MAX_RETRIES} after error: {e}", flush=True)
                    time.sleep(DELAY_BETWEEN_CALLS * 2)
                else:
                    print(f"    ERROR: Failed after {MAX_RETRIES + 1} attempts: {e}", flush=True)
                    stats["errors"] += len(batch)
                    continue

        if not results:
            continue

        # Index results by signal_id
        results_by_id = {}
        for r in results:
            sid = r.get("signal_id")
            if sid:
                results_by_id[sid] = r

        # Process each signal's extraction
        for s in batch:
            sid = s["id"]
            r = results_by_id.get(sid)
            if not r:
                stats["skipped_no_company"] += 1
                continue

            company_name = r.get("target_company")
            if not company_name:
                stats["skipped_no_company"] += 1
                continue

            is_direct = r.get("is_direct_investment", False)
            action = r.get("action", "other")

            if not is_direct:
                stats["skipped_addon"] += 1
                continue

            if action == "other":
                stats["skipped_no_company"] += 1
                continue

            # Check if already in portfolio
            if _matches_existing(company_name, existing_names, existing_compact):
                # If exit signal and company exists as current → update status
                if action == "exit":
                    norm = normalize_company_name(company_name)
                    existing_entry = existing_by_norm.get(norm)
                    if existing_entry and existing_entry.get("status") == "current":
                        existing_entry["status"] = "exited"
                        stats["exits_updated"] += 1
                        print(f"    EXIT: {company_name} → status=exited (signal: {sid})")
                    else:
                        stats["skipped_existing"] += 1
                else:
                    stats["skipped_existing"] += 1
                continue

            if action == "exit":
                # Exit for company not in portfolio — skip (we don't add unknown exits)
                stats["skipped_existing"] += 1
                continue

            # New investment — add to portfolio
            data_source, confidence = classify_source(s.get("source_url"), fund_domain)

            # Use signal's published_at as investment_date, or Gemini's extraction
            investment_date = r.get("investment_date")
            if not investment_date and s.get("published_at"):
                try:
                    investment_date = s["published_at"][:10]
                except Exception:
                    pass

            new_entry = {
                "name": company_name,
                "sector": r.get("sector") if r.get("sector") in SECTOR_SET else None,
                "status": "current",
                "confidence": confidence,
                "website": None,
                "description": None,
                "detail_page_url": None,
                "headquarters": r.get("headquarters"),
                "investment_date": investment_date,
                "source_url": s.get("source_url"),
                "data_source": data_source,
                "signal_id": sid,
            }

            new_entries.append(new_entry)
            # Add to dedup sets so we don't add the same company twice from multiple signals
            norm = normalize_company_name(company_name)
            existing_names.add(norm)
            existing_compact.add(norm.replace(" ", ""))
            stats["added"] += 1
            print(f"    ADD: {company_name} (sector={r.get('sector')}, source={data_source}, signal={sid})")

        if batch_start + BATCH_SIZE < len(signals):
            time.sleep(DELAY_BETWEEN_CALLS)

    # Append new entries to the fund's portfolio
    if not dry_run and new_entries:
        existing_entries.extend(new_entries)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Convert deal/exit signals to portfolio entries")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done, don't write")
    parser.add_argument("--slugs", type=str, help="Comma-separated fund slugs to process")
    parser.add_argument("--force", action="store_true", help="Reprocess all signals (ignore progress)")
    parser.add_argument("--pipeline", action="store_true", help="Pipeline mode (auto-skip if no API key)")
    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  Signal → Portfolio Conversion")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 60}\n")

    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        if args.pipeline:
            print("  GEMINI_API_KEY not set — skipping signal-to-portfolio (pipeline mode)")
            return
        print("  ERROR: GEMINI_API_KEY not set. Export it or add to .env")
        sys.exit(1)

    # Load data
    print("  Loading data...", flush=True)
    funds_by_slug = load_funds_by_slug()
    all_signals = load_enriched_signals()
    portfolio_data = load_portfolio()
    fund_portfolios = portfolio_data.get("fund_portfolios", {})

    # Load progress
    progress = load_progress()
    processed_ids = set(progress.get("processed_signal_ids", []))

    # Filter to deal/exit signals
    deal_signals = [
        s for s in all_signals
        if s.get("signal_type") in DEAL_TYPES
        and s.get("fund_slug")
        and s.get("id")
    ]
    print(f"  Total deal/exit signals: {len(deal_signals)}")

    # Filter by progress (unless --force)
    if not args.force:
        before = len(deal_signals)
        deal_signals = [s for s in deal_signals if s["id"] not in processed_ids]
        skipped = before - len(deal_signals)
        if skipped:
            print(f"  Skipping {skipped} already-processed signals (use --force to reprocess)")
    print(f"  Signals to process: {len(deal_signals)}")

    if not deal_signals:
        print("\n  No new signals to process. Done.")
        return

    # Filter by slugs
    slug_filter = None
    if args.slugs:
        slug_filter = set(args.slugs.split(","))
        deal_signals = [s for s in deal_signals if s["fund_slug"] in slug_filter]
        print(f"  After slug filter: {len(deal_signals)}")

    # Group by fund
    by_fund: dict[str, list[dict]] = {}
    for s in deal_signals:
        slug = s["fund_slug"]
        by_fund.setdefault(slug, []).append(s)

    print(f"  Funds with signals: {len(by_fund)}")

    # Init Gemini client (unless dry-run)
    client = None
    if not args.dry_run:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=SDK_TIMEOUT_MS),
        )

    # Process each fund
    total_stats = {
        "added": 0, "exits_updated": 0, "skipped_addon": 0,
        "skipped_existing": 0, "skipped_no_company": 0, "errors": 0,
    }
    processed_in_run: list[str] = []

    for fund_slug, signals in sorted(by_fund.items()):
        fund = funds_by_slug.get(fund_slug)
        fund_name = fund["name"] if fund else fund_slug
        fund_domain = _get_fund_domain(fund_slug, funds_by_slug)
        existing = fund_portfolios.get(fund_slug, [])

        print(f"\n  {fund_name} ({fund_slug}): {len(signals)} signals, {len(existing)} existing portfolio entries")

        stats = process_fund_signals(
            fund_slug=fund_slug,
            fund_name=fund_name,
            signals=signals,
            existing_entries=existing,
            fund_domain=fund_domain,
            client=client,
            dry_run=args.dry_run,
        )

        # Update portfolio reference (process_fund_signals modifies existing_entries in place)
        if not args.dry_run and stats["added"] > 0:
            fund_portfolios[fund_slug] = existing

        for k in total_stats:
            total_stats[k] += stats[k]

        # Track processed signal IDs
        for s in signals:
            processed_in_run.append(s["id"])

    # Save results
    if not args.dry_run:
        if total_stats["added"] > 0 or total_stats["exits_updated"] > 0:
            print(f"\n  Saving portfolio...", flush=True)
            # Re-read from disk to merge (same pattern as enrich_portfolio)
            fresh = load_portfolio()
            fresh_portfolios = fresh.get("fund_portfolios", {})
            for slug, entries in fund_portfolios.items():
                fresh_portfolios[slug] = entries
            fresh["fund_portfolios"] = fresh_portfolios
            save_portfolio(fresh)
            print(f"  Portfolio saved.")

        # Update progress
        all_processed = list(processed_ids | set(processed_in_run))
        progress = {
            "processed_signal_ids": all_processed,
            "last_run": datetime.now(timezone.utc).isoformat(),
            "stats": total_stats,
        }
        save_progress(progress)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Summary")
    print(f"{'=' * 60}")
    print(f"  Added to portfolio: {total_stats['added']}")
    print(f"  Exits updated:      {total_stats['exits_updated']}")
    print(f"  Skipped (add-on):   {total_stats['skipped_addon']}")
    print(f"  Skipped (existing): {total_stats['skipped_existing']}")
    print(f"  Skipped (no co.):   {total_stats['skipped_no_company']}")
    print(f"  Errors:             {total_stats['errors']}")
    print()


if __name__ == "__main__":
    main()
