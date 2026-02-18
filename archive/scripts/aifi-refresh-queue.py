#!/usr/bin/env python3
"""
AIFI Refresh Queue

Builds a queue of funds missing key AIFI fields.
Output: data/derived/aifi_refresh_queue.json

Usage:
    python3 scripts/aifi-refresh-queue.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
DERIVED = DATA / "derived"

DB_PATH = DATA / "db.json"
OUTPUT_PATH = DERIVED / "aifi_refresh_queue.json"

AIFI_FIELDS = [
    "aum_eur",
    "num_funds",
    "num_portfolio_companies",
    "num_executives",
    "investment_min_eur",
    "investment_max_eur",
]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    db = load_json(DB_PATH)

    funds = []
    for f in db.get("funds", []):
        funds.append({
            "slug": f.get("slug"),
            "name": f.get("name"),
            "website": f.get("website"),
            "aifi_url": f.get("aifi_url"),
            "fields": f,
        })

    entries = []
    for f in funds:
        missing = [field for field in AIFI_FIELDS if f["fields"].get(field) in (None, "", [])]
        if missing:
            entries.append({
                "fund_slug": f["slug"],
                "fund_name": f["name"],
                "website": f["website"],
                "aifi_url": f["aifi_url"],
                "missing_fields": missing,
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
