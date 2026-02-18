#!/usr/bin/env python3
"""
Generate per-fund manual Gemini prompts for uncovered/incomplete funds.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "db.json"
PORTFOLIO_PATH = REPO_ROOT / "data" / "derived" / "portfolio_items.json"
AUDIT_PATH = REPO_ROOT / "data" / "derived" / "gemini_fund_asset_audit.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "derived" / "gemini_fund_asset_logs" / "manual_prompts"

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


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON: {path}")
    return data


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


def sanitize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": entry.get("name"),
        "status": entry.get("status"),
        "sector": entry.get("sector"),
        "headquarters": entry.get("headquarters"),
        "description": (entry.get("description") or "")[:260] or None,
        "website": entry.get("website"),
        "investment_date": entry.get("investment_date"),
        "source_url": entry.get("source_url"),
        "data_source": entry.get("data_source"),
    }


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


def fund_has_italy_signal(fund: dict[str, Any], entries: list[dict[str, Any]]) -> bool:
    hq = str(fund.get("hq_city") or "").lower()
    if hq in ITALIAN_CITY_HINTS or "italy" in hq or "italia" in hq:
        return True

    desc = str(fund.get("description") or "").lower()
    if "italy" in desc or "italian" in desc or "italia" in desc:
        return True

    return any(is_likely_italian_entry(e) for e in entries if isinstance(e, dict))


def build_prompt(
    *,
    fund: dict[str, Any],
    entries: list[dict[str, Any]],
    italian_entries: list[dict[str, Any]],
    reason: str,
) -> str:
    all_entries_json = json.dumps([sanitize_entry(e) for e in entries], ensure_ascii=False, indent=2)
    italian_entries_json = json.dumps([sanitize_entry(e) for e in italian_entries], ensure_ascii=False, indent=2)
    existing_names_json = json.dumps(
        [str(e.get("name")).strip() for e in entries if isinstance(e.get("name"), str) and str(e.get("name")).strip()],
        ensure_ascii=False,
    )

    return f"""You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: {fund.get("name")}
- slug: {fund.get("slug")}
- website: {fund.get("website")}
- aum_eur: {fund.get("aum_eur")}
- category: {fund.get("category")}
- hq_city (current db value): {fund.get("hq_city")}
- description (current db value): {fund.get("description")}
- target_reason: {reason}

Current portfolio entries in our DB (all):
{all_entries_json}

Likely Italy-relevant entries subset (HQ/text hints):
{italian_entries_json}

Existing names list (for duplicate filtering):
{existing_names_json}

Task:
1) Audit ONLY the likely Italy-relevant entries subset for wrong entry/duplicate/status/sector/headquarters/description.
2) Find likely MISSING Italian assets (current or exited) not already in existing names.
3) Suggest fund metadata corrections only if likely wrong (hq_city, description, website).
4) If you find no credible Italian asset exposure for this fund, set `confirmed_no_italian_assets=true`.

Rules:
- Be conservative when uncertain and lower confidence.
- Use high confidence only with credible evidence.
- Return ONLY strict JSON object (no markdown).

JSON schema:
{{
  "entry_issues": [
    {{
      "entry_name": "string",
      "issue_type": "wrong_entry|duplicate_entry|wrong_status|wrong_sector|wrong_headquarters|wrong_description|other",
      "severity": "critical|high|medium|low",
      "reason": "short reason",
      "current_value": {{"status": "...", "sector": "...", "headquarters": "...", "description": "..."}},
      "suggested_fix": {{"status": "current|exited|partial|unknown|null", "sector": "string|null", "headquarters": "string|null", "description": "string|null"}},
      "confidence": "high|medium|low",
      "evidence_urls": ["https://..."]
    }}
  ],
  "missing_assets": [
    {{
      "name": "string",
      "status": "current|exited|unknown",
      "sector": "string|null",
      "headquarters": "string|null",
      "description": "string|null",
      "reason": "why this is likely missing",
      "confidence": "high|medium|low",
      "evidence_urls": ["https://..."]
    }}
  ],
  "fund_metadata_corrections": {{
    "hq_city": {{"current": "string|null", "suggested": "string|null", "reason": "string", "confidence": "high|medium|low", "evidence_urls": ["https://..."]}},
    "description": {{"current": "string|null", "suggested": "string|null", "reason": "string", "confidence": "high|medium|low", "evidence_urls": ["https://..."]}},
    "website": {{"current": "string|null", "suggested": "string|null", "reason": "string", "confidence": "high|medium|low", "evidence_urls": ["https://..."]}}
  }},
  "confirmed_no_italian_assets": false,
  "notes": "optional short note"
}}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate per-fund manual Gemini prompts.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR.relative_to(REPO_ROOT)),
        help="Output directory for prompt files",
    )
    parser.add_argument(
        "--slugs",
        type=str,
        help="Comma-separated explicit slugs (overrides auto selection)",
    )
    parser.add_argument(
        "--include-incomplete",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include slugs that are in audit output but completion_ready=false",
    )
    parser.add_argument(
        "--include-uncovered-db",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include DB slugs not present in audit output",
    )
    parser.add_argument(
        "--italy-focus",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only generate prompts for funds with Italy signals (HQ/description/entries)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional limit")
    args = parser.parse_args()

    out_dir = resolve_repo_relative_path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    db = load_json(DB_PATH)
    portfolio = load_json(PORTFOLIO_PATH)
    audit = load_json(AUDIT_PATH)

    db_funds = [f for f in db.get("funds", []) if isinstance(f, dict) and isinstance(f.get("slug"), str)]
    db_funds = sort_funds_by_aum_desc(db_funds)
    db_by_slug = {f["slug"]: f for f in db_funds}
    fund_portfolios = portfolio.get("fund_portfolios") or {}
    audit_by_slug = {
        f.get("slug"): f
        for f in (audit.get("funds") or [])
        if isinstance(f, dict) and isinstance(f.get("slug"), str)
    }

    targets: list[tuple[str, str]] = []
    if args.slugs:
        for raw in args.slugs.split(","):
            slug = raw.strip()
            if slug:
                targets.append((slug, "explicit"))
    else:
        if args.include_incomplete:
            for slug, result in audit_by_slug.items():
                if result.get("completion_ready") is False:
                    targets.append((slug, "incomplete"))
        if args.include_uncovered_db:
            for fund in db_funds:
                slug = fund["slug"]
                if slug not in audit_by_slug:
                    targets.append((slug, "uncovered_db"))

    # De-duplicate while preserving first reason.
    dedup_targets: dict[str, str] = {}
    for slug, reason in targets:
        if slug not in dedup_targets:
            dedup_targets[slug] = reason

    ordered_targets = [slug for slug in [f["slug"] for f in db_funds] if slug in dedup_targets]
    if args.limit > 0:
        ordered_targets = ordered_targets[:args.limit]

    generated: list[str] = []
    skipped: list[str] = []
    for slug in ordered_targets:
        fund = db_by_slug.get(slug)
        if not fund:
            skipped.append(slug)
            continue
        entries = fund_portfolios.get(slug, [])
        if not isinstance(entries, list):
            entries = []
        if args.italy_focus and not fund_has_italy_signal(fund, [e for e in entries if isinstance(e, dict)]):
            skipped.append(slug)
            continue
        italian_entries = [e for e in entries if isinstance(e, dict) and is_likely_italian_entry(e)]
        prompt = build_prompt(
            fund=fund,
            entries=[e for e in entries if isinstance(e, dict)],
            italian_entries=italian_entries,
            reason=dedup_targets.get(slug, "unknown"),
        )
        output_path = out_dir / f"{slug}.md"
        output_path.write_text(prompt, encoding="utf-8")
        generated.append(slug)

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_count": len(ordered_targets),
        "generated_count": len(generated),
        "skipped_count": len(skipped),
        "generated_slugs": generated,
        "skipped_slugs": skipped,
        "output_dir": str(out_dir),
        "instructions": [
            "Open each .md file and paste into Gemini.",
            "Save Gemini JSON reply as data/derived/gemini_fund_asset_logs/manual_responses/<slug>.json",
            "Run scripts/import-manual-gemini-fund-responses.py, then rerun recovery script.",
        ],
    }
    (out_dir / "INDEX.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Generated prompts: {len(generated)}")
    if generated:
        print("Slugs:", ", ".join(generated))
    print(f"Output dir: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
