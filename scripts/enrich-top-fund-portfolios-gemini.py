#!/usr/bin/env python3
"""
Enrich portfolio data for top funds by AUM using Gemini 3 Flash.

These mega-funds have websites that block scraping, so their portfolios are thin
(Italy-only from manual entries + PEM deals). This script asks Gemini for their
major global portfolio companies to provide a more complete view.

Uses REST API (same pattern as generate-fund-descriptions-gemini.py).

Outputs: updates `data/derived/portfolio_items.json`
Progress: `data/derived/top_fund_portfolio_enrichment_progress.json`

Usage:
  python3 scripts/enrich-top-fund-portfolios-gemini.py --dry-run
  python3 scripts/enrich-top-fund-portfolios-gemini.py --slugs blackstone,carlyle
  python3 scripts/enrich-top-fund-portfolios-gemini.py --top 10
  python3 scripts/enrich-top-fund-portfolios-gemini.py --top 10 --max-per-fund 50
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import signal as _signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys; sys.path.insert(0, str(REPO_ROOT / "apps" / "worker"))
from fundradar_worker.paths import GEMINI_MODEL
from fundradar_worker.io_utils import safe_json_write
DATA_DIR = REPO_ROOT / "data"
DERIVED_DIR = DATA_DIR / "derived"

DB_PATH = DATA_DIR / "db.json"
PORTFOLIO_PATH = DERIVED_DIR / "portfolio_items.json"
PROGRESS_PATH = DERIVED_DIR / "top_fund_portfolio_enrichment_progress.json"

DEFAULT_MODEL = GEMINI_MODEL
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}

DEFAULT_SLEEP_SECONDS = 4.5  # Gemini free tier: 15 RPM → need ~4s between calls
DEFAULT_TIMEOUT_SEC = 60
DEFAULT_HARD_TIMEOUT_SEC = 90
DEFAULT_RETRIES = 2
DEFAULT_MIN_BACKOFF_SEC = 2.0
DEFAULT_MAX_BACKOFF_SEC = 20.0
DEFAULT_MAX_OUTPUT_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TOP_N = 10
DEFAULT_MAX_PER_FUND = 40


# ---------------------------------------------------------------------------
# Helpers (same as generate-fund-descriptions-gemini.py)
# ---------------------------------------------------------------------------


class _AlarmTimeout(Exception):
    pass


def _alarm_handler(signum: int, frame: Any) -> None:
    raise _AlarmTimeout()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)



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


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def parse_json_from_model_text(text: str) -> dict[str, Any]:
    cleaned = strip_markdown_fences(text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Model response JSON is not an object")
    return parsed


def extract_text_from_gemini_response(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError(f"No candidates in Gemini response: {json.dumps(payload)[:500]}")
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            texts.append(part["text"])
    if not texts:
        raise ValueError(f"No text parts in Gemini response: {json.dumps(payload)[:500]}")
    return "\n".join(texts).strip()


def _sleep_with_jitter(base_seconds: float, jitter_seconds: float = 0.8) -> None:
    delay = max(0.0, base_seconds) + random.uniform(0.0, max(0.0, jitter_seconds))
    if delay > 0:
        time.sleep(delay)


def _compute_backoff(
    *, attempt: int, min_backoff_sec: float, max_backoff_sec: float, is_rate_limit: bool,
) -> float:
    scaled = min_backoff_sec * (2**attempt)
    if is_rate_limit:
        scaled = max(scaled, min_backoff_sec + 2)
    return min(max_backoff_sec, scaled)


def _request_with_hard_timeout(
    *, session: requests.Session, url: str, payload: dict[str, Any],
    timeout_sec: int, hard_timeout_sec: int,
) -> requests.Response:
    """Use a thread pool for hard timeout — SIGALRM is unreliable on macOS."""
    def _do_request() -> requests.Response:
        return session.post(url, json=payload, timeout=timeout_sec)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_do_request)
        try:
            return future.result(timeout=hard_timeout_sec)
        except FuturesTimeout:
            future.cancel()
            raise _AlarmTimeout()


def call_gemini_json(
    *, session: requests.Session, api_key: str, model: str, prompt: str,
    response_schema: dict[str, Any] | None, max_output_tokens: int,
    temperature: float, timeout_sec: int, hard_timeout_sec: int,
    retries: int, min_backoff_sec: float, max_backoff_sec: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    url = f"{GEMINI_BASE_URL}/{model}:generateContent"
    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
        "responseMimeType": "application/json",
    }
    if response_schema:
        generation_config["responseSchema"] = response_schema

    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }

    last_error = ""
    for attempt in range(retries + 1):
        try:
            resp = _request_with_hard_timeout(
                session=session, url=f"{url}?key={api_key}", payload=payload,
                timeout_sec=timeout_sec, hard_timeout_sec=hard_timeout_sec,
            )

            if resp.status_code in RETRYABLE_HTTP_STATUS or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                if attempt < retries:
                    _sleep_with_jitter(_compute_backoff(
                        attempt=attempt, min_backoff_sec=min_backoff_sec,
                        max_backoff_sec=max_backoff_sec, is_rate_limit=resp.status_code == 429,
                    ))
                    continue
                raise RuntimeError(last_error)

            if resp.status_code >= 400:
                body = resp.text
                body_lower = body.lower()
                if (
                    isinstance(payload.get("generationConfig"), dict)
                    and payload["generationConfig"].get("responseSchema") is not None
                    and ("responseschema" in body_lower or "schema" in body_lower)
                ):
                    payload["generationConfig"].pop("responseSchema", None)
                    if attempt < retries:
                        _sleep_with_jitter(1.0, 0.5)
                        continue
                if resp.status_code in {401, 403, 404}:
                    raise RuntimeError(f"Gemini error {resp.status_code}: {body[:500]}")
                if attempt < retries:
                    _sleep_with_jitter(_compute_backoff(
                        attempt=attempt, min_backoff_sec=min_backoff_sec,
                        max_backoff_sec=max_backoff_sec, is_rate_limit=resp.status_code == 429,
                    ))
                    continue
                raise RuntimeError(f"Gemini error {resp.status_code}: {body[:500]}")

            raw = resp.json()
            text = extract_text_from_gemini_response(raw)
            parsed = parse_json_from_model_text(text)
            usage = raw.get("usageMetadata") or {}
            meta = {
                "prompt_token_count": usage.get("promptTokenCount"),
                "candidates_token_count": usage.get("candidatesTokenCount"),
                "total_token_count": usage.get("totalTokenCount"),
            }
            return parsed, meta

        except _AlarmTimeout:
            last_error = f"Hard timeout after {hard_timeout_sec}s"
            if attempt < retries:
                _sleep_with_jitter(_compute_backoff(
                    attempt=attempt, min_backoff_sec=min_backoff_sec,
                    max_backoff_sec=max_backoff_sec, is_rate_limit=False,
                ))
                continue
            raise RuntimeError(last_error) from None

        except requests.RequestException as e:
            last_error = f"Request failed: {e}"
            if attempt < retries:
                _sleep_with_jitter(_compute_backoff(
                    attempt=attempt, min_backoff_sec=min_backoff_sec,
                    max_backoff_sec=max_backoff_sec, is_rate_limit=False,
                ))
                continue
            raise RuntimeError(last_error) from e

        except json.JSONDecodeError as e:
            last_error = f"JSON decode failed: {e}"
            if attempt < retries:
                _sleep_with_jitter(_compute_backoff(
                    attempt=attempt, min_backoff_sec=min_backoff_sec,
                    max_backoff_sec=max_backoff_sec, is_rate_limit=False,
                ))
                continue
            raise RuntimeError(last_error) from e

        except Exception as e:
            last_error = str(e)
            if "gemini error 401" in last_error.lower() or "gemini error 403" in last_error.lower():
                raise RuntimeError(last_error) from e
            if attempt < retries:
                _sleep_with_jitter(_compute_backoff(
                    attempt=attempt, min_backoff_sec=min_backoff_sec,
                    max_backoff_sec=max_backoff_sec, is_rate_limit="429" in last_error,
                ))
                continue
            raise RuntimeError(last_error) from e

    raise RuntimeError(last_error or "Unknown Gemini failure")


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

PORTFOLIO_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "companies": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "sector": {"type": "STRING"},
                    "headquarters": {"type": "STRING"},
                    "status": {"type": "STRING", "enum": ["current", "exited"]},
                    "description": {"type": "STRING"},
                },
                "required": ["name", "sector", "headquarters", "status"],
            },
        },
    },
    "required": ["companies"],
}


# ---------------------------------------------------------------------------
# Name normalization for dedup
# ---------------------------------------------------------------------------

_LEGAL_SUFFIXES = re.compile(
    r"\b(s\.?p\.?a\.?|s\.?r\.?l\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?s\.?|ltd\.?|inc\.?|corp\.?|"
    r"llc\.?|plc\.?|gmbh|ag|sa|nv|bv|se|pty|co\.?|limited|group|technologies)\s*$",
    re.I,
)


def normalize_name(name: str) -> str:
    """Normalize company name for dedup matching."""
    n = name.lower().strip()
    # Strip parenthetical
    n = re.sub(r"\s*\(.*?\)\s*", " ", n)
    # Strip legal suffixes
    n = _LEGAL_SUFFIXES.sub("", n).strip()
    # Non-alphanumeric to space, collapse
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return n


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def build_prompt(
    fund: dict[str, Any],
    existing_names: list[str],
    max_companies: int,
    focus: str = "",
) -> str:
    existing_json = json.dumps(existing_names, ensure_ascii=False)
    strategies = ', '.join(fund.get('strategy_tags') or []) or 'N/A'

    focus_instruction = ""
    if focus:
        focus_instruction = f"\nFOCUS THIS ROUND ON: {focus}\n"

    return f"""You are building a portfolio database for a PE/VC fund directory.

FUND:
- Name: {fund.get('name')}
- Website: {fund.get('website') or 'N/A'}
- Category: {fund.get('category') or 'N/A'}
- AUM (EUR): {fund.get('aum_eur') or 'N/A'}
- Strategies: {strategies}

EXISTING PORTFOLIO (already in our database — DO NOT repeat these):
{existing_json}
{focus_instruction}
TASK:
List the major portfolio companies for this fund that are NOT in the existing list.
Include both current investments and notable exits (last 5 years).
Cover all geographies — this is a global view.
Only include companies you are genuinely confident are or were in this fund's portfolio.
It is perfectly fine to return fewer companies if that is all you know with certainty.
Do NOT pad the list — accuracy matters more than quantity.

For each company provide:
- name: official company name (no fund name, no deal description)
- sector: one of: Technology, Healthcare, Industrial Manufacturing, Consumer Goods, Financial Services, Real Estate, Energy, Renewable Energy, Media & Entertainment, Telecommunications, Transportation & Logistics, Food & Beverage, Professional Services, Education, Retail, Automotive, Aerospace & Defence, Chemicals & Materials, Construction, Fashion & Luxury, Hospitality & Tourism, Water & Utilities, Agriculture, Insurance, Pharma & Biotech
- headquarters: "City, Country" format
- status: "current" or "exited"
- description: one sentence about what the company does (optional but preferred)

RULES:
- Quality over quantity — only include companies you can verify from public records
- Use the fund's actual known portfolio, not general industry knowledge
- For multi-strategy firms, focus on private equity, growth equity, and infrastructure deals
- Exclude pure credit/lending positions, individual real estate properties, and fund-of-funds

Return JSON: {{"companies": [...]}}"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _print(*args: Any, **kwargs: Any) -> None:
    """Print with flush to ensure output appears in piped contexts."""
    print(*args, **kwargs, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich top fund portfolios with global companies via Gemini."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="Top N funds by AUM")
    parser.add_argument("--slugs", type=str, help="Comma-separated fund slugs (overrides --top)")
    parser.add_argument("--max-per-fund", type=int, default=DEFAULT_MAX_PER_FUND,
                        help="Max new companies to request per fund")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true", help="Ignore previous progress")
    parser.add_argument("--skip-large", type=int, default=100,
                        help="Skip funds already having this many portfolio entries (0=no skip)")
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--hard-timeout-sec", type=int, default=DEFAULT_HARD_TIMEOUT_SEC)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--min-backoff-sec", type=float, default=DEFAULT_MIN_BACKOFF_SEC)
    parser.add_argument("--max-backoff-sec", type=float, default=DEFAULT_MAX_BACKOFF_SEC)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    args = parser.parse_args()

    # Load data
    db = load_json(DB_PATH)
    if not db or not isinstance(db, dict):
        _print("Error: could not load db.json", file=sys.stderr)
        return 2
    portfolio_data = load_json(PORTFOLIO_PATH)
    if not portfolio_data or not isinstance(portfolio_data, dict):
        _print("Error: could not load portfolio_items.json", file=sys.stderr)
        return 2

    fund_portfolios = portfolio_data.get("fund_portfolios") or {}
    funds = db.get("funds") or []
    fund_by_slug = {f["slug"]: f for f in funds if f.get("slug")}

    # Build queue
    if args.slugs:
        slugs = [s.strip() for s in args.slugs.split(",") if s.strip()]
        invalid = [s for s in slugs if s not in fund_by_slug]
        if invalid:
            _print(f"Warning: unknown slugs: {', '.join(invalid)}")
        queue = [fund_by_slug[s] for s in slugs if s in fund_by_slug]
    else:
        sorted_funds = sorted(
            [f for f in funds if f.get("aum_eur")],
            key=lambda f: f["aum_eur"],
            reverse=True,
        )
        queue = sorted_funds[: args.top]

    # Filter out funds that already have large portfolios
    if args.skip_large > 0:
        filtered = []
        for fund in queue:
            count = len(fund_portfolios.get(fund["slug"], []))
            if count >= args.skip_large:
                _print(f"Skipping {fund['slug']} — already has {count} entries (threshold: {args.skip_large})")
            else:
                filtered.append(fund)
        queue = filtered

    # Load progress
    progress: dict[str, Any]
    if args.reset:
        progress = {"completed_slugs": [], "started_at": now_iso()}
    else:
        progress = load_json(PROGRESS_PATH) or {"completed_slugs": []}
    completed = set(progress.get("completed_slugs") or [])

    # Skip already completed
    if not args.reset:
        queue = [f for f in queue if f["slug"] not in completed]

    _print(f"Funds to enrich: {len(queue)}")
    for f in queue:
        existing = len(fund_portfolios.get(f["slug"], []))
        _print(f"  {f['slug']}: AUM={f.get('aum_eur', 0):,.0f} | existing={existing}")

    if not queue:
        _print("Nothing to do.")
        return 0

    # Focus lenses — each pass asks about a different slice of the portfolio.
    # This naturally discovers more companies without inflating any single call.
    FOCUS_PASSES: list[tuple[str, str]] = [
        ("general", ""),
        ("technology_healthcare", "Technology, Healthcare, and Pharma & Biotech investments"),
        ("industrials_infra", "Industrial Manufacturing, Energy, Renewable Energy, and Infrastructure investments"),
        ("consumer_services", "Consumer Goods, Retail, Food & Beverage, Hospitality, and Media & Entertainment investments"),
        ("financial_other", "Financial Services, Insurance, Professional Services, Aerospace & Defence, and other sectors not yet covered"),
    ]

    if args.dry_run:
        _print("\n--- DRY RUN ---\n")
        fund = queue[0]
        slug = fund["slug"]
        existing = fund_portfolios.get(slug, [])
        existing_names = [e["name"] for e in existing if isinstance(e, dict) and e.get("name")]
        for pass_name, focus in FOCUS_PASSES:
            prompt = build_prompt(fund, existing_names, args.max_per_fund, focus=focus)
            _print(f"[{slug}] Pass '{pass_name}' — Prompt ({len(prompt)} chars):")
            _print(prompt[:600])
            _print("---\n")
        _print("Dry-run complete.")
        return 0

    # Resolve API key
    api_key = resolve_gemini_api_key()
    if not api_key:
        _print("Error: GEMINI_API_KEY not found", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    _print(f"\nSettings: model={args.model}, passes={len(FOCUS_PASSES)}, "
           f"sleep={args.sleep_seconds}s, retries={args.retries}")

    total_added = 0
    total_skipped_dupes = 0

    for idx, fund in enumerate(queue, 1):
        slug = fund["slug"]
        name = fund.get("name") or slug
        existing = fund_portfolios.get(slug, [])
        existing_names = [e["name"] for e in existing if isinstance(e, dict) and e.get("name")]
        existing_normalized = {normalize_name(n) for n in existing_names}

        _print(f"\n[{idx}/{len(queue)}] {name} ({slug}) | existing={len(existing)}")
        fund_added = 0
        fund_dupes = 0
        consecutive_empty = 0

        for pass_idx, (pass_name, focus) in enumerate(FOCUS_PASSES, 1):
            # Stop if 2 consecutive passes returned nothing new — model has exhausted its knowledge
            if consecutive_empty >= 2:
                _print(f"  Pass {pass_idx} '{pass_name}' — skipped (2 empty passes, stopping)")
                continue

            # Rebuild names list each pass (grows as we add)
            current_names = [e["name"] for e in existing if isinstance(e, dict) and e.get("name")]
            prompt = build_prompt(fund, current_names, args.max_per_fund, focus=focus)

            try:
                parsed, meta = call_gemini_json(
                    session=session, api_key=api_key, model=args.model, prompt=prompt,
                    response_schema=PORTFOLIO_SCHEMA, max_output_tokens=args.max_output_tokens,
                    temperature=args.temperature, timeout_sec=args.timeout_sec,
                    hard_timeout_sec=args.hard_timeout_sec, retries=args.retries,
                    min_backoff_sec=args.min_backoff_sec, max_backoff_sec=args.max_backoff_sec,
                )

                companies = parsed.get("companies", [])
                if not isinstance(companies, list):
                    _print(f"  Pass {pass_idx} '{pass_name}' — unexpected format, skipping")
                    consecutive_empty += 1
                    _sleep_with_jitter(args.sleep_seconds)
                    continue

                added = 0
                dupes = 0
                for comp in companies:
                    if not isinstance(comp, dict):
                        continue
                    comp_name = (comp.get("name") or "").strip()
                    if not comp_name:
                        continue

                    norm = normalize_name(comp_name)
                    if norm in existing_normalized or len(norm) < 3:
                        dupes += 1
                        continue

                    status = comp.get("status", "current")
                    if status not in ("current", "exited"):
                        status = "current"

                    entry: dict[str, Any] = {
                        "name": comp_name,
                        "sector": comp.get("sector") or None,
                        "headquarters": comp.get("headquarters") or None,
                        "status": status,
                        "description": comp.get("description") or None,
                        "confidence": 0.7,
                        "data_source": "gemini_global_enrichment",
                        "detail_page_url": None,
                        "website": None,
                        "investment_date": None,
                    }

                    existing.append(entry)
                    existing_normalized.add(norm)
                    added += 1

                tokens = meta.get("total_token_count", "?")
                _print(f"  Pass {pass_idx} '{pass_name}': +{added} new, {dupes} dupes, "
                       f"{len(companies)} returned | tokens={tokens}")
                fund_added += added
                fund_dupes += dupes

                if added == 0:
                    consecutive_empty += 1
                else:
                    consecutive_empty = 0

            except Exception as e:
                _print(f"  Pass {pass_idx} '{pass_name}' FAILED: {str(e)[:150]}")
                consecutive_empty += 1

            _sleep_with_jitter(args.sleep_seconds)

        fund_portfolios[slug] = existing
        total_added += fund_added
        total_skipped_dupes += fund_dupes
        completed.add(slug)

        _print(f"  TOTAL for {slug}: +{fund_added} new, {fund_dupes} dupes")

        # Save after each fund
        safe_json_write(PORTFOLIO_PATH, portfolio_data)
        progress["completed_slugs"] = sorted(completed)
        progress["updated_at"] = now_iso()
        progress["total_added"] = total_added
        safe_json_write(PROGRESS_PATH, progress)

    session.close()

    _print(f"\nDone. Added: {total_added}, Dupes skipped: {total_skipped_dupes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
