#!/usr/bin/env python3
"""
Apply Asset Status Updates

Reads asset_status_evidence.json and applies high-confidence status updates.
Updates:
  - data/derived/pem_status_overrides.json for PEM-only assets
  - data/derived/portfolio_items.json for website assets

Usage:
  python3 scripts/apply-asset-status.py --apply
  python3 scripts/apply-asset-status.py --min-confidence high --apply
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
DERIVED = DATA / "derived"

EVIDENCE_PATH = DERIVED / "asset_status_evidence.json"
PORTFOLIO_PATH = DERIVED / "portfolio_items.json"
OVERRIDES_PATH = DERIVED / "pem_status_overrides.json"


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


CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def best_evidence(evs: list, min_conf: str):
    threshold = CONF_ORDER[min_conf]
    best = None
    for ev in evs:
        conf = ev.get("confidence", "low")
        if CONF_ORDER.get(conf, 0) < threshold:
            continue
        status = ev.get("status")
        if status not in ("current", "exited", "unknown"):
            continue
        if not best or CONF_ORDER.get(conf, 0) > CONF_ORDER.get(best.get("confidence", "low"), 0):
            best = ev
    return best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", default=str(EVIDENCE_PATH))
    parser.add_argument("--min-confidence", default="high", choices=["low", "medium", "high"])
    parser.add_argument("--apply", action="store_true", help="Write changes to files")
    args = parser.parse_args()

    evidence = load_json(Path(args.evidence))
    portfolio = load_json(PORTFOLIO_PATH)
    overrides = load_json(OVERRIDES_PATH) or {"generated_at": "", "overrides": {}}

    fund_portfolios = portfolio.get("fund_portfolios", {})
    override_map = overrides.get("overrides", {})

    changes = {
        "portfolio_updates": 0,
        "override_updates": 0,
        "skipped": 0,
    }

    for item in evidence.get("items", []):
        fund_slug = item["fund_slug"]
        company_name = item["company_name"]
        normalized = item.get("normalized_name") or normalize_name(company_name)
        sources = item.get("sources", [])

        ev = best_evidence(item.get("evidence", []), args.min_confidence)
        if not ev:
            changes["skipped"] += 1
            continue

        status = ev["status"]
        if status == "unknown":
            status = None
        source_url = ev.get("source_url")
        source_label = ev.get("source_label")
        evidence_type = ev.get("evidence_type")

        # PEM-only assets -> overrides
        if sources == ["pem"]:
            if status is None:
                changes["skipped"] += 1
                continue
            override_map.setdefault(fund_slug, {})
            for did in item.get("pem_deal_ids", []) or []:
                override_map[fund_slug][did] = {
                    "status": status,
                    "source_url": source_url,
                    "source_label": source_label,
                    "verified_at": now_iso(),
                    "confidence": ev.get("confidence"),
                    "evidence_type": evidence_type,
                }
                changes["override_updates"] += 1
            # also store by normalized name for safety
            override_map[fund_slug][normalized] = {
                "status": status,
                "source_url": source_url,
                "source_label": source_label,
                "verified_at": now_iso(),
                "confidence": ev.get("confidence"),
                "evidence_type": evidence_type,
            }
            changes["override_updates"] += 1
            continue

        # Website assets -> update portfolio_items.json
        if "website" in sources:
            entries = fund_portfolios.get(fund_slug, [])
            for entry in entries:
                if normalize_name(entry.get("name", "")) == normalized:
                    if entry.get("status") != status:
                        entry["status"] = status
                        changes["portfolio_updates"] += 1
                    break
            continue

        # Signal-only assets: do not auto-apply
        changes["skipped"] += 1

    if args.apply:
        overrides["generated_at"] = now_iso()
        overrides["overrides"] = override_map
        OVERRIDES_PATH.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
        PORTFOLIO_PATH.write_text(json.dumps(portfolio, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(changes, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
