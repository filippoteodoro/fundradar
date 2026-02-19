#!/usr/bin/env python3
"""
Convert deal/exit signals into portfolio entries.

Two-phase pipeline:
  Phase 1 — Gemini extraction: read enriched signals, send to Gemini 3 Flash
             with existing portfolio context so it can distinguish direct investments
             from add-on acquisitions by portfolio companies.
  Phase 2 — Dedup + write: match extracted companies against existing portfolio,
             add new entries, update exits, skip add-ons/duplicates.

Trust hierarchy (confidence scoring):
  0.95  fund_website          — already on the fund's portfolio page (handled elsewhere)
  0.90  signal_fund_press     — fund's own press release / news page
  0.80  signal_news_verified  — reputable journal + high quality score
  0.75  signal_news           — reputable PE/VC journal
  0.70  signal_rss            — other RSS / unknown source
  0.60  signal_rumor          — explicitly flagged as rumor

New entries get sector, HQ, and description from Gemini in the same call
(one-shot enrichment). Entries still get the full enrichment treatment from
enrich_portfolio_gemini_full.py on the next pipeline run.

Why Gemini over OpenAI:
  - Native structured JSON output mode (not function-calling workarounds)
  - ~$0.01 total for all signals (Gemini 3 Flash pricing)
  - Already used for portfolio enrichment in this project
  - Excellent Italian language understanding

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
import signal as _signal
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
# Gemini Flash free tier: ~30s per signal for structured extraction. Batches of 5
# take ~150s, batches of 10 take ~300s. Keep batches small to stay within timeout.
BATCH_SIZE = 5
MAX_RETRIES = 2
CALL_TIMEOUT = 300  # 5min — Gemini Flash free tier is slow on complex structured output
SDK_TIMEOUT_MS = 360_000  # SDK-level timeout — must exceed CALL_TIMEOUT
DELAY_BETWEEN_CALLS = 4.0  # 4s between calls — Gemini free tier ~15 RPM

# Auto-split: when a batch fails at size N, retry at next smaller size
BATCH_SPLIT_SIZES = [5, 2, 1]

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

# Known reputable PE/VC industry journals (higher trust)
NEWS_DOMAINS = {
    "bebeez.it", "financecommunity.it", "ilsole24ore.com",
    "startupitalia.eu", "milanofinanza.it", "reuters.com",
    "bloomberg.com", "corriere.it", "repubblica.it",
    "ansa.it", "dealflower.com", "privateequityitalia.it",
    "mergermarket.com", "pitchbook.com",
}

# ─── Company name normalization (mirrors entity_resolver.py + data.ts) ─────

LEGAL_SUFFIXES_RE = re.compile(
    r"(?:\s+|,\s*)(?:"
    r"\bS\.?p\.?A\.?|\bS\.?r\.?l\.?|\bS\.?a\.?s\.?|\bS\.?n\.?c\.?"
    r"|\bLtd\.?|\bLLC\.?|\bInc\.?|\bGmbH\.?|\bAG\.?|\bB\.?V\.?"
    r"|\bN\.?V\.?|\bPLC\.?|\bCorp\.?|\bCorporation|\bCompany"
    r"|\bGroup|\bGruppo|\bHolding|\bHoldings|\bPartecipazioni"
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
    for _ in range(3):
        cleaned = LEGAL_SUFFIXES_RE.sub("", n).strip()
        if cleaned == n:
            break
        n = cleaned
    n = re.sub(r"\s+technologies\s*$", "", n)
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return n


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
    Uses: exact normalized, compact (no spaces), and token overlap (≥0.8 Jaccard).
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

    # 3. Token overlap (≥0.8 Jaccard) — safer than substring matching
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


def _extract_domain(url: str) -> str | None:
    """Extract bare domain from URL."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or None
    except Exception:
        return None


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

    source_domain = _extract_domain(source_url) if source_url else None

    # Fund's own website → press release (highest trust for signals)
    if fund_domain and source_domain and source_domain == fund_domain:
        return "signal_fund_press", 0.90

    # Reputable PE/VC journals
    if source_domain and source_domain in NEWS_DOMAINS:
        if quality_score >= 90:
            return "signal_news_verified", 0.80
        return "signal_news", 0.75

    # Other / RSS
    if quality_score >= 90:
        return "signal_other", 0.72
    return "signal_other", 0.70


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
                    "description": genai_types.Schema(
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


def build_prompt(fund_name: str, signals: list[dict], existing_company_names: list[str]) -> str:
    """
    Build Gemini prompt for a batch of signals.

    Includes existing portfolio company names so Gemini can detect add-on
    acquisitions (portfolio company X acquires company Y).
    """
    signal_lines = []
    for s in signals:
        # Use the richest available text: enriched_summary > what_changed > title
        text = s.get("enriched_summary") or s.get("what_changed") or ""
        title = s.get("title", "")
        title_orig = s.get("title_original", "")

        parts = [f"id={s['id']}"]
        parts.append(f"type={s.get('signal_type', 'unknown')}")
        parts.append(f"title={title}")
        if title_orig and title_orig != title:
            parts.append(f"title_it={title_orig}")
        if text and text != title:
            parts.append(f"summary={text[:400]}")
        if s.get("published_at"):
            parts.append(f"date={s['published_at'][:10]}")
        if s.get("source_name"):
            parts.append(f"source={s['source_name']}")
        # Include extracted entities if available
        entities = s.get("extracted_entities", {})
        if entities.get("companies"):
            parts.append(f"entities={','.join(entities['companies'][:5])}")

        signal_lines.append(" | ".join(parts))

    signals_block = "\n".join(signal_lines)

    # Portfolio context — helps detect add-ons. Keep short to avoid Gemini timeouts.
    portfolio_context = ""
    if existing_company_names:
        sample = existing_company_names[:50]
        portfolio_context = f"""
EXISTING PORTFOLIO of "{fund_name}" (already invested): {', '.join(sample)}{"..." if len(existing_company_names) > 50 else ""}
"""

    example_portco = existing_company_names[0] if existing_company_names else "PortCo X"

    return f"""You are analyzing investment news signals for the PE/VC fund "{fund_name}".
{portfolio_context}
For each signal, extract:
1. target_company: The company being invested in or exited from. Use the company's proper name (not the fund name, not the advisor name). null if no specific target company is mentioned or if the signal is about fund-level activity (fundraising, fund launch, etc.). IMPORTANT: If a signal mentions MULTIPLE target companies (e.g. "acquires CompanyA and CompanyB"), return a SEPARATE object for EACH company, all sharing the same signal_id.
2. is_direct_investment: true ONLY if "{fund_name}" is directly investing in or exiting the target company. Set false if:
   - A company from the EXISTING PORTFOLIO list above is making an acquisition (add-on/bolt-on)
   - The signal is about a different fund's deal, not "{fund_name}"'s
   - The signal mentions "{fund_name}" only as a co-investor alongside the lead investor
3. action: "investment" if the fund is buying/investing, "exit" if the fund is selling/exiting/divesting, "other" for anything else (fundraising, partnerships, events, reports).
4. sector: one of the allowed enum values if clearly inferable from the signal text, or null.
5. headquarters: city and country of the target company if mentioned (e.g. "Milan, Italy"), or null.
6. description: a 1-2 sentence description of the target company's business, based on what's mentioned in the signal. null if nothing is described.
7. investment_date: the date of the investment/exit in YYYY-MM-DD format if mentioned, or null.

CRITICAL RULES:
- "{fund_name}" is the fund we're tracking. We only care about THEIR direct investments/exits.
- If a company from the existing portfolio list (e.g. "{example_portco}") acquires another company, that is an add-on — set is_direct_investment=false.
- Fundraising signals (fund raises capital), fund launches, reports, and partnership announcements are action="other".
- For the company name, prefer the Italian/original name if it's a proper noun (e.g. "Marullo" not "Marulloper").

Signals:
{signals_block}

Return a JSON array with one object per signal, matching by signal_id."""


class _AlarmTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _AlarmTimeout()


def _do_api_call(client, prompt: str) -> tuple[list[dict], int, int]:
    """Execute a single Gemini API call with structured JSON output."""
    global _schema_disabled
    from google.genai import types

    config_kwargs = {
        "temperature": 0.1,
        "response_mime_type": "application/json",
        "http_options": types.HttpOptions(timeout=SDK_TIMEOUT_MS),
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

    results = json.loads(text)

    # Safety: ensure we got a list (schema-disabled mode may return a dict)
    if isinstance(results, dict):
        for key in ("items", "signals", "results"):
            if isinstance(results.get(key), list):
                results = results[key]
                break
        else:
            results = []

    usage = response.usage_metadata
    in_tok = usage.prompt_token_count or 0
    out_tok = usage.candidates_token_count or 0
    return results, in_tok, out_tok


def _call_gemini_single(client, prompt: str) -> tuple[list[dict], int, int]:
    """Call Gemini with SIGALRM hard timeout and retries at a fixed batch size.

    Returns (results, in_tokens, out_tokens). Empty results on total failure.
    """
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
                wait = 15 * (attempt + 1)  # 15s, 30s — longer backoff for rate limits
                print(f"    Timeout (attempt {attempt+1}), retrying in {wait}s...", flush=True)
                time.sleep(wait)
                continue
            return [], 0, 0

        except json.JSONDecodeError:
            _signal.alarm(0)
            if attempt < MAX_RETRIES:
                time.sleep(5)
                continue
            return [], 0, 0

        except Exception as e:
            _signal.alarm(0)
            err_str = str(e).lower()
            is_rate_limit = "429" in err_str or "rate" in err_str or "quota" in err_str
            if attempt < MAX_RETRIES:
                wait = 30 * (attempt + 1) if is_rate_limit else 10 * (attempt + 1)
                print(f"    Error (attempt {attempt+1}): {str(e)[:80]}, retrying in {wait}s...", flush=True)
                time.sleep(wait)
                continue
            return [], 0, 0

    return [], 0, 0


def call_gemini_batch(
    client, signals: list[dict], fund_name: str, existing_company_names: list[str],
) -> tuple[list[dict], int, int]:
    """Call Gemini with auto-split on failure.

    Tries the full batch first. If all retries fail, splits into smaller
    sub-batches (15 → 7 → 3 → 1) and retries each.

    Returns (results, in_tokens, out_tokens).
    """
    batch_size = len(signals)
    prompt = build_prompt(fund_name, signals, existing_company_names)

    # Find the starting split tier for this batch size
    split_sizes = [s for s in BATCH_SPLIT_SIZES if s <= batch_size]
    if not split_sizes:
        split_sizes = [1]

    for tier_idx, split_size in enumerate(split_sizes):
        if tier_idx == 0:
            # First tier: try the full batch as-is
            results, in_tok, out_tok = _call_gemini_single(client, prompt)
            if results:
                return results, in_tok, out_tok
            if split_size == 1:
                return [], 0, 0
            next_size = split_sizes[tier_idx + 1] if tier_idx + 1 < len(split_sizes) else 1
            print(f"    Batch of {batch_size} failed, auto-splitting to size {next_size}...", flush=True)
            continue

        # Split into sub-batches of this tier's size
        all_results = []
        total_in, total_out = 0, 0
        sub_failed = False

        for sub_idx, sub_start in enumerate(range(0, len(signals), split_size)):
            sub_batch = signals[sub_start:sub_start + split_size]
            sub_prompt = build_prompt(fund_name, sub_batch, existing_company_names)
            if sub_idx > 0:
                time.sleep(DELAY_BETWEEN_CALLS)
            sub_results, sub_in, sub_out = _call_gemini_single(client, sub_prompt)
            total_in += sub_in
            total_out += sub_out

            if sub_results:
                all_results.extend(sub_results)
            else:
                sub_failed = True

        if all_results and not sub_failed:
            return all_results, total_in, total_out

        if all_results:
            print(f"    Split size {split_size}: partial success ({len(all_results)}/{len(signals)})", flush=True)
            if tier_idx + 1 < len(split_sizes):
                continue
            return all_results, total_in, total_out

        if tier_idx + 1 < len(split_sizes):
            print(f"    Split size {split_size} failed, trying size {split_sizes[tier_idx + 1]}...", flush=True)
            continue

    return [], 0, 0


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


def process_fund_signals(
    fund_slug: str,
    fund_name: str,
    signals: list[dict],
    existing_entries: list[dict],
    fund_domain: str | None,
    client,
    dry_run: bool = False,
) -> tuple[dict, list[str]]:
    """
    Process signals for a single fund.

    Phase 1: Send signals + existing portfolio context to Gemini.
    Phase 2: Dedup results, add new entries, update exits.

    Returns (stats_dict, successfully_processed_signal_ids).
    """
    stats = {
        "added": 0, "exits_updated": 0, "skipped_addon": 0,
        "skipped_existing": 0, "skipped_no_company": 0, "skipped_other": 0,
        "skipped_exit_no_match": 0,
        "errors": 0, "tokens_in": 0, "tokens_out": 0,
    }

    existing_names, existing_compact = build_existing_names(existing_entries)
    # Lookup by normalized name for exit updates.
    # NOTE: these are the SAME dict objects as in existing_entries —
    # in-place mutation of existing_entry["status"] propagates to existing_entries.
    existing_by_norm: dict[str, dict] = {}
    for e in existing_entries:
        n = normalize_company_name(e.get("name", ""))
        if n:
            existing_by_norm[n] = e

    # Build list of current portfolio company names for Gemini context
    existing_raw_names = [
        e.get("name", "") for e in existing_entries
        if e.get("name") and e.get("status") in ("current", None)
    ]

    new_entries: list[dict] = []
    processed_ids: list[str] = []  # Only IDs from successful batches

    # Process in batches
    for batch_start in range(0, len(signals), BATCH_SIZE):
        batch = signals[batch_start:batch_start + BATCH_SIZE]

        if dry_run:
            print(f"    [dry-run] Would send {len(batch)} signals to Gemini for {fund_slug}")
            for s in batch:
                print(f"      {s['id']}: {s.get('title', '')[:90]}")
            # Dry-run: do NOT mark IDs as processed (avoids progress pollution)
            continue

        # Call Gemini with auto-split on failure
        results, in_tok, out_tok = call_gemini_batch(client, batch, fund_name, existing_raw_names)
        stats["tokens_in"] += in_tok
        stats["tokens_out"] += out_tok

        if not results:
            # Don't mark failed batch signal IDs as processed — they'll be retried next run
            stats["errors"] += len(batch)
            continue

        # Mark this batch as successfully processed
        processed_ids.extend(s["id"] for s in batch)

        # Index by signal_id (list: one signal can yield multiple companies)
        results_by_id: dict[str, list[dict]] = {}
        for r in results:
            sid = r.get("signal_id")
            if sid:
                results_by_id.setdefault(sid, []).append(r)

        # Phase 2: process each extraction
        for s in batch:
            sid = s["id"]
            extractions = results_by_id.get(sid)
            if not extractions:
                stats["skipped_no_company"] += 1
                continue

            for r in extractions:
                company_name = (r.get("target_company") or "").strip()
                if not company_name:
                    stats["skipped_no_company"] += 1
                    continue

                is_direct = r.get("is_direct_investment", False)
                action = r.get("action", "other")

                # Skip add-on acquisitions by portfolio companies
                if not is_direct:
                    stats["skipped_addon"] += 1
                    continue

                # Skip non-investment/exit actions (fundraise, partnership, report, etc.)
                if action == "other":
                    stats["skipped_other"] += 1
                    continue

                # Check if already in portfolio
                matched, matched_norm = _matches_existing(company_name, existing_names, existing_compact)
                if matched:
                    if action == "exit" and matched_norm:
                        existing_entry = existing_by_norm.get(matched_norm)
                        if existing_entry and existing_entry.get("status") == "current":
                            # Guard: never mutate curation_locked entries
                            if existing_entry.get("curation_locked"):
                                stats["skipped_existing"] += 1
                            else:
                                existing_entry["status"] = "exited"
                                stats["exits_updated"] += 1
                                print(f"    EXIT: {existing_entry.get('name')} → status=exited (signal: {sid})")
                        else:
                            stats["skipped_existing"] += 1
                    else:
                        stats["skipped_existing"] += 1
                    continue

                if action == "exit":
                    # Exit for company not in portfolio — nothing to update
                    stats["skipped_exit_no_match"] += 1
                    continue

                # ── New investment: create portfolio entry ──
                data_source, confidence = classify_source(s, fund_domain)

                # Investment date: prefer Gemini extraction, fallback to signal date
                investment_date = r.get("investment_date")
                if not investment_date and s.get("published_at"):
                    try:
                        investment_date = s["published_at"][:10]
                    except Exception:
                        pass

                # Sector: validate against taxonomy
                sector = r.get("sector")
                if sector and sector not in SECTOR_SET:
                    sector = None

                new_entry = {
                    "name": company_name,
                    "sector": sector,
                    "status": "current",
                    "confidence": confidence,
                    "website": None,
                    "description": r.get("description"),
                    "detail_page_url": None,
                    "headquarters": r.get("headquarters"),
                    "investment_date": investment_date,
                    "source_url": s.get("source_url"),
                    "data_source": data_source,
                    "signal_id": sid,
                }

                new_entries.append(new_entry)
                # Update dedup sets so subsequent signals in the same run don't add duplicates
                norm = normalize_company_name(company_name)
                existing_names.add(norm)
                existing_compact.add(norm.replace(" ", ""))
                existing_by_norm[norm] = new_entry
                stats["added"] += 1
                print(f"    ADD: {company_name} (sector={sector}, hq={r.get('headquarters')}, "
                      f"conf={confidence}, source={data_source}, signal={sid})")

        # Rate limit between batches
        if batch_start + BATCH_SIZE < len(signals):
            time.sleep(DELAY_BETWEEN_CALLS)

    # Append new entries
    if not dry_run and new_entries:
        existing_entries.extend(new_entries)

    return stats, processed_ids


def main():
    parser = argparse.ArgumentParser(description="Convert deal/exit signals to portfolio entries")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done, don't write")
    parser.add_argument("--slugs", type=str, help="Comma-separated fund slugs to process")
    parser.add_argument("--force", action="store_true",
                        help="Re-send all signals to Gemini (ignore progress). Dedup still applies.")
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

    # Load progress and prune stale IDs (signals no longer in enriched file)
    progress = load_progress()
    current_signal_ids = {s.get("id") for s in all_signals if s.get("id")}
    raw_processed = set(progress.get("processed_signal_ids", []))
    processed_ids = raw_processed & current_signal_ids  # prune stale
    pruned = len(raw_processed) - len(processed_ids)
    if pruned > 0:
        print(f"  Pruned {pruned} stale IDs from progress file")

    # Filter to deal/exit signals with minimum quality
    deal_signals = [
        s for s in all_signals
        if s.get("signal_type") in DEAL_TYPES
        and s.get("fund_slug")
        and s.get("id")
        and (s.get("quality_score", 0) or 0) >= 60  # Skip very low quality
    ]
    print(f"  Total deal/exit signals (quality>=60): {len(deal_signals)}")

    # Filter by slugs FIRST (before progress filter and early-exit)
    if args.slugs:
        slug_filter = set(args.slugs.split(","))
        deal_signals = [s for s in deal_signals if s["fund_slug"] in slug_filter]
        print(f"  After slug filter: {len(deal_signals)}")

    # Filter by progress (unless --force)
    if not args.force:
        before = len(deal_signals)
        deal_signals = [s for s in deal_signals if s["id"] not in processed_ids]
        skipped = before - len(deal_signals)
        if skipped:
            print(f"  Skipping {skipped} already-processed signals (use --force to reprocess)")
    else:
        # --force for specific slugs: clear progress for those slugs only
        if args.slugs:
            slug_filter_set = set(args.slugs.split(","))
            # Remove progress entries for the targeted slugs
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
        "skipped_existing": 0, "skipped_no_company": 0, "skipped_other": 0,
        "skipped_exit_no_match": 0,
        "errors": 0, "tokens_in": 0, "tokens_out": 0,
    }
    all_processed_in_run: list[str] = []
    funds_processed = 0
    start_time = time.time()

    # Track which fund portfolios changed (for per-fund saves)
    changed_slugs: set[str] = set()

    for fund_slug, signals in sorted(by_fund.items()):
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
            client=client,
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

        # Per-fund disk save for crash safety (same pattern as enrich_portfolio_gemini_full.py)
        if not args.dry_run and fund_processed_ids:
            # Save progress after each fund
            updated_processed = list(processed_ids | set(all_processed_in_run))
            progress = {
                "processed_signal_ids": updated_processed,
                "last_run": datetime.now(timezone.utc).isoformat(),
                "stats": total_stats,
            }
            save_progress(progress)

            # Save portfolio if THIS fund changed (only write the current fund to avoid stale overwrites)
            if fund_slug in changed_slugs:
                fresh = load_portfolio()
                fresh_portfolios = fresh.get("fund_portfolios", {})
                fresh_portfolios[fund_slug] = fund_portfolios[fund_slug]
                fresh["fund_portfolios"] = fresh_portfolios
                save_portfolio(fresh)

        # Running rate logging
        if not args.dry_run and funds_processed > 0:
            elapsed = time.time() - start_time
            rate = funds_processed / (elapsed / 60) if elapsed > 0 else 0
            print(f"    [{funds_processed}/{len(by_fund)}] "
                  f"+{fund_stats['added']}add +{fund_stats['exits_updated']}exit | "
                  f"Total: +{total_stats['added']}add +{total_stats['exits_updated']}exit "
                  f"{total_stats['errors']}err | {rate:.1f} funds/min", flush=True)

    # Final save (also saves incrementally after each fund above)
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
    cost = total_stats["tokens_in"] * 0.10 / 1_000_000 + total_stats["tokens_out"] * 0.40 / 1_000_000

    print(f"\n{'=' * 60}")
    print(f"  Summary ({elapsed / 60:.1f}m)")
    print(f"{'=' * 60}")
    print(f"  Portfolio entries added:   {total_stats['added']}")
    print(f"  Exits detected & updated: {total_stats['exits_updated']}")
    print(f"  Skipped (add-on/bolt-on): {total_stats['skipped_addon']}")
    print(f"  Skipped (already exists): {total_stats['skipped_existing']}")
    print(f"  Skipped (no company):     {total_stats['skipped_no_company']}")
    print(f"  Skipped (non-deal/other): {total_stats['skipped_other']}")
    print(f"  Skipped (exit, no match): {total_stats['skipped_exit_no_match']}")
    print(f"  Errors:                   {total_stats['errors']}")
    if not args.dry_run:
        print(f"  Gemini tokens:            {total_stats['tokens_in']:,} in / {total_stats['tokens_out']:,} out")
        print(f"  Estimated cost:           ${cost:.4f}")
    print()

    # Exit code 2 for partial success (some batches failed but progress was made)
    if total_stats["errors"] > 0 and (total_stats["added"] > 0 or total_stats["exits_updated"] > 0):
        print(f"  {total_stats['errors']} signals failed — will be retried on next run")
        sys.exit(2)
    elif total_stats["errors"] > 0 and total_stats["added"] == 0 and total_stats["exits_updated"] == 0:
        print(f"  All batches failed — check API key and quota")
        sys.exit(1)


if __name__ == "__main__":
    main()
