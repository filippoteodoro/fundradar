#!/usr/bin/env python3
"""
HQ verification script for funds with potentially wrong headquarters.

Two-phase approach:
  Phase 1 (auto-fix): Funds already have correct non-Italy office in offices[]
                      but top-level hq_region/hq_country still says "Italy".
                      Fixed locally — no API call needed.

  Phase 2 (Gemini):   Funds with offices=null and hq_region=Italy.
                      Gemini+GoogleSearch determines whether real HQ is in Italy
                      or abroad. If abroad, updates hq_* fields and adds Italian
                      address to offices[].

Usage:
  python3 scripts/check-fund-hq-gemini.py --dry-run --limit 5
  python3 scripts/check-fund-hq-gemini.py --slugs bridgepoint,h-i-g-capital
  python3 scripts/check-fund-hq-gemini.py                  # all eligible funds
  python3 scripts/check-fund-hq-gemini.py --force          # re-check even completed
  python3 scripts/check-fund-hq-gemini.py --phase1-only    # auto-fix only, no API
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

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "worker"))
from fundradar_worker.paths import GEMINI_MODEL
from fundradar_worker.io_utils import safe_json_write

DATA_DIR = REPO_ROOT / "data"
DERIVED_DIR = DATA_DIR / "derived"
DB_PATH = DATA_DIR / "db.json"
PROGRESS_PATH = DERIVED_DIR / "fund_hq_check_progress.json"

DEFAULT_MODEL = GEMINI_MODEL
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}

DEFAULT_SLEEP_SECONDS = 3.0
DEFAULT_TIMEOUT_SEC = 60
DEFAULT_HARD_TIMEOUT_SEC = 90
DEFAULT_RETRIES = 2
DEFAULT_MIN_BACKOFF_SEC = 2.0
DEFAULT_MAX_BACKOFF_SEC = 20.0
DEFAULT_MAX_OUTPUT_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.1
SAVE_EVERY_N = 5

HQ_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "is_italy_hq": {"type": "BOOLEAN"},
        "hq_city": {"type": "STRING", "nullable": True},
        "hq_country": {"type": "STRING", "nullable": True},
        "hq_address": {"type": "STRING", "nullable": True},
        "confidence": {"type": "STRING"},
        "source": {"type": "STRING"},
    },
    "required": ["is_italy_hq", "confidence", "source"],
}


# ---------------------------------------------------------------------------
# Shared HTTP / Gemini helpers (same pattern as enrich-fund-metadata-gemini.py)
# ---------------------------------------------------------------------------

class _AlarmTimeout(Exception):
    pass


def _alarm_handler(signum: int, frame: Any) -> None:  # noqa: ARG001
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


def _compute_backoff(*, attempt: int, min_backoff_sec: float, max_backoff_sec: float, is_rate_limit: bool) -> float:
    scaled = min_backoff_sec * (2**attempt)
    if is_rate_limit:
        scaled = max(scaled, min_backoff_sec + 2)
    return min(max_backoff_sec, scaled)


def _request_with_hard_timeout(*, session: requests.Session, url: str, payload: dict[str, Any], timeout_sec: int, hard_timeout_sec: int) -> requests.Response:
    if not hasattr(_signal, "SIGALRM"):
        return session.post(url, json=payload, timeout=timeout_sec)
    old_handler = _signal.signal(_signal.SIGALRM, _alarm_handler)
    _signal.alarm(max(1, int(hard_timeout_sec)))
    try:
        return session.post(url, json=payload, timeout=timeout_sec)
    finally:
        _signal.alarm(0)
        _signal.signal(_signal.SIGALRM, old_handler)


def call_gemini_json(
    *,
    session: requests.Session,
    api_key: str,
    model: str,
    prompt: str,
    response_schema: dict[str, Any] | None,
    use_google_search: bool,
    max_output_tokens: int,
    temperature: float,
    timeout_sec: int,
    hard_timeout_sec: int,
    retries: int,
    min_backoff_sec: float,
    max_backoff_sec: float,
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
    if use_google_search:
        payload["tools"] = [{"google_search": {}}]

    last_error = ""
    used_grounding = use_google_search

    for attempt in range(retries + 1):
        try:
            resp = _request_with_hard_timeout(
                session=session,
                url=f"{url}?key={api_key}",
                payload=payload,
                timeout_sec=timeout_sec,
                hard_timeout_sec=hard_timeout_sec,
            )

            if resp.status_code in RETRYABLE_HTTP_STATUS or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                if attempt < retries:
                    _sleep_with_jitter(_compute_backoff(attempt=attempt, min_backoff_sec=min_backoff_sec, max_backoff_sec=max_backoff_sec, is_rate_limit=resp.status_code == 429))
                    continue
                raise RuntimeError(last_error)

            if resp.status_code >= 400:
                body = resp.text
                body_lower = body.lower()
                if used_grounding and ("google_search" in body or "tools" in body_lower or "ground" in body_lower):
                    payload.pop("tools", None)
                    used_grounding = False
                    if attempt < retries:
                        _sleep_with_jitter(1.0, 0.5)
                        continue

                if (isinstance(payload.get("generationConfig"), dict) and payload["generationConfig"].get("responseSchema") is not None and ("responseschema" in body_lower or "schema" in body_lower)):
                    payload["generationConfig"].pop("responseSchema", None)
                    if attempt < retries:
                        _sleep_with_jitter(1.0, 0.5)
                        continue

                if resp.status_code in {401, 403, 404}:
                    raise RuntimeError(f"Gemini error {resp.status_code}: {body[:500]}")

                if attempt < retries:
                    _sleep_with_jitter(_compute_backoff(attempt=attempt, min_backoff_sec=min_backoff_sec, max_backoff_sec=max_backoff_sec, is_rate_limit=resp.status_code == 429))
                    continue
                raise RuntimeError(f"Gemini error {resp.status_code}: {body[:500]}")

            raw = resp.json()
            text = extract_text_from_gemini_response(raw)
            parsed = parse_json_from_model_text(text)
            usage = raw.get("usageMetadata") or {}
            meta = {
                "grounding_used": used_grounding,
                "prompt_token_count": usage.get("promptTokenCount"),
                "candidates_token_count": usage.get("candidatesTokenCount"),
                "total_token_count": usage.get("totalTokenCount"),
            }
            return parsed, meta

        except _AlarmTimeout:
            last_error = f"Hard timeout after {hard_timeout_sec}s"
            if attempt < retries:
                _sleep_with_jitter(_compute_backoff(attempt=attempt, min_backoff_sec=min_backoff_sec, max_backoff_sec=max_backoff_sec, is_rate_limit=False))
                continue
            raise RuntimeError(last_error) from None

        except requests.RequestException as e:
            last_error = f"Request failed: {e}"
            if attempt < retries:
                _sleep_with_jitter(_compute_backoff(attempt=attempt, min_backoff_sec=min_backoff_sec, max_backoff_sec=max_backoff_sec, is_rate_limit=False))
                continue
            raise RuntimeError(last_error) from e

        except json.JSONDecodeError as e:
            last_error = f"JSON decode failed: {e}"
            if attempt < retries:
                _sleep_with_jitter(_compute_backoff(attempt=attempt, min_backoff_sec=min_backoff_sec, max_backoff_sec=max_backoff_sec, is_rate_limit=False))
                continue
            raise RuntimeError(last_error) from e

        except Exception as e:  # noqa: BLE001
            last_error = str(e)
            if "gemini error 401" in last_error.lower() or "gemini error 403" in last_error.lower():
                raise RuntimeError(last_error) from e
            if attempt < retries:
                _sleep_with_jitter(_compute_backoff(attempt=attempt, min_backoff_sec=min_backoff_sec, max_backoff_sec=max_backoff_sec, is_rate_limit="429" in last_error))
                continue
            raise RuntimeError(last_error) from e

    raise RuntimeError(last_error or "Unknown Gemini failure")


# ---------------------------------------------------------------------------
# Phase 1: auto-fix funds where offices[] already has the real HQ
# ---------------------------------------------------------------------------

def phase1_auto_fix(funds: list[dict[str, Any]]) -> int:
    """
    Fix hq_city / hq_region / hq_address / hq_country for funds that already
    have a non-Italy is_hq=True office in offices[].
    Returns number of funds updated.
    """
    updated = 0
    for fund in funds:
        if fund.get("hq_region") != "Italy":
            continue
        offices = fund.get("offices")
        if not offices:
            continue
        real_hq = next((o for o in offices if o.get("is_hq") and not o.get("is_italy")), None)
        if not real_hq:
            continue

        old_city = fund.get("hq_city")
        fund["hq_city"] = real_hq.get("city") or fund.get("hq_city")
        fund["hq_region"] = real_hq.get("country") or fund.get("hq_region")
        fund["hq_country"] = real_hq.get("country") or fund.get("hq_country")
        fund["hq_address"] = real_hq.get("address") or fund.get("hq_address")
        updated += 1
        print(f"  [auto-fix] {fund['slug']}: {old_city}/Italy → {fund['hq_city']}/{fund['hq_region']}")

    return updated


# ---------------------------------------------------------------------------
# Phase 2: Gemini prompt
# ---------------------------------------------------------------------------

def build_prompt(fund: dict[str, Any]) -> str:
    current_address = fund.get("hq_address") or "N/A"
    current_city = fund.get("hq_city") or "N/A"

    return f"""You are a financial data researcher. Determine the TRUE global headquarters of this investment fund.

FUND DATA:
- Name: {fund.get('name')}
- Website: {fund.get('website') or 'N/A'}
- Current HQ city in our database: {current_city} (Italy) — this is likely their Italian office, not global HQ
- Current address in our database: {current_address}

TASK:
Search for the fund's official global headquarters. Many international PE/VC funds have Italian offices but are actually headquartered in London, New York, Paris, etc.

RULES:
- is_italy_hq = true ONLY if the fund was genuinely founded in Italy and its primary global HQ is in Italy
- is_italy_hq = false if the fund has its main/global HQ in another country (even if it has an Italian office)
- hq_city: the city of the TRUE global headquarters
- hq_country: country of TRUE global HQ (e.g. "UK", "USA", "France", "Luxembourg", "Germany")
- hq_address: street address of global HQ if publicly available, otherwise null
- confidence: "high" if official website confirms, "medium" if reputable source, "low" if uncertain
- source: brief citation (e.g. "Fund website contact page", "Bloomberg", "PitchBook")
- If genuinely Italian HQ, set is_italy_hq=true and hq_city/country to the Italian city/Italy

Return JSON: {{"is_italy_hq": bool, "hq_city": "city or null", "hq_country": "country or null", "hq_address": "address or null", "confidence": "high|medium|low", "source": "source"}}"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Check and fix fund HQ data using Gemini.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=0, help="Max funds for Phase 2 (0 = all)")
    parser.add_argument("--slugs", type=str, help="Comma-separated slugs to process in Phase 2")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-check even if already completed")
    parser.add_argument("--reset", action="store_true", help="Ignore previous progress")
    parser.add_argument("--phase1-only", action="store_true", help="Run Phase 1 auto-fix only, skip Gemini")
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--hard-timeout-sec", type=int, default=DEFAULT_HARD_TIMEOUT_SEC)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--min-backoff-sec", type=float, default=DEFAULT_MIN_BACKOFF_SEC)
    parser.add_argument("--max-backoff-sec", type=float, default=DEFAULT_MAX_BACKOFF_SEC)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    args = parser.parse_args()

    db = load_json(DB_PATH)
    if not db or not isinstance(db, dict):
        print("Error: could not load db.json", file=sys.stderr)
        return 2
    funds = db.get("funds") or []
    if not funds:
        print("Error: no funds in db.json", file=sys.stderr)
        return 2

    # -------------------------------------------------------------------------
    # Phase 1: auto-fix funds where offices[] already has the real non-Italy HQ
    # -------------------------------------------------------------------------
    print("=== Phase 1: Auto-fix from existing offices data ===")
    p1_count = phase1_auto_fix(funds)
    print(f"Phase 1 complete: {p1_count} funds auto-fixed.")

    if p1_count > 0 and not args.dry_run:
        safe_json_write(DB_PATH, db)
        print("db.json saved.\n")

    if args.phase1_only:
        return 0

    # -------------------------------------------------------------------------
    # Phase 2: Gemini check for funds with offices=null and hq_region=Italy
    # -------------------------------------------------------------------------
    print("\n=== Phase 2: Gemini HQ check for funds without offices data ===")

    fund_by_slug: dict[str, dict[str, Any]] = {f["slug"]: f for f in funds if f.get("slug")}

    slugs_filter: set[str] | None = None
    if args.slugs:
        slugs_filter = {s.strip() for s in args.slugs.split(",") if s.strip()}
        invalid = slugs_filter - set(fund_by_slug.keys())
        if invalid:
            print(f"Warning: unknown slugs ignored: {', '.join(sorted(invalid))}")
            slugs_filter -= invalid

    progress: dict[str, Any]
    if args.reset:
        progress = {"completed_slugs": [], "failed_slugs": {}, "started_at": now_iso()}
    else:
        progress = load_json(PROGRESS_PATH) or {"completed_slugs": [], "failed_slugs": {}}
    completed_slugs: set[str] = set(progress.get("completed_slugs") or [])

    # Build queue: funds with offices=null and hq_region=Italy
    queue: list[dict[str, Any]] = []
    for fund in funds:
        slug = fund.get("slug")
        if not slug:
            continue
        if fund.get("hq_region") != "Italy":
            continue
        if fund.get("offices"):
            continue  # already has offices — Phase 1 handled or already correct
        if slugs_filter and slug not in slugs_filter:
            continue
        if slug in completed_slugs and not args.force:
            continue
        queue.append(fund)

    if args.limit > 0:
        queue = queue[: args.limit]

    print(f"Funds to check: {len(queue)}")
    if queue:
        preview = ", ".join(f["slug"] for f in queue[:10])
        print(f"Queue preview: {preview}")
        if len(queue) > 10:
            print(f"  ... +{len(queue) - 10} more")

    if not queue:
        print("Nothing to do.")
        return 0

    if args.dry_run:
        print("\n--- DRY RUN ---\n")
        for i, fund in enumerate(queue[:5], 1):
            prompt = build_prompt(fund)
            print(f"[{i}] {fund['slug']} — {fund['name']}")
            print(f"Prompt ({len(prompt)} chars):")
            print(prompt[:500])
            print("...\n")
        print("Dry-run complete. No API calls made.")
        return 0

    api_key = resolve_gemini_api_key()
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment/.env", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    total_calls = 0
    total_failures = 0
    total_foreign_hq = 0
    total_italy_hq = 0
    failed_slugs: dict[str, str] = dict(progress.get("failed_slugs") or {})

    for idx, fund in enumerate(queue, 1):
        slug = fund["slug"]
        name = fund.get("name") or slug
        italian_address = fund.get("hq_address")
        italian_city = fund.get("hq_city")

        prompt = build_prompt(fund)
        print(f"[{idx}/{len(queue)}] {name} ({slug})...", end=" ", flush=True)

        try:
            parsed, meta = call_gemini_json(
                session=session,
                api_key=api_key,
                model=args.model,
                prompt=prompt,
                response_schema=HQ_SCHEMA,
                use_google_search=True,
                max_output_tokens=args.max_output_tokens,
                temperature=args.temperature,
                timeout_sec=args.timeout_sec,
                hard_timeout_sec=args.hard_timeout_sec,
                retries=args.retries,
                min_backoff_sec=args.min_backoff_sec,
                max_backoff_sec=args.max_backoff_sec,
            )
            total_calls += 1

            is_italy = parsed.get("is_italy_hq", True)
            confidence = parsed.get("confidence", "low")
            source = parsed.get("source", "")[:50]
            grounding_flag = "G" if meta.get("grounding_used") else "g"

            if is_italy:
                total_italy_hq += 1
                print(f"OK [{grounding_flag}|{confidence}] Italy HQ confirmed ({source})")
            else:
                hq_city = parsed.get("hq_city")
                hq_country = parsed.get("hq_country")
                hq_address = parsed.get("hq_address")

                if hq_city and hq_country:
                    # Update top-level HQ fields
                    old_city = fund.get("hq_city")
                    fund["hq_city"] = hq_city
                    fund["hq_region"] = hq_country
                    fund["hq_country"] = hq_country
                    fund["hq_address"] = hq_address  # real HQ address

                    # Move Italian address to offices[]
                    italian_office: dict[str, Any] = {
                        "city": italian_city,
                        "country": "Italy",
                        "address": italian_address,
                        "postal_code": None,
                        "phone": None,
                        "lat": None,
                        "lng": None,
                        "is_hq": False,
                        "is_italy": True,
                        "source_name": "AIFI member directory",
                    }
                    fund["offices"] = [italian_office]

                    total_foreign_hq += 1
                    print(f"UPDATED [{grounding_flag}|{confidence}] {old_city}/Italy → {hq_city}/{hq_country} ({source})")
                else:
                    # Foreign HQ but no city/country found — mark as low confidence
                    print(f"SKIP [{grounding_flag}|{confidence}] foreign HQ suspected but no location data ({source})")

            completed_slugs.add(slug)
            failed_slugs.pop(slug, None)

        except Exception as e:  # noqa: BLE001
            total_calls += 1
            total_failures += 1
            err = str(e)[:150]
            print(f"FAILED: {err}")
            failed_slugs[slug] = err

        # Save periodically
        if idx % SAVE_EVERY_N == 0 or idx == len(queue):
            safe_json_write(DB_PATH, db)
            progress["completed_slugs"] = sorted(completed_slugs)
            progress["failed_slugs"] = failed_slugs
            progress["updated_at"] = now_iso()
            progress["total_foreign_hq"] = total_foreign_hq
            progress["total_italy_hq"] = total_italy_hq
            safe_json_write(PROGRESS_PATH, progress)

    # Final save
    safe_json_write(DB_PATH, db)
    progress["completed_slugs"] = sorted(completed_slugs)
    progress["failed_slugs"] = failed_slugs
    progress["updated_at"] = now_iso()
    progress["total_foreign_hq"] = total_foreign_hq
    progress["total_italy_hq"] = total_italy_hq
    progress["finished_at"] = now_iso()
    safe_json_write(PROGRESS_PATH, progress)

    session.close()

    print(f"\n=== Done ===")
    print(f"Phase 1 auto-fixed: {p1_count}")
    print(f"Phase 2 — Foreign HQ updated: {total_foreign_hq}, Italy HQ confirmed: {total_italy_hq}, Failures: {total_failures}, API calls: {total_calls}")
    if failed_slugs:
        print(f"Failed slugs ({len(failed_slugs)}): {', '.join(sorted(failed_slugs.keys())[:10])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
