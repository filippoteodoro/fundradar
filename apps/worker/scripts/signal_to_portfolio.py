#!/usr/bin/env python3
"""
Convert deal/exit signals into portfolio entries.

Purely local pipeline step — zero API calls. Reads target_companies
pre-extracted by step 7 (enrich_signals_openai.py) from each signal.

Two-phase pipeline:
  Phase 1 — Read: load enriched signals with pre-extracted target_companies
  Phase 2 — Dedup + write: match extracted companies against existing portfolio,
             add new entries, update exits, skip add-ons/duplicates.

Trust hierarchy (confidence scoring):
  0.95  fund_website          — already on the fund's portfolio page (handled elsewhere)
  0.90  signal_fund_press     — fund's own press release / news page
  0.80  signal_news_verified  — reputable journal + high quality score
  0.75  signal_news           — reputable PE/VC journal
  0.70  signal_rss            — other RSS / unknown source
  0.60  signal_rumor          — explicitly flagged as rumor

Usage:
    python apps/worker/scripts/signal_to_portfolio.py --dry-run
    python apps/worker/scripts/signal_to_portfolio.py --slugs cdp-venture-capital,wise-equity-sgr
    python apps/worker/scripts/signal_to_portfolio.py --force
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
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from fundradar_worker.paths import PROJECT_ROOT, DATA_DIR, DB_PATH, ENRICHED_SIGNALS_FILE, PORTFOLIO_FILE, ROOT_ENV_PATH
from fundradar_worker.portfolio_validation import clean_portfolio_name, is_valid_portfolio_entry
from fundradar_worker.url_utils import extract_domain, is_same_domain

load_dotenv(ROOT_ENV_PATH, override=False)

PROGRESS_FILE = DATA_DIR / "signal_to_portfolio_progress.json"

# Primary signal types to process.
# We also process any signal with explicit direct target_companies actions.
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

# Known reputable PE/VC industry journals (higher trust)
NEWS_DOMAINS = {
    "bebeez.it", "financecommunity.it", "ilsole24ore.com",
    "startupitalia.eu", "milanofinanza.it", "reuters.com",
    "bloomberg.com", "corriere.it", "repubblica.it",
    "ansa.it", "dealflower.com", "privateequityitalia.it",
    "mergermarket.com", "pitchbook.com",
}

# Company name normalization — delegates to entity_resolver (single source of truth)
from fundradar_worker.entity_resolver import normalize_company_name


def _token_overlap(a: str, b: str) -> float:
    """Jaccard token overlap between two normalized name strings."""
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _matches_existing(
    new_name: str,
    existing_names: set[str],
    existing_compact: set[str],
) -> tuple[bool, str | None]:
    """
    Check if a company name matches any existing portfolio entry.

    Returns (matched: bool, matched_norm: str | None for exit updates).
    Uses: exact normalized, compact (no spaces), numeric suffix, and token overlap (≥0.8 Jaccard).
    """
    norm = normalize_company_name(new_name)
    if not norm:
        return False, None

    # 1. Exact normalized
    if norm in existing_names:
        return True, norm

    # 2. Compact (no spaces)
    comp = norm.replace(" ", "")
    if comp in existing_compact:
        for en in existing_names:
            if en.replace(" ", "") == comp:
                return True, en
        return True, None

    # 3. Numeric suffix: "company 2" matches "company", "abc3" matches "abc"
    norm_stripped = re.sub(r"\s*\d+$", "", norm)
    if norm_stripped and norm_stripped != norm and norm_stripped in existing_names:
        return True, norm_stripped
    for en in existing_names:
        en_stripped = re.sub(r"\s*\d+$", "", en)
        if en_stripped and en_stripped != en and en_stripped == norm:
            return True, en

    # 4. Token overlap (≥0.8 Jaccard) — safer than substring matching
    norm_tokens = set(norm.split())
    if len(norm_tokens) >= 1:
        for en in existing_names:
            en_tokens = set(en.split())
            if not en_tokens:
                continue
            # For single-word names, require exact or compact match (already checked above)
            if len(norm_tokens) == 1 and len(en_tokens) == 1:
                continue
            overlap = _token_overlap(norm, en)
            if overlap >= 0.8:
                return True, en

    return False, None


# ─── Source classification & confidence ────────────────────────────────────

def _get_fund_domain(fund_slug: str, funds_by_slug: dict) -> str | None:
    """Get the website domain for a fund (delegates to shared extract_domain)."""
    fund = funds_by_slug.get(fund_slug)
    if not fund or not fund.get("website"):
        return None
    return extract_domain(fund["website"]) or None


def classify_source(signal: dict, fund_domain: str | None) -> tuple[str, float]:
    """
    Classify signal source and assign confidence based on trust hierarchy.

    Factors: source domain, quality_score, is_rumor flag.
    Returns (data_source, confidence).
    """
    source_url = signal.get("source_url")
    quality_score = signal.get("quality_score", 50)
    is_rumor = signal.get("is_rumor", False)

    if is_rumor:
        return "signal_rumor", 0.60

    source_domain = extract_domain(source_url) if source_url else None

    # Fund's own website → press release (highest trust for signals)
    if fund_domain and source_domain and source_domain == fund_domain:
        return "signal_fund_press", 0.90

    # Reputable PE/VC journals
    if source_domain and source_domain in NEWS_DOMAINS:
        if quality_score >= 90:
            return "signal_news_verified", 0.80
        return "signal_news", 0.75

    # Other / RSS — 0.70 per trust hierarchy
    return "signal_other", 0.70


# ─── Progress tracking ─────────────────────────────────────────────────────

def load_progress() -> dict:
    """Load progress tracking file."""
    from fundradar_worker.io_utils import load_progress_file
    return load_progress_file(PROGRESS_FILE, default={"processed_signal_ids": [], "last_run": None, "stats": {}})


def save_progress(progress: dict):
    """Save progress tracking file."""
    from fundradar_worker.io_utils import safe_json_write
    safe_json_write(PROGRESS_FILE, progress)


# ─── Main logic ────────────────────────────────────────────────────────────

def load_funds_by_slug() -> dict:
    """Load db.json and return funds indexed by slug."""
    from fundradar_worker.io_utils import load_funds_by_slug as _shared
    return _shared(DB_PATH)


def load_enriched_signals() -> list[dict]:
    """Load enriched signals file."""
    if not ENRICHED_SIGNALS_FILE.exists():
        print(f"  WARNING: {ENRICHED_SIGNALS_FILE.name} not found. "
              f"Run 'pnpm pipeline:signals' first to generate enriched signals.")
        return []
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


def _matching_existing_entries(existing_entries: list[dict], matched_norm: str | None) -> list[dict]:
    """Return all existing entries matching a normalized/compact company key."""
    if not matched_norm:
        return []
    matched_compact = matched_norm.replace(" ", "")
    out: list[dict] = []
    for e in existing_entries:
        n = normalize_company_name(e.get("name", ""))
        if not n:
            continue
        if n == matched_norm or n.replace(" ", "") == matched_compact:
            out.append(e)
    return out


def _detect_addon_locally(
    signal: dict,
    target_name: str,
    all_target_names: list[str],
    existing_names: set[str],
    existing_compact: set[str],
) -> bool:
    """
    Local add-on detection: if the signal text mentions ANOTHER company that's
    already in the portfolio (and is NOT one of the target companies), the
    target_name is likely an add-on acquisition.

    Example: "Casa della Piada acquires Pizze Vincenti" where Casa della Piada
    is a portfolio company → Pizze Vincenti is an add-on, not a direct investment.
    """
    text = " ".join(filter(None, [
        signal.get("title"), signal.get("enriched_summary"), signal.get("what_changed"),
    ])).lower()
    if not text:
        return False
    text_norm = normalize_company_name(text)
    text_compact = text_norm.replace(" ", "") if text_norm else ""

    # Build set of all target company names to exclude from add-on check
    target_norms = set()
    target_compacts = set()
    for tn in all_target_names:
        n = normalize_company_name(tn)
        if n:
            target_norms.add(n)
            target_compacts.add(n.replace(" ", ""))

    for en in existing_names:
        if not en:
            continue
        # Skip if this existing name is any of the target companies
        if en in target_norms or en.replace(" ", "") in target_compacts:
            continue
        # Check if this existing portfolio company name appears in the signal text
        en_words = en.split()
        if len(en_words) < 2:
            # Single-word names: require exact word boundary match (min 4 chars to avoid noise)
            if len(en) >= 4 and re.search(r"\b" + re.escape(en) + r"\b", text):
                return True
        else:
            # Multi-word names: check if the full name appears in text
            if en in text:
                return True
            # Spacing/punctuation variants: "dili trust" vs "dilitrust"
            en_compact = en.replace(" ", "")
            if len(en_compact) >= 6 and en_compact in text_compact:
                return True
    return False


def _has_processable_target_actions(signal: dict) -> bool:
    """
    Return True when signal carries direct target_companies actions that can
    mutate portfolio state, even if signal_type is not deal_announced/exit_announced.
    """
    target_companies = signal.get("target_companies")
    if not isinstance(target_companies, list) or not target_companies:
        return False

    for tc in target_companies:
        if not isinstance(tc, dict):
            continue
        action = tc.get("action", "other")
        if action not in {"investment", "exit"}:
            continue
        if not tc.get("is_direct_investment", False):
            continue
        name = clean_portfolio_name((tc.get("name") or "").strip())
        if name:
            return True
    return False


def process_fund_signals(
    fund_slug: str,
    fund_name: str,
    signals: list[dict],
    existing_entries: list[dict],
    fund_domain: str | None,
    dry_run: bool = False,
) -> tuple[dict, list[str]]:
    """
    Process signals for a single fund — purely local, no API calls.

    Reads target_companies from pre-enriched signals (extracted by step 7).
    Dedup results, add new entries, update exits.

    Returns (stats_dict, successfully_processed_signal_ids).
    """
    stats = {
        "added": 0, "exits_updated": 0, "skipped_addon": 0,
        "skipped_existing": 0, "skipped_no_company": 0, "skipped_other": 0,
        "skipped_exit_no_match": 0, "skipped_invalid_name": 0,
        "errors": 0,
    }

    existing_names, existing_compact = build_existing_names(existing_entries)
    # Lookup by normalized name for exit updates.
    existing_by_norm: dict[str, dict] = {}
    for e in existing_entries:
        n = normalize_company_name(e.get("name", ""))
        if n:
            existing_by_norm[n] = e

    new_entries: list[dict] = []
    processed_ids: list[str] = []

    for s in signals:
        sid = s["id"]
        target_companies = s.get("target_companies")

        if target_companies is None:
            stats["skipped_no_company"] += 1
            # None = never attempted extraction — needs enrichment by step 7
            continue

        if not target_companies or not isinstance(target_companies, list):
            stats["skipped_no_company"] += 1
            # [] = LLM tried but found no extractable company name — mark as processed
            processed_ids.append(sid)
            continue

        for tc in target_companies:
            company_name = clean_portfolio_name((tc.get("name") or "").strip())
            if not company_name:
                stats["skipped_no_company"] += 1
                continue
            if not is_valid_portfolio_entry(company_name, fund_slug):
                stats["skipped_invalid_name"] += 1
                continue

            is_direct = tc.get("is_direct_investment", False)
            action = tc.get("action", "other")

            # Skip add-on acquisitions by portfolio companies
            if not is_direct:
                stats["skipped_addon"] += 1
                continue

            # Local add-on detection: if signal text mentions a portfolio company
            # (other than the target companies) making the acquisition, it's an add-on
            all_target_names = [tc2.get("name", "") for tc2 in target_companies]
            if action == "investment" and _detect_addon_locally(s, company_name, all_target_names, existing_names, existing_compact):
                stats["skipped_addon"] += 1
                print(f"    ADDON (local): {company_name} — signal mentions existing portfolio company (signal: {sid})")
                continue

            # Skip non-investment/exit actions
            if action == "other":
                stats["skipped_other"] += 1
                continue

            # Check if already in portfolio
            matched, matched_norm = _matches_existing(company_name, existing_names, existing_compact)
            if matched:
                if action == "exit" and matched_norm:
                    matches = _matching_existing_entries(existing_entries, matched_norm)
                    updatable = [e for e in matches if e.get("status") != "exited" and not e.get("curation_locked")]
                    if updatable:
                        if not dry_run:
                            for existing_entry in updatable:
                                existing_entry["status"] = "exited"
                                stats["exits_updated"] += 1
                                print(f"    EXIT: {existing_entry.get('name')} → status=exited (signal: {sid})")
                        else:
                            for existing_entry in updatable:
                                stats["exits_updated"] += 1
                                print(f"    [dry-run] EXIT: {existing_entry.get('name')} → status=exited (signal: {sid})")
                    else:
                        stats["skipped_existing"] += 1
                else:
                    stats["skipped_existing"] += 1
                continue

            if action == "exit":
                stats["skipped_exit_no_match"] += 1
                continue

            # ── New investment: create portfolio entry ──
            data_source, confidence = classify_source(s, fund_domain)

            # Investment date: prefer signal's enriched date, fallback to published_at
            investment_date = s.get("enriched_date") or None
            if not investment_date and s.get("published_at"):
                try:
                    investment_date = s["published_at"][:10]
                except Exception:
                    pass

            new_entry = {
                "name": company_name,
                "sector": None,
                "status": "current",
                "confidence": confidence,
                "website": None,
                "description": None,
                "detail_page_url": None,
                "headquarters": None,
                "investment_date": investment_date,
                "source_url": s.get("source_url"),
                "data_source": data_source,
                "signal_id": sid,
            }

            if dry_run:
                print(f"    [dry-run] ADD: {company_name} (conf={confidence}, source={data_source}, signal={sid})")
            else:
                new_entries.append(new_entry)
                print(f"    ADD: {company_name} (conf={confidence}, source={data_source}, signal={sid})")

            # Update dedup sets so subsequent signals don't add duplicates
            norm = normalize_company_name(company_name)
            existing_names.add(norm)
            existing_compact.add(norm.replace(" ", ""))
            existing_by_norm[norm] = new_entry
            stats["added"] += 1

        processed_ids.append(sid)

    # Append new entries
    if not dry_run and new_entries:
        existing_entries.extend(new_entries)

    return stats, processed_ids


def _requires_reconciliation(signal: dict, fund_slug: str, existing_entries: list[dict]) -> bool:
    """
    Return True if a previously-processed signal still has unresolved portfolio effects.

    Cases:
    - investment action target is still missing from portfolio
    - exit action target exists but status is not exited
    """
    target_companies = signal.get("target_companies")
    if not isinstance(target_companies, list) or not target_companies:
        return False

    existing_names, existing_compact = build_existing_names(existing_entries)
    for tc in target_companies:
        if not isinstance(tc, dict):
            continue
        company_name = clean_portfolio_name((tc.get("name") or "").strip())
        if not company_name or not is_valid_portfolio_entry(company_name, fund_slug):
            continue

        is_direct = tc.get("is_direct_investment", False)
        action = tc.get("action", "other")
        if not is_direct or action == "other":
            continue

        matched, matched_norm = _matches_existing(company_name, existing_names, existing_compact)
        if action == "investment":
            if not matched:
                return True
        elif action == "exit":
            if matched_norm:
                matches = _matching_existing_entries(existing_entries, matched_norm)
                if any(e.get("status") != "exited" and not e.get("curation_locked") for e in matches):
                    return True

    return False


def _send_alert(
    stats: dict, elapsed: float, signals_without_extraction: int,
):
    """Send Telegram alert summarizing signal-to-portfolio results.

    Only sends if there are issues. Clean runs are silent.
    """
    try:
        from fundradar_worker.alerting import AlertConfig, AlertManager, Alert
    except ImportError:
        return

    config = AlertConfig.from_env()
    if not config.telegram_enabled:
        return

    has_issues = stats["errors"] > 0 or signals_without_extraction > 20

    if not has_issues:
        return

    manager = AlertManager(config)
    elapsed_min = elapsed / 60
    lines: list[str] = []

    lines.append(f"Signal to Portfolio: {elapsed_min:.1f}m (local)")
    lines.append(f"+{stats['added']} added, +{stats['exits_updated']} exits, {stats['errors']} errors")

    if signals_without_extraction > 20:
        lines.append(f"\nMissing extraction: {signals_without_extraction} deal/exit signals lack target_companies")
        lines.append("(re-run pnpm pipeline step 7 to extract)")

    level = "error" if stats["errors"] > 0 else "warning"
    title = "Signal to Portfolio"
    if stats["errors"] > 0:
        title += f": {stats['errors']} errors"
    elif signals_without_extraction > 20:
        title += f": {signals_without_extraction} missing extractions"

    manager.add_alert(Alert(
        title=title,
        message="\n".join(lines),
        level=level,
        source="signal_to_portfolio",
    ))
    manager.send_pending_alerts()


def main():
    parser = argparse.ArgumentParser(description="Convert deal/exit signals to portfolio entries (local, no API)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done, don't write")
    parser.add_argument("--slugs", type=str, help="Comma-separated fund slugs to process")
    parser.add_argument("--force", action="store_true",
                        help="Reprocess all signals (ignore progress). Dedup still applies.")
    parser.add_argument("--pipeline", action="store_true", help="Pipeline mode")
    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  Signal → Portfolio Conversion (local)")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 60}\n")

    # Load data
    print("  Loading data...", flush=True)
    funds_by_slug = load_funds_by_slug()
    all_signals = load_enriched_signals()
    portfolio_data = load_portfolio()
    fund_portfolios = portfolio_data.get("fund_portfolios", {})

    # Load progress and prune stale IDs (signals no longer in enriched file)
    progress = load_progress()
    current_signal_ids = {s.get("id") for s in all_signals if s.get("id")}
    raw_processed = set(progress.get("processed_signal_ids", []))
    processed_ids = raw_processed & current_signal_ids  # prune stale
    pruned = len(raw_processed) - len(processed_ids)
    if pruned > 0:
        print(f"  Pruned {pruned} stale IDs from progress file")

    # Filter to actionable signals with minimum quality:
    # - primary deal/exit signal types
    # - OR any signal carrying direct investment/exit target_companies actions
    # Threshold 60 is intentionally lower than filter's 80 — portfolio conversion
    # should be more lenient since deal/exit signals have high intrinsic value
    # even when their text quality is moderate.
    deal_signals = [
        s for s in all_signals
        if (s.get("signal_type") in DEAL_TYPES or _has_processable_target_actions(s))
        and s.get("fund_slug")
        and s.get("id")
        and (s.get("quality_score", 0) or 0) >= 60
    ]
    print(f"  Total actionable signals (quality>=60): {len(deal_signals)}")

    # Count extraction status: None = never attempted, [] = attempted/none found, [...] = extracted
    with_extraction = sum(1 for s in deal_signals if s.get("target_companies"))
    never_attempted = sum(1 for s in deal_signals if s.get("target_companies") is None)
    attempted_empty = sum(1 for s in deal_signals if isinstance(s.get("target_companies"), list) and not s.get("target_companies"))
    without_extraction = never_attempted  # Only count truly missing ones
    print(f"  With target_companies: {with_extraction}, no company found: {attempted_empty}, never attempted: {never_attempted}")

    # Filter by slugs FIRST (before progress filter and early-exit)
    if args.slugs:
        slug_filter = set(args.slugs.split(","))
        deal_signals = [s for s in deal_signals if s["fund_slug"] in slug_filter]
        print(f"  After slug filter: {len(deal_signals)}")

    # Filter by progress (unless --force)
    if not args.force:
        before = len(deal_signals)
        reconciled = 0
        unresolved: list[dict] = []
        for s in deal_signals:
            sid = s["id"]
            if sid not in processed_ids:
                unresolved.append(s)
                continue
            fund_slug = s["fund_slug"]
            existing_entries = fund_portfolios.get(fund_slug, [])
            if _requires_reconciliation(s, fund_slug, existing_entries):
                unresolved.append(s)
                reconciled += 1
        deal_signals = unresolved
        skipped = before - len(deal_signals)
        if skipped:
            print(f"  Skipping {skipped} already-processed signals (use --force to reprocess)")
        if reconciled:
            print(f"  Reprocessing {reconciled} previously-processed signals with unresolved portfolio sync")
    else:
        if args.slugs:
            slug_filter_set = set(args.slugs.split(","))
            signals_in_scope = {
                s["id"] for s in all_signals
                if s.get("fund_slug") in slug_filter_set and s.get("id")
            }
            processed_ids -= signals_in_scope

    print(f"  Signals to process: {len(deal_signals)}")

    if not deal_signals:
        print("\n  No new signals to process. Done.")
        return

    # Group by fund
    by_fund: dict[str, list[dict]] = {}
    for s in deal_signals:
        slug = s["fund_slug"]
        by_fund.setdefault(slug, []).append(s)

    print(f"  Funds with signals: {len(by_fund)}")

    # Process each fund
    total_stats = {
        "added": 0, "exits_updated": 0, "skipped_addon": 0,
        "skipped_existing": 0, "skipped_no_company": 0, "skipped_other": 0,
        "skipped_exit_no_match": 0, "skipped_invalid_name": 0,
        "errors": 0,
    }
    all_processed_in_run: list[str] = []
    funds_processed = 0
    start_time = time.time()

    # Track which fund portfolios changed
    changed_slugs: set[str] = set()

    # Sort funds by signal count ascending (small funds first for broader coverage)
    sorted_funds = sorted(by_fund.items(), key=lambda x: len(x[1]))

    for fund_slug, signals in sorted_funds:
        fund = funds_by_slug.get(fund_slug)
        fund_name = fund["name"] if fund else fund_slug
        fund_domain = _get_fund_domain(fund_slug, funds_by_slug)
        existing = fund_portfolios.get(fund_slug, [])

        print(f"\n  {fund_name} ({fund_slug}): {len(signals)} signals, "
              f"{len(existing)} existing portfolio entries")

        fund_stats, fund_processed_ids = process_fund_signals(
            fund_slug=fund_slug,
            fund_name=fund_name,
            signals=signals,
            existing_entries=existing,
            fund_domain=fund_domain,
            dry_run=args.dry_run,
        )

        # Update portfolio reference (process_fund_signals modifies existing_entries in place)
        if not args.dry_run and (fund_stats["added"] > 0 or fund_stats["exits_updated"] > 0):
            fund_portfolios[fund_slug] = existing
            changed_slugs.add(fund_slug)

        for k in total_stats:
            total_stats[k] += fund_stats[k]

        all_processed_in_run.extend(fund_processed_ids)
        funds_processed += 1

        # Per-fund disk save for crash safety
        if not args.dry_run and fund_processed_ids:
            updated_processed = list(processed_ids | set(all_processed_in_run))
            progress = {
                "processed_signal_ids": updated_processed,
                "last_run": datetime.now(timezone.utc).isoformat(),
                "stats": total_stats,
            }
            save_progress(progress)

            if fund_slug in changed_slugs:
                fresh = load_portfolio()
                fresh_portfolios = fresh.get("fund_portfolios", {})
                fresh_portfolios[fund_slug] = fund_portfolios[fund_slug]
                fresh["fund_portfolios"] = fresh_portfolios
                save_portfolio(fresh)

        # Running rate logging
        if not args.dry_run and funds_processed > 0 and (fund_stats["added"] > 0 or fund_stats["exits_updated"] > 0):
            elapsed = time.time() - start_time
            print(f"    [{funds_processed}/{len(by_fund)}] "
                  f"+{fund_stats['added']}add +{fund_stats['exits_updated']}exit | "
                  f"Total: +{total_stats['added']}add +{total_stats['exits_updated']}exit", flush=True)

    # Final save
    if not args.dry_run:
        updated_processed = list(processed_ids | set(all_processed_in_run))
        progress = {
            "processed_signal_ids": updated_processed,
            "last_run": datetime.now(timezone.utc).isoformat(),
            "stats": total_stats,
        }
        save_progress(progress)

    # Summary
    elapsed = time.time() - start_time

    print(f"\n{'=' * 60}")
    print(f"  Summary ({elapsed:.1f}s — local, zero API calls)")
    print(f"{'=' * 60}")
    print(f"  Portfolio entries added:   {total_stats['added']}")
    print(f"  Exits detected & updated: {total_stats['exits_updated']}")
    print(f"  Skipped (add-on/bolt-on): {total_stats['skipped_addon']}")
    print(f"  Skipped (already exists): {total_stats['skipped_existing']}")
    print(f"  Skipped (no company):     {total_stats['skipped_no_company']}")
    print(f"  Skipped (non-deal/other): {total_stats['skipped_other']}")
    print(f"  Skipped (exit, no match): {total_stats['skipped_exit_no_match']}")
    print(f"  Skipped (invalid name):   {total_stats['skipped_invalid_name']}")
    print(f"  Errors:                   {total_stats['errors']}")
    if without_extraction > 0:
        print(f"  Signals without extraction: {without_extraction} (need re-enrichment via step 7)")
    print()

    # Telegram alert (skip for dry-run)
    if not args.dry_run:
        _send_alert(total_stats, elapsed, without_extraction)


if __name__ == "__main__":
    main()
