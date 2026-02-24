#!/usr/bin/env python3
"""
Enrich fund metadata (AUM, investment ranges) using Gemini 3 Flash with Google Search grounding.

Fills missing `aum_eur`, `investment_min_eur`, `investment_max_eur` in db.json by
querying Gemini with Google Search to find publicly available fund data.

Uses REST API (not SDK) to enable `tools: [{"google_search": {}}]` for grounding.

Outputs: directly updates `data/db.json`
Progress: `data/derived/fund_metadata_enrichment_progress.json`

Usage:
  python3 scripts/enrich-fund-metadata-gemini.py --dry-run --limit 5
  python3 scripts/enrich-fund-metadata-gemini.py --slugs cherry-bay-capital,key-capital
  python3 scripts/enrich-fund-metadata-gemini.py                          # all funds missing data
  python3 scripts/enrich-fund-metadata-gemini.py --force                  # re-enrich even if data exists
  python3 scripts/enrich-fund-metadata-gemini.py --pipeline               # graceful skip if no API key
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
DATA_DIR = REPO_ROOT / "data"
DERIVED_DIR = DATA_DIR / "derived"

DB_PATH = DATA_DIR / "db.json"
PROGRESS_PATH = DERIVED_DIR / "fund_metadata_enrichment_progress.json"

DEFAULT_MODEL = "gemini-3-flash-preview"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}

DEFAULT_SLEEP_SECONDS = 3.0
DEFAULT_TIMEOUT_SEC = 60
DEFAULT_HARD_TIMEOUT_SEC = 90
DEFAULT_RETRIES = 2
DEFAULT_MIN_BACKOFF_SEC = 2.0
DEFAULT_MAX_BACKOFF_SEC = 20.0
DEFAULT_MAX_OUTPUT_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.2  # Lower temp for factual data

SAVE_EVERY_N = 5

METADATA_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "aum_eur": {"type": "NUMBER", "nullable": True},
        "aum_source": {"type": "STRING"},
        "aum_year": {"type": "INTEGER", "nullable": True},
        "investment_min_eur": {"type": "NUMBER", "nullable": True},
        "investment_max_eur": {"type": "NUMBER", "nullable": True},
        "investment_range_source": {"type": "STRING"},
        "confidence": {"type": "STRING"},
    },
    "required": ["confidence"],
}


# ---------------------------------------------------------------------------
# Helpers (shared patterns from generate-fund-descriptions-gemini.py)
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
    *,
    attempt: int,
    min_backoff_sec: float,
    max_backoff_sec: float,
    is_rate_limit: bool,
) -> float:
    scaled = min_backoff_sec * (2**attempt)
    if is_rate_limit:
        scaled = max(scaled, min_backoff_sec + 2)
    return min(max_backoff_sec, scaled)


def _request_with_hard_timeout(
    *,
    session: requests.Session,
    url: str,
    payload: dict[str, Any],
    timeout_sec: int,
    hard_timeout_sec: int,
) -> requests.Response:
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
                    _sleep_with_jitter(
                        _compute_backoff(
                            attempt=attempt,
                            min_backoff_sec=min_backoff_sec,
                            max_backoff_sec=max_backoff_sec,
                            is_rate_limit=resp.status_code == 429,
                        )
                    )
                    continue
                raise RuntimeError(last_error)

            if resp.status_code >= 400:
                body = resp.text
                body_lower = body.lower()
                # Fallback: disable grounding if rejected
                if used_grounding and (
                    "google_search" in body
                    or "tools" in body_lower
                    or "ground" in body_lower
                ):
                    payload.pop("tools", None)
                    used_grounding = False
                    if attempt < retries:
                        _sleep_with_jitter(1.0, 0.5)
                        continue

                # Fallback: drop schema if rejected
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
                    _sleep_with_jitter(
                        _compute_backoff(
                            attempt=attempt,
                            min_backoff_sec=min_backoff_sec,
                            max_backoff_sec=max_backoff_sec,
                            is_rate_limit=resp.status_code == 429,
                        )
                    )
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
                _sleep_with_jitter(
                    _compute_backoff(
                        attempt=attempt,
                        min_backoff_sec=min_backoff_sec,
                        max_backoff_sec=max_backoff_sec,
                        is_rate_limit=False,
                    )
                )
                continue
            raise RuntimeError(last_error) from None

        except requests.RequestException as e:
            last_error = f"Request failed: {e}"
            if attempt < retries:
                _sleep_with_jitter(
                    _compute_backoff(
                        attempt=attempt,
                        min_backoff_sec=min_backoff_sec,
                        max_backoff_sec=max_backoff_sec,
                        is_rate_limit=False,
                    )
                )
                continue
            raise RuntimeError(last_error) from e

        except json.JSONDecodeError as e:
            last_error = f"JSON decode failed: {e}"
            if attempt < retries:
                _sleep_with_jitter(
                    _compute_backoff(
                        attempt=attempt,
                        min_backoff_sec=min_backoff_sec,
                        max_backoff_sec=max_backoff_sec,
                        is_rate_limit=False,
                    )
                )
                continue
            raise RuntimeError(last_error) from e

        except Exception as e:  # noqa: BLE001
            last_error = str(e)
            if "gemini error 401" in last_error.lower() or "gemini error 403" in last_error.lower():
                raise RuntimeError(last_error) from e
            if attempt < retries:
                _sleep_with_jitter(
                    _compute_backoff(
                        attempt=attempt,
                        min_backoff_sec=min_backoff_sec,
                        max_backoff_sec=max_backoff_sec,
                        is_rate_limit="429" in last_error,
                    )
                )
                continue
            raise RuntimeError(last_error) from e

    raise RuntimeError(last_error or "Unknown Gemini failure")


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def build_prompt(fund: dict[str, Any]) -> str:
    """Build the Gemini prompt for a single fund."""
    context_parts = [
        f"Fund name: {fund.get('name')}",
        f"Legal name: {fund.get('legal_name') or 'N/A'}",
        f"Website: {fund.get('website') or 'N/A'}",
        f"Category: {fund.get('category') or 'N/A'}",
        f"HQ city: {fund.get('hq_city') or 'N/A'}",
        f"Country: {fund.get('hq_region') or 'N/A'}",
        f"Strategies: {', '.join(fund.get('strategy_tags') or []) or 'N/A'}",
        f"Geographies: {', '.join(fund.get('geographies') or []) or 'N/A'}",
    ]

    # Include current values if any
    aum = fund.get("aum_eur")
    inv_min = fund.get("investment_min_eur")
    inv_max = fund.get("investment_max_eur")
    if aum is not None:
        context_parts.append(f"Current AUM (EUR): {aum}")
    if inv_min is not None:
        context_parts.append(f"Current investment min (EUR): {inv_min}")
    if inv_max is not None:
        context_parts.append(f"Current investment max (EUR): {inv_max}")

    context = "\n".join(context_parts)

    return f"""You are a financial data researcher. Find the latest publicly available financial metadata for this PE/VC fund.

FUND DATA:
{context}

TASK:
Search for this fund's current Assets Under Management (AUM) and typical investment ticket size range.
Return the data as JSON.

RULES:
- AUM must be in EUR. If reported in USD or GBP, convert using approximate current rates (1 USD ≈ 0.92 EUR, 1 GBP ≈ 1.17 EUR).
- Express AUM as a plain number in EUR (e.g., 500000000 for €500M, 1500000000 for €1.5B).
- investment_min_eur and investment_max_eur are the typical equity ticket size per deal, in EUR.
- Only return data you can verify from public sources (fund website, press releases, AIFI, Preqin, PitchBook references, news articles).
- If you cannot find reliable data for a field, set it to null.
- aum_source and investment_range_source should briefly cite where the data came from (e.g., "Fund website", "2024 annual report", "Preqin", "AIFI member page").
- aum_year: the year the AUM figure refers to (e.g., 2024, 2025). null if unknown.
- confidence: "high" if from official fund source, "medium" if from reputable third-party, "low" if estimated.
- Do NOT fabricate numbers. null is always better than a guess.
- For very small funds or boutique family offices where AUM is not publicly disclosed, return null.

Return JSON: {{"aum_eur": number_or_null, "aum_source": "source", "aum_year": year_or_null, "investment_min_eur": number_or_null, "investment_max_eur": number_or_null, "investment_range_source": "source", "confidence": "high|medium|low"}}"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_response(parsed: dict[str, Any], fund_name: str) -> dict[str, Any] | None:
    """Validate and clean the Gemini response. Returns None if unusable."""
    confidence = parsed.get("confidence", "low")
    if confidence not in ("high", "medium", "low"):
        confidence = "low"

    aum = parsed.get("aum_eur")
    inv_min = parsed.get("investment_min_eur")
    inv_max = parsed.get("investment_max_eur")

    # Validate AUM range (€1M to €2T)
    if aum is not None:
        try:
            aum = float(aum)
            if aum < 1_000_000 or aum > 2_000_000_000_000:
                print(f"  AUM out of range ({aum}), setting to null")
                aum = None
            else:
                aum = int(aum)
        except (TypeError, ValueError):
            aum = None

    # Validate investment ranges (€10K to €10B)
    for label, val in [("min", inv_min), ("max", inv_max)]:
        if val is not None:
            try:
                val = float(val)
                if val < 10_000 or val > 10_000_000_000:
                    print(f"  investment_{label}_eur out of range ({val}), setting to null")
                    if label == "min":
                        inv_min = None
                    else:
                        inv_max = None
                else:
                    if label == "min":
                        inv_min = int(val)
                    else:
                        inv_max = int(val)
            except (TypeError, ValueError):
                if label == "min":
                    inv_min = None
                else:
                    inv_max = None

    # Sanity: min should be <= max
    if inv_min is not None and inv_max is not None and inv_min > inv_max:
        print(f"  min ({inv_min}) > max ({inv_max}), swapping")
        inv_min, inv_max = inv_max, inv_min

    # If everything is null, return None
    if aum is None and inv_min is None and inv_max is None:
        return None

    return {
        "aum_eur": aum,
        "aum_source": parsed.get("aum_source", ""),
        "aum_year": parsed.get("aum_year"),
        "investment_min_eur": inv_min,
        "investment_max_eur": inv_max,
        "investment_range_source": parsed.get("investment_range_source", ""),
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def fmt_eur(val: int | float | None) -> str:
    if val is None:
        return "null"
    if val >= 1_000_000_000:
        return f"€{val / 1_000_000_000:.1f}B"
    if val >= 1_000_000:
        return f"€{val / 1_000_000:.0f}M"
    return f"€{val:,.0f}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich fund metadata (AUM, investment ranges) with Gemini 3 Flash + Google Search grounding."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model")
    parser.add_argument("--limit", type=int, default=0, help="Max funds to process (0 = all)")
    parser.add_argument("--slugs", type=str, help="Comma-separated fund slugs to process")
    parser.add_argument("--dry-run", action="store_true", help="Show prompts, don't call API")
    parser.add_argument("--force", action="store_true", help="Re-enrich even if data exists")
    parser.add_argument("--reset", action="store_true", help="Ignore previous progress")
    parser.add_argument("--pipeline", action="store_true", help="Graceful skip if GEMINI_API_KEY not set")
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--hard-timeout-sec", type=int, default=DEFAULT_HARD_TIMEOUT_SEC)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--min-backoff-sec", type=float, default=DEFAULT_MIN_BACKOFF_SEC)
    parser.add_argument("--max-backoff-sec", type=float, default=DEFAULT_MAX_BACKOFF_SEC)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    args = parser.parse_args()

    # Load db.json
    db = load_json(DB_PATH)
    if not db or not isinstance(db, dict):
        print("Error: could not load db.json", file=sys.stderr)
        return 2
    funds = db.get("funds") or []
    if not funds:
        print("Error: no funds in db.json", file=sys.stderr)
        return 2

    # Build lookup
    fund_by_slug: dict[str, dict[str, Any]] = {f["slug"]: f for f in funds if f.get("slug")}

    # Determine which funds to process
    slugs_filter: set[str] | None = None
    if args.slugs:
        slugs_filter = {s.strip() for s in args.slugs.split(",") if s.strip()}
        invalid = slugs_filter - set(fund_by_slug.keys())
        if invalid:
            print(f"Warning: unknown slugs ignored: {', '.join(sorted(invalid))}")
            slugs_filter -= invalid

    # Load progress
    progress: dict[str, Any]
    if args.reset:
        progress = {"completed_slugs": [], "failed_slugs": {}, "started_at": now_iso()}
    else:
        progress = load_json(PROGRESS_PATH) or {"completed_slugs": [], "failed_slugs": {}}
    completed_slugs: set[str] = set(progress.get("completed_slugs") or [])

    # Build queue — funds missing AUM or investment ranges
    queue: list[dict[str, Any]] = []
    for fund in funds:
        slug = fund.get("slug")
        if not slug:
            continue
        if slugs_filter and slug not in slugs_filter:
            continue
        if slug in completed_slugs and not args.reset:
            continue

        has_aum = fund.get("aum_eur") is not None
        has_inv_min = fund.get("investment_min_eur") is not None
        has_inv_max = fund.get("investment_max_eur") is not None

        # Skip funds that already have all data unless --force
        if has_aum and has_inv_min and has_inv_max and not args.force:
            continue

        queue.append(fund)

    if args.limit > 0:
        queue = queue[: args.limit]

    print(f"Funds to process: {len(queue)} (total in db: {len(funds)})")
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
            slug = fund["slug"]
            prompt = build_prompt(fund)
            print(f"[{i}] {slug}")
            print(f"Prompt ({len(prompt)} chars):")
            print(prompt[:600])
            print("...\n")
        print("Dry-run complete. No API calls made.")
        return 0

    # Resolve API key
    api_key = resolve_gemini_api_key()
    if not api_key:
        if args.pipeline:
            print("GEMINI_API_KEY not set. --pipeline mode: skipping gracefully.")
            return 0
        print("Error: GEMINI_API_KEY not found in environment/.env", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    print(
        f"Settings: model={args.model}, sleep={args.sleep_seconds}s, retries={args.retries}, "
        f"timeout={args.timeout_sec}s, hard_timeout={args.hard_timeout_sec}s, grounding=ON"
    )

    total_calls = 0
    total_failures = 0
    total_updated = 0
    fields_updated = {"aum_eur": 0, "investment_min_eur": 0, "investment_max_eur": 0}
    failed_slugs: dict[str, str] = dict(progress.get("failed_slugs") or {})

    for idx, fund in enumerate(queue, 1):
        slug = fund["slug"]
        name = fund.get("name") or slug

        prompt = build_prompt(fund)

        print(f"[{idx}/{len(queue)}] {name} ({slug})...", end=" ", flush=True)

        try:
            parsed, meta = call_gemini_json(
                session=session,
                api_key=api_key,
                model=args.model,
                prompt=prompt,
                response_schema=METADATA_SCHEMA,
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

            validated = validate_response(parsed, name)
            if not validated:
                print("SKIP (no usable data)")
                completed_slugs.add(slug)
                failed_slugs.pop(slug, None)
                _sleep_with_jitter(args.sleep_seconds)
                continue

            confidence = validated["confidence"]
            grounding_flag = "G" if meta.get("grounding_used") else "g"
            any_update = False

            # Update AUM if missing (or --force)
            new_aum = validated["aum_eur"]
            if new_aum is not None and (fund.get("aum_eur") is None or args.force):
                fund["aum_eur"] = new_aum
                fields_updated["aum_eur"] += 1
                any_update = True

            # Update investment ranges if missing (or --force)
            new_min = validated["investment_min_eur"]
            if new_min is not None and (fund.get("investment_min_eur") is None or args.force):
                fund["investment_min_eur"] = new_min
                fields_updated["investment_min_eur"] += 1
                any_update = True

            new_max = validated["investment_max_eur"]
            if new_max is not None and (fund.get("investment_max_eur") is None or args.force):
                fund["investment_max_eur"] = new_max
                fields_updated["investment_max_eur"] += 1
                any_update = True

            if any_update:
                total_updated += 1

            completed_slugs.add(slug)
            failed_slugs.pop(slug, None)

            # Format output
            parts = []
            if new_aum is not None:
                parts.append(f"AUM={fmt_eur(new_aum)}")
            if new_min is not None or new_max is not None:
                parts.append(f"range={fmt_eur(new_min)}-{fmt_eur(new_max)}")
            src = validated.get("aum_source", "")[:30]
            print(f"OK [{grounding_flag}|{confidence}] {' '.join(parts)} ({src})")

        except Exception as e:  # noqa: BLE001
            total_calls += 1
            total_failures += 1
            err = str(e)[:150]
            print(f"FAILED: {err}")
            failed_slugs[slug] = err

        # Save periodically
        if idx % SAVE_EVERY_N == 0 or idx == len(queue):
            save_json_atomic(DB_PATH, db)
            progress["completed_slugs"] = sorted(completed_slugs)
            progress["failed_slugs"] = failed_slugs
            progress["updated_at"] = now_iso()
            progress["total_updated"] = total_updated
            progress["fields_updated"] = fields_updated
            save_json_atomic(PROGRESS_PATH, progress)

        _sleep_with_jitter(args.sleep_seconds)

    # Final save
    save_json_atomic(DB_PATH, db)
    progress["completed_slugs"] = sorted(completed_slugs)
    progress["failed_slugs"] = failed_slugs
    progress["updated_at"] = now_iso()
    progress["total_updated"] = total_updated
    progress["fields_updated"] = fields_updated
    progress["finished_at"] = now_iso()
    save_json_atomic(PROGRESS_PATH, progress)

    session.close()

    print(f"\nDone. Updated: {total_updated}, Failed: {total_failures}, API calls: {total_calls}")
    print(f"Fields: AUM={fields_updated['aum_eur']}, min={fields_updated['investment_min_eur']}, max={fields_updated['investment_max_eur']}")
    if failed_slugs:
        print(f"Failed slugs ({len(failed_slugs)}): {', '.join(sorted(failed_slugs.keys())[:10])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
