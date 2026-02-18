#!/usr/bin/env python3
"""
Recover Gemini fund-asset audit outputs from exported AI Studio JSONL logs.

This script:
1) Merges and deduplicates raw JSONL call logs.
2) Extracts fund-level chunk/missing responses.
3) Rebuilds canonical audit + progress files to match recovered coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gemini_audit_completion import is_fund_result_complete, load_verified_zero_italy_slugs

REPO_ROOT = Path(__file__).resolve().parent.parent
DERIVED = REPO_ROOT / "data" / "derived"
DB_PATH = REPO_ROOT / "data" / "db.json"
PORTFOLIO_PATH = DERIVED / "portfolio_items.json"

DEFAULT_OUTPUT_PATH = DERIVED / "gemini_fund_asset_audit.json"
DEFAULT_PROGRESS_PATH = DERIVED / "gemini_fund_asset_audit_progress.json"
DEFAULT_REPORT_PATH = DERIVED / "gemini_fund_asset_audit_recovery_report.json"
DEFAULT_DEDUP_JSONL_PATH = DERIVED / "gemini_fund_asset_logs" / "fund_checks_deduplicated.jsonl"
DEFAULT_ZERO_ITALY_VERIFIED_PATH = DERIVED / "gemini_fund_asset_zero_italy_verified.json"

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
CONF_RANK = {"high": 0, "medium": 1, "low": 2}

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

SLUG_RE = re.compile(r"(?:^|\n)\s*(?:-|\\*)?\s*slug\s*:\s*([a-z0-9][a-z0-9-]*)\b", re.IGNORECASE)
CHUNK_POS_RE = re.compile(r"chunk\s*\((\d+)\s*/\s*(\d+)\)", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def save_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def resolve_repo_relative_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def sort_funds_by_aum_desc(funds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(f: dict[str, Any]) -> tuple[bool, float, str]:
        aum = f.get("aum_eur")
        has_no_aum = aum is None
        aum_num = float(aum) if isinstance(aum, (int, float)) else -1.0
        return (has_no_aum, -aum_num, (f.get("name") or f.get("slug") or "").lower())

    return sorted(funds, key=key)


def build_fund_queue(
    db: dict[str, Any],
    portfolio: dict[str, Any],
    *,
    include_all_db_funds: bool,
) -> list[dict[str, Any]]:
    funds = db.get("funds") or []
    fund_portfolios = portfolio.get("fund_portfolios") or {}
    queue: list[dict[str, Any]] = []
    for fund in funds:
        if not isinstance(fund, dict):
            continue
        slug = fund.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            continue
        if not include_all_db_funds:
            entries = fund_portfolios.get(slug, [])
            if not isinstance(entries, list) or len(entries) == 0:
                continue
        queue.append(fund)
    return sort_funds_by_aum_desc(queue)


def is_likely_italian_entry(entry: dict[str, Any]) -> bool:
    hq_raw = str(entry.get("headquarters") or "").strip()
    if hq_raw:
        hq = hq_raw.lower()
        if "italy" in hq or "italia" in hq:
            return True
        tokens = [x.strip() for x in re.split(r"[,/\\-]", hq) if x.strip()]
        if tokens and tokens[0] in ITALIAN_CITY_HINTS:
            return True

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
        confidence = str(item.get("confidence") or "medium").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"
        evidence = item.get("evidence_urls") if isinstance(item.get("evidence_urls"), list) else []
        evidence = [str(x) for x in evidence if isinstance(x, str) and x.startswith("http")]
        cleaned.append({
            "entry_name": name,
            "issue_type": issue_type,
            "severity": severity,
            "reason": str(item.get("reason") or "").strip(),
            "current_value": item.get("current_value") if isinstance(item.get("current_value"), dict) else {},
            "suggested_fix": item.get("suggested_fix") if isinstance(item.get("suggested_fix"), dict) else {},
            "confidence": confidence,
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
        confidence = str(item.get("confidence") or "medium").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"
        evidence = item.get("evidence_urls") if isinstance(item.get("evidence_urls"), list) else []
        evidence = [str(x) for x in evidence if isinstance(x, str) and x.startswith("http")]
        cleaned.append({
            "name": name,
            "status": status,
            "sector": item.get("sector"),
            "headquarters": item.get("headquarters"),
            "description": item.get("description"),
            "reason": str(item.get("reason") or "").strip(),
            "confidence": confidence,
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
            CONF_RANK.get(issue.get("confidence", "low"), 9),
            -len(issue.get("evidence_urls") or []),
        )
        prev_rank = (
            SEVERITY_ORDER.get(existing.get("severity", "medium"), 9),
            CONF_RANK.get(existing.get("confidence", "low"), 9),
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
        curr_rank = (
            CONF_RANK.get(asset.get("confidence", "low"), 9),
            -len(asset.get("evidence_urls") or []),
        )
        prev_rank = (
            CONF_RANK.get(prev.get("confidence", "low"), 9),
            -len(prev.get("evidence_urls") or []),
        )
        if curr_rank < prev_rank:
            out[key] = asset
    items = list(out.values())
    items.sort(key=lambda x: (x.get("confidence") != "high", x.get("name", "").lower()))
    return items


def extract_prompt_text(request_obj: Any) -> str:
    if not isinstance(request_obj, dict):
        return ""
    contents = request_obj.get("contents")
    if not isinstance(contents, list):
        return ""
    texts: list[str] = []
    for content in contents:
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        elif isinstance(content.get("text"), str):
            texts.append(content["text"])
    return "\n".join(texts)


def extract_response_text(response_obj: Any) -> str:
    texts: list[str] = []

    if isinstance(response_obj, list):
        for item in response_obj:
            if not isinstance(item, dict):
                continue
            candidates = item.get("candidates")
            if isinstance(candidates, list):
                for candidate in candidates:
                    if not isinstance(candidate, dict):
                        continue
                    content = candidate.get("content")
                    if isinstance(content, dict):
                        parts = content.get("parts")
                        if isinstance(parts, list):
                            for part in parts:
                                if isinstance(part, dict) and isinstance(part.get("text"), str):
                                    texts.append(part["text"])
                    if isinstance(candidate.get("output"), str):
                        texts.append(candidate["output"])
            if isinstance(item.get("text"), str):
                texts.append(item["text"])
    elif isinstance(response_obj, dict):
        if isinstance(response_obj.get("text"), str):
            texts.append(response_obj["text"])

    return "\n".join(texts)


def parse_slug_from_prompt(prompt: str) -> str | None:
    match = SLUG_RE.search(prompt)
    if not match:
        return None
    slug = match.group(1).strip().lower()
    return slug or None


def infer_slug_from_row(row: dict[str, Any]) -> str | None:
    manual_slug = row.get("manual_slug")
    if isinstance(manual_slug, str) and manual_slug.strip():
        return manual_slug.strip().lower()
    prompt = extract_prompt_text(row.get("request"))
    return parse_slug_from_prompt(prompt)


def parse_call_type(prompt: str) -> str:
    if "Review ONLY the entries in this chunk" in prompt:
        return "chunk"
    low = prompt.lower()
    if "find likely missing italian assets" in low or "missing italian portfolio assets" in low:
        return "missing"
    return "other"


def parse_chunk_position(prompt: str) -> tuple[int | None, int | None]:
    match = CHUNK_POS_RE.search(prompt)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def parse_json_object_from_text(text: str) -> dict[str, Any] | None:
    s = text.strip()
    if not s:
        return None

    candidates = [
        s,
        s.replace("```json", "").replace("```", "").strip(),
    ]
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    # Scan for first parseable JSON object.
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
                    fragment = s[i:j + 1]
                    try:
                        obj = json.loads(fragment)
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                    break
    return None


def dedupe_key(row: dict[str, Any]) -> str:
    if row.get("manual_import") is True and isinstance(row.get("turnId"), str):
        return f"manual:{row['turnId']}"
    turn_id = row.get("turnId")
    create_time = row.get("createTime")
    if isinstance(turn_id, str) and isinstance(create_time, str):
        return f"{turn_id}|{create_time}"
    fallback = json.dumps(
        {
            "request": row.get("request"),
            "response": row.get("response"),
            "createTime": row.get("createTime"),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha1(fallback.encode("utf-8")).hexdigest()


def parse_create_time_ts(raw: Any) -> float:
    if not isinstance(raw, str) or not raw.strip():
        return 0.0
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def choose_better_meta(current: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if current is None:
        return candidate
    curr_rank = (
        CONF_RANK.get(str(current.get("confidence") or "low").lower(), 9),
        -len(current.get("evidence_urls") or []),
    )
    cand_rank = (
        CONF_RANK.get(str(candidate.get("confidence") or "low").lower(), 9),
        -len(candidate.get("evidence_urls") or []),
    )
    if cand_rank < curr_rank:
        return candidate
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover Gemini fund-asset audit from AI Studio JSONL logs.")
    parser.add_argument(
        "--input-jsonl",
        action="append",
        required=True,
        help="Input JSONL path (repeat for multiple files)",
    )
    parser.add_argument(
        "--dedup-jsonl-path",
        type=str,
        default=str(DEFAULT_DEDUP_JSONL_PATH.relative_to(REPO_ROOT)),
        help="Output path for deduplicated JSONL",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=str(DEFAULT_OUTPUT_PATH.relative_to(REPO_ROOT)),
        help="Recovered audit output JSON path",
    )
    parser.add_argument(
        "--progress-path",
        type=str,
        default=str(DEFAULT_PROGRESS_PATH.relative_to(REPO_ROOT)),
        help="Recovered progress JSON path",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default=str(DEFAULT_REPORT_PATH.relative_to(REPO_ROOT)),
        help="Recovery report JSON path",
    )
    parser.add_argument(
        "--zero-italy-verified-path",
        type=str,
        default=str(DEFAULT_ZERO_ITALY_VERIFIED_PATH.relative_to(REPO_ROOT)),
        help="Path to whitelist JSON/TXT for verified zero-Italy funds",
    )
    parser.add_argument(
        "--include-all-db-funds",
        action="store_true",
        help="Include funds without existing portfolio entries (for full DB coverage)",
    )
    parser.add_argument(
        "--allow-non-db-slugs",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If true, keep non-db slugs in deduplicated JSONL and parsing counters",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and report only; do not write output/progress")
    args = parser.parse_args()

    input_paths = [resolve_repo_relative_path(p) for p in args.input_jsonl]
    for path in input_paths:
        if not path.exists():
            print(f"Error: input JSONL not found: {path}")
            return 2

    dedup_jsonl_path = resolve_repo_relative_path(args.dedup_jsonl_path)
    output_path = resolve_repo_relative_path(args.output_path)
    progress_path = resolve_repo_relative_path(args.progress_path)
    report_path = resolve_repo_relative_path(args.report_path)
    verified_zero_italy_slugs = load_verified_zero_italy_slugs(resolve_repo_relative_path(args.zero_italy_verified_path))

    db = load_json(DB_PATH)
    db_slug_set = {
        f.get("slug")
        for f in (db.get("funds") or [])
        if isinstance(f, dict) and isinstance(f.get("slug"), str) and f.get("slug").strip()
    }
    portfolio = load_json(PORTFOLIO_PATH)
    fund_portfolios = portfolio.get("fund_portfolios") or {}
    fund_source_urls = portfolio.get("fund_source_urls") or {}
    queue = build_fund_queue(db, portfolio, include_all_db_funds=args.include_all_db_funds)
    queue_slugs = [f["slug"] for f in queue if f.get("slug")]
    queue_slug_set = set(queue_slugs)
    fund_by_slug = {f["slug"]: f for f in queue if isinstance(f, dict) and isinstance(f.get("slug"), str)}

    dedup_rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    rows_total = 0
    duplicate_rows = 0
    rows_removed_non_db_slug = 0

    for input_path in input_paths:
        with open(input_path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                rows_total += 1
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                key = dedupe_key(row)
                if key in seen_keys:
                    duplicate_rows += 1
                    continue
                seen_keys.add(key)
                row["_source_file"] = str(input_path)
                dedup_rows.append(row)

    dedup_rows.sort(key=lambda r: parse_create_time_ts(r.get("createTime")))
    if not args.allow_non_db_slugs:
        filtered_rows: list[dict[str, Any]] = []
        for row in dedup_rows:
            slug = infer_slug_from_row(row)
            if slug and slug not in db_slug_set:
                rows_removed_non_db_slug += 1
                continue
            filtered_rows.append(row)
        dedup_rows = filtered_rows

    slug_state: dict[str, dict[str, Any]] = {}
    parse_success_calls = 0
    parse_failed_calls = 0
    calls_with_slug = 0
    calls_dropped_non_db_slug = 0

    for row in dedup_rows:
        prompt = extract_prompt_text(row.get("request"))
        slug = parse_slug_from_prompt(prompt)
        if not slug:
            continue
        calls_with_slug += 1
        if not args.allow_non_db_slugs and slug not in db_slug_set:
            calls_dropped_non_db_slug += 1
            continue
        if slug not in queue_slug_set:
            continue

        call_type = parse_call_type(prompt)
        create_time = row.get("createTime")
        state = slug_state.setdefault(
            slug,
            {
                "chunk_calls_total": 0,
                "missing_calls_total": 0,
                "chunk_success_calls": 0,
                "missing_success_calls": 0,
                "parse_failed_calls": 0,
                "issues": [],
                "missing_assets": [],
                "meta_fields": {},  # field -> best correction object
                "call_diagnostics": [],
                "first_call_time": create_time,
                "last_call_time": create_time,
            },
        )
        if isinstance(create_time, str):
            first = state.get("first_call_time")
            last = state.get("last_call_time")
            if not isinstance(first, str) or create_time < first:
                state["first_call_time"] = create_time
            if not isinstance(last, str) or create_time > last:
                state["last_call_time"] = create_time

        if call_type == "chunk":
            state["chunk_calls_total"] += 1
        elif call_type == "missing":
            state["missing_calls_total"] += 1
        else:
            continue

        response_text = extract_response_text(row.get("response"))
        parsed = parse_json_object_from_text(response_text)
        if parsed is None:
            parse_failed_calls += 1
            state["parse_failed_calls"] += 1
            continue
        parse_success_calls += 1

        if call_type == "chunk":
            chunk_issues = clean_entry_issues(parsed.get("entry_issues"))
            state["issues"].extend(chunk_issues)
            state["chunk_success_calls"] += 1
            chunk_idx, chunk_total = parse_chunk_position(prompt)
            state["call_diagnostics"].append(
                {
                    "chunk": chunk_idx,
                    "chunk_count": chunk_total,
                    "recovered_from_logs": True,
                    "create_time": create_time,
                }
            )
            continue

        missing_assets = clean_missing_assets(parsed.get("missing_assets"))
        state["missing_assets"].extend(missing_assets)
        state["missing_success_calls"] += 1

        raw_corr = parsed.get("fund_metadata_corrections")
        if isinstance(raw_corr, dict):
            for field in ("hq_city", "description", "website"):
                item = raw_corr.get(field)
                if not isinstance(item, dict):
                    continue
                suggested = item.get("suggested")
                current = item.get("current")
                if suggested is None:
                    continue
                if isinstance(suggested, str) and not suggested.strip():
                    continue
                if isinstance(current, str) and isinstance(suggested, str) and current.strip() == suggested.strip():
                    continue
                confidence = str(item.get("confidence") or "medium").strip().lower()
                if confidence not in {"high", "medium", "low"}:
                    confidence = "medium"
                evidence = item.get("evidence_urls") if isinstance(item.get("evidence_urls"), list) else []
                evidence = [str(x) for x in evidence if isinstance(x, str) and x.startswith("http")]
                candidate = {
                    "current": current,
                    "suggested": suggested,
                    "reason": str(item.get("reason") or "").strip(),
                    "confidence": confidence,
                    "evidence_urls": evidence,
                }
                prev = state["meta_fields"].get(field)
                state["meta_fields"][field] = choose_better_meta(prev, candidate)

        state["call_diagnostics"].append(
            {
                "missing_assets_call": True,
                "recovered_from_logs": True,
                "create_time": create_time,
            }
        )

    recovered_funds: list[dict[str, Any]] = []
    for slug in queue_slugs:
        state = slug_state.get(slug)
        if not state:
            continue
        fund = fund_by_slug.get(slug)
        if not fund:
            continue

        all_entries = list(fund_portfolios.get(slug) or [])
        italian_entries = [e for e in all_entries if isinstance(e, dict) and is_likely_italian_entry(e)]
        existing_names_set = {
            str(e.get("name")).strip().lower()
            for e in all_entries
            if isinstance(e, dict) and isinstance(e.get("name"), str) and str(e.get("name")).strip()
        }

        deduped_issues = dedupe_issues(state["issues"])
        deduped_missing_assets = dedupe_missing_assets(state["missing_assets"], existing_names_set)

        fund_meta_corr: dict[str, Any] = {}
        for field in ("hq_city", "description", "website"):
            item = state["meta_fields"].get(field)
            if isinstance(item, dict):
                fund_meta_corr[field] = item

        per_fund_failed = False
        if state["missing_success_calls"] == 0:
            per_fund_failed = True
        if len(italian_entries) > 0 and state["chunk_success_calls"] == 0:
            per_fund_failed = True

        result = {
            "slug": slug,
            "name": fund.get("name") or slug,
            "aum_eur": fund.get("aum_eur"),
            "category": fund.get("category"),
            "website": fund.get("website"),
            "hq_city": fund.get("hq_city"),
            "description": fund.get("description"),
            "portfolio_source_url": fund_source_urls.get(slug),
            "existing_portfolio_count": len(all_entries),
            "italian_portfolio_count": len(italian_entries),
            "audited_portfolio_count": len(italian_entries) if state["chunk_success_calls"] > 0 else 0,
            "wrong_or_correction_issues": deduped_issues,
            "missing_assets": deduped_missing_assets,
            "fund_metadata_corrections": fund_meta_corr,
            "unresolved_entries_after_split": 0,
            "call_diagnostics": state["call_diagnostics"],
            "checked_at": state.get("last_call_time") or now_iso(),
            "model": "gemini-3-flash-preview",
            "status": "partial_failure" if per_fund_failed else "ok",
            "recovered_from_logs": True,
            "recovery_parse_failed_calls": state["parse_failed_calls"],
            "recovery_chunk_success_calls": state["chunk_success_calls"],
            "recovery_missing_success_calls": state["missing_success_calls"],
        }
        is_complete, blockers = is_fund_result_complete(
            result,
            verified_zero_italy_slugs=verified_zero_italy_slugs,
        )
        result["completion_ready"] = is_complete
        result["completion_blockers"] = blockers
        recovered_funds.append(result)

    completed_slugs: set[str] = set()
    incomplete_reason_counts: dict[str, int] = {}
    unverified_zero_italy_slugs: list[str] = []
    failed_map: dict[str, str] = {}
    partial_failure_slugs: list[str] = []
    for fund in recovered_funds:
        slug = fund.get("slug")
        if not isinstance(slug, str):
            continue
        status = str(fund.get("status") or "")
        if status == "partial_failure":
            partial_failure_slugs.append(slug)

        is_complete, blockers = is_fund_result_complete(
            fund,
            verified_zero_italy_slugs=verified_zero_italy_slugs,
        )
        if is_complete:
            completed_slugs.add(slug)
            continue

        failed_map[slug] = "not strictly complete: " + ", ".join(blockers)
        for blocker in blockers:
            incomplete_reason_counts[blocker] = incomplete_reason_counts.get(blocker, 0) + 1
        if "zero_italian_unverified" in blockers:
            unverified_zero_italy_slugs.append(slug)

    remaining = [slug for slug in queue_slugs if slug not in completed_slugs]
    total_issues = sum(len(f.get("wrong_or_correction_issues") or []) for f in recovered_funds)
    total_missing_assets = sum(len(f.get("missing_assets") or []) for f in recovered_funds)
    api_calls = sum(len(f.get("call_diagnostics") or []) for f in recovered_funds)
    api_failures = sum(int(f.get("recovery_parse_failed_calls") or 0) for f in recovered_funds)

    output = {
        "generated_at": now_iso(),
        "model": "gemini-3-flash-preview",
        "run_recovered_at": now_iso(),
        "funds": recovered_funds,
        "summary": {
            "funds_in_queue": len(queue_slugs),
            "funds_with_results": len(recovered_funds),
            "funds_completed": len([s for s in completed_slugs if s in queue_slug_set]),
            "funds_completed_strict": len([s for s in completed_slugs if s in queue_slug_set]),
            "funds_remaining": len(remaining),
            "total_wrong_or_correction_issues": total_issues,
            "total_missing_assets": total_missing_assets,
            "api_calls": api_calls,
            "api_failures": api_failures,
            "partial_failure_slugs": sorted(set(partial_failure_slugs)),
            "incomplete_reason_counts": dict(sorted(incomplete_reason_counts.items())),
            "unverified_zero_italy_slugs": sorted(set(unverified_zero_italy_slugs)),
            "zero_italy_verified_slugs_count": len(verified_zero_italy_slugs),
            "updated_at": now_iso(),
        },
    }

    progress = {
        "started_at": now_iso(),
        "completed_slugs": sorted(completed_slugs),
        "failed": failed_map,
        "last_slug": recovered_funds[-1]["slug"] if recovered_funds else None,
        "updated_at": now_iso(),
        "partial_failure_slugs": sorted(set(partial_failure_slugs)),
        "incomplete_slugs": sorted(set(failed_map.keys())),
        "incomplete_reason_counts": dict(sorted(incomplete_reason_counts.items())),
        "unverified_zero_italy_slugs": sorted(set(unverified_zero_italy_slugs)),
        "zero_italy_verified_slugs_count": len(verified_zero_italy_slugs),
        "remaining_slugs_count": len(remaining),
    }

    report = {
        "generated_at": now_iso(),
        "include_all_db_funds": args.include_all_db_funds,
        "allow_non_db_slugs": args.allow_non_db_slugs,
        "input_files": [str(p) for p in input_paths],
        "rows_total": rows_total,
        "rows_deduplicated": len(dedup_rows),
        "rows_removed_as_duplicates": duplicate_rows,
        "rows_removed_non_db_slug": rows_removed_non_db_slug,
        "calls_with_slug": calls_with_slug,
        "calls_dropped_non_db_slug": calls_dropped_non_db_slug,
        "parse_success_calls": parse_success_calls,
        "parse_failed_calls": parse_failed_calls,
        "queue_funds_total": len(queue_slugs),
        "queue_funds_with_recovered_results": len(recovered_funds),
        "queue_funds_completed_strict": len([s for s in completed_slugs if s in queue_slug_set]),
        "queue_funds_remaining": len(remaining),
        "remaining_preview": remaining[:20],
        "coverage_types": {
            "both_chunk_and_missing": len(
                [
                    s
                    for s, st in slug_state.items()
                    if s in queue_slug_set and st.get("chunk_success_calls", 0) > 0 and st.get("missing_success_calls", 0) > 0
                ]
            ),
            "missing_only": len(
                [
                    s
                    for s, st in slug_state.items()
                    if s in queue_slug_set and st.get("chunk_success_calls", 0) == 0 and st.get("missing_success_calls", 0) > 0
                ]
            ),
            "chunk_only": len(
                [
                    s
                    for s, st in slug_state.items()
                    if s in queue_slug_set and st.get("chunk_success_calls", 0) > 0 and st.get("missing_success_calls", 0) == 0
                ]
            ),
        },
    }

    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    dedup_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dedup_jsonl_path, "w", encoding="utf-8") as f:
        for row in dedup_rows:
            out_row = dict(row)
            # Keep source trace in dedup artifact but remove any accidental non-serializable values.
            f.write(json.dumps(out_row, ensure_ascii=False, separators=(",", ":")))
            f.write("\n")

    save_json_atomic(output_path, output)
    save_json_atomic(progress_path, progress)
    save_json_atomic(report_path, report)

    print(f"Wrote deduplicated JSONL: {dedup_jsonl_path} ({len(dedup_rows)} rows)")
    print(f"Wrote recovered output:   {output_path} ({len(recovered_funds)} funds)")
    print(f"Wrote recovered progress: {progress_path}")
    print(f"Wrote recovery report:    {report_path}")
    print(f"Strict completed: {len(completed_slugs)}/{len(queue_slugs)}")
    print(f"Remaining: {len(remaining)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
