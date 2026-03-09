#!/usr/bin/env python3
"""
Import manual Gemini per-fund JSON replies into deduplicated JSONL call log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys; sys.path.insert(0, str(REPO_ROOT / "apps" / "worker"))
from fundradar_worker.paths import GEMINI_MODEL
DEFAULT_RESPONSES_DIR = REPO_ROOT / "data" / "derived" / "gemini_fund_asset_logs" / "manual_responses"
DEFAULT_DEDUP_JSONL = REPO_ROOT / "data" / "derived" / "gemini_fund_asset_logs" / "fund_checks_deduplicated.jsonl"
DEFAULT_ZERO_ITALY_VERIFIED = REPO_ROOT / "data" / "derived" / "gemini_fund_asset_zero_italy_verified.json"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "db.json"


def resolve_repo_relative_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return data


def load_valid_fund_slugs(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    db = load_json(db_path)
    funds = db.get("funds")
    if not isinstance(funds, list):
        return set()
    return {
        str(f.get("slug")).strip()
        for f in funds
        if isinstance(f, dict) and isinstance(f.get("slug"), str) and str(f.get("slug")).strip()
    }


def normalize_urlish(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None

    # Markdown links: [label](url) or [url](url)
    md_match = re.fullmatch(r"\[[^\]]*\]\((https?://[^)\s]+)\)", s)
    if md_match:
        return md_match.group(1)

    # Bracket-only URL: [https://example.com]
    bracket_match = re.fullmatch(r"\[(https?://[^\]\s]+)\]", s)
    if bracket_match:
        return bracket_match.group(1)

    if s.startswith("http://") or s.startswith("https://"):
        return s
    return None


def clean_entry_issues(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("entry_name") or "").strip()
        if not name:
            continue
        issue_type = str(item.get("issue_type") or "other").strip() or "other"
        severity = str(item.get("severity") or "medium").strip().lower()
        if severity not in {"critical", "high", "medium", "low"}:
            severity = "medium"
        confidence = str(item.get("confidence") or "medium").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"
        evidence = item.get("evidence_urls") if isinstance(item.get("evidence_urls"), list) else []
        normalized = [normalize_urlish(x) for x in evidence]
        evidence = [x for x in normalized if isinstance(x, str)]
        out.append(
            {
                "entry_name": name,
                "issue_type": issue_type,
                "severity": severity,
                "reason": str(item.get("reason") or "").strip(),
                "current_value": item.get("current_value") if isinstance(item.get("current_value"), dict) else {},
                "suggested_fix": item.get("suggested_fix") if isinstance(item.get("suggested_fix"), dict) else {},
                "confidence": confidence,
                "evidence_urls": evidence,
            }
        )
    return out


def clean_missing_assets(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
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
        normalized = [normalize_urlish(x) for x in evidence]
        evidence = [x for x in normalized if isinstance(x, str)]
        out.append(
            {
                "name": name,
                "status": status,
                "sector": item.get("sector"),
                "headquarters": item.get("headquarters"),
                "description": item.get("description"),
                "reason": str(item.get("reason") or "").strip(),
                "confidence": confidence,
                "evidence_urls": evidence,
            }
        )
    return out


def clean_metadata(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for field in ("hq_city", "description", "website"):
        item = raw.get(field)
        if not isinstance(item, dict):
            continue
        confidence = str(item.get("confidence") or "medium").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"
        evidence = item.get("evidence_urls") if isinstance(item.get("evidence_urls"), list) else []
        normalized = [normalize_urlish(x) for x in evidence]
        evidence = [x for x in normalized if isinstance(x, str)]
        current = item.get("current")
        suggested = item.get("suggested")
        current_norm = normalize_urlish(current) if field == "website" else current
        suggested_norm = normalize_urlish(suggested) if field == "website" else suggested
        out[field] = {
            "current": current_norm,
            "suggested": suggested_norm,
            "reason": str(item.get("reason") or "").strip(),
            "confidence": confidence,
            "evidence_urls": evidence,
        }
    return out


def dedupe_key(row: dict[str, Any]) -> str:
    if row.get("manual_import") is True and isinstance(row.get("turnId"), str):
        return f"manual:{row['turnId']}"
    turn_id = row.get("turnId")
    create_time = row.get("createTime")
    if isinstance(turn_id, str) and isinstance(create_time, str):
        return f"{turn_id}|{create_time}"
    payload = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def make_row(
    *,
    slug: str,
    kind: str,
    response_obj: dict[str, Any],
    create_time: str,
) -> dict[str, Any]:
    body_text = json.dumps(response_obj, ensure_ascii=False)
    turn_hash = hashlib.sha1(f"{slug}|{kind}|{body_text}".encode("utf-8")).hexdigest()[:16]
    turn_id = f"manual-{slug}-{kind}-{turn_hash}"

    if kind == "chunk":
        prompt = (
            "You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.\n\n"
            f"Fund:\n- slug: {slug}\n\n"
            "Task:\nReview ONLY the entries in this chunk (1/1).\n"
            "Return ONLY strict JSON object with schema {\"entry_issues\": [...]}."
        )
    else:
        prompt = (
            "You are auditing missing Italian portfolio assets for a PE/VC fund.\n\n"
            f"Fund:\n- slug: {slug}\n\n"
            "Task:\nFind likely MISSING Italian assets and fund metadata corrections.\n"
            "Return ONLY strict JSON with {\"missing_assets\": [...], \"fund_metadata_corrections\": {...}}."
        )

    return {
        "request": {
            "model": GEMINI_MODEL,
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
            "tools": [],
        },
        "response": [
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": body_text}]},
                    }
                ]
            }
        ],
        "turnId": turn_id,
        "datasetIds": [],
        "createTime": create_time,
        "responseStatus": "manual_import",
        "manual_import": True,
        "manual_slug": slug,
        "manual_kind": kind,
    }


def load_verified_zero_italy(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    if isinstance(data, list):
        return {str(x).strip() for x in data if isinstance(x, str) and str(x).strip()}
    if isinstance(data, dict):
        for key in ("verified_slugs", "slugs", "funds"):
            value = data.get(key)
            if isinstance(value, list):
                return {str(x).strip() for x in value if isinstance(x, str) and str(x).strip()}
    return set()


def save_verified_zero_italy(path: Path, slugs: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"verified_slugs": sorted(slugs)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import manual Gemini responses into deduplicated JSONL.")
    parser.add_argument(
        "--responses-dir",
        type=str,
        default=str(DEFAULT_RESPONSES_DIR.relative_to(REPO_ROOT)),
        help="Directory containing <slug>.json files",
    )
    parser.add_argument(
        "--dedup-jsonl-path",
        type=str,
        default=str(DEFAULT_DEDUP_JSONL.relative_to(REPO_ROOT)),
        help="Deduplicated JSONL path to append to",
    )
    parser.add_argument(
        "--zero-italy-verified-path",
        type=str,
        default=str(DEFAULT_ZERO_ITALY_VERIFIED.relative_to(REPO_ROOT)),
        help="Path to zero-Italy verified whitelist JSON/TXT",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DEFAULT_DB_PATH.relative_to(REPO_ROOT)),
        help="db.json path used as slug source of truth",
    )
    parser.add_argument(
        "--allow-non-db-slugs",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Allow importing response files whose slug is not present in db.json",
    )
    parser.add_argument(
        "--update-zero-italy-whitelist",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If response has confirmed_no_italian_assets=true, add slug to whitelist",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without writing")
    args = parser.parse_args()

    responses_dir = resolve_repo_relative_path(args.responses_dir)
    dedup_jsonl_path = resolve_repo_relative_path(args.dedup_jsonl_path)
    zero_italy_path = resolve_repo_relative_path(args.zero_italy_verified_path)
    db_path = resolve_repo_relative_path(args.db_path)
    valid_slugs = load_valid_fund_slugs(db_path)

    if not valid_slugs and not args.allow_non_db_slugs:
        print(f"Error: no valid slugs loaded from db path: {db_path}")
        return 2

    if not responses_dir.exists():
        print(f"Error: responses dir not found: {responses_dir}")
        return 2

    response_files = sorted([p for p in responses_dir.glob("*.json") if p.is_file()])
    if not response_files:
        print(f"No response JSON files found in: {responses_dir}")
        return 0

    existing_keys: set[str] = set()
    existing_rows: list[str] = []
    if dedup_jsonl_path.exists():
        with open(dedup_jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                existing_rows.append(line)
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    existing_keys.add(dedupe_key(row))

    rows_to_append: list[dict[str, Any]] = []
    added_rows = 0
    skipped_duplicates = 0
    processed_slugs: list[str] = []
    skipped_non_db_slugs: list[str] = []
    zero_italy_new: set[str] = set()

    for response_file in response_files:
        slug = response_file.stem.strip().lower()
        if not args.allow_non_db_slugs and slug not in valid_slugs:
            skipped_non_db_slugs.append(slug)
            print(f"Skip {response_file.name}: slug not found in db.json ({slug})")
            continue
        try:
            payload = json.loads(response_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Skip {response_file.name}: invalid JSON ({e})")
            continue
        if not isinstance(payload, dict):
            print(f"Skip {response_file.name}: root must be object")
            continue

        entry_issues = clean_entry_issues(payload.get("entry_issues"))
        missing_assets = clean_missing_assets(payload.get("missing_assets"))
        metadata = clean_metadata(payload.get("fund_metadata_corrections"))
        confirmed_no_italy = bool(payload.get("confirmed_no_italian_assets") is True)

        base_time = now_iso()
        chunk_row = make_row(
            slug=slug,
            kind="chunk",
            response_obj={"entry_issues": entry_issues},
            create_time=base_time,
        )
        missing_row = make_row(
            slug=slug,
            kind="missing",
            response_obj={
                "missing_assets": missing_assets,
                "fund_metadata_corrections": metadata,
                "confirmed_no_italian_assets": confirmed_no_italy,
            },
            create_time=base_time,
        )

        for row in (chunk_row, missing_row):
            key = dedupe_key(row)
            if key in existing_keys:
                skipped_duplicates += 1
                continue
            existing_keys.add(key)
            rows_to_append.append(row)
            added_rows += 1

        if confirmed_no_italy and len(missing_assets) == 0:
            zero_italy_new.add(slug)
        processed_slugs.append(slug)

    if args.dry_run:
        print(f"Would process slugs: {len(processed_slugs)}")
        print(f"Would skip non-db slugs: {len(skipped_non_db_slugs)}")
        print(f"Would append rows: {added_rows}")
        print(f"Would skip duplicates: {skipped_duplicates}")
        if args.update_zero_italy_whitelist and zero_italy_new:
            print(f"Would add to zero-Italy whitelist: {sorted(zero_italy_new)}")
        return 0

    dedup_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dedup_jsonl_path, "a", encoding="utf-8") as f:
        for row in rows_to_append:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            f.write("\n")

    if args.update_zero_italy_whitelist and zero_italy_new:
        verified = load_verified_zero_italy(zero_italy_path)
        verified |= zero_italy_new
        save_verified_zero_italy(zero_italy_path, verified)

    print(f"Processed slugs: {len(processed_slugs)}")
    print(f"Skipped non-db slugs: {len(skipped_non_db_slugs)}")
    print(f"Appended rows: {added_rows}")
    print(f"Skipped duplicates: {skipped_duplicates}")
    if args.update_zero_italy_whitelist and zero_italy_new:
        print(f"Updated zero-Italy whitelist with: {', '.join(sorted(zero_italy_new))}")
    print(f"Deduplicated JSONL: {dedup_jsonl_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
