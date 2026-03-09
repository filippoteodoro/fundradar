#!/usr/bin/env python3
"""
Verify Gemini-generated portfolio entries using Gemini + Google Search grounding.

For each entry with data_source="gemini_global_enrichment", asks Gemini to verify
whether the company is actually a portfolio company of the fund, using live Google
search results as evidence.

Outputs: data/derived/portfolio_verification.json
Actions: optionally removes entries that fail verification

Usage:
  python3 scripts/verify-portfolio-gemini.py --dry-run
  python3 scripts/verify-portfolio-gemini.py --slugs carlyle,advent-international
  python3 scripts/verify-portfolio-gemini.py --all --apply
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys; sys.path.insert(0, str(REPO_ROOT / "apps" / "worker"))
from fundradar_worker.paths import GEMINI_MODEL
DATA_DIR = REPO_ROOT / "data"
DERIVED_DIR = DATA_DIR / "derived"
PORTFOLIO_PATH = DERIVED_DIR / "portfolio_items.json"
DB_PATH = DATA_DIR / "db.json"
VERIFICATION_PATH = DERIVED_DIR / "portfolio_verification.json"

DEFAULT_MODEL = GEMINI_MODEL
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

DEFAULT_SLEEP_SECONDS = 4.5
DEFAULT_TIMEOUT_SEC = 30
DEFAULT_HARD_TIMEOUT_SEC = 45
DEFAULT_RETRIES = 2


def _print(*args: Any, **kwargs: Any) -> None:
    print(*args, **kwargs, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def resolve_gemini_api_key() -> str | None:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    for env_path in [REPO_ROOT / ".env", REPO_ROOT / "apps" / "worker" / ".env"]:
        env = parse_env_file(env_path)
        if env.get("GEMINI_API_KEY"):
            return env["GEMINI_API_KEY"]
    return None


def _sleep_with_jitter(base_seconds: float, jitter_seconds: float = 0.8) -> None:
    delay = max(0.0, base_seconds) + random.uniform(0.0, max(0.0, jitter_seconds))
    if delay > 0:
        time.sleep(delay)


def verify_entry(
    session: requests.Session,
    api_key: str,
    model: str,
    fund_name: str,
    company_name: str,
    sector: str | None,
    headquarters: str | None,
    status: str | None,
    timeout_sec: int,
    hard_timeout_sec: int,
    retries: int,
) -> dict[str, Any]:
    """Ask Gemini with grounding: is this company really in this fund's portfolio?"""

    prompt = f"""Verify this claim: "{company_name}" is a portfolio company of {fund_name} (private equity fund).

Details provided:
- Sector: {sector or 'unknown'}
- Headquarters: {headquarters or 'unknown'}
- Status: {status or 'unknown'}

Using Google Search, determine:
1. Is "{company_name}" a real company? (yes/no)
2. Is it currently or was it recently a portfolio company of {fund_name}? (yes/no/uncertain)
3. If the status says "current", is it still held? If "exited", was it actually sold?

Respond with ONLY a JSON object:
{{
  "real_company": true/false,
  "is_portfolio_company": true/false/null,
  "confidence": "high"/"medium"/"low",
  "correct_status": "current"/"exited"/null,
  "notes": "brief explanation"
}}

If you cannot find evidence either way, set is_portfolio_company to null and confidence to "low"."""

    url = f"{GEMINI_BASE_URL}/{model}:generateContent?key={api_key}"
    # NOTE: grounding (google_search) is incompatible with responseMimeType/responseSchema.
    # We use plain text output and parse JSON from the response.
    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
        },
        "tools": [{"google_search": {}}],
    }

    last_error = ""
    for attempt in range(retries + 1):
        try:
            def _do_request() -> requests.Response:
                return session.post(url, json=payload, timeout=timeout_sec)

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_do_request)
                try:
                    resp = future.result(timeout=hard_timeout_sec)
                except FuturesTimeout:
                    future.cancel()
                    last_error = f"Hard timeout after {hard_timeout_sec}s"
                    if attempt < retries:
                        _sleep_with_jitter(2.0)
                        continue
                    return {"error": last_error}

            if resp.status_code == 429:
                last_error = f"Rate limited (429)"
                if attempt < retries:
                    _sleep_with_jitter(5.0 + attempt * 3)
                    continue
                return {"error": last_error}

            if resp.status_code >= 400:
                body = resp.text[:300]
                # If grounding is rejected, retry without it
                if "google_search" in body.lower() or "tool" in body.lower():
                    payload.pop("tools", None)
                    if attempt < retries:
                        _sleep_with_jitter(1.0)
                        continue
                last_error = f"HTTP {resp.status_code}: {body}"
                if attempt < retries:
                    _sleep_with_jitter(2.0)
                    continue
                return {"error": last_error}

            raw = resp.json()
            candidates = raw.get("candidates") or []
            if not candidates:
                return {"error": "No candidates in response"}

            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            text = ""
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    text += part["text"]

            if not text.strip():
                return {"error": "Empty response text"}

            # Check if grounding was used
            grounding = candidates[0].get("groundingMetadata")
            grounded = grounding is not None and bool(grounding.get("groundingChunks"))

            # Parse JSON response
            text = text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(lines).strip()

            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if match:
                    result = json.loads(match.group(0))
                else:
                    return {"error": f"JSON parse failed: {text[:200]}"}

            result["grounded"] = grounded
            return result

        except requests.RequestException as e:
            last_error = f"Request error: {e}"
            if attempt < retries:
                _sleep_with_jitter(2.0)
                continue
            return {"error": last_error}

        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                _sleep_with_jitter(2.0)
                continue
            return {"error": last_error}

    return {"error": last_error or "Unknown failure"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Gemini portfolio entries via Google Search grounding.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--slugs", type=str, help="Comma-separated fund slugs to verify")
    parser.add_argument("--all", action="store_true", help="Verify all funds with Gemini entries")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be verified, don't call API")
    parser.add_argument("--apply", action="store_true", help="Remove entries that fail verification")
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--hard-timeout-sec", type=int, default=DEFAULT_HARD_TIMEOUT_SEC)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--reset", action="store_true", help="Re-verify already verified entries")
    parser.add_argument("--retry-errors", action="store_true", help="Re-verify only entries that had errors")
    args = parser.parse_args()

    db = load_json(DB_PATH)
    if not db:
        _print("Error: could not load db.json", file=sys.stderr)
        return 2
    portfolio_data = load_json(PORTFOLIO_PATH)
    if not portfolio_data:
        _print("Error: could not load portfolio_items.json", file=sys.stderr)
        return 2

    fund_portfolios = portfolio_data.get("fund_portfolios") or {}
    fund_by_slug = {f["slug"]: f for f in db.get("funds", []) if f.get("slug")}

    # Load previous verification results
    prev_results: dict[str, Any] = {}
    if not args.reset:
        prev_results = load_json(VERIFICATION_PATH) or {}

    # Build verification queue
    if args.slugs:
        slugs = [s.strip() for s in args.slugs.split(",") if s.strip()]
    elif args.all:
        slugs = sorted(fund_by_slug.keys())
    else:
        _print("Error: specify --slugs or --all")
        return 2

    # Collect entries to verify
    queue: list[tuple[str, str, dict[str, Any]]] = []  # (slug, fund_name, entry)
    for slug in slugs:
        fund = fund_by_slug.get(slug)
        if not fund:
            _print(f"Warning: unknown slug {slug}")
            continue
        fund_name = fund.get("name") or slug
        entries = fund_portfolios.get(slug, [])
        gemini_entries = [e for e in entries if e.get("data_source") == "gemini_global_enrichment"]
        if not gemini_entries:
            continue

        for entry in gemini_entries:
            company = entry.get("name", "")
            key = f"{slug}::{company}"
            if key in prev_results:
                if args.reset:
                    pass  # Re-verify everything
                elif args.retry_errors and "error" in prev_results[key]:
                    pass  # Retry errors only
                else:
                    continue  # Already verified
            queue.append((slug, fund_name, entry))

    _print(f"Entries to verify: {len(queue)}")
    if not queue:
        _print("Nothing to verify.")
        return 0

    # Group by fund for display
    by_fund: dict[str, int] = {}
    for slug, _, _ in queue:
        by_fund[slug] = by_fund.get(slug, 0) + 1
    for slug, count in sorted(by_fund.items()):
        _print(f"  {slug}: {count} entries")

    if args.dry_run:
        _print("\nDry run — would verify the above entries. Exiting.")
        return 0

    api_key = resolve_gemini_api_key()
    if not api_key:
        _print("Error: GEMINI_API_KEY not found", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    results = dict(prev_results)  # Carry forward previous results
    verified = 0
    confirmed = 0
    rejected = 0
    uncertain = 0
    errors = 0

    for idx, (slug, fund_name, entry) in enumerate(queue, 1):
        company = entry.get("name", "")
        key = f"{slug}::{company}"

        _print(f"[{idx}/{len(queue)}] {fund_name} / {company} ... ", end="")

        result = verify_entry(
            session=session,
            api_key=api_key,
            model=args.model,
            fund_name=fund_name,
            company_name=company,
            sector=entry.get("sector"),
            headquarters=entry.get("headquarters"),
            status=entry.get("status"),
            timeout_sec=args.timeout_sec,
            hard_timeout_sec=args.hard_timeout_sec,
            retries=args.retries,
        )

        if "error" in result:
            _print(f"ERROR: {result['error'][:80]}")
            errors += 1
            result["_slug"] = slug
            result["_company"] = company
            result["_verified_at"] = now_iso()
            results[key] = result
        else:
            is_portfolio = result.get("is_portfolio_company")
            confidence = result.get("confidence", "low")
            grounded = result.get("grounded", False)
            notes = result.get("notes", "")[:100]

            if is_portfolio is True:
                _print(f"CONFIRMED ({confidence}, grounded={grounded})")
                confirmed += 1
            elif is_portfolio is False:
                _print(f"REJECTED ({confidence}) — {notes}")
                rejected += 1
            else:
                _print(f"UNCERTAIN ({confidence}) — {notes}")
                uncertain += 1

            result["_slug"] = slug
            result["_company"] = company
            result["_verified_at"] = now_iso()
            results[key] = result

        verified += 1

        # Save every 10
        if verified % 10 == 0:
            save_json_atomic(VERIFICATION_PATH, results)

        _sleep_with_jitter(args.sleep_seconds)

    session.close()
    save_json_atomic(VERIFICATION_PATH, results)

    _print(f"\nVerification complete:")
    _print(f"  Confirmed: {confirmed}")
    _print(f"  Rejected:  {rejected}")
    _print(f"  Uncertain: {uncertain}")
    _print(f"  Errors:    {errors}")

    # Apply removals if requested
    if args.apply and rejected > 0:
        _print(f"\nApplying removals...")
        removed_total = 0
        for key, result in results.items():
            if result.get("is_portfolio_company") is not False:
                continue
            if result.get("confidence") not in ("high", "medium"):
                continue  # Only remove high/medium confidence rejections
            slug = result.get("_slug")
            company = result.get("_company")
            if not slug or not company:
                continue

            entries = fund_portfolios.get(slug, [])
            before = len(entries)
            fund_portfolios[slug] = [
                e for e in entries
                if not (e.get("name") == company and e.get("data_source") == "gemini_global_enrichment")
            ]
            removed = before - len(fund_portfolios[slug])
            if removed > 0:
                _print(f"  Removed: {slug}/{company}")
                removed_total += removed

        if removed_total > 0:
            save_json_atomic(PORTFOLIO_PATH, portfolio_data)
            _print(f"  Total removed: {removed_total}")
        else:
            _print("  Nothing to remove.")

    # Also fix statuses if verification found corrections
    status_fixes = 0
    for key, result in results.items():
        if result.get("is_portfolio_company") is not True:
            continue
        correct_status = result.get("correct_status")
        if not correct_status or correct_status not in ("current", "exited"):
            continue
        slug = result.get("_slug")
        company = result.get("_company")
        if not slug or not company:
            continue
        for entry in fund_portfolios.get(slug, []):
            if entry.get("name") == company and entry.get("status") != correct_status:
                if args.apply:
                    entry["status"] = correct_status
                    _print(f"  Status fix: {slug}/{company} → {correct_status}")
                status_fixes += 1

    if args.apply and status_fixes > 0:
        save_json_atomic(PORTFOLIO_PATH, portfolio_data)
        _print(f"  Status fixes applied: {status_fixes}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
