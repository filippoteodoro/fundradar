#!/usr/bin/env python3
"""
Asset Status Audit

Builds a canonical asset index per fund from website portfolio, PEM deals, and signals.
Outputs a queue of assets needing evidence to resolve status mistakes.

Usage:
  python3 scripts/audit-asset-status.py
  python3 scripts/audit-asset-status.py --fund wise-equity-sgr
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
DERIVED = DATA / "derived"

PORTFOLIO_PATH = DERIVED / "portfolio_items.json"
PEM_DEALS_PATH = DERIVED / "pem_deals.json"
SIGNALS_PATH = DERIVED / "detected_signals_filtered.json"
ALIASES_PATH = DERIVED / "fund_aliases.json"
OVERRIDES_PATH = DERIVED / "pem_status_overrides.json"

OUTPUT_PATH = DERIVED / "asset_status_audit.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_name(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"\s*\(.*?\)", "", s)
    s = re.sub(r"\b(s\.?p\.?a\.?|s\.?r\.?l\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?s\.?)\b", "", s)
    s = re.sub(r"\s+(group|technologies)\s*$", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def compact_name(name: str) -> str:
    return name.replace(" ", "")


def names_match(a: str, b: str) -> bool:
    na = normalize_name(a)
    nb = normalize_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if compact_name(na) == compact_name(nb):
        return True
    na_ng = na.replace("group", "").strip()
    nb_ng = nb.replace("group", "").strip()
    if na_ng and nb_ng and na_ng == nb_ng:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 5 and shorter in longer:
        idx = longer.index(shorter)
        end = idx + len(shorter)
        start_ok = idx == 0 or longer[idx - 1] == " "
        end_ok = end == len(longer) or longer[end] == " "
        if start_ok and end_ok:
            return True
    return False


def load_pem_index(pem_deals: list, aliases: dict) -> dict:
    alias_map = aliases.get("aliases", {})
    index = {}
    for deal in pem_deals:
        lead_slug = deal.get("lead_investor_slug") or ""
        canonical = alias_map.get(lead_slug, lead_slug)
        if canonical:
            index.setdefault(canonical, []).append(deal)
    return index


def build_asset_index(fund_slug: str, portfolio_items: list, pem_deals: list, signals: list, overrides: dict) -> dict:
    assets = []

    # Website portfolio assets
    for item in portfolio_items:
        name = item.get("name") or ""
        assets.append({
            "fund_slug": fund_slug,
            "company_name": name,
            "normalized_name": normalize_name(name),
            "sources": ["website"],
            "website_status": item.get("status"),
            "pem_deal_ids": [],
            "signal_ids": [],
        })

    # PEM deals (merge into website asset if matched)
    for deal in pem_deals:
        target = deal.get("target_company") or ""
        matched = False
        for asset in assets:
            if names_match(asset["company_name"], target):
                asset["sources"].append("pem")
                asset["pem_deal_ids"].append(deal.get("id"))
                matched = True
                break
        if not matched:
            assets.append({
                "fund_slug": fund_slug,
                "company_name": target,
                "normalized_name": normalize_name(target),
                "sources": ["pem"],
                "website_status": None,
                "pem_deal_ids": [deal.get("id")],
                "signal_ids": [],
            })

    # Signals (deal/exits only)
    for s in signals:
        if s.get("signal_type") not in ("deal_announced", "exit_announced"):
            continue
        title = s.get("title") or ""
        if not title:
            continue
        matched = False
        for asset in assets:
            if names_match(asset["company_name"], title):
                asset["sources"].append("signal")
                asset["signal_ids"].append(s.get("id"))
                matched = True
                break
        if not matched:
            assets.append({
                "fund_slug": fund_slug,
                "company_name": title,
                "normalized_name": normalize_name(title),
                "sources": ["signal"],
                "website_status": None,
                "pem_deal_ids": [],
                "signal_ids": [s.get("id")],
            })

    # Deduplicate sources
    for asset in assets:
        asset["sources"] = sorted(set(asset["sources"]))

        # UI status approximation (mirrors data.ts behavior)
        if "website" in asset["sources"]:
            asset["ui_status"] = asset["website_status"] or "current"
        elif "pem" in asset["sources"]:
            pem_override = overrides.get(fund_slug, {})
            override = None
            for did in asset["pem_deal_ids"]:
                if did and did in pem_override:
                    override = pem_override[did]
                    break
            if not override:
                override = pem_override.get(asset["normalized_name"])
            asset["ui_status"] = override.get("status") if override else None
        elif "signal" in asset["sources"]:
            asset["ui_status"] = "current"
        else:
            asset["ui_status"] = None

    return assets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fund", help="Limit to a specific fund slug")
    args = parser.parse_args()

    portfolio = load_json(PORTFOLIO_PATH)
    pem = load_json(PEM_DEALS_PATH).get("deals", [])
    signals = load_json(SIGNALS_PATH).get("signals", [])
    aliases = load_json(ALIASES_PATH)
    overrides = load_json(OVERRIDES_PATH).get("overrides", {})
    # Portfolio source URLs are now stored in portfolio_items.json
    portfolio_urls = portfolio_file.get("fund_source_urls", {})

    pem_index = load_pem_index(pem, aliases)
    signal_index = {}
    for s in signals:
        slug = s.get("fund_slug")
        if not slug:
            continue
        signal_index.setdefault(slug, []).append(s)

    fund_portfolios = portfolio.get("fund_portfolios", {})
    all_funds = set(fund_portfolios.keys()) | set(pem_index.keys()) | set(signal_index.keys())

    if args.fund:
        all_funds = {args.fund} if args.fund in all_funds else set()

    audit = {
        "generated_at": now_iso(),
        "fund_count": 0,
        "asset_count": 0,
        "queue": [],
        "funds": {},
    }

    for fund_slug in sorted(all_funds):
        assets = build_asset_index(
            fund_slug,
            fund_portfolios.get(fund_slug, []),
            pem_index.get(fund_slug, []),
            signal_index.get(fund_slug, []),
            overrides,
        )

        issues = []
        queue = []
        for asset in assets:
            reasons = []
            sources = asset["sources"]

            if sources == ["pem"] and asset["ui_status"] is None:
                reasons.append("pem_only_no_override")
            if sources == ["signal"]:
                reasons.append("signal_only")
            if "website" in sources and asset["website_status"] is None:
                reasons.append("website_status_null")
            if sources == ["pem"] and asset["ui_status"] == "exited":
                # require explicit evidence (source_url) to keep exited
                pem_override = overrides.get(fund_slug, {})
                override = None
                for did in asset["pem_deal_ids"]:
                    if did and did in pem_override:
                        override = pem_override[did]
                        break
                if override and not override.get("source_url"):
                    reasons.append("pem_override_missing_source")

            if reasons:
                # Get portfolio source URL from portfolio_items.json
                portfolio_url = portfolio_urls.get(fund_slug)

                queue.append({
                    "fund_slug": fund_slug,
                    "company_name": asset["company_name"],
                    "normalized_name": asset["normalized_name"],
                    "sources": sources,
                    "pem_deal_ids": asset["pem_deal_ids"],
                    "signal_ids": asset["signal_ids"],
                    "ui_status": asset.get("ui_status"),
                    "reasons": reasons,
                    "portfolio_source_url": portfolio_url,
                })

        audit["funds"][fund_slug] = {
            "asset_count": len(assets),
            "queue_count": len(queue),
            "queue": queue,
        }
        audit["queue"].extend(queue)
        audit["fund_count"] += 1
        audit["asset_count"] += len(assets)

    OUTPUT_PATH.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(audit['queue'])} queued)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
