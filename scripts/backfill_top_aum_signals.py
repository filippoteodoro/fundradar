#!/usr/bin/env python3
"""Backfill top-AUM fund signals with vetted historical Italy-relevant entries.

Adds manual historical signals to BOTH:
- data/derived/detected_signals_filtered.json
- data/derived/detected_signals_enriched.json

The script is parity-safe (same IDs in both files) and deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"
DB_PATH = ROOT / "data" / "db.json"
FILTERED_PATH = DERIVED / "detected_signals_filtered.json"
ENRICHED_PATH = DERIVED / "detected_signals_enriched.json"
DEFAULT_CANDIDATES_PATH = DERIVED / "top_aum_historical_signal_backfill.json"

_ITALY_TERMS = (
    "italy",
    "italian",
    "italia",
    "milan",
    "milano",
    "rome",
    "roma",
    "turin",
    "torino",
    "naples",
    "napoli",
    "bologna",
    "venice",
    "venezia",
    "pesaro",
)

_CORE_TYPES = {
    "deal_announced",
    "portfolio_update",
    "exit_announced",
    "fundraise_announced",
    "fundraise_closed",
    "debt_financing",
    "people_move",
    "partnership",
}


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _slug_scope(fund: dict[str, Any] | None) -> str:
    if not fund:
        return "unknown"
    geos = [str(g).lower().strip() for g in (fund.get("geographies") or []) if g]
    if not geos:
        return "unknown"
    non_eu = {"worldwide", "north america", "south america", "usa", "canada", "asia", "asia pacific", "asia-pacific"}
    if any(g in non_eu for g in geos):
        return "mixed_or_global"
    if "italy" in geos:
        return "italy_focused"
    return "europe_wide"


def _has_italy_evidence(candidate: dict[str, Any]) -> bool:
    text = " ".join(
        str(candidate.get(k) or "")
        for k in ("title", "what_changed", "relevance_basis")
    ).lower()
    return any(term in text for term in _ITALY_TERMS)


def _iso_date(date_text: str | None) -> str | None:
    if not date_text:
        return None
    raw = str(date_text).strip()
    if not raw:
        return None
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    return None


def _signal_id(slug: str, date_iso: str, title: str) -> str:
    digest = hashlib.blake2s(f"{slug}|{date_iso}|{title}".encode("utf-8"), digest_size=6).hexdigest()
    return f"manual-backfill-{slug}-{date_iso.replace('-', '')}-{digest}"


def _build_rows(
    candidate: dict[str, Any],
    *,
    fund: dict[str, Any] | None,
    observed_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    slug = str(candidate["fund_slug"]).strip()
    signal_type = str(candidate.get("signal_type") or "").strip()
    if signal_type not in _CORE_TYPES:
        raise ValueError(f"Unsupported signal_type '{signal_type}' for {slug}")

    published_date = _iso_date(candidate.get("published_date"))
    if not published_date:
        raise ValueError(f"Missing/invalid published_date for {slug}")

    title = str(candidate.get("title") or "").strip()
    if len(title) < 12:
        raise ValueError(f"Title too short for {slug}")

    what_changed = str(candidate.get("what_changed") or "").strip()
    source_url = str(candidate.get("source_url") or "").strip()
    source_name = str(candidate.get("source_name") or "").strip() or "Manual backfill"
    quality_score = int(candidate.get("quality_score") or 85)
    relevance_basis = str(candidate.get("relevance_basis") or "explicit_italy_text")
    sid = _signal_id(slug, published_date, title)
    fund_scope = _slug_scope(fund)

    common: dict[str, Any] = {
        "id": sid,
        "fund_id": "",
        "fund_slug": slug,
        "signal_type": signal_type,
        "title": title,
        "what_changed": what_changed,
        "source_url": source_url,
        "source_name": source_name,
        "published_at": f"{published_date}T00:00:00+00:00",
        "observed_at": observed_at,
        "created_at": observed_at,
        "diff_summary": what_changed,
        "page_category": "NEWS",
        "page_type": "NEWS",
        "relevance_score": 1.0,
        "relevance_reasons": ["Manual backfill with explicit Italy evidence"],
        "italy_relevant": True,
        "extracted_entities": {"companies": [], "people": [], "locations": ["Italy"]},
        "_fund_geo_scope": fund_scope,
        "quality_score": quality_score,
        "evidence_score": 4,
        "quality_confidence": "high",
        "confidence_score": 0.92,
        "signal_types": [signal_type],
        "extraction_source": "manual_historical_backfill",
        "is_historical_backfill": True,
        "relevance_basis": relevance_basis,
    }

    filtered_row = dict(common)
    enriched_row = dict(common)
    enriched_row.update(
        {
            "type": signal_type,
            "enriched_summary": "",
            "enriched_date": published_date,
            "enrichment_confidence": "high",
            "llm_keep": True,
            "llm_keep_reason": "manual historical backfill: verified Italy relevance",
            "llm_keep_confidence": "high",
            "llm_keep_source": "local",
            "target_companies": [],
        }
    )
    return filtered_row, enriched_row


def _count_by_slug(signals: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for s in signals:
        slug = str(s.get("fund_slug") or "").strip()
        if slug:
            counts[slug] += 1
    return counts


def _parse_slugs(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {s.strip() for s in raw.split(",") if s.strip()}


def _sort_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(sig: dict[str, Any]) -> tuple[str, str]:
        d1 = str(sig.get("enriched_date") or "")[:10]
        d2 = str(sig.get("published_at") or "")[:10]
        d3 = str(sig.get("observed_at") or "")
        return (d1 or d2, d3)

    return sorted(signals, key=key, reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill top-AUM signals with historical Italy-relevant entries")
    parser.add_argument("--top-n", type=int, default=25, help="Number of highest-AUM funds to enforce completeness on")
    parser.add_argument("--min-signals", type=int, default=2, help="Minimum filtered signals per target fund")
    parser.add_argument("--slugs", type=str, default="", help="Optional comma-separated slug override")
    parser.add_argument("--candidates", type=str, default=str(DEFAULT_CANDIDATES_PATH), help="Candidate JSON file")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()

    db = _load_json(DB_PATH)
    filtered = _load_json(FILTERED_PATH)
    enriched = _load_json(ENRICHED_PATH)
    candidates_payload = _load_json(Path(args.candidates))

    funds: list[dict[str, Any]] = db.get("funds", [])
    funds_by_slug = {str(f.get("slug") or ""): f for f in funds if f.get("slug")}
    ranked = sorted(
        [f for f in funds if isinstance(f.get("aum_eur"), (int, float)) and float(f.get("aum_eur")) > 0],
        key=lambda x: float(x.get("aum_eur") or 0),
        reverse=True,
    )
    ranked_slugs = [str(f.get("slug")) for f in ranked if f.get("slug")]

    selected_slugs = _parse_slugs(args.slugs)
    targets = sorted(selected_slugs) if selected_slugs else ranked_slugs[: max(args.top_n, 0)]

    filtered_signals: list[dict[str, Any]] = list(filtered.get("signals") or [])
    enriched_signals: list[dict[str, Any]] = list(enriched.get("signals") or [])
    filtered_counts = _count_by_slug(filtered_signals)

    undercovered: dict[str, int] = {}
    for slug in targets:
        count = int(filtered_counts.get(slug, 0))
        if count < args.min_signals:
            undercovered[slug] = count

    candidates = [c for c in (candidates_payload.get("signals") or []) if isinstance(c, dict)]
    by_slug: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        slug = str(c.get("fund_slug") or "").strip()
        if slug:
            by_slug[slug].append(c)
    for slug in by_slug:
        by_slug[slug].sort(key=lambda c: str(c.get("published_date") or ""), reverse=True)

    existing_ids = {str(s.get("id")) for s in filtered_signals if s.get("id")}
    existing_ids |= {str(s.get("id")) for s in enriched_signals if s.get("id")}
    observed_at = datetime.now(timezone.utc).isoformat()
    added_ids: list[str] = []
    skipped: list[str] = []

    for slug, current_count in undercovered.items():
        need = args.min_signals - current_count
        if need <= 0:
            continue
        pool = by_slug.get(slug, [])
        if not pool:
            skipped.append(f"{slug}: no backfill candidates")
            continue

        for candidate in pool:
            if need <= 0:
                break
            if not _has_italy_evidence(candidate):
                skipped.append(f"{slug}: candidate rejected (no explicit Italy evidence)")
                continue
            try:
                filtered_row, enriched_row = _build_rows(candidate, fund=funds_by_slug.get(slug), observed_at=observed_at)
            except Exception as exc:
                skipped.append(f"{slug}: invalid candidate ({exc})")
                continue
            sid = str(filtered_row["id"])
            if sid in existing_ids:
                continue
            filtered_signals.append(filtered_row)
            enriched_signals.append(enriched_row)
            existing_ids.add(sid)
            added_ids.append(sid)
            need -= 1

        if need > 0:
            skipped.append(f"{slug}: still below minimum after candidates (missing {need})")

    # Ensure strict parity for newly inserted rows.
    f_ids = {str(s.get("id")) for s in filtered_signals if s.get("id")}
    e_ids = {str(s.get("id")) for s in enriched_signals if s.get("id")}
    missing_in_enriched = sorted((set(added_ids) & f_ids) - e_ids)
    missing_in_filtered = sorted((set(added_ids) & e_ids) - f_ids)
    if missing_in_enriched or missing_in_filtered:
        raise RuntimeError(
            f"Parity failure: missing_in_enriched={missing_in_enriched} missing_in_filtered={missing_in_filtered}"
        )

    print("Top-AUM historical backfill")
    print("=" * 54)
    print(f"Targets: {len(targets)} (top_n={args.top_n}, min_signals={args.min_signals})")
    print(f"Undercovered targets: {len(undercovered)}")
    print(f"Candidates loaded: {len(candidates)} from {args.candidates}")
    print(f"Would add: {len(added_ids)}")
    for sid in added_ids:
        print(f"  + {sid}")
    if skipped:
        print("Skipped:")
        for msg in skipped:
            print(f"  - {msg}")

    if not args.apply:
        print("\nDry-run mode (no files written). Use --apply to persist.")
        return 0

    filtered["signals"] = _sort_signals(filtered_signals)
    filtered["signal_count"] = len(filtered["signals"])
    filtered["filtered_at"] = observed_at

    enriched["signals"] = _sort_signals(enriched_signals)
    enriched["signal_count"] = len(enriched["signals"])
    enriched["enriched_at"] = observed_at

    _save_json(FILTERED_PATH, filtered)
    _save_json(ENRICHED_PATH, enriched)

    print("\nApplied changes:")
    print(f"  filtered signals: {filtered['signal_count']}")
    print(f"  enriched signals: {enriched['signal_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
