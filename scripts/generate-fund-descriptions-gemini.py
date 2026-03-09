#!/usr/bin/env python3
"""
Generate distinctive fund descriptions using Gemini 3 Flash with Google Search grounding.

Replaces template descriptions in db.json with unique, informative 1-2 sentence descriptions
that capture what makes each fund distinctive (founding story, notable investments, positioning).

Uses REST API (not SDK) to enable `tools: [{"google_search": {}}]` for grounding.

Outputs: directly updates `data/db.json` (description + description_source fields)
Progress: `data/derived/fund_descriptions_progress.json`

Usage:
  python3 scripts/generate-fund-descriptions-gemini.py --dry-run --limit 5
  python3 scripts/generate-fund-descriptions-gemini.py --slugs invitalia,cdp-venture-capital
  python3 scripts/generate-fund-descriptions-gemini.py --limit 20
  python3 scripts/generate-fund-descriptions-gemini.py              # all template funds
  python3 scripts/generate-fund-descriptions-gemini.py --force      # overwrite non-template too
  python3 scripts/generate-fund-descriptions-gemini.py --pipeline   # graceful skip if no API key
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
import sys; sys.path.insert(0, str(REPO_ROOT / "apps" / "worker"))
from fundradar_worker.paths import GEMINI_MODEL
DATA_DIR = REPO_ROOT / "data"
DERIVED_DIR = DATA_DIR / "derived"

DB_PATH = DATA_DIR / "db.json"
PORTFOLIO_PATH = DERIVED_DIR / "portfolio_items.json"
SIGNALS_PATH = DERIVED_DIR / "detected_signals_enriched.json"
PROGRESS_PATH = DERIVED_DIR / "fund_descriptions_progress.json"

DEFAULT_MODEL = GEMINI_MODEL
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}

DEFAULT_SLEEP_SECONDS = 3.0
DEFAULT_TIMEOUT_SEC = 60
DEFAULT_HARD_TIMEOUT_SEC = 90
DEFAULT_RETRIES = 2
DEFAULT_MIN_BACKOFF_SEC = 2.0
DEFAULT_MAX_BACKOFF_SEC = 20.0
DEFAULT_MAX_OUTPUT_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.4

SAVE_EVERY_N = 10

# Detect template descriptions — matches the auto-generated pattern
TEMPLATE_RE = re.compile(
    r"is an? (?:Italian |European )?(?:private equity|venture capital|infrastructure|"
    r"investment|PE/VC|multi-strategy|sovereign|deep tech)",
    re.I,
)

DESCRIPTION_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "description": {"type": "STRING"},
    },
    "required": ["description"],
}


# ---------------------------------------------------------------------------
# Helpers (reused patterns from audit-fund-assets-gemini.py)
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
# Context building
# ---------------------------------------------------------------------------


def load_portfolio_context(portfolio_path: Path) -> dict[str, list[str]]:
    """Return {slug: [top 10 current company names]}."""
    data = load_json(portfolio_path)
    if not data or not isinstance(data, dict):
        return {}
    fund_portfolios = data.get("fund_portfolios") or {}
    result: dict[str, list[str]] = {}
    for slug, entries in fund_portfolios.items():
        if not isinstance(entries, list):
            continue
        current = [
            e["name"]
            for e in entries
            if isinstance(e, dict)
            and isinstance(e.get("name"), str)
            and e.get("name", "").strip()
            and e.get("status") in ("current", None)
        ]
        result[slug] = current[:10]
    return result


def load_signal_context(signals_path: Path) -> dict[str, list[str]]:
    """Return {slug: [top 3 recent signal titles]}."""
    data = load_json(signals_path)
    if not data or not isinstance(data, dict):
        return {}
    signals = data.get("signals") or []
    by_slug: dict[str, list[dict[str, Any]]] = {}
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        slug = sig.get("fund_slug")
        if not isinstance(slug, str):
            continue
        by_slug.setdefault(slug, []).append(sig)

    result: dict[str, list[str]] = {}
    for slug, sigs in by_slug.items():
        # Sort by published_at descending (most recent first)
        sigs.sort(key=lambda s: s.get("published_at") or s.get("observed_at") or "", reverse=True)
        titles = [
            s["title"]
            for s in sigs[:3]
            if isinstance(s.get("title"), str) and s["title"].strip()
        ]
        result[slug] = titles
    return result


def build_prompt(fund: dict[str, Any], portfolio_names: list[str], signal_titles: list[str]) -> str:
    """Build the Gemini prompt for a single fund."""
    # Fund context
    context_parts = [
        f"Fund name: {fund.get('name')}",
        f"Legal name: {fund.get('legal_name') or 'N/A'}",
        f"Website: {fund.get('website') or 'N/A'}",
        f"Category: {fund.get('category') or 'N/A'}",
        f"HQ city: {fund.get('hq_city') or 'N/A'}",
        f"AUM (EUR): {fund.get('aum_eur') or 'N/A'}",
        f"Strategies: {', '.join(fund.get('strategy_tags') or []) or 'N/A'}",
        f"Sectors: {', '.join(fund.get('sector_tags') or []) or 'N/A'}",
        f"Geographies: {', '.join(fund.get('geographies') or []) or 'N/A'}",
        f"Average investment: {fund.get('average_investment') or 'N/A'}",
    ]
    context = "\n".join(context_parts)

    portfolio_str = ", ".join(portfolio_names) if portfolio_names else "None available"
    signals_str = "\n".join(f"  - {t}" for t in signal_titles) if signal_titles else "  None available"

    return f"""You are writing a brief description for a PE/VC fund directory.

FUND DATA:
{context}

CURRENT PORTFOLIO COMPANIES (sample):
{portfolio_str}

RECENT NEWS/SIGNALS:
{signals_str}

TASK:
Write 1-2 sentences (max 250 characters) that highlight what distinguishes this fund.

RULES:
- DO NOT use template language like "based in X with Y AUM" or "focused on X across Y sectors"
- DO highlight: founding story, notable investments, specialized focus, unique market positioning, or distinctive strategy
- Use the fund's website and your knowledge to find real, verifiable facts
- If the fund has a well-known founding story (family office, spinoff, government agency), mention it
- If the fund is known for specific landmark deals, mention 1-2
- Write in English, present tense, no marketing superlatives
- Never fabricate facts. If you cannot find distinctive information, write a factual description from the provided data that avoids the template pattern
- Do NOT start with the fund name

GOOD EXAMPLES:
- "State-owned agency operating PE-style vehicles to achieve Italian industrial policy goals."
- "Milan-based specialist in clean energy infrastructure (BESS, solar PV, green hydrogen). Founded 2022 as a Generali Investments JV."
- "Founded in 1998 by the Benetton family, backs mid-market Italian companies in food, healthcare, and industrial sectors."
- "Pioneer of the Italian PE market since 1988, specializing in succession-driven buyouts of family-owned SMEs in Northern Italy."

Return JSON: {{"description": "your description here"}}"""


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------


def postprocess_description(raw: str, fund_name: str) -> str | None:
    """Clean and validate the generated description. Returns None if invalid."""
    desc = raw.strip()

    # Strip wrapping quotes
    if (desc.startswith('"') and desc.endswith('"')) or (desc.startswith("'") and desc.endswith("'")):
        desc = desc[1:-1].strip()

    # Strip fund name prefix ("Fund Name: description" or "Fund Name - description")
    for sep in [": ", " - ", " — ", " – "]:
        if desc.startswith(fund_name + sep):
            desc = desc[len(fund_name + sep) :].strip()

    # Also handle case-insensitive name prefix
    if desc.lower().startswith(fund_name.lower() + " is "):
        # Keep "is" — just strip the name
        desc = desc[len(fund_name) :].strip()
        # Capitalize first letter
        if desc:
            desc = desc[0].upper() + desc[1:]

    # Ensure terminal period
    if desc and not desc.endswith("."):
        desc += "."

    # Truncate at sentence boundary if >350 chars
    if len(desc) > 350:
        # Find the last period before 350 chars
        last_period = desc.rfind(".", 0, 350)
        if last_period > 50:
            desc = desc[: last_period + 1]
        else:
            desc = desc[:347] + "..."

    # Reject too short
    if len(desc) < 20:
        return None

    # Reject if still matches template
    if TEMPLATE_RE.search(desc):
        return None

    return desc


# ---------------------------------------------------------------------------
# Sort by AUM descending
# ---------------------------------------------------------------------------


def sort_funds_by_aum_desc(funds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(f: dict[str, Any]) -> tuple[bool, float, str]:
        aum = f.get("aum_eur")
        has_no_aum = aum is None
        aum_num = float(aum) if isinstance(aum, (int, float)) else -1.0
        return (has_no_aum, -aum_num, (f.get("name") or f.get("slug") or "").lower())

    return sorted(funds, key=key)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate distinctive fund descriptions with Gemini 3 Flash + Google Search grounding."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model")
    parser.add_argument("--limit", type=int, default=0, help="Max funds to process (0 = all)")
    parser.add_argument("--slugs", type=str, help="Comma-separated fund slugs to process")
    parser.add_argument("--dry-run", action="store_true", help="Show prompts, don't call API")
    parser.add_argument("--force", action="store_true", help="Overwrite non-template descriptions too")
    parser.add_argument("--reset", action="store_true", help="Ignore previous progress")
    parser.add_argument("--grounding", action="store_true", help="Enable Google Search grounding (off by default)")
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

    # Build queue
    queue: list[dict[str, Any]] = []
    for fund in funds:
        slug = fund.get("slug")
        if not slug:
            continue
        if slugs_filter and slug not in slugs_filter:
            continue
        if slug in completed_slugs and not args.reset:
            continue

        desc = fund.get("description") or ""
        is_template = bool(TEMPLATE_RE.search(desc))

        # Skip non-template unless --force
        if desc and not is_template and not args.force:
            continue

        queue.append(fund)

    queue = sort_funds_by_aum_desc(queue)
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

    # Load context data
    portfolio_ctx = load_portfolio_context(PORTFOLIO_PATH)
    signal_ctx = load_signal_context(SIGNALS_PATH)

    if args.dry_run:
        print("\n--- DRY RUN ---\n")
        for i, fund in enumerate(queue[:5], 1):
            slug = fund["slug"]
            prompt = build_prompt(fund, portfolio_ctx.get(slug, []), signal_ctx.get(slug, []))
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
        f"timeout={args.timeout_sec}s, hard_timeout={args.hard_timeout_sec}s, "
        f"grounding={'ON' if args.grounding else 'OFF'}"
    )

    total_calls = 0
    total_failures = 0
    total_updated = 0
    failed_slugs: dict[str, str] = dict(progress.get("failed_slugs") or {})

    for idx, fund in enumerate(queue, 1):
        slug = fund["slug"]
        name = fund.get("name") or slug

        prompt = build_prompt(fund, portfolio_ctx.get(slug, []), signal_ctx.get(slug, []))

        print(f"[{idx}/{len(queue)}] {name} ({slug})...", end=" ", flush=True)

        try:
            parsed, meta = call_gemini_json(
                session=session,
                api_key=api_key,
                model=args.model,
                prompt=prompt,
                response_schema=DESCRIPTION_SCHEMA,
                use_google_search=args.grounding,
                max_output_tokens=args.max_output_tokens,
                temperature=args.temperature,
                timeout_sec=args.timeout_sec,
                hard_timeout_sec=args.hard_timeout_sec,
                retries=args.retries,
                min_backoff_sec=args.min_backoff_sec,
                max_backoff_sec=args.max_backoff_sec,
            )
            total_calls += 1

            raw_desc = parsed.get("description", "")
            if not isinstance(raw_desc, str) or not raw_desc.strip():
                print("SKIP (empty response)")
                failed_slugs[slug] = "empty response"
                _sleep_with_jitter(args.sleep_seconds)
                continue

            cleaned = postprocess_description(raw_desc, name)
            if not cleaned:
                print(f"REJECTED ({raw_desc[:80]})")
                failed_slugs[slug] = f"rejected: {raw_desc[:100]}"
                _sleep_with_jitter(args.sleep_seconds)
                continue

            # Update db.json in memory
            fund["description"] = cleaned
            fund["description_source"] = "gemini_grounded" if meta.get("grounding_used") else "gemini"
            completed_slugs.add(slug)
            failed_slugs.pop(slug, None)
            total_updated += 1

            grounding_flag = "G" if meta.get("grounding_used") else "g"
            print(f"OK [{grounding_flag}] ({len(cleaned)}c) {cleaned[:80]}")

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
            save_json_atomic(PROGRESS_PATH, progress)

        _sleep_with_jitter(args.sleep_seconds)

    # Final save
    save_json_atomic(DB_PATH, db)
    progress["completed_slugs"] = sorted(completed_slugs)
    progress["failed_slugs"] = failed_slugs
    progress["updated_at"] = now_iso()
    progress["total_updated"] = total_updated
    progress["finished_at"] = now_iso()
    save_json_atomic(PROGRESS_PATH, progress)

    session.close()

    print(f"\nDone. Updated: {total_updated}, Failed: {total_failures}, API calls: {total_calls}")
    if failed_slugs:
        print(f"Failed slugs ({len(failed_slugs)}): {', '.join(sorted(failed_slugs.keys())[:10])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
