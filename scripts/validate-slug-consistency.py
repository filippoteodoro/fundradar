#!/usr/bin/env python3
"""
Validate slug consistency across active Fundradar artifacts.

Source of truth: data/db.json -> funds[*].slug
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "db.json"
PORTFOLIO_PATH = REPO_ROOT / "data" / "derived" / "portfolio_items.json"
LINKEDIN_PATH = REPO_ROOT / "data" / "derived" / "linkedin" / "fund_linkedin_urls.json"
LINKEDIN_PRIORITIZED_PATH = REPO_ROOT / "data" / "derived" / "linkedin" / "fund_linkedin_urls_prioritized.json"
LINKEDIN_PEOPLE_STATS_PATH = REPO_ROOT / "data" / "derived" / "linkedin" / "fund_people_stats.json"
EXTRACTOR_WORK_QUEUE_PATH = REPO_ROOT / "data" / "derived" / "extractor_work_queue.json"
SIGNAL_WORK_QUEUE_PATH = REPO_ROOT / "data" / "derived" / "signal_work_queue.json"
URL_DISCOVERY_QUEUE_PATH = REPO_ROOT / "data" / "derived" / "url_discovery_queue.json"
FUND_EXTRACTION_AUDIT_PATH = REPO_ROOT / "data" / "derived" / "fund_extraction_audit.json"
FUND_PAGE_AUDIT_PATH = REPO_ROOT / "data" / "derived" / "fund_page_audit.json"
FUND_QUALITY_AUDIT_PATH = REPO_ROOT / "data" / "derived" / "fund_quality_audit.json"
SIGNAL_AUDIT_REPORT_PATH = REPO_ROOT / "data" / "derived" / "signal_audit_report.json"
QUALITY_BASELINES_PATH = REPO_ROOT / "data" / "derived" / "quality_baselines.json"
POISON_URLS_PATH = REPO_ROOT / "data" / "derived" / "poison_urls.json"
ASSET_STATUS_AUDIT_PATH = REPO_ROOT / "data" / "derived" / "asset_status_audit.json"
AIFI_REFRESH_QUEUE_PATH = REPO_ROOT / "data" / "derived" / "aifi_refresh_queue.json"
BULK_EXTRACTION_AUDIT_PATH = REPO_ROOT / "data" / "derived" / "bulk_extraction_audit.json"
AUDIT_PATH = REPO_ROOT / "data" / "derived" / "gemini_fund_asset_audit.json"
PROGRESS_PATH = REPO_ROOT / "data" / "derived" / "gemini_fund_asset_audit_progress.json"
ZERO_ITALY_PATH = REPO_ROOT / "data" / "derived" / "gemini_fund_asset_zero_italy_verified.json"
DEDUP_JSONL_PATH = REPO_ROOT / "data" / "derived" / "gemini_fund_asset_logs" / "fund_checks_deduplicated.jsonl"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PROMPT_SLUG_RE = re.compile(r"(?:^|\n)\s*(?:-|\\*)?\s*slug\s*:\s*([a-z0-9][a-z0-9-]*)\b", re.IGNORECASE)


def resolve_repo_relative_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON: {path}")
    return data


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


def infer_slug_from_jsonl_row(row: dict[str, Any]) -> str | None:
    manual_slug = row.get("manual_slug")
    if isinstance(manual_slug, str) and manual_slug.strip():
        return manual_slug.strip().lower()
    prompt = extract_prompt_text(row.get("request"))
    m = PROMPT_SLUG_RE.search(prompt)
    if m:
        return m.group(1).strip().lower()
    return None


def diff_against_db(db_slugs: set[str], observed_slugs: set[str]) -> dict[str, list[str]]:
    return {
        "extra_not_in_db": sorted(observed_slugs - db_slugs),
        "missing_vs_db": sorted(db_slugs - observed_slugs),
    }


def extract_string_set(items: list[Any]) -> set[str]:
    return {x for x in items if isinstance(x, str) and x.strip()}


def extract_field_from_list(rows: list[Any], field: str) -> set[str]:
    return {
        row.get(field)
        for row in rows
        if isinstance(row, dict) and isinstance(row.get(field), str) and row.get(field).strip()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate slug consistency with db.json as source of truth.")
    parser.add_argument("--db-path", type=str, default=str(DB_PATH.relative_to(REPO_ROOT)))
    parser.add_argument("--portfolio-path", type=str, default=str(PORTFOLIO_PATH.relative_to(REPO_ROOT)))
    parser.add_argument("--linkedin-path", type=str, default=str(LINKEDIN_PATH.relative_to(REPO_ROOT)))
    parser.add_argument(
        "--linkedin-prioritized-path",
        type=str,
        default=str(LINKEDIN_PRIORITIZED_PATH.relative_to(REPO_ROOT)),
    )
    parser.add_argument("--audit-path", type=str, default=str(AUDIT_PATH.relative_to(REPO_ROOT)))
    parser.add_argument("--progress-path", type=str, default=str(PROGRESS_PATH.relative_to(REPO_ROOT)))
    parser.add_argument("--zero-italy-path", type=str, default=str(ZERO_ITALY_PATH.relative_to(REPO_ROOT)))
    parser.add_argument("--dedup-jsonl-path", type=str, default=str(DEDUP_JSONL_PATH.relative_to(REPO_ROOT)))
    parser.add_argument(
        "--allow-missing-portfolio-keys",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If true, do not fail when fund_portfolios is missing DB slugs",
    )
    args = parser.parse_args()

    db_path = resolve_repo_relative_path(args.db_path)
    portfolio_path = resolve_repo_relative_path(args.portfolio_path)
    linkedin_path = resolve_repo_relative_path(args.linkedin_path)
    linkedin_prioritized_path = resolve_repo_relative_path(args.linkedin_prioritized_path)
    audit_path = resolve_repo_relative_path(args.audit_path)
    progress_path = resolve_repo_relative_path(args.progress_path)
    zero_italy_path = resolve_repo_relative_path(args.zero_italy_path)
    dedup_jsonl_path = resolve_repo_relative_path(args.dedup_jsonl_path)

    if not db_path.exists():
        print(f"Error: DB file not found: {db_path}")
        return 2

    db = load_json(db_path)
    db_funds = db.get("funds")
    if not isinstance(db_funds, list):
        print("Error: data/db.json missing funds[]")
        return 2

    db_slugs_raw = [f.get("slug") for f in db_funds if isinstance(f, dict)]
    db_slugs = [s for s in db_slugs_raw if isinstance(s, str) and s.strip()]
    db_slug_set = set(db_slugs)

    duplicates: list[str] = []
    seen: set[str] = set()
    for slug in db_slugs:
        if slug in seen and slug not in duplicates:
            duplicates.append(slug)
        seen.add(slug)

    invalid_format = [s for s in db_slugs if not SLUG_RE.match(s)]

    report: dict[str, Any] = {
        "db": {
            "fund_count": len(db_slugs),
            "unique_count": len(db_slug_set),
            "duplicate_slugs": sorted(duplicates),
            "invalid_format_slugs": sorted(invalid_format),
        },
        "checks": {},
    }
    failures: list[str] = []

    def add_failure(reason: str) -> None:
        if reason not in failures:
            failures.append(reason)

    def run_extra_only_check(label: str, observed: set[str], failure_reason: str) -> None:
        diff = diff_against_db(db_slug_set, observed)
        report["checks"][label] = diff
        if diff["extra_not_in_db"]:
            add_failure(failure_reason)

    if duplicates:
        add_failure("db_duplicate_slugs")
    if invalid_format:
        add_failure("db_invalid_slug_format")

    # portfolio_items
    if portfolio_path.exists():
        portfolio = load_json(portfolio_path)
        fund_portfolios = portfolio.get("fund_portfolios") if isinstance(portfolio.get("fund_portfolios"), dict) else {}
        fund_source_urls = portfolio.get("fund_source_urls") if isinstance(portfolio.get("fund_source_urls"), dict) else {}
        portfolio_geo_scope = portfolio.get("portfolio_geo_scope") if isinstance(portfolio.get("portfolio_geo_scope"), dict) else {}
        portfolio_notes = portfolio.get("portfolio_notes") if isinstance(portfolio.get("portfolio_notes"), dict) else {}

        fp_diff = diff_against_db(db_slug_set, set(fund_portfolios.keys()))
        fsu_diff = diff_against_db(db_slug_set, set(fund_source_urls.keys()))
        pgs_diff = diff_against_db(db_slug_set, set(portfolio_geo_scope.keys()))
        pn_diff = diff_against_db(db_slug_set, set(portfolio_notes.keys()))
        report["checks"]["portfolio_items.fund_portfolios"] = fp_diff
        report["checks"]["portfolio_items.fund_source_urls"] = fsu_diff
        report["checks"]["portfolio_items.portfolio_geo_scope"] = pgs_diff
        report["checks"]["portfolio_items.portfolio_notes"] = pn_diff

        if fp_diff["extra_not_in_db"]:
            add_failure("portfolio_extra_not_in_db")
        if fp_diff["missing_vs_db"] and not args.allow_missing_portfolio_keys:
            add_failure("portfolio_missing_db_slug_keys")
        if fsu_diff["extra_not_in_db"]:
            add_failure("fund_source_urls_extra_not_in_db")
        if pgs_diff["extra_not_in_db"]:
            add_failure("portfolio_geo_scope_extra_not_in_db")
        if pn_diff["extra_not_in_db"]:
            add_failure("portfolio_notes_extra_not_in_db")
    else:
        report["checks"]["portfolio_items"] = {"missing_file": str(portfolio_path)}
        add_failure("portfolio_items_missing")

    # LinkedIn URL files
    for label, path in (
        ("linkedin.fund_linkedin_urls", linkedin_path),
        ("linkedin.fund_linkedin_urls_prioritized", linkedin_prioritized_path),
    ):
        if not path.exists():
            report["checks"][label] = {"missing_file": str(path)}
            add_failure(f"{label}_missing")
            continue
        payload = load_json(path)
        companies = payload.get("companies")
        if not isinstance(companies, list):
            report["checks"][label] = {"invalid_shape": "companies must be list"}
            add_failure(f"{label}_invalid_shape")
            continue
        observed = extract_field_from_list(companies, "slug")
        run_extra_only_check(label, observed, f"{label}_extra_not_in_db")

    # LinkedIn people stats
    if LINKEDIN_PEOPLE_STATS_PATH.exists():
        payload = load_json(LINKEDIN_PEOPLE_STATS_PATH)
        observed: set[str] = set()
        funds = payload.get("funds")
        if isinstance(funds, dict):
            observed |= extract_string_set(list(funds.keys()))
            for value in funds.values():
                if isinstance(value, dict):
                    slug = value.get("fund_slug")
                    if isinstance(slug, str) and slug.strip():
                        observed.add(slug)
        run_extra_only_check("linkedin.fund_people_stats", observed, "linkedin_fund_people_stats_extra_not_in_db")
    else:
        report["checks"]["linkedin.fund_people_stats"] = {"missing_file": str(LINKEDIN_PEOPLE_STATS_PATH)}

    # Queue-style files
    queue_specs: list[tuple[str, Path, str, str]] = [
        ("extractor_work_queue", EXTRACTOR_WORK_QUEUE_PATH, "fund_id", "extractor_work_queue_extra_not_in_db"),
        ("signal_work_queue", SIGNAL_WORK_QUEUE_PATH, "slug", "signal_work_queue_extra_not_in_db"),
        ("url_discovery_queue", URL_DISCOVERY_QUEUE_PATH, "fund_id", "url_discovery_queue_extra_not_in_db"),
    ]
    for label, path, field, fail_reason in queue_specs:
        if not path.exists():
            report["checks"][label] = {"missing_file": str(path)}
            continue
        payload = load_json(path)
        observed: set[str] = set()
        list_keys = [
            key
            for key, value in payload.items()
            if isinstance(value, list) and any(isinstance(item, dict) and field in item for item in value)
        ]
        for key in list_keys:
            observed |= extract_field_from_list(payload.get(key, []), field)
        run_extra_only_check(label, observed, fail_reason)
        report["checks"][label]["list_keys_checked"] = list_keys

    # Fund extraction audit
    if FUND_EXTRACTION_AUDIT_PATH.exists():
        payload = load_json(FUND_EXTRACTION_AUDIT_PATH)
        observed: set[str] = set()
        funds = payload.get("funds")
        if isinstance(funds, dict):
            observed |= extract_string_set(list(funds.keys()))
            for value in funds.values():
                if isinstance(value, dict):
                    fund_id = value.get("fund_id")
                    if isinstance(fund_id, str) and fund_id.strip():
                        observed.add(fund_id)
        run_extra_only_check("fund_extraction_audit", observed, "fund_extraction_audit_extra_not_in_db")
    else:
        report["checks"]["fund_extraction_audit"] = {"missing_file": str(FUND_EXTRACTION_AUDIT_PATH)}

    if BULK_EXTRACTION_AUDIT_PATH.exists():
        payload = load_json(BULK_EXTRACTION_AUDIT_PATH)
        observed = extract_field_from_list(payload.get("results", []) if isinstance(payload.get("results"), list) else [], "fund_id")
        run_extra_only_check("bulk_extraction_audit", observed, "bulk_extraction_audit_extra_not_in_db")
    else:
        report["checks"]["bulk_extraction_audit"] = {"missing_file": str(BULK_EXTRACTION_AUDIT_PATH)}

    if FUND_PAGE_AUDIT_PATH.exists():
        payload = load_json(FUND_PAGE_AUDIT_PATH)
        observed = extract_field_from_list(payload.get("funds", []) if isinstance(payload.get("funds"), list) else [], "slug")
        run_extra_only_check("fund_page_audit", observed, "fund_page_audit_extra_not_in_db")
    else:
        report["checks"]["fund_page_audit"] = {"missing_file": str(FUND_PAGE_AUDIT_PATH)}

    if FUND_QUALITY_AUDIT_PATH.exists():
        payload = load_json(FUND_QUALITY_AUDIT_PATH)
        observed = extract_field_from_list(payload.get("funds", []) if isinstance(payload.get("funds"), list) else [], "slug")
        run_extra_only_check("fund_quality_audit", observed, "fund_quality_audit_extra_not_in_db")
    else:
        report["checks"]["fund_quality_audit"] = {"missing_file": str(FUND_QUALITY_AUDIT_PATH)}

    if SIGNAL_AUDIT_REPORT_PATH.exists():
        payload = load_json(SIGNAL_AUDIT_REPORT_PATH)
        observed: set[str] = set()

        for key in ("all_funds_low_quality", "all_funds_zero_signals"):
            rows = payload.get(key)
            if isinstance(rows, list):
                observed |= extract_field_from_list(rows, "slug")

        funds_working_well = payload.get("funds_working_well")
        if isinstance(funds_working_well, list):
            observed |= extract_string_set(funds_working_well)

        priority = payload.get("priority_issues")
        if isinstance(priority, dict):
            for key in ("italian_funds_zero_signals", "funds_with_extractor_but_zero_signals", "high_pem_deals_zero_signals"):
                rows = priority.get(key)
                if isinstance(rows, list):
                    observed |= extract_field_from_list(rows, "slug")

        run_extra_only_check("signal_audit_report", observed, "signal_audit_report_extra_not_in_db")
    else:
        report["checks"]["signal_audit_report"] = {"missing_file": str(SIGNAL_AUDIT_REPORT_PATH)}

    if QUALITY_BASELINES_PATH.exists():
        payload = load_json(QUALITY_BASELINES_PATH)
        observed: set[str] = set()
        baselines = payload.get("baselines")
        if isinstance(baselines, dict):
            for key, value in baselines.items():
                if isinstance(key, str) and key:
                    slug = key.split(":", 1)[0]
                    if slug:
                        observed.add(slug)
                if isinstance(value, dict):
                    fund_slug = value.get("fund_slug")
                    if isinstance(fund_slug, str) and fund_slug.strip():
                        observed.add(fund_slug)
        run_extra_only_check("quality_baselines", observed, "quality_baselines_extra_not_in_db")
    else:
        report["checks"]["quality_baselines"] = {"missing_file": str(QUALITY_BASELINES_PATH)}

    if POISON_URLS_PATH.exists():
        payload = load_json(POISON_URLS_PATH)
        rows = payload.get("poison_urls")
        observed = extract_field_from_list(rows if isinstance(rows, list) else [], "fund_slug")
        run_extra_only_check("poison_urls", observed, "poison_urls_extra_not_in_db")
    else:
        report["checks"]["poison_urls"] = {"missing_file": str(POISON_URLS_PATH)}

    if ASSET_STATUS_AUDIT_PATH.exists():
        payload = load_json(ASSET_STATUS_AUDIT_PATH)
        observed: set[str] = set()
        queue = payload.get("queue")
        if isinstance(queue, list):
            observed |= extract_field_from_list(queue, "fund_slug")
        funds = payload.get("funds")
        if isinstance(funds, dict):
            observed |= extract_string_set(list(funds.keys()))
        run_extra_only_check("asset_status_audit", observed, "asset_status_audit_extra_not_in_db")
    else:
        report["checks"]["asset_status_audit"] = {"missing_file": str(ASSET_STATUS_AUDIT_PATH)}

    if AIFI_REFRESH_QUEUE_PATH.exists():
        payload = load_json(AIFI_REFRESH_QUEUE_PATH)
        rows = payload.get("entries")
        observed = extract_field_from_list(rows if isinstance(rows, list) else [], "fund_slug")
        run_extra_only_check("aifi_refresh_queue", observed, "aifi_refresh_queue_extra_not_in_db")
    else:
        report["checks"]["aifi_refresh_queue"] = {"missing_file": str(AIFI_REFRESH_QUEUE_PATH)}

    # gemini audit/progress
    if audit_path.exists():
        audit = load_json(audit_path)
        funds = audit.get("funds") if isinstance(audit.get("funds"), list) else []
        observed = {
            f.get("slug")
            for f in funds
            if isinstance(f, dict) and isinstance(f.get("slug"), str) and f.get("slug").strip()
        }
        diff = diff_against_db(db_slug_set, observed)
        report["checks"]["gemini.audit.funds"] = diff
        if diff["extra_not_in_db"]:
            add_failure("gemini_audit_extra_not_in_db")
    else:
        report["checks"]["gemini.audit.funds"] = {"missing_file": str(audit_path)}

    if progress_path.exists():
        progress = load_json(progress_path)
        completed = progress.get("completed_slugs") if isinstance(progress.get("completed_slugs"), list) else []
        failed = progress.get("failed") if isinstance(progress.get("failed"), dict) else {}
        completed_set = {s for s in completed if isinstance(s, str) and s.strip()}
        failed_set = {s for s in failed.keys() if isinstance(s, str) and s.strip()}
        completed_diff = diff_against_db(db_slug_set, completed_set)
        failed_diff = diff_against_db(db_slug_set, failed_set)
        report["checks"]["gemini.progress.completed_slugs"] = completed_diff
        report["checks"]["gemini.progress.failed_keys"] = failed_diff
        if completed_diff["extra_not_in_db"]:
            add_failure("gemini_progress_completed_extra_not_in_db")
        if failed_diff["extra_not_in_db"]:
            add_failure("gemini_progress_failed_extra_not_in_db")
    else:
        report["checks"]["gemini.progress"] = {"missing_file": str(progress_path)}

    if zero_italy_path.exists():
        zi = load_json(zero_italy_path)
        verified = zi.get("verified_slugs") if isinstance(zi.get("verified_slugs"), list) else []
        verified_set = {s for s in verified if isinstance(s, str) and s.strip()}
        diff = diff_against_db(db_slug_set, verified_set)
        report["checks"]["gemini.zero_italy_verified"] = diff
        if diff["extra_not_in_db"]:
            add_failure("zero_italy_verified_extra_not_in_db")
    else:
        report["checks"]["gemini.zero_italy_verified"] = {"missing_file": str(zero_italy_path)}

    # dedup jsonl
    if dedup_jsonl_path.exists():
        observed: set[str] = set()
        total_rows = 0
        parse_errors = 0
        with open(dedup_jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                total_rows += 1
                try:
                    row = json.loads(line)
                except Exception:
                    parse_errors += 1
                    continue
                if not isinstance(row, dict):
                    continue
                slug = infer_slug_from_jsonl_row(row)
                if slug:
                    observed.add(slug)
        diff = diff_against_db(db_slug_set, observed)
        report["checks"]["gemini.logs.dedup_jsonl"] = {
            "rows_total": total_rows,
            "rows_parse_errors": parse_errors,
            **diff,
        }
        if diff["extra_not_in_db"]:
            add_failure("gemini_dedup_jsonl_extra_not_in_db")
    else:
        report["checks"]["gemini.logs.dedup_jsonl"] = {"missing_file": str(dedup_jsonl_path)}

    report["status"] = "ok" if not failures else "failed"
    report["failures"] = failures

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
