#!/usr/bin/env python3
"""
PEM Status Audit Queue

Builds a queue of PEM deals that do not have verified status.
Output: data/derived/pem_status_audit.json

Usage:
    python3 scripts/audit-pem-status.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
DERIVED = DATA / "derived"

PORTFOLIO_PATH = DERIVED / "portfolio_items.json"
PEM_DEALS_PATH = DERIVED / "pem_deals.json"
ALIASES_PATH = DERIVED / "fund_aliases.json"
DB_PATH = DATA / "db.json"
OVERRIDES_PATH = DERIVED / "pem_status_overrides.json"
OUTPUT_PATH = DERIVED / "pem_status_audit.json"

PEM_BASE_URL = "https://www.liucbs.it/osservatori/private-equity-monitor-pem/"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_name(name: str) -> str:
    import re
    s = name.lower().strip()
    s = re.sub(r"\s*\(.*?\)", "", s)
    s = re.sub(r"\b(s\.?p\.?a\.?|s\.?r\.?l\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?s\.?)\b", "", s)
    s = re.sub(r"\s+(group|technologies)\s*$", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def names_match(a: str, b: str) -> bool:
    na = normalize_name(a)
    nb = normalize_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na.replace(" ", "") == nb.replace(" ", ""):
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


def build_fund_lookup(db: dict) -> dict:
    funds = {}
    for f in db.get("funds", []):
        slug = f.get("slug")
        if slug:
            funds[slug] = {
                "name": f.get("name", slug),
                "website": f.get("website"),
            }
    return funds


def suggested_status(deal: dict) -> str:
    orig = (deal.get("deal_origination") or "").lower()
    if any(k in orig for k in ["exit", "ipo", "trade sale"]):
        return "exited"
    year = deal.get("source_year") or 0
    current_year = datetime.now(timezone.utc).year
    if year and current_year - year >= 7:
        return "exited"
    return "unknown"


def main() -> int:
    portfolio = load_json(PORTFOLIO_PATH)
    pem_deals = load_json(PEM_DEALS_PATH).get("deals", [])
    aliases = load_json(ALIASES_PATH)
    db = load_json(DB_PATH)
    overrides = load_json(OVERRIDES_PATH).get("overrides", {})

    fund_lookup = build_fund_lookup(db)
    alias_map = aliases.get("aliases", {})

    fund_portfolios = portfolio.get("fund_portfolios", {})

    entries = []
    for deal in pem_deals:
        lead_slug = deal.get("lead_investor_slug", "")
        canonical = alias_map.get(lead_slug, lead_slug)
        if canonical not in fund_lookup:
            continue

        fund_name = fund_lookup[canonical]["name"]
        portfolio_entries = fund_portfolios.get(canonical, [])

        matched = False
        for item in portfolio_entries:
            if names_match(item.get("name", ""), deal.get("target_company", "")):
                matched = True
                break

        deal_id = deal.get("id")
        normalized = normalize_name(deal.get("target_company", ""))
        override = overrides.get(canonical, {}).get(deal_id) or overrides.get(canonical, {}).get(normalized)

        if matched or override:
            continue

        entries.append({
            "fund_slug": canonical,
            "fund_name": fund_name,
            "pem_deal_id": deal_id,
            "target_company": deal.get("target_company"),
            "source_year": deal.get("source_year"),
            "deal_origination": deal.get("deal_origination"),
            "suggested_status": suggested_status(deal),
            "source_url": PEM_BASE_URL,
            "matched_website": matched,
            "override_status": None,
        })

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fund_count": len({e["fund_slug"] for e in entries}),
        "entry_count": len(entries),
        "entries": entries,
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
