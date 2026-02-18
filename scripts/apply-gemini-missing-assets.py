#!/usr/bin/env python3
"""
Apply Gemini missing-asset suggestions into portfolio_items.json.

Default behavior:
- apply only high-confidence suggestions
- include non-Italy high-confidence suggestions (can be restricted with --italy-only)
- honor manual review decisions (reject / openai-check / ready)
- mark inserted entries as curation_locked to protect against future pipeline overwrites
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DERIVED = REPO_ROOT / "data" / "derived"

DEFAULT_PORTFOLIO = DERIVED / "portfolio_items.json"
DEFAULT_AUDIT_INPUTS = [
    DERIVED / "gemini_fund_asset_audit.json",
    DERIVED / "gemini_fund_asset_audit.shard1.json",
    DERIVED / "gemini_fund_asset_audit.shard2.json",
]
DEFAULT_MANUAL_REVIEW = DERIVED / "gemini_fund_asset_manual_review.json"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "db.json"
DEFAULT_CANONICAL_JSONL = DERIVED / "gemini_fund_asset_logs" / "fund_checks_deduplicated.jsonl"
DEFAULT_APPLY_REPORT_DIR = DERIVED / "gemini_apply_runs"

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}

# Legacy slug compatibility map for pre-normalization artifacts.
# Keep until all historical audit inputs are clean.
LEGACY_SLUG_REDIRECTS: dict[str, str] = {
    "banca-sella-holding": "sella-venture-partners",
}

# Legacy merged/retired slugs require manual handling (no blind auto-map).
LEGACY_SLUG_RETIRED: set[str] = {
    "simest",
    "generali-investments",
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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_path(raw: str) -> Path:
    p = Path(raw)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


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


def count_non_empty_lines(path: Path) -> int:
    count = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            if raw.strip():
                count += 1
    return count


def backup_before_write_compat(path: Path) -> str | None:
    """
    Prefer worker backup_before_write() helper, fallback to local copy.
    """
    try:
        worker_root = REPO_ROOT / "apps" / "worker"
        if str(worker_root) not in sys.path:
            sys.path.insert(0, str(worker_root))
        from fundradar_worker.io_utils import backup_before_write  # type: ignore

        backup_path = backup_before_write(path)
        return str(backup_path) if backup_path else None
    except Exception:
        stamp = now_stamp()
        backup_path = path.with_name(f"{path.name}.apply_gemini_{stamp}.bak")
        shutil.copy2(path, backup_path)
        return str(backup_path)


def normalize_company_name(name: str) -> str:
    s = name.lower()
    s = re.sub(r"\s*\(.*?\)\s*", " ", s)
    s = re.sub(r"\b(s\.?p\.?a\.?|s\.?r\.?l\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?s\.?)\b", " ", s)
    s = re.sub(r"\bgroup\b", " ", s)
    s = re.sub(r"[^a-z0-9]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_likely_italian_hq(hq: str | None) -> bool:
    if not hq:
        return False
    text = hq.strip().lower()
    if "italy" in text or "italia" in text:
        return True
    tokens = [x.strip() for x in re.split(r"[,/\\-]", text) if x.strip()]
    if not tokens:
        return False
    return tokens[0] in ITALIAN_CITY_HINTS


def confidence_to_score(confidence: str) -> float:
    c = confidence.strip().lower()
    if c == "high":
        return 0.9
    if c == "medium":
        return 0.6
    return 0.4


def parse_inputs(raw_inputs: str) -> list[Path]:
    paths: list[Path] = []
    for token in raw_inputs.split(","):
        t = token.strip()
        if not t:
            continue
        p = resolve_path(t)
        if p.exists():
            paths.append(p)
    return paths


def merge_audit_funds(input_files: list[Path]) -> dict[str, dict[str, Any]]:
    by_slug: dict[str, dict[str, Any]] = {}
    mtime_by_slug: dict[str, float] = {}
    for path in input_files:
        data = load_json(path)
        funds = data.get("funds")
        if not isinstance(funds, list):
            continue
        mtime = path.stat().st_mtime
        for fund in funds:
            if not isinstance(fund, dict):
                continue
            slug = fund.get("slug")
            if not isinstance(slug, str) or not slug.strip():
                continue
            if slug not in by_slug or mtime > mtime_by_slug[slug]:
                by_slug[slug] = fund
                mtime_by_slug[slug] = mtime
    return by_slug


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


def build_manual_decision_map(manual_review: dict[str, Any]) -> dict[tuple[str, str], tuple[str, str]]:
    out: dict[tuple[str, str], tuple[str, str]] = {}
    funds = manual_review.get("funds")
    if not isinstance(funds, dict):
        return out
    for slug, fund_block in funds.items():
        if not isinstance(fund_block, dict):
            continue
        missing_assets = fund_block.get("missing_assets")
        if not isinstance(missing_assets, dict):
            continue
        for asset_name, decision_obj in missing_assets.items():
            if not isinstance(asset_name, str) or not isinstance(decision_obj, dict):
                continue
            decision = str(decision_obj.get("decision") or "").strip()
            note = str(decision_obj.get("note") or "").strip()
            out[(slug, normalize_company_name(asset_name))] = (decision, note)
    return out


def should_apply_suggestion(
    *,
    slug: str,
    asset: dict[str, Any],
    min_confidence: str,
    italy_only: bool,
    include_openai_check: bool,
    manual_map: dict[tuple[str, str], tuple[str, str]],
) -> tuple[bool, str]:
    name = str(asset.get("name") or "").strip()
    if not name:
        return False, "missing_name"

    normalized = normalize_company_name(name)
    key = (slug, normalized)
    decision_note = ""

    if key in manual_map:
        decision, note = manual_map[key]
        decision_note = note
        if decision == "rejected":
            return False, "manual_rejected"
        if decision == "needs_openai_double_check" and not include_openai_check:
            return False, "manual_openai_check"
        if decision == "ready_for_apply":
            # Manual ready bypasses confidence threshold.
            pass
        elif decision not in {"", "needs_openai_double_check", "ready_for_apply"}:
            return False, "invalid_manual_decision"
    else:
        confidence = str(asset.get("confidence") or "").strip().lower()
        if CONFIDENCE_RANK.get(confidence, -1) < CONFIDENCE_RANK[min_confidence]:
            return False, "below_confidence_threshold"

    if italy_only and not is_likely_italian_hq(asset.get("headquarters")):
        return False, "non_italy_hq_filtered"

    return True, decision_note or "ok"


def build_entry_from_missing_asset(asset: dict[str, Any], decision_note: str) -> dict[str, Any]:
    confidence = str(asset.get("confidence") or "medium").strip().lower()
    evidence_urls = asset.get("evidence_urls") if isinstance(asset.get("evidence_urls"), list) else []
    evidence_urls = [str(u) for u in evidence_urls if isinstance(u, str) and u.startswith("http")]

    status = str(asset.get("status") or "unknown").strip().lower()
    if status not in {"current", "exited", "partial", "unknown"}:
        status = "unknown"

    return {
        "name": str(asset.get("name") or "").strip(),
        "sector": asset.get("sector"),
        "status": status,
        "confidence": confidence_to_score(confidence),
        "website": None,
        "description": asset.get("description"),
        "detail_page_url": None,
        "headquarters": asset.get("headquarters"),
        "investment_date": None,
        "source_url": evidence_urls[0] if evidence_urls else None,
        "data_source": "gemini_missing_asset",
        "gemini_confidence": confidence,
        "gemini_reason": str(asset.get("reason") or "").strip() or None,
        "gemini_evidence_urls": evidence_urls,
        "curation_locked": True,
        "curation_source": "gemini_audit_missing_asset",
        "curation_applied_at": now_iso(),
        "curation_note": decision_note or None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Gemini missing-asset suggestions to portfolio_items.json")
    parser.add_argument(
        "--inputs",
        type=str,
        default=",".join(str(p.relative_to(REPO_ROOT)) for p in DEFAULT_AUDIT_INPUTS),
        help="Comma-separated audit JSON files (master + shard files)",
    )
    parser.add_argument(
        "--portfolio-path",
        type=str,
        default=str(DEFAULT_PORTFOLIO.relative_to(REPO_ROOT)),
        help="Portfolio JSON path",
    )
    parser.add_argument(
        "--manual-review-path",
        type=str,
        default=str(DEFAULT_MANUAL_REVIEW.relative_to(REPO_ROOT)),
        help="Manual decision JSON path",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DEFAULT_DB_PATH.relative_to(REPO_ROOT)),
        help="db.json path used to validate canonical slugs",
    )
    parser.add_argument(
        "--min-confidence",
        type=str,
        default="high",
        choices=["low", "medium", "high"],
        help="Minimum confidence to apply when no manual decision exists",
    )
    parser.add_argument(
        "--italy-only",
        action="store_true",
        help="Apply only suggestions with Italy-like headquarters",
    )
    parser.add_argument(
        "--include-openai-check",
        action="store_true",
        help="Also apply manual entries marked needs_openai_double_check",
    )
    parser.add_argument(
        "--canonical-jsonl-path",
        type=str,
        default=str(DEFAULT_CANONICAL_JSONL.relative_to(REPO_ROOT)),
        help="Canonical deduplicated Gemini JSONL source-of-truth path",
    )
    parser.add_argument(
        "--require-canonical-jsonl",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require canonical Gemini JSONL to exist and be non-empty before apply",
    )
    parser.add_argument(
        "--apply-report-dir",
        type=str,
        default=str(DEFAULT_APPLY_REPORT_DIR.relative_to(REPO_ROOT)),
        help="Directory for timestamped apply reports",
    )
    parser.add_argument(
        "--apply-report-path",
        type=str,
        default="",
        help="Optional explicit apply report path (overrides --apply-report-dir)",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()

    input_files = parse_inputs(args.inputs)
    if not input_files:
        print("Error: no valid input files found", flush=True)
        return 2

    portfolio_path = resolve_path(args.portfolio_path)
    if not portfolio_path.exists():
        print(f"Error: portfolio file not found: {portfolio_path}", flush=True)
        return 2

    manual_path = resolve_path(args.manual_review_path)
    manual_review = load_json(manual_path) if manual_path.exists() else {}
    manual_map = build_manual_decision_map(manual_review)
    valid_slugs = load_valid_fund_slugs(resolve_path(args.db_path))
    canonical_jsonl_path = resolve_path(args.canonical_jsonl_path)
    canonical_jsonl_rows = 0
    if canonical_jsonl_path.exists():
        canonical_jsonl_rows = count_non_empty_lines(canonical_jsonl_path)
    if args.require_canonical_jsonl:
        if not canonical_jsonl_path.exists():
            print(f"Error: canonical JSONL not found: {canonical_jsonl_path}", flush=True)
            return 2
        if canonical_jsonl_rows == 0:
            print(f"Error: canonical JSONL is empty: {canonical_jsonl_path}", flush=True)
            return 2

    merged = merge_audit_funds(input_files)
    portfolio = load_json(portfolio_path)
    fund_portfolios = portfolio.get("fund_portfolios")
    if not isinstance(fund_portfolios, dict):
        print("Error: invalid portfolio format (fund_portfolios missing)", flush=True)
        return 2

    added = 0
    skipped_existing = 0
    skipped_by_reason: dict[str, int] = {}
    redirected_slugs = 0
    funds_touched: set[str] = set()
    candidates = 0

    for audit_slug, fund in merged.items():
        slug = audit_slug
        if slug not in valid_slugs:
            if slug in LEGACY_SLUG_RETIRED:
                skipped_by_reason["retired_or_merged_slug_requires_manual_mapping"] = (
                    skipped_by_reason.get("retired_or_merged_slug_requires_manual_mapping", 0) + 1
                )
                continue
            redirected = LEGACY_SLUG_REDIRECTS.get(slug)
            if redirected and redirected in valid_slugs:
                slug = redirected
                redirected_slugs += 1
            else:
                skipped_by_reason["unknown_slug_not_in_db"] = (
                    skipped_by_reason.get("unknown_slug_not_in_db", 0) + 1
                )
                continue

        missing_assets = fund.get("missing_assets")
        if not isinstance(missing_assets, list):
            continue
        entries = fund_portfolios.get(slug)
        if not isinstance(entries, list):
            entries = []
            fund_portfolios[slug] = entries

        existing_names = {normalize_company_name(str(e.get("name") or "")) for e in entries if isinstance(e, dict)}

        for asset in missing_assets:
            if not isinstance(asset, dict):
                continue

            ok, reason = should_apply_suggestion(
                slug=audit_slug,
                asset=asset,
                min_confidence=args.min_confidence,
                italy_only=args.italy_only,
                include_openai_check=args.include_openai_check,
                manual_map=manual_map,
            )
            if not ok:
                skipped_by_reason[reason] = skipped_by_reason.get(reason, 0) + 1
                continue

            candidates += 1
            name_norm = normalize_company_name(str(asset.get("name") or ""))
            if not name_norm:
                skipped_by_reason["invalid_name_after_normalization"] = (
                    skipped_by_reason.get("invalid_name_after_normalization", 0) + 1
                )
                continue
            if name_norm in existing_names:
                skipped_existing += 1
                continue

            entry = build_entry_from_missing_asset(asset, decision_note=reason if reason != "ok" else "")
            entries.append(entry)
            existing_names.add(name_norm)
            added += 1
            funds_touched.add(slug)

    print(f"Audit files loaded: {len(input_files)}")
    print(f"Funds with audit results: {len(merged)}")
    print(f"Candidate suggestions after filters: {candidates}")
    print(f"Added entries: {added}")
    print(f"Skipped existing: {skipped_existing}")
    print(f"Funds touched: {len(funds_touched)}")
    print(f"Legacy slug redirects applied: {redirected_slugs}")
    if skipped_by_reason:
        print("Skipped by reason:")
        for key in sorted(skipped_by_reason):
            print(f"  - {key}: {skipped_by_reason[key]}")

    report: dict[str, Any] = {
        "generated_at": now_iso(),
        "mode": "apply" if args.apply else "dry_run",
        "inputs": [str(p) for p in input_files],
        "portfolio_path": str(portfolio_path),
        "canonical_jsonl_path": str(canonical_jsonl_path),
        "canonical_jsonl_rows": canonical_jsonl_rows,
        "require_canonical_jsonl": bool(args.require_canonical_jsonl),
        "filters": {
            "min_confidence": args.min_confidence,
            "italy_only": bool(args.italy_only),
            "include_openai_check": bool(args.include_openai_check),
        },
        "summary": {
            "audit_files_loaded": len(input_files),
            "funds_with_audit_results": len(merged),
            "candidate_suggestions_after_filters": candidates,
            "added_entries": added,
            "skipped_existing": skipped_existing,
            "funds_touched_count": len(funds_touched),
            "legacy_slug_redirects_applied": redirected_slugs,
        },
        "funds_touched": sorted(funds_touched),
        "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
    }

    if args.apply:
        backup_path = backup_before_write_compat(portfolio_path)
        save_json_atomic(portfolio_path, portfolio)
        report["portfolio_backup_path"] = backup_path
        print(f"Written: {portfolio_path}")

        if args.apply_report_path.strip():
            report_path = resolve_path(args.apply_report_path.strip())
        else:
            report_dir = resolve_path(args.apply_report_dir)
            report_path = report_dir / f"gemini_apply_report_{now_stamp()}.json"
        save_json_atomic(report_path, report)
        print(f"Apply report: {report_path}")
    else:
        print("Dry-run: no file written. Use --apply to persist.")
        print("Dry-run note: apply report is written only when --apply is used.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
