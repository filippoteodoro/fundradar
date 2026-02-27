#!/usr/bin/env python3
"""
Audit fund portfolio assets with Gemini 3 Flash, one fund at a time.

Workflow:
1. Sort funds by AUM descending.
2. For each fund, audit existing portfolio entries in chunks.
3. Ask Gemini for:
   - wrong entries / wrong fields (status, sector, HQ, description)
   - missing Italian assets
   - fund metadata corrections (HQ city, description, website)
4. Save structured output + progress after each fund.

Gemini hardening:
- paced sequential calls (3s default) + retry with jittered backoff
- hard timeout guard (SIGALRM) in addition to HTTP timeout
- auto-split for failed chunk audits (20 -> 8 -> 1)
- smaller prompt fallback for missing-assets pass (120 -> 60 -> 20 -> 1 names)

Outputs:
  data/derived/gemini_fund_asset_audit.json
  data/derived/gemini_fund_asset_audit_progress.json

Usage examples:
  python3 scripts/audit-fund-assets-gemini.py --dry-run --limit-funds 10
  python3 scripts/audit-fund-assets-gemini.py --limit-funds 25
  python3 scripts/audit-fund-assets-gemini.py --slugs investindustrial,clessidra-sgr
  python3 scripts/audit-fund-assets-gemini.py --reset --limit-funds 50
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
from gemini_audit_completion import is_fund_result_complete, load_verified_zero_italy_slugs

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DERIVED_DIR = DATA_DIR / "derived"

DB_PATH = DATA_DIR / "db.json"
PORTFOLIO_PATH = DERIVED_DIR / "portfolio_items.json"
OUTPUT_PATH = DERIVED_DIR / "gemini_fund_asset_audit.json"
PROGRESS_PATH = DERIVED_DIR / "gemini_fund_asset_audit_progress.json"
ZERO_ITALY_VERIFIED_PATH = DERIVED_DIR / "gemini_fund_asset_zero_italy_verified.json"

DEFAULT_MODEL = "gemini-3-flash-preview"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}
DEFAULT_CHUNK_SPLIT_SIZES = [20, 8, 1]
DEFAULT_MISSING_NAME_CAPS = [60, 20, 1]
DEFAULT_SLEEP_SECONDS = 3.0
DEFAULT_TIMEOUT_SEC = 120
DEFAULT_HARD_TIMEOUT_SEC = 150
DEFAULT_RETRIES = 3
DEFAULT_MIN_BACKOFF_SEC = 2.0
DEFAULT_MAX_BACKOFF_SEC = 20.0

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
ISSUE_PRIORITY = {
    "wrong_entry": 0,
    "duplicate_entry": 1,
    "wrong_status": 2,
    "wrong_sector": 3,
    "wrong_headquarters": 4,
    "wrong_description": 5,
    "other": 6,
}


class _AlarmTimeout(Exception):
    pass


def _alarm_handler(signum: int, frame: Any) -> None:  # noqa: ARG001
    raise _AlarmTimeout()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_repo_relative_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def save_json_atomic(path: Path, data: dict[str, Any]) -> None:
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


def _extract_first_json_object_fragment(text: str) -> str | None:
    """Extract the first balanced JSON object from arbitrary model text."""
    s = text.strip()
    if not s:
        return None

    for i, ch in enumerate(s):
        if ch != "{":
            continue
        depth = 0
        in_str = False
        escaped = False
        for j in range(i, len(s)):
            c = s[j]
            if in_str:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return s[i:j + 1]
    return None


def parse_json_from_model_text(text: str) -> dict[str, Any]:
    cleaned = strip_markdown_fences(text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        fragment = _extract_first_json_object_fragment(cleaned)
        if not fragment:
            raise e
        parsed = json.loads(fragment)
    if not isinstance(parsed, dict):
        raise ValueError("Model response JSON is not an object")
    return parsed


CHUNK_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "entry_issues": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "entry_name": {"type": "STRING"},
                    "issue_type": {
                        "type": "STRING",
                        "enum": [
                            "wrong_entry",
                            "duplicate_entry",
                            "wrong_status",
                            "wrong_sector",
                            "wrong_headquarters",
                            "wrong_description",
                            "other",
                        ],
                    },
                    "severity": {
                        "type": "STRING",
                        "enum": ["critical", "high", "medium", "low"],
                    },
                    "reason": {"type": "STRING"},
                    "current_value": {
                        "type": "OBJECT",
                        "properties": {
                            "status": {"type": "STRING", "nullable": True},
                            "sector": {"type": "STRING", "nullable": True},
                            "headquarters": {"type": "STRING", "nullable": True},
                            "description": {"type": "STRING", "nullable": True},
                        },
                    },
                    "suggested_fix": {
                        "type": "OBJECT",
                        "properties": {
                            "status": {
                                "type": "STRING",
                                "enum": ["current", "exited", "partial", "unknown"],
                                "nullable": True,
                            },
                            "sector": {"type": "STRING", "nullable": True},
                            "headquarters": {"type": "STRING", "nullable": True},
                            "description": {"type": "STRING", "nullable": True},
                        },
                    },
                    "confidence": {
                        "type": "STRING",
                        "enum": ["high", "medium", "low"],
                    },
                    "evidence_urls": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                },
                "required": [
                    "entry_name",
                    "issue_type",
                    "severity",
                    "reason",
                    "current_value",
                    "suggested_fix",
                    "confidence",
                    "evidence_urls",
                ],
            },
        },
    },
    "required": ["entry_issues"],
}


_META_CORRECTION_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "current": {"type": "STRING", "nullable": True},
        "suggested": {"type": "STRING", "nullable": True},
        "reason": {"type": "STRING"},
        "confidence": {"type": "STRING", "enum": ["high", "medium", "low"]},
        "evidence_urls": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": ["current", "suggested", "reason", "confidence", "evidence_urls"],
}


MISSING_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "missing_assets": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "status": {"type": "STRING", "enum": ["current", "exited", "unknown"]},
                    "sector": {"type": "STRING", "nullable": True},
                    "headquarters": {"type": "STRING", "nullable": True},
                    "description": {"type": "STRING", "nullable": True},
                    "reason": {"type": "STRING"},
                    "confidence": {"type": "STRING", "enum": ["high", "medium", "low"]},
                    "evidence_urls": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                },
                "required": [
                    "name",
                    "status",
                    "sector",
                    "headquarters",
                    "description",
                    "reason",
                    "confidence",
                    "evidence_urls",
                ],
            },
        },
        "fund_metadata_corrections": {
            "type": "OBJECT",
            "properties": {
                "hq_city": _META_CORRECTION_SCHEMA,
                "description": _META_CORRECTION_SCHEMA,
                "website": _META_CORRECTION_SCHEMA,
            },
        },
    },
    "required": ["missing_assets", "fund_metadata_corrections"],
}


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


def parse_positive_int_csv(raw: str) -> list[int]:
    values: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            raise ValueError(f"Invalid integer value in CSV list: {token!r}") from None
        if value <= 0:
            raise ValueError(f"CSV list values must be > 0, got {value}")
        values.append(value)
    if not values:
        raise ValueError("CSV list must contain at least one positive integer")
    return values


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
    scaled = min_backoff_sec * (2 ** attempt)
    if is_rate_limit:
        scaled = max(scaled, min_backoff_sec + 2)
    return min(max_backoff_sec, scaled)


def resolve_split_sizes(requested_sizes: list[int], initial_size: int) -> list[int]:
    if initial_size <= 1:
        return [1]
    out: list[int] = [initial_size]
    for size in requested_sizes:
        if size <= 0 or size > initial_size:
            continue
        if size not in out:
            out.append(size)
    if 1 not in out:
        out.append(1)
    out.sort(reverse=True)
    return out


def resolve_name_caps(
    *,
    total_existing_names: int,
    configured_max_names: int,
    requested_caps: list[int],
) -> list[int]:
    if total_existing_names <= 0:
        return [0]
    initial_cap = configured_max_names if configured_max_names > 0 else total_existing_names
    initial_cap = min(initial_cap, total_existing_names)

    out: list[int] = []
    for cap in [initial_cap, *requested_caps]:
        cap = min(cap, total_existing_names)
        if cap <= 0:
            continue
        if cap not in out:
            out.append(cap)
    if 1 not in out:
        out.append(1)
    return out


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
                # Fallback if this model/key combination rejects tools.google_search
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

                # Structured output schema fallback for model/key compatibility:
                # keep JSON mime mode, but remove explicit schema if rejected.
                if (
                    isinstance(payload.get("generationConfig"), dict)
                    and payload["generationConfig"].get("responseSchema") is not None
                    and ("responseschema" in body_lower or "schema" in body_lower)
                ):
                    payload["generationConfig"].pop("responseSchema", None)
                    if attempt < retries:
                        _sleep_with_jitter(1.0, 0.5)
                        continue

                # Auth/config issues should fail fast.
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
            # Grounding sometimes injects malformed wrappers around the JSON body.
            # Retry without grounding before normal retry/backoff handling.
            if used_grounding:
                payload.pop("tools", None)
                used_grounding = False
                if attempt < retries:
                    _sleep_with_jitter(1.0, 0.5)
                    continue
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


def sort_funds_by_aum_desc(funds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(f: dict[str, Any]) -> tuple[bool, float, str]:
        aum = f.get("aum_eur")
        has_no_aum = aum is None
        aum_num = float(aum) if isinstance(aum, (int, float)) else -1.0
        return (has_no_aum, -aum_num, (f.get("name") or f.get("slug") or "").lower())

    return sorted(funds, key=key)


def chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def sanitize_entry_for_prompt(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": entry.get("name"),
        "status": entry.get("status"),
        "sector": entry.get("sector"),
        "headquarters": entry.get("headquarters"),
        "description": (entry.get("description") or "")[:240] or None,
        "website": entry.get("website"),
        "investment_date": entry.get("investment_date"),
        "source_url": entry.get("source_url"),
        "data_source": entry.get("data_source"),
    }


ITALIAN_CITY_HINTS = {
    "agropoli", "ancona", "arezzo", "asti", "avellino", "bari", "bergamo", "bologna",
    "brescia", "brindisi", "cagliari", "caserta", "catania", "catanzaro", "como",
    "cremona", "ferrara", "florence", "firenze", "foggia", "forli", "genoa", "genova",
    "lecce", "livorno", "lucca", "milan", "milano", "modena", "monza", "naples",
    "napoli", "novara", "padova", "padua", "palermo", "parma", "pavia", "perugia",
    "pesaro", "pescara", "piacenza", "pisa", "prato", "ravenna", "reggio emilia",
    "rimini", "rome", "roma", "salerno", "sassari", "siena", "syracuse", "siracusa",
    "taranto", "terni", "torino", "turin", "trento", "treviso", "trieste", "udine",
    "venice", "venezia", "verona", "vicenza",
}


def is_likely_italian_entry(entry: dict[str, Any]) -> bool:
    hq_raw = str(entry.get("headquarters") or "").strip()
    if hq_raw:
        hq = hq_raw.lower()
        if "italy" in hq or "italia" in hq:
            return True

        # Handle common HQ formats without explicit country (e.g. "Milan", "Turin, Lombardy").
        tokens = [x.strip() for x in re.split(r"[,/\\-]", hq) if x.strip()]
        if tokens and tokens[0] in ITALIAN_CITY_HINTS:
            return True

    # Fallback on textual hints for Italian exposure when HQ is absent or non-Italian.
    hint_blob = " ".join(
        [
            str(entry.get("name") or ""),
            str(entry.get("description") or ""),
            str(entry.get("source_url") or ""),
        ]
    ).lower()
    if re.search(r"\bital(y|ia|ian)\b", hint_blob):
        return True
    return False


def build_chunk_prompt(
    *,
    fund: dict[str, Any],
    portfolio_source_url: str | None,
    chunk_index: int,
    chunk_count: int,
    entries: list[dict[str, Any]],
) -> str:
    entries_json = json.dumps(entries, ensure_ascii=False, indent=2)
    return f"""You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: {fund.get("name")}
- slug: {fund.get("slug")}
- website: {fund.get("website")}
- portfolio_source_url: {portfolio_source_url}
- aum_eur: {fund.get("aum_eur")}
- category: {fund.get("category")}
- hq_city (current db value): {fund.get("hq_city")}
- description (current db value): {fund.get("description")}

Task:
Review ONLY the entries in this chunk ({chunk_index}/{chunk_count}).
Prioritize:
1) wrong entries (not real portfolio companies / duplicates / obvious scrape garbage)
2) wrong current vs exited status
3) wrong sector / headquarters / description

If uncertain, be conservative and lower confidence.
Return ONLY strict JSON object with this schema:
{{
  "entry_issues": [
    {{
      "entry_name": "string",
      "issue_type": "wrong_entry|duplicate_entry|wrong_status|wrong_sector|wrong_headquarters|wrong_description|other",
      "severity": "critical|high|medium|low",
      "reason": "short reason",
      "current_value": {{"status": "...", "sector": "...", "headquarters": "...", "description": "..."}},
      "suggested_fix": {{"status": "current|exited|partial|unknown|null", "sector": "string|null", "headquarters": "string|null", "description": "string|null"}},
      "confidence": "high|medium|low",
      "evidence_urls": ["https://..."]
    }}
  ]
}}

Chunk entries:
{entries_json}
"""


def build_missing_prompt(
    *,
    fund: dict[str, Any],
    portfolio_source_url: str | None,
    existing_names: list[str],
) -> str:
    existing_names_json = json.dumps(existing_names, ensure_ascii=False)
    return f"""You are auditing missing Italian portfolio assets for a PE/VC fund.

Fund:
- name: {fund.get("name")}
- slug: {fund.get("slug")}
- website: {fund.get("website")}
- portfolio_source_url: {portfolio_source_url}
- aum_eur: {fund.get("aum_eur")}
- category: {fund.get("category")}
- current_hq_city: {fund.get("hq_city")}
- current_description: {fund.get("description")}

Existing portfolio names already in our dataset:
{existing_names_json}

Task:
1) Find likely MISSING Italian assets for this fund (current or exited) that are not in the existing list.
   Include Italian subsidiaries/platform investments even if group HQ is outside Italy.
2) Suggest fund metadata corrections only if likely wrong (hq_city, description, website).

Focus on official fund pages and credible sources. If none found, return empty arrays/objects.
Return ONLY strict JSON object:
{{
  "missing_assets": [
    {{
      "name": "string",
      "status": "current|exited|unknown",
      "sector": "string|null",
      "headquarters": "string|null",
      "description": "string|null",
      "reason": "why this is likely missing",
      "confidence": "high|medium|low",
      "evidence_urls": ["https://..."]
    }}
  ],
  "fund_metadata_corrections": {{
    "hq_city": {{"current": "string|null", "suggested": "string|null", "reason": "string", "confidence": "high|medium|low", "evidence_urls": ["https://..."]}},
    "description": {{"current": "string|null", "suggested": "string|null", "reason": "string", "confidence": "high|medium|low", "evidence_urls": ["https://..."]}},
    "website": {{"current": "string|null", "suggested": "string|null", "reason": "string", "confidence": "high|medium|low", "evidence_urls": ["https://..."]}}
  }}
}}
"""


def audit_entries_chunk_with_auto_split(
    *,
    session: requests.Session,
    api_key: str,
    model: str,
    fund: dict[str, Any],
    portfolio_source_url: str | None,
    chunk_index: int,
    chunk_count: int,
    entries: list[dict[str, Any]],
    split_sizes: list[int],
    use_google_search: bool,
    max_output_tokens: int,
    temperature: float,
    timeout_sec: int,
    hard_timeout_sec: int,
    retries: int,
    min_backoff_sec: float,
    max_backoff_sec: float,
    sleep_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int, int]:
    """
    Run chunk audit with progressive auto-splitting on failure.

    Returns:
      issues, call_diagnostics, api_calls, api_failures, unresolved_entries
    """
    if not entries:
        return [], [], 0, 0, 0

    sizes = resolve_split_sizes(split_sizes, len(entries))
    pending_batches: list[list[dict[str, Any]]] = [entries]
    all_issues: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    api_calls = 0
    api_failures = 0
    unresolved_entries = 0

    for tier_idx, split_size in enumerate(sizes):
        if not pending_batches:
            break

        tier_batches: list[list[dict[str, Any]]] = []
        for batch in pending_batches:
            if len(batch) <= split_size:
                tier_batches.append(batch)
            else:
                tier_batches.extend(chunks(batch, split_size))

        next_pending: list[list[dict[str, Any]]] = []
        for sub_idx, sub_entries in enumerate(tier_batches, 1):
            prompt = build_chunk_prompt(
                fund=fund,
                portfolio_source_url=portfolio_source_url,
                chunk_index=chunk_index,
                chunk_count=chunk_count,
                entries=sub_entries,
            )
            try:
                parsed, meta = call_gemini_json(
                    session=session,
                    api_key=api_key,
                    model=model,
                    prompt=prompt,
                    response_schema=CHUNK_RESPONSE_SCHEMA,
                    use_google_search=use_google_search,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                    timeout_sec=timeout_sec,
                    hard_timeout_sec=hard_timeout_sec,
                    retries=retries,
                    min_backoff_sec=min_backoff_sec,
                    max_backoff_sec=max_backoff_sec,
                )
                issues = clean_entry_issues(parsed.get("entry_issues"))
                all_issues.extend(issues)
                diagnostics.append({
                    "chunk_index": chunk_index,
                    "entry_count": len(sub_entries),
                    "issues_found": len(issues),
                    "split_tier": tier_idx + 1,
                    "split_size": split_size,
                    "split_batch_index": sub_idx,
                    "split_batch_total": len(tier_batches),
                    **meta,
                })
            except Exception as e:  # noqa: BLE001
                api_failures += 1
                err = str(e)
                can_retry_smaller = tier_idx < len(sizes) - 1
                diagnostics.append({
                    "chunk_index": chunk_index,
                    "entry_count": len(sub_entries),
                    "issues_found": 0,
                    "split_tier": tier_idx + 1,
                    "split_size": split_size,
                    "split_batch_index": sub_idx,
                    "split_batch_total": len(tier_batches),
                    "error": err,
                    "will_retry_smaller": can_retry_smaller,
                })
                if can_retry_smaller:
                    next_pending.append(sub_entries)
                else:
                    unresolved_entries += len(sub_entries)
            finally:
                api_calls += 1
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

        pending_batches = next_pending
        if pending_batches and tier_idx < len(sizes) - 1:
            remaining = sum(len(x) for x in pending_batches)
            print(
                f"    Chunk {chunk_index}/{chunk_count}: {remaining} entries still failing, "
                f"retrying with split size {sizes[tier_idx + 1]}"
            )

    return all_issues, diagnostics, api_calls, api_failures, unresolved_entries


def clean_entry_issues(raw: Any) -> list[dict[str, Any]]:
    issues = raw if isinstance(raw, list) else []
    cleaned: list[dict[str, Any]] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        name = str(item.get("entry_name") or "").strip()
        issue_type = str(item.get("issue_type") or "other").strip() or "other"
        severity = str(item.get("severity") or "medium").strip().lower()
        if not name:
            continue
        if severity not in SEVERITY_ORDER:
            severity = "medium"
        evidence = item.get("evidence_urls") if isinstance(item.get("evidence_urls"), list) else []
        evidence = [str(x) for x in evidence if isinstance(x, str) and x.startswith("http")]
        cleaned.append({
            "entry_name": name,
            "issue_type": issue_type,
            "severity": severity,
            "reason": str(item.get("reason") or "").strip(),
            "current_value": item.get("current_value") if isinstance(item.get("current_value"), dict) else {},
            "suggested_fix": item.get("suggested_fix") if isinstance(item.get("suggested_fix"), dict) else {},
            "confidence": str(item.get("confidence") or "medium").strip().lower(),
            "evidence_urls": evidence,
        })
    return cleaned


def clean_missing_assets(raw: Any) -> list[dict[str, Any]]:
    assets = raw if isinstance(raw, list) else []
    cleaned: list[dict[str, Any]] = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        status = str(item.get("status") or "unknown").strip().lower()
        if status not in {"current", "exited", "unknown", "partial"}:
            status = "unknown"
        evidence = item.get("evidence_urls") if isinstance(item.get("evidence_urls"), list) else []
        evidence = [str(x) for x in evidence if isinstance(x, str) and x.startswith("http")]
        cleaned.append({
            "name": name,
            "status": status,
            "sector": item.get("sector"),
            "headquarters": item.get("headquarters"),
            "description": item.get("description"),
            "reason": str(item.get("reason") or "").strip(),
            "confidence": str(item.get("confidence") or "medium").strip().lower(),
            "evidence_urls": evidence,
        })
    return cleaned


def dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for issue in issues:
        key = (
            issue.get("entry_name", "").strip().lower(),
            issue.get("issue_type", "other").strip().lower(),
        )
        existing = best.get(key)
        if not existing:
            best[key] = issue
            continue
        curr_rank = (
            SEVERITY_ORDER.get(issue.get("severity", "medium"), 9),
            0 if issue.get("confidence") == "high" else 1 if issue.get("confidence") == "medium" else 2,
            -len(issue.get("evidence_urls") or []),
        )
        prev_rank = (
            SEVERITY_ORDER.get(existing.get("severity", "medium"), 9),
            0 if existing.get("confidence") == "high" else 1 if existing.get("confidence") == "medium" else 2,
            -len(existing.get("evidence_urls") or []),
        )
        if curr_rank < prev_rank:
            best[key] = issue
    deduped = list(best.values())
    deduped.sort(
        key=lambda x: (
            SEVERITY_ORDER.get(x.get("severity", "medium"), 9),
            ISSUE_PRIORITY.get(x.get("issue_type", "other"), 99),
            x.get("entry_name", "").lower(),
        )
    )
    return deduped


def dedupe_missing_assets(assets: list[dict[str, Any]], existing_names: set[str]) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for asset in assets:
        name = str(asset.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in existing_names:
            continue
        prev = out.get(key)
        if not prev:
            out[key] = asset
            continue
        prev_conf = prev.get("confidence", "low")
        curr_conf = asset.get("confidence", "low")
        rank = {"high": 0, "medium": 1, "low": 2}
        if rank.get(curr_conf, 2) < rank.get(prev_conf, 2):
            out[key] = asset
    items = list(out.values())
    items.sort(key=lambda x: (x.get("confidence") != "high", x.get("name", "").lower()))
    return items


def load_progress(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "started_at": now_iso(),
            "completed_slugs": [],
            "failed": {},
            "last_slug": None,
            "updated_at": now_iso(),
        }
    return load_json(path)


def completed_slugs_from_output(
    output: dict[str, Any],
    *,
    verified_zero_italy_slugs: set[str],
) -> tuple[set[str], dict[str, int]]:
    funds = output.get("funds")
    if not isinstance(funds, list):
        return set(), {}

    completed: set[str] = set()
    incomplete_reason_counts: dict[str, int] = {}
    for item in funds:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            continue
        is_complete, reasons = is_fund_result_complete(
            item,
            verified_zero_italy_slugs=verified_zero_italy_slugs,
        )
        if is_complete:
            completed.add(slug)
        for reason in reasons:
            incomplete_reason_counts[reason] = incomplete_reason_counts.get(reason, 0) + 1
    return completed, incomplete_reason_counts


def build_fund_queue(
    *,
    db: dict[str, Any],
    portfolio: dict[str, Any],
    slugs_filter: set[str] | None,
) -> list[dict[str, Any]]:
    funds = db.get("funds") or []
    fund_portfolios = portfolio.get("fund_portfolios") or {}

    queue: list[dict[str, Any]] = []
    for fund in funds:
        slug = fund.get("slug")
        if not slug:
            continue
        if slugs_filter and slug not in slugs_filter:
            continue
        entries = fund_portfolios.get(slug, [])
        # This workflow is about fund-page assets; include only funds with assets on file.
        if not isinstance(entries, list) or len(entries) == 0:
            continue
        queue.append(fund)

    return sort_funds_by_aum_desc(queue)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit fund assets with Gemini 3 Flash (AUM desc, one-by-one).")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model (default: gemini-3-flash-preview)")
    parser.add_argument("--limit-funds", type=int, default=0, help="Max funds to process (0 = all)")
    parser.add_argument("--chunk-size", type=int, default=20, help="Entries per chunk for existing-entry audit")
    parser.add_argument(
        "--chunk-split-sizes",
        type=str,
        default=",".join(str(x) for x in DEFAULT_CHUNK_SPLIT_SIZES),
        help="Fallback split sizes for failed chunk calls (largest->smallest)",
    )
    parser.add_argument("--max-entries-per-fund", type=int, default=0, help="Limit entries audited per fund (0 = all)")
    parser.add_argument("--max-existing-names-in-missing-prompt", type=int, default=60, help="Cap existing names passed to missing-assets prompt")
    parser.add_argument(
        "--missing-name-caps",
        type=str,
        default=",".join(str(x) for x in DEFAULT_MISSING_NAME_CAPS),
        help="Fallback caps for existing names in missing-assets prompt",
    )
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS, help="Delay between model calls")
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC, help="HTTP timeout per API call")
    parser.add_argument(
        "--hard-timeout-sec",
        type=int,
        default=DEFAULT_HARD_TIMEOUT_SEC,
        help="Hard timeout guard (SIGALRM) per API call",
    )
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Retries per API call")
    parser.add_argument("--min-backoff-sec", type=float, default=DEFAULT_MIN_BACKOFF_SEC, help="Minimum backoff before retries")
    parser.add_argument("--max-backoff-sec", type=float, default=DEFAULT_MAX_BACKOFF_SEC, help="Maximum backoff before retries")
    parser.add_argument("--max-output-tokens", type=int, default=4096, help="Gemini maxOutputTokens")
    parser.add_argument("--temperature", type=float, default=0.1, help="Gemini temperature")
    parser.add_argument("--slugs", type=str, help="Comma-separated fund slugs to audit")
    parser.add_argument("--slugs-file", type=str, help="Path to file with slugs (comma/newline separated)")
    parser.add_argument(
        "--output-path",
        type=str,
        default=str(OUTPUT_PATH.relative_to(REPO_ROOT)),
        help="Output JSON path (repo-relative or absolute)",
    )
    parser.add_argument(
        "--progress-path",
        type=str,
        default=str(PROGRESS_PATH.relative_to(REPO_ROOT)),
        help="Progress JSON path (repo-relative or absolute)",
    )
    parser.add_argument(
        "--zero-italy-verified-path",
        type=str,
        default=str(ZERO_ITALY_VERIFIED_PATH.relative_to(REPO_ROOT)),
        help="Path to JSON/TXT whitelist for funds verified to have no Italy assets",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print queue and exit without API calls")
    parser.add_argument("--reset", action="store_true", help="Ignore previous progress/results and start fresh")
    parser.add_argument("--no-grounding", action="store_true", help="Disable google_search tool")
    args = parser.parse_args()

    if args.chunk_size <= 0:
        print("Error: --chunk-size must be > 0", file=sys.stderr)
        return 2
    if args.timeout_sec <= 0:
        print("Error: --timeout-sec must be > 0", file=sys.stderr)
        return 2
    if args.hard_timeout_sec <= 0:
        print("Error: --hard-timeout-sec must be > 0", file=sys.stderr)
        return 2
    if args.hard_timeout_sec < args.timeout_sec:
        print("Error: --hard-timeout-sec should be >= --timeout-sec", file=sys.stderr)
        return 2
    if args.retries < 0:
        print("Error: --retries must be >= 0", file=sys.stderr)
        return 2
    if args.min_backoff_sec <= 0 or args.max_backoff_sec <= 0:
        print("Error: backoff values must be > 0", file=sys.stderr)
        return 2
    if args.min_backoff_sec > args.max_backoff_sec:
        print("Error: --min-backoff-sec cannot be greater than --max-backoff-sec", file=sys.stderr)
        return 2
    if args.max_existing_names_in_missing_prompt < 0:
        print("Error: --max-existing-names-in-missing-prompt must be >= 0", file=sys.stderr)
        return 2

    try:
        requested_split_sizes = parse_positive_int_csv(args.chunk_split_sizes)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    try:
        requested_missing_caps = parse_positive_int_csv(args.missing_name_caps)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    db = load_json(DB_PATH)
    portfolio = load_json(PORTFOLIO_PATH)
    fund_portfolios = portfolio.get("fund_portfolios") or {}
    fund_source_urls = portfolio.get("fund_source_urls") or {}
    output_path = resolve_repo_relative_path(args.output_path)
    progress_path = resolve_repo_relative_path(args.progress_path)
    verified_zero_italy_slugs = load_verified_zero_italy_slugs(
        resolve_repo_relative_path(args.zero_italy_verified_path)
    )

    slugs_filter: set[str] | None = None
    if args.slugs or args.slugs_file:
        merged_slugs: set[str] = set()
        if args.slugs:
            merged_slugs |= {s.strip() for s in args.slugs.split(",") if s.strip()}
        if args.slugs_file:
            slugs_file_path = resolve_repo_relative_path(args.slugs_file)
            if not slugs_file_path.exists():
                print(f"Error: --slugs-file not found: {slugs_file_path}", file=sys.stderr)
                return 2
            raw = slugs_file_path.read_text(encoding="utf-8")
            tokens = re.split(r"[\s,]+", raw)
            merged_slugs |= {t.strip() for t in tokens if t.strip()}
        slugs_filter = merged_slugs

    queue = build_fund_queue(db=db, portfolio=portfolio, slugs_filter=slugs_filter)
    if args.limit_funds > 0:
        queue = queue[:args.limit_funds]

    print(f"Funds with portfolio entries: {len(queue)}")
    if queue:
        preview = ", ".join(f"{f.get('slug')}({f.get('aum_eur')})" for f in queue[:10])
        print(f"Top of queue (AUM desc): {preview}")
        if len(queue) > 10:
            print(f"... +{len(queue) - 10} more")

    if args.dry_run:
        print("Dry-run only. No API calls made.")
        return 0

    api_key = resolve_gemini_api_key()
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment/.env", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    print(
        "Gemini safety settings: "
        f"sleep={args.sleep_seconds}s, retries={args.retries}, "
        f"timeout={args.timeout_sec}s, hard_timeout={args.hard_timeout_sec}s, "
        f"chunk_split={resolve_split_sizes(requested_split_sizes, args.chunk_size)}, "
        f"missing_name_caps={requested_missing_caps}"
    )

    if args.reset:
        progress = {
            "started_at": now_iso(),
            "completed_slugs": [],
            "failed": {},
            "last_slug": None,
            "updated_at": now_iso(),
        }
        output: dict[str, Any] = {
            "generated_at": now_iso(),
            "model": args.model,
            "funds": [],
            "summary": {},
        }
        completed: set[str] = set()
    else:
        progress = load_progress(progress_path)
        output = load_json(output_path) if output_path.exists() else {
            "generated_at": now_iso(),
            "model": args.model,
            "funds": [],
            "summary": {},
        }
        completed, incomplete_reason_counts = completed_slugs_from_output(
            output,
            verified_zero_italy_slugs=verified_zero_italy_slugs,
        )
        progress_completed = {
            str(s)
            for s in (progress.get("completed_slugs") or [])
            if isinstance(s, str) and s.strip()
        }
        stale_progress_completed = sorted(progress_completed - completed)
        if stale_progress_completed:
            print(
                "Resume note: ignoring stale progress-only completed slugs "
                f"({len(stale_progress_completed)})."
            )
        if incomplete_reason_counts:
            print(
                "Resume note: strict incomplete reasons in existing output: "
                + ", ".join(f"{k}={v}" for k, v in sorted(incomplete_reason_counts.items()))
            )

    output_funds = output.get("funds") if isinstance(output.get("funds"), list) else []
    by_slug: dict[str, dict[str, Any]] = {
        f.get("slug"): f for f in output_funds if isinstance(f, dict) and f.get("slug")
    }

    total_calls = 0
    total_failures = 0
    run_started_at = now_iso()
    configured_chunk_split_sizes = resolve_split_sizes(requested_split_sizes, args.chunk_size)

    for idx, fund in enumerate(queue, 1):
        slug = fund.get("slug")
        if not slug:
            continue
        if slug in completed:
            print(f"[{idx}/{len(queue)}] {slug}: already completed, skipping")
            continue

        name = fund.get("name") or slug
        website = fund.get("website")
        aum = fund.get("aum_eur")
        all_entries = list(fund_portfolios.get(slug) or [])
        italian_entries = [e for e in all_entries if isinstance(e, dict) and is_likely_italian_entry(e)]

        if args.max_entries_per_fund > 0:
            italian_entries = italian_entries[:args.max_entries_per_fund]

        sanitized_entries = [sanitize_entry_for_prompt(e) for e in italian_entries]
        entry_chunks = chunks(sanitized_entries, args.chunk_size)

        print(
            f"[{idx}/{len(queue)}] Auditing {name} ({slug}) | AUM={aum} | "
            f"italian_entries={len(sanitized_entries)} | chunks={len(entry_chunks)}"
        )

        all_issues: list[dict[str, Any]] = []
        chunk_meta: list[dict[str, Any]] = []
        per_fund_failed = False
        unresolved_entry_calls = 0

        for chunk_idx, chunk_entries in enumerate(entry_chunks, 1):
            (
                chunk_issues,
                chunk_diagnostics,
                chunk_calls,
                chunk_failures,
                unresolved_entries,
            ) = audit_entries_chunk_with_auto_split(
                session=session,
                api_key=api_key,
                model=args.model,
                fund=fund,
                portfolio_source_url=fund_source_urls.get(slug),
                chunk_index=chunk_idx,
                chunk_count=len(entry_chunks),
                entries=chunk_entries,
                split_sizes=configured_chunk_split_sizes,
                use_google_search=not args.no_grounding,
                max_output_tokens=args.max_output_tokens,
                temperature=args.temperature,
                timeout_sec=args.timeout_sec,
                hard_timeout_sec=args.hard_timeout_sec,
                retries=args.retries,
                min_backoff_sec=args.min_backoff_sec,
                max_backoff_sec=args.max_backoff_sec,
                sleep_seconds=args.sleep_seconds,
            )

            all_issues.extend(chunk_issues)
            chunk_meta.extend(chunk_diagnostics)
            total_calls += chunk_calls
            total_failures += chunk_failures

            if unresolved_entries > 0:
                per_fund_failed = True
                unresolved_entry_calls += unresolved_entries
                print(
                    f"  Chunk {chunk_idx}/{len(entry_chunks)} unresolved entries after auto-split: "
                    f"{unresolved_entries}"
                )

        # Missing-assets + fund-metadata pass (single call per fund)
        missing_assets: list[dict[str, Any]] = []
        fund_metadata_corrections: dict[str, Any] = {}

        all_existing_names = [
            e.get("name")
            for e in all_entries
            if isinstance(e, dict) and isinstance(e.get("name"), str) and str(e.get("name")).strip()
        ]
        existing_names_all = [str(name).strip() for name in all_existing_names if str(name).strip()]
        existing_names_set = {str(n).lower().strip() for n in all_existing_names}

        name_caps = resolve_name_caps(
            total_existing_names=len(existing_names_all),
            configured_max_names=args.max_existing_names_in_missing_prompt,
            requested_caps=requested_missing_caps,
        )

        missing_call_done = False
        for cap_idx, cap in enumerate(name_caps, 1):
            existing_names = existing_names_all[:cap] if cap > 0 else []
            missing_prompt = build_missing_prompt(
                fund=fund,
                portfolio_source_url=fund_source_urls.get(slug),
                existing_names=existing_names,
            )
            try:
                parsed, meta = call_gemini_json(
                    session=session,
                    api_key=api_key,
                    model=args.model,
                    prompt=missing_prompt,
                    response_schema=MISSING_RESPONSE_SCHEMA,
                    use_google_search=not args.no_grounding,
                    max_output_tokens=args.max_output_tokens,
                    temperature=args.temperature,
                    timeout_sec=args.timeout_sec,
                    hard_timeout_sec=args.hard_timeout_sec,
                    retries=args.retries,
                    min_backoff_sec=args.min_backoff_sec,
                    max_backoff_sec=args.max_backoff_sec,
                )
                total_calls += 1
                missing_assets = clean_missing_assets(parsed.get("missing_assets"))
                missing_assets = dedupe_missing_assets(missing_assets, existing_names_set)

                raw_meta_corr = parsed.get("fund_metadata_corrections")
                if isinstance(raw_meta_corr, dict):
                    fund_metadata_corrections = raw_meta_corr
                chunk_meta.append({
                    "missing_assets_call": True,
                    "existing_names_count": len(existing_names),
                    "attempt": cap_idx,
                    **meta,
                    "missing_assets_found": len(missing_assets),
                })
                missing_call_done = True
                if args.sleep_seconds > 0:
                    time.sleep(args.sleep_seconds)
                break
            except Exception as e:  # noqa: BLE001
                total_calls += 1
                total_failures += 1
                err = str(e)
                will_retry_smaller = cap_idx < len(name_caps)
                chunk_meta.append({
                    "missing_assets_call": True,
                    "existing_names_count": len(existing_names),
                    "attempt": cap_idx,
                    "error": err,
                    "will_retry_smaller_prompt": will_retry_smaller,
                })
                if will_retry_smaller:
                    next_cap = name_caps[cap_idx]
                    print(
                        f"  Missing-assets pass failed at names={len(existing_names)}; "
                        f"retrying with names={next_cap} | {err[:180]}"
                    )
                else:
                    per_fund_failed = True
                    print(f"  Missing-assets pass failed: {err[:220]}")
                if args.sleep_seconds > 0:
                    time.sleep(args.sleep_seconds)

        if not missing_call_done:
            per_fund_failed = True

        deduped_issues = dedupe_issues(all_issues)
        fund_result = {
            "slug": slug,
            "name": name,
            "aum_eur": aum,
            "category": fund.get("category"),
            "website": website,
            "hq_city": fund.get("hq_city"),
            "description": fund.get("description"),
            "portfolio_source_url": fund_source_urls.get(slug),
            "existing_portfolio_count": len(all_entries),
            "italian_portfolio_count": len(italian_entries),
            "audited_portfolio_count": len(sanitized_entries),
            "wrong_or_correction_issues": deduped_issues,
            "missing_assets": missing_assets,
            "fund_metadata_corrections": fund_metadata_corrections,
            "unresolved_entries_after_split": unresolved_entry_calls,
            "call_diagnostics": chunk_meta,
            "checked_at": now_iso(),
            "model": args.model,
            "status": "partial_failure" if per_fund_failed else "ok",
        }
        is_strict_complete, completion_reasons = is_fund_result_complete(
            fund_result,
            verified_zero_italy_slugs=verified_zero_italy_slugs,
        )
        fund_result["completion_ready"] = is_strict_complete
        fund_result["completion_blockers"] = completion_reasons
        by_slug[slug] = fund_result

        failed_map = progress.get("failed") if isinstance(progress.get("failed"), dict) else {}
        call_error_count = sum(1 for x in chunk_meta if isinstance(x, dict) and x.get("error"))
        if is_strict_complete:
            completed.add(slug)
            failed_map.pop(slug, None)
        else:
            if per_fund_failed:
                failed_map[slug] = f"{call_error_count} call(s) failed"
            else:
                failed_map[slug] = "not strictly complete: " + ", ".join(completion_reasons)
            completed.discard(slug)
        progress["failed"] = failed_map

        queue_slug_set = {f.get("slug") for f in queue if f.get("slug")}
        ordered_results = [by_slug[f.get("slug")] for f in queue if f.get("slug") in by_slug]
        # Preserve previously stored results when running a subset (e.g. --slugs retries),
        # so we don't truncate the canonical output file.
        preserved_results = [
            fund_result
            for slug_key, fund_result in by_slug.items()
            if slug_key not in queue_slug_set
        ]
        all_results = ordered_results + preserved_results
        strict_completed_all, incomplete_reason_counts_all = completed_slugs_from_output(
            {"funds": all_results},
            verified_zero_italy_slugs=verified_zero_italy_slugs,
        )
        completed = strict_completed_all
        for completed_slug in completed:
            failed_map.pop(completed_slug, None)
        progress["failed"] = failed_map
        unverified_zero_italy_slugs_all: list[str] = []
        for result in all_results:
            if not isinstance(result, dict):
                continue
            result_slug = result.get("slug")
            if not isinstance(result_slug, str):
                continue
            _, result_reasons = is_fund_result_complete(
                result,
                verified_zero_italy_slugs=verified_zero_italy_slugs,
            )
            if "zero_italian_unverified" in result_reasons:
                unverified_zero_italy_slugs_all.append(result_slug)

        progress["completed_slugs"] = sorted(completed)
        progress["last_slug"] = slug
        progress["updated_at"] = now_iso()
        progress["incomplete_reason_counts"] = dict(sorted(incomplete_reason_counts_all.items()))
        progress["unverified_zero_italy_slugs"] = sorted(set(unverified_zero_italy_slugs_all))
        progress["zero_italy_verified_slugs_count"] = len(verified_zero_italy_slugs)

        output["generated_at"] = now_iso()
        output["model"] = args.model
        output["run_started_at"] = run_started_at
        output["funds"] = all_results
        output["summary"] = {
            "funds_in_queue": len(queue),
            "funds_completed": len(completed.intersection({f.get("slug") for f in queue})),
            "funds_completed_strict": len(completed.intersection({f.get("slug") for f in queue})),
            "funds_with_results": len(all_results),
            "total_wrong_or_correction_issues": sum(len((f.get("wrong_or_correction_issues") or [])) for f in all_results),
            "total_missing_assets": sum(len((f.get("missing_assets") or [])) for f in all_results),
            "api_calls": total_calls,
            "api_failures": total_failures,
            "incomplete_reason_counts": dict(sorted(incomplete_reason_counts_all.items())),
            "unverified_zero_italy_slugs": sorted(set(unverified_zero_italy_slugs_all)),
            "zero_italy_verified_slugs_count": len(verified_zero_italy_slugs),
            "updated_at": now_iso(),
        }

        save_json_atomic(output_path, output)
        save_json_atomic(progress_path, progress)

        print(
            f"  -> issues={len(deduped_issues)} missing={len(missing_assets)} "
            f"unresolved_entries={unresolved_entry_calls} "
            f"status={fund_result['status']} completion_ready={fund_result['completion_ready']}"
        )

    session.close()

    print("\nDone.")
    print(f"Output:   {output_path}")
    print(f"Progress: {progress_path}")
    print(f"API calls: {total_calls}, failures: {total_failures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
