#!/usr/bin/env python3
"""
Enrich portfolio entries (HQ only) using Gemini 3 Flash with Google Search grounding.

Sectors are handled separately via manual Claude prompts (free, no web search needed).
This script focuses on headquarters which genuinely requires web search.

Usage:
    python apps/worker/scripts/enrich_gemini.py --dry-run
    python apps/worker/scripts/enrich_gemini.py --limit 5
    python apps/worker/scripts/enrich_gemini.py
    python apps/worker/scripts/enrich_gemini.py --slug alto-partners-sgr

Multi-pass approach: processes all batches, skips timeouts, then re-runs to catch failures.
Failed batches are NOT marked as done, so running the script again picks up where it left off.
Merge-safe saves: re-reads file from disk before writing, preserves concurrent manual edits.
"""

import argparse
import json
import os
import signal as _signal
import sys
import time
from pathlib import Path

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
PORTFOLIO_FILE = DATA_DIR / "portfolio_items.json"
PROGRESS_FILE = DATA_DIR / "enrichment_gemini_progress.json"

MODEL = "gemini-3-flash-preview"
BATCH_SIZE = 5
MAX_RETRIES = 2  # Retry failed calls
CALL_TIMEOUT = 300  # 5 minutes - grounding searches can be slow
DELAY_BETWEEN_CALLS = 3.0


def build_prompt(companies: list[dict], fund_name: str) -> str:
    lines = []
    for i, c in enumerate(companies, 1):
        parts = [c["name"]]
        if c.get("website"):
            parts.append(f"[{c['website']}]")
        if c.get("description"):
            parts.append(f"({c['description'][:60]})")
        parts.append(f"fund={fund_name}")
        lines.append(f"{i}. " + " | ".join(parts))

    company_block = "\n".join(lines)

    return f"""Look up these companies (portfolio investments of "{fund_name}" PE/VC fund). Search the web for each.

For each company, find its headquarters location.

Return ONLY a JSON array: [{{"company":"Name","hq":"City, Country"}}]
Use null for hq if truly unknown after searching. No explanation text.

{company_block}"""


class _CallTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _CallTimeout()


def enrich_batch(client, companies: list[dict], fund_name: str) -> tuple:
    """Call Gemini API with timeout and retry."""
    from google.genai import types

    prompt = build_prompt(companies, fund_name)

    for attempt in range(1 + MAX_RETRIES):
        try:
            old_handler = _signal.signal(_signal.SIGALRM, _alarm_handler)
            _signal.alarm(CALL_TIMEOUT)

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                ),
            )

            _signal.alarm(0)
            _signal.signal(_signal.SIGALRM, old_handler)

            text = response.text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(lines)

            results = json.loads(text)

            usage = response.usage_metadata
            in_tok = usage.prompt_token_count or 0
            out_tok = usage.candidates_token_count or 0
            return results, in_tok, out_tok

        except _CallTimeout:
            _signal.alarm(0)
            _signal.signal(_signal.SIGALRM, old_handler)
            if attempt < MAX_RETRIES:
                print(f"    Timeout (attempt {attempt+1}), retrying in 10s...", flush=True)
                time.sleep(10)
                continue
            return [], 0, 0

        except json.JSONDecodeError:
            _signal.alarm(0)
            _signal.signal(_signal.SIGALRM, old_handler)
            if attempt < MAX_RETRIES:
                time.sleep(5)
                continue
            return [], 0, 0

        except Exception as e:
            _signal.alarm(0)
            _signal.signal(_signal.SIGALRM, old_handler)
            if attempt < MAX_RETRIES:
                print(f"    Error (attempt {attempt+1}): {str(e)[:60]}, retrying...", flush=True)
                time.sleep(10)
                continue
            return [], 0, 0


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"done": {}}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)


def _merge_and_save(pending: dict):
    """Re-read portfolio from disk, merge pending enrichments, write back.

    This is safe for concurrent edits: we only fill in fields that are
    STILL missing on disk, so manual enrichments done in parallel are preserved.

    pending: {slug: {company_name_lower: {"hq": ...}}}
    """
    with open(PORTFOLIO_FILE) as f:
        portfolio = json.load(f)

    applied_h = 0
    for slug, companies in pending.items():
        entries = portfolio.get("fund_portfolios", {}).get(slug, [])
        for entry in entries:
            name_key = entry.get("name", "").lower().strip()
            enrichment = companies.get(name_key)
            if not enrichment:
                continue
            if not entry.get("headquarters") and enrichment.get("hq"):
                entry["headquarters"] = enrichment["hq"]
                applied_h += 1

    try:
        from fundradar_worker.io_utils import safe_json_write, backup_before_write
        backup_before_write(PORTFOLIO_FILE)
        safe_json_write(PORTFOLIO_FILE, portfolio)
    except ImportError:
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".json")
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(portfolio, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(PORTFOLIO_FILE))

    return applied_h


def main():
    parser = argparse.ArgumentParser(description="Enrich portfolio via Gemini Flash")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max API calls")
    parser.add_argument("--slug", type=str, help="Only process one fund")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and not args.dry_run:
        print("Error: GEMINI_API_KEY not found")
        sys.exit(1)

    # Load data
    with open(PORTFOLIO_FILE) as f:
        portfolio = json.load(f)
    fund_portfolios = portfolio.get("fund_portfolios", {})

    db_path = PROJECT_ROOT / "data" / "db.json"
    fund_names = {}
    if db_path.exists():
        db = json.load(open(db_path))
        for fund in db.get("funds", []):
            fund_names[fund["slug"]] = fund.get("name", fund["slug"])

    progress = load_progress()
    done = progress.get("done", {})

    # Find work — only entries missing headquarters (sectors handled by manual prompts)
    all_batches = []
    for slug, entries in sorted(fund_portfolios.items()):
        if args.slug and slug != args.slug:
            continue
        needs_work = []
        for e in entries:
            key = f"{slug}::{e.get('name', '')}"
            if key in done:
                continue
            if not e.get("headquarters"):
                needs_work.append(e)
        if needs_work:
            fund_name = fund_names.get(slug, slug)
            for batch_start in range(0, len(needs_work), BATCH_SIZE):
                batch = needs_work[batch_start: batch_start + BATCH_SIZE]
                all_batches.append((slug, fund_name, batch))

    total_entries = sum(len(b[2]) for b in all_batches)
    print(f"Entries to enrich: {total_entries}")
    print(f"API calls needed:  {len(all_batches)}")
    print(f"Model: {MODEL} + Google Search grounding")
    print(f"Timeout: {CALL_TIMEOUT}s, Retries: {MAX_RETRIES}")
    print(f"Failed batches are NOT marked done — re-run script to retry them")
    print()

    if args.dry_run:
        fund_counts = {}
        for slug, _, batch in all_batches:
            fund_counts[slug] = fund_counts.get(slug, 0) + len(batch)
        for slug, count in sorted(fund_counts.items())[:15]:
            print(f"  {slug}: {count} entries")
        if len(fund_counts) > 15:
            print(f"  ... +{len(fund_counts) - 15} more funds")
        return

    from google import genai
    client = genai.Client(api_key=api_key)

    if args.limit:
        all_batches = all_batches[:args.limit]

    api_calls = 0
    total_in = 0
    total_out = 0
    enriched_hqs = 0
    skipped = 0
    errors = 0
    start_time = time.time()

    # Collect enrichments for merge-on-save (safe with concurrent edits)
    # {slug: {company_name_lower: {"sector": ..., "hq": ...}}}
    pending_enrichments = {}

    print(f"Processing {len(all_batches)} batches...\n", flush=True)

    for batch_idx, (slug, fund_name, batch) in enumerate(all_batches):
        results, in_tok, out_tok = enrich_batch(client, batch, fund_name)
        api_calls += 1
        total_in += in_tok
        total_out += out_tok

        if not results:
            errors += 1
            print(f"  [{batch_idx+1}/{len(all_batches)}] {fund_name} — FAILED (will retry next run)", flush=True)
            time.sleep(DELAY_BETWEEN_CALLS)
            continue

        # Match results to entries
        results_map = {r.get("company", "").lower().strip(): r for r in results}

        batch_hqs = 0

        if slug not in pending_enrichments:
            pending_enrichments[slug] = {}

        for entry in batch:
            name = entry.get("name", "")
            key = f"{slug}::{name}"
            name_lower = name.lower().strip()
            r = results_map.get(name_lower)

            if r and r.get("hq"):
                pending_enrichments[slug][name_lower] = {"hq": r["hq"]}
                batch_hqs += 1
            else:
                skipped += 1

            # Only mark as done on success
            done[key] = True

        enriched_hqs += batch_hqs

        elapsed = time.time() - start_time
        successful = api_calls - errors
        rate = successful / (elapsed / 60) if elapsed > 0 else 0

        print(f"  [{batch_idx+1}/{len(all_batches)}] {fund_name} +{batch_hqs}h | "
              f"Total: +{enriched_hqs}h | {errors} err | "
              f"{rate:.1f} ok/min", flush=True)

        # Save every 10 calls — re-reads file from disk to preserve concurrent edits
        if api_calls % 10 == 0:
            save_progress(progress)
            h = _merge_and_save(pending_enrichments)
            pending_enrichments.clear()
            print(f"  === SAVED (merged {h}h to disk) ===", flush=True)

        time.sleep(DELAY_BETWEEN_CALLS)

    # Final save — merge remaining pending enrichments
    save_progress(progress)
    if pending_enrichments:
        h = _merge_and_save(pending_enrichments)
        print(f"  === FINAL SAVE (merged {h}h to disk) ===", flush=True)

    elapsed = time.time() - start_time
    cost = total_in * 0.10 / 1_000_000 + total_out * 0.40 / 1_000_000
    print(f"\n{'='*50}")
    print(f"Done in {elapsed/60:.1f}m")
    print(f"HQs: +{enriched_hqs}, Skipped: {skipped}")
    print(f"API calls: {api_calls} ({errors} failed)")
    print(f"Tokens: {total_in} in / {total_out} out, Cost: ${cost:.4f}")
    if errors > 0:
        print(f"\n{errors} batches failed — run the script again to retry them")


if __name__ == "__main__":
    main()
