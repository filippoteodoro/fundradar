#!/usr/bin/env python3
"""Hard-gate verifier for newly added funds.

Checks:
- db fields (AUM + required metadata)
- portfolio presence + enrichment coverage
- Gemini asset audit completion
- filtered/enriched signal ID parity
- top-AUM minimum signal completeness
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gemini_audit_completion import load_verified_zero_italy_slugs

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"

DB_PATH = ROOT / "data" / "db.json"
PORTFOLIO_PATH = DERIVED / "portfolio_items.json"
FILTERED_PATH = DERIVED / "detected_signals_filtered.json"
ENRICHED_PATH = DERIVED / "detected_signals_enriched.json"
ASSET_AUDIT_PATH = DERIVED / "gemini_fund_asset_audit.json"
ZERO_ITALY_VERIFIED_PATH = DERIVED / "gemini_fund_asset_zero_italy_verified.json"
REPORT_PATH = DERIVED / "new_fund_completion_report.json"


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_repo_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return ROOT / path


def _parse_slugs(raw: str | None) -> list[str]:
    if not raw:
        return []
    return sorted({s.strip() for s in raw.split(",") if s.strip()})


def _auto_detect_new_slugs(funds: list[dict[str, Any]]) -> list[str]:
    """Detect newly-added slugs by created_at outlier vs baseline bulk."""
    created = [str(f.get("created_at") or "") for f in funds]
    if not created:
        return []
    mode_value, _ = Counter(created).most_common(1)[0]
    return sorted(
        str(f.get("slug"))
        for f in funds
        if f.get("slug") and str(f.get("created_at") or "") != mode_value
    )


def _is_complete_portfolio_entry(row: dict[str, Any]) -> bool:
    has_sector = bool(row.get("sector"))
    has_desc = bool(row.get("description"))
    has_hq = bool(row.get("headquarters") or row.get("hq_country"))
    return has_sector and has_desc and has_hq


def _signal_ids(rows: list[dict[str, Any]], slug: str) -> set[str]:
    return {str(r.get("id")) for r in rows if r.get("fund_slug") == slug and r.get("id")}


def _as_non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return 0
        try:
            if "." in raw:
                return max(int(float(raw)), 0)
            return max(int(raw), 0)
        except ValueError:
            return 0
    return 0


def _top_aum_italy_assets_blocker(
    *,
    slug: str,
    top_slugs: set[str],
    audit_entry: dict[str, Any] | None,
    verified_zero_italy_slugs: set[str],
) -> str | None:
    if slug not in top_slugs or not audit_entry:
        return None
    italian_portfolio_count = _as_non_negative_int(audit_entry.get("italian_portfolio_count"))
    if italian_portfolio_count == 0 and slug not in verified_zero_italy_slugs:
        return "top_aum_no_italy_assets_unverified"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify hard-gate completion for newly added funds")
    parser.add_argument("--slugs", type=str, default="", help="Comma-separated fund slugs; default auto-detect")
    parser.add_argument("--top-n", type=int, default=25, help="Top AUM set for minimum-signal completeness")
    parser.add_argument("--min-signals", type=int, default=2, help="Minimum filtered signals for top-AUM funds")
    parser.add_argument("--output", type=str, default=str(REPORT_PATH), help="JSON report output path")
    parser.add_argument(
        "--zero-italy-verified-path",
        type=str,
        default=str(ZERO_ITALY_VERIFIED_PATH.relative_to(ROOT)),
        help="Verified whitelist for funds with no Italian assets",
    )
    parser.add_argument(
        "--require-top-aum-italy-assets",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "For top-AUM funds, require italian_portfolio_count>0 in Gemini asset audit, "
            "or a whitelist entry in --zero-italy-verified-path"
        ),
    )
    parser.add_argument(
        "--established-slugs",
        type=str,
        default="",
        help=(
            "Comma-separated slugs for funds already in db.json before this change set. "
            "Skips data-completeness checks (portfolio enrichment, signal completeness, "
            "signal parity, top-AUM Italy assets) that are only required for newly added funds."
        ),
    )
    args = parser.parse_args()

    db = _load_json(DB_PATH)
    portfolio = _load_json(PORTFOLIO_PATH).get("fund_portfolios", {})
    filtered_rows = _load_json(FILTERED_PATH).get("signals", [])
    enriched_rows = _load_json(ENRICHED_PATH).get("signals", [])
    asset_audit = _load_json(ASSET_AUDIT_PATH).get("funds", [])
    verified_zero_italy_slugs = load_verified_zero_italy_slugs(
        _resolve_repo_path(args.zero_italy_verified_path)
    )

    funds: list[dict[str, Any]] = db.get("funds", [])
    funds_by_slug = {str(f.get("slug")): f for f in funds if f.get("slug")}
    selected_slugs = _parse_slugs(args.slugs) or _auto_detect_new_slugs(funds)

    ranked = sorted(
        [f for f in funds if isinstance(f.get("aum_eur"), (int, float)) and float(f.get("aum_eur")) > 0],
        key=lambda x: float(x.get("aum_eur") or 0),
        reverse=True,
    )
    top_slugs = {str(f.get("slug")) for f in ranked[: max(args.top_n, 0)] if f.get("slug")}

    audit_by_slug = {str(f.get("slug")): f for f in asset_audit if isinstance(f, dict) and f.get("slug")}
    established_slugs = _parse_slugs(args.established_slugs)
    now_iso = datetime.now(timezone.utc).isoformat()

    fund_reports: list[dict[str, Any]] = []
    for slug in selected_slugs:
        fund = funds_by_slug.get(slug)
        blockers: list[str] = []
        warnings: list[str] = []
        # Established funds (already in db before this change set) skip data-completeness
        # checks that are only meaningful for newly added funds. Core metadata and audit
        # checks still apply to all funds.
        is_established = slug in established_slugs

        if not fund:
            blockers.append("missing_in_db")
            fund_reports.append(
                {"slug": slug, "status": "failed", "blockers": blockers, "warnings": warnings}
            )
            continue

        aum = fund.get("aum_eur")
        if not isinstance(aum, (int, float)) or float(aum) <= 0:
            blockers.append("missing_aum_eur")
        if not fund.get("description"):
            blockers.append("missing_fund_description")
        if not fund.get("geographies"):
            blockers.append("missing_geographies")
        if not fund.get("strategy_tags"):
            blockers.append("missing_strategy_tags")

        companies = list(portfolio.get(slug, []) or [])
        if len(companies) == 0:
            blockers.append("portfolio_empty")
            completion_ratio = 0.0
        else:
            complete = sum(1 for c in companies if _is_complete_portfolio_entry(c))
            completion_ratio = complete / len(companies)
            if not is_established and completion_ratio < 1.0:
                blockers.append(f"portfolio_enrichment_incomplete:{complete}/{len(companies)}")

        audit_entry = audit_by_slug.get(slug)
        italian_portfolio_count = 0
        if not audit_entry:
            blockers.append("gemini_asset_audit_missing")
        else:
            if str(audit_entry.get("status") or "").lower() != "ok":
                blockers.append(f"gemini_asset_audit_status:{audit_entry.get('status')}")
            if not bool(audit_entry.get("completion_ready")):
                blockers.append("gemini_asset_audit_not_completion_ready")
            italian_portfolio_count = _as_non_negative_int(audit_entry.get("italian_portfolio_count"))

            if not is_established and args.require_top_aum_italy_assets and slug in top_slugs:
                italy_blocker = _top_aum_italy_assets_blocker(
                    slug=slug,
                    top_slugs=top_slugs,
                    audit_entry=audit_entry,
                    verified_zero_italy_slugs=verified_zero_italy_slugs,
                )
                if italy_blocker:
                    blockers.append(italy_blocker)

        f_ids = _signal_ids(filtered_rows, slug)
        e_ids = _signal_ids(enriched_rows, slug)
        missing_in_enriched = sorted(f_ids - e_ids)
        stale_in_enriched = sorted(e_ids - f_ids)
        if not is_established and missing_in_enriched:
            blockers.append(f"signal_parity_missing_in_enriched:{len(missing_in_enriched)}")
        if not is_established and stale_in_enriched:
            blockers.append(f"signal_parity_stale_in_enriched:{len(stale_in_enriched)}")

        filtered_count = len(f_ids)
        if not is_established and slug in top_slugs and filtered_count < args.min_signals:
            blockers.append(f"top_aum_signal_completeness:{filtered_count}/{args.min_signals}")

        status = "passed" if not blockers else "failed"
        fund_reports.append(
            {
                "slug": slug,
                "name": fund.get("name"),
                "status": status,
                "blockers": blockers,
                "warnings": warnings,
                "checks": {
                    "filtered_count": filtered_count,
                    "enriched_count": len(e_ids),
                    "portfolio_count": len(companies),
                    "portfolio_complete_ratio": round(completion_ratio, 4),
                    "top_aum_target": slug in top_slugs,
                    "asset_audit_present": bool(audit_entry),
                    "italian_portfolio_count": italian_portfolio_count,
                    "zero_italy_verified": slug in verified_zero_italy_slugs,
                },
            }
        )

    failed = [r for r in fund_reports if r.get("status") == "failed"]
    report = {
        "generated_at": now_iso,
        "selected_slugs": selected_slugs,
        "summary": {
            "funds_checked": len(fund_reports),
            "failed": len(failed),
            "passed": len(fund_reports) - len(failed),
            "top_n": args.top_n,
            "min_signals": args.min_signals,
            "require_top_aum_italy_assets": args.require_top_aum_italy_assets,
        },
        "funds": fund_reports,
    }

    out_path = _resolve_repo_path(args.output)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("New Fund Completion Verification")
    print("=" * 44)
    print(f"Checked: {len(fund_reports)}")
    print(f"Passed:  {len(fund_reports) - len(failed)}")
    print(f"Failed:  {len(failed)}")
    print(f"Report:  {out_path}")
    if failed:
        for row in failed:
            print(f"  - {row['slug']}: {', '.join(row['blockers'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
