#!/usr/bin/env python3
"""
Collect Asset Evidence

Builds evidence records for assets in asset_status_audit.json.
Optionally fetches fund portfolio pages and checks for company name matches.
Optionally uses OpenAI to classify evidence text (internal only).

Usage:
  python3 scripts/collect-asset-evidence.py --fetch-portfolio
  python3 scripts/collect-asset-evidence.py --fund wise-equity-sgr --fetch-portfolio
"""

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
DERIVED = DATA / "derived"

AUDIT_PATH = DERIVED / "asset_status_audit.json"
OUTPUT_PATH = DERIVED / "asset_status_evidence.json"


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


def normalize_blob(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fetch_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "FundradarBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        text = data.decode(errors="ignore")
    # Strip basic HTML tags for matching
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def openai_classify_evidence(evidence_text: str):
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    if not api_key:
        return None
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Classify whether the evidence implies current ownership, exited ownership, or unknown. Return JSON."},
            {"role": "user", "content": evidence_text},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    content = data["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(AUDIT_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--fund", help="Limit to a specific fund slug")
    parser.add_argument("--limit", type=int, help="Limit number of queue items")
    parser.add_argument("--fetch-portfolio", action="store_true", help="Fetch portfolio pages and match company names")
    parser.add_argument("--manual-evidence", help="JSON file with manual evidence entries")
    parser.add_argument("--use-portfolio-data", action="store_true", help="Use portfolio_items.json as evidence for website assets")
    parser.add_argument("--openai", action="store_true", help="Use OpenAI to classify evidence text")
    args = parser.parse_args()

    audit = load_json(Path(args.input))
    queue = audit.get("queue", [])
    if args.fund:
        queue = [q for q in queue if q.get("fund_slug") == args.fund]
    if args.limit:
        queue = queue[: args.limit]

    manual = load_json(Path(args.manual_evidence)) if args.manual_evidence else {}

    evidence = {
        "generated_at": now_iso(),
        "count": 0,
        "items": [],
    }

    # Pre-fetch portfolio pages once per fund when enabled
    portfolio_cache = {}
    if args.fetch_portfolio:
        fund_to_url = {}
        for q in queue:
            if q.get("portfolio_source_url"):
                fund_to_url[q["fund_slug"]] = q["portfolio_source_url"]
        for fund_slug, url in fund_to_url.items():
            try:
                portfolio_cache[fund_slug] = normalize_blob(fetch_text(url))
            except Exception:
                portfolio_cache[fund_slug] = ""

    for item in queue:
        fund_slug = item["fund_slug"]
        company_name = item["company_name"]
        normalized = normalize_name(company_name)
        ev_list = []

        # Portfolio page match
        if args.fetch_portfolio and item.get("portfolio_source_url"):
            blob = portfolio_cache.get(fund_slug, "")
            if normalized and blob and normalize_blob(normalized) in blob:
                ev_list.append({
                    "source_url": item["portfolio_source_url"],
                    "source_label": "Fund Website",
                    "evidence_type": "portfolio",
                    "status": "current",
                    "confidence": "high",
                    "evidence_text": None,
                })

        # Use portfolio data as evidence (website assets)
        if args.use_portfolio_data and "website" in (item.get("sources") or []):
            ev_list.append({
                "source_url": item.get("portfolio_source_url"),
                "source_label": "Fund Website (scraped)",
                "evidence_type": "portfolio",
                "status": "current",
                "confidence": "high",
                "evidence_text": None,
            })

        # Manual evidence
        manual_entries = (manual.get(fund_slug) or {}).get(company_name) or []
        for m in manual_entries:
            ev = {
                "source_url": m.get("source_url"),
                "source_label": m.get("source_label"),
                "evidence_type": m.get("evidence_type", "manual"),
                "status": m.get("status"),
                "confidence": m.get("confidence", "medium"),
                "evidence_text": m.get("evidence_text"),
            }
            if args.openai and ev.get("evidence_text"):
                classified = openai_classify_evidence(ev["evidence_text"])
                if classified:
                    ev["status"] = classified.get("status", ev["status"])
                    ev["confidence"] = classified.get("confidence", ev["confidence"])
            ev_list.append(ev)

        # Auto invalidate PEM overrides that lack sources
        if "pem_override_missing_source" in (item.get("reasons") or []):
            ev_list.append({
                "source_url": None,
                "source_label": "System",
                "evidence_type": "override_missing_source",
                "status": "unknown",
                "confidence": "high",
                "evidence_text": None,
            })

        if ev_list:
            evidence["items"].append({
                "fund_slug": fund_slug,
                "company_name": company_name,
                "normalized_name": normalized,
                "sources": item.get("sources"),
                "pem_deal_ids": item.get("pem_deal_ids"),
                "signal_ids": item.get("signal_ids"),
                "evidence": ev_list,
            })

    evidence["count"] = len(evidence["items"])
    Path(args.output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.output} ({evidence['count']} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
