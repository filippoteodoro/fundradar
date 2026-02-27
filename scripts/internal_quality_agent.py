#!/usr/bin/env python3
"""Internal deterministic QA agent for Fundradar data quality.

Runs rule-based checks over enriched/filtered signals and portfolio data to
surface actionable issues without external LLM dependencies.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"
OUT = DERIVED / "internal_agent_audit.json"

ENRICHED_PATH = DERIVED / "detected_signals_enriched.json"
FILTERED_PATH = DERIVED / "detected_signals_filtered.json"
RAW_PATH = DERIVED / "detected_signals.json"
PORTFOLIO_PATH = DERIVED / "portfolio_items.json"
DB_PATH = ROOT / "data" / "db.json"


ITALIAN_LEAK_RE = re.compile(
    r"\b(?:chiude|raccolta|investimento|partecipazione|societ[àa]"
    r"|acquisizione|annuncia|nomina|consiglio|capitale|nel|nella|del|della|con|per|tra)\b",
    re.IGNORECASE,
)
PEOPLE_MARKERS_RE = re.compile(
    r"\b(?:appointed|appoints|hired|joins?|named|ceo|cfo|coo|cto|managing director|partner)\b",
    re.IGNORECASE,
)
DEAL_MARKERS_RE = re.compile(
    r"\b(?:acquires?|acquired|investment|invests?|stake|merger|buyout|exit|sold|sale)\b",
    re.IGNORECASE,
)
BOILERPLATE_RE = re.compile(
    r"\b(?:tracked universe|top-ranked company|transaction is a concrete|publicly observed)\b",
    re.IGNORECASE,
)
BAD_CURRENCY_RE = re.compile(
    r"(?:[€$£]\s*\d{1,3}(?:,\d{3})+)|(?:\b\d+(?:\.\d+)?\s+(?:Billion|Million|Thousand)\b)",
    re.IGNORECASE,
)
LONG_LOWER_TOKEN_RE = re.compile(r"\b[a-z]{18,}\b")
ALL_CAPS_ALLOWLIST = {
    "CEO", "CFO", "COO", "CTO", "IPO", "M&A", "ESG", "PE", "VC", "LP", "GP", "IRR",
    "NAV", "EV", "AI", "ICT", "B2B", "B2C", "SME", "EU", "UK", "USA", "AUM",
}


@dataclass
class Finding:
    severity: str
    category: str
    signal_id: str | None
    fund_slug: str | None
    evidence: str
    recommended_fix: str


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _normalize_name(name: str) -> str:
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\b(spa|srl|ltd|llc|inc|gmbh|ag|bv|nv|plc|corp|corporation|company|group|holding|holdings)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _compact(name: str) -> str:
    return _normalize_name(name).replace(" ", "")


def _text(signal: dict) -> str:
    return " ".join(
        x for x in [
            signal.get("title", ""),
            signal.get("what_changed", ""),
            signal.get("enriched_summary", ""),
            signal.get("diff_summary", ""),
        ] if x
    )


def main() -> int:
    enriched = _load_json(ENRICHED_PATH).get("signals", [])
    filtered = _load_json(FILTERED_PATH).get("signals", [])
    raw = _load_json(RAW_PATH).get("signals", [])
    portfolio = _load_json(PORTFOLIO_PATH).get("fund_portfolios", {})
    db_funds = _load_json(DB_PATH).get("funds", [])

    fund_names = {f["slug"]: f.get("name", "") for f in db_funds if f.get("slug")}
    findings: list[Finding] = []

    # 1) Signal-level quality checks (website-visible set = enriched).
    for s in enriched:
        sid = s.get("id")
        slug = s.get("fund_slug")
        text = _text(s)
        title = (s.get("title") or "").strip()
        summary = (s.get("enriched_summary") or "").strip()
        what_changed = (s.get("what_changed") or "").strip()
        stype = (s.get("signal_type") or "").strip()

        it_matches = ITALIAN_LEAK_RE.findall(text)
        if len(it_matches) >= 2:
            findings.append(Finding(
                severity="medium",
                category="italian_leakage",
                signal_id=sid,
                fund_slug=slug,
                evidence=f"Potential Italian text in signal: {title[:120]}",
                recommended_fix="Expand translation/cleanup patterns for mixed-language fragments.",
            ))

        if BAD_CURRENCY_RE.search(text):
            findings.append(Finding(
                severity="medium",
                category="currency_format",
                signal_id=sid,
                fund_slug=slug,
                evidence=f"Non-standard money notation detected: {title[:120]}",
                recommended_fix="Normalize to €X.XK/€X.XM/€X.XB/€X.XT in signal_text_utils.",
            ))

        if BOILERPLATE_RE.search(text):
            findings.append(Finding(
                severity="low",
                category="boilerplate_wording",
                signal_id=sid,
                fund_slug=slug,
                evidence=f"Boilerplate phrase detected: {title[:120]}",
                recommended_fix="Strip known boilerplate templates in clean_display_text().",
            ))

        if len(title) < 12 and len(what_changed) < 30:
            findings.append(Finding(
                severity="medium",
                category="too_short_or_contextless",
                signal_id=sid,
                fund_slug=slug,
                evidence=f"Signal may be too short/contextless: title='{title}'",
                recommended_fix="Require richer what_changed context for short titles.",
            ))

        if len(what_changed) > 420 or len(summary) > 260:
            findings.append(Finding(
                severity="low",
                category="too_long_text",
                signal_id=sid,
                fund_slug=slug,
                evidence=f"Long text payload (what_changed={len(what_changed)}, summary={len(summary)})",
                recommended_fix="Trim and de-duplicate narrative text in enrichment post-processing.",
            ))

        if stype == "other" and PEOPLE_MARKERS_RE.search(text):
            findings.append(Finding(
                severity="high",
                category="people_misclassified_as_other",
                signal_id=sid,
                fund_slug=slug,
                evidence=f"People markers in type=other: {title[:120]}",
                recommended_fix="Strengthen appointment rescue rules in signal_corrections.",
            ))

        if stype in {"other", "people_move"} and DEAL_MARKERS_RE.search(text) and not PEOPLE_MARKERS_RE.search(text):
            findings.append(Finding(
                severity="medium",
                category="deal_misclassification",
                signal_id=sid,
                fund_slug=slug,
                evidence=f"Deal-like markers with type={stype}: {title[:120]}",
                recommended_fix="Raise deal keyword precedence over weak people/title cues.",
            ))

        if LONG_LOWER_TOKEN_RE.search(text):
            token = LONG_LOWER_TOKEN_RE.search(text).group(0)
            findings.append(Finding(
                severity="medium",
                category="word_concatenation",
                signal_id=sid,
                fund_slug=slug,
                evidence=f"Long merged token detected: '{token}'",
                recommended_fix="Extend token-split repair rules in signal_text_utils.",
            ))

        all_caps_bad = [
            tok for tok in re.findall(r"\b[A-Z]{4,}\b", text)
            if tok not in ALL_CAPS_ALLOWLIST
        ]
        if all_caps_bad:
            findings.append(Finding(
                severity="low",
                category="all_caps_misuse",
                signal_id=sid,
                fund_slug=slug,
                evidence=f"Suspicious ALL-CAPS tokens: {', '.join(sorted(set(all_caps_bad))[:5])}",
                recommended_fix="Normalize casing while preserving domain acronyms.",
            ))

    # 2) Signal -> portfolio linkage checks.
    normalized_portfolio = defaultdict(set)
    compact_portfolio = defaultdict(set)
    status_lookup = defaultdict(dict)
    for slug, rows in portfolio.items():
        for row in rows:
            name = row.get("name", "")
            norm = _normalize_name(name)
            if not norm:
                continue
            normalized_portfolio[slug].add(norm)
            compact_portfolio[slug].add(norm.replace(" ", ""))
            status_lookup[slug][norm] = row.get("status")

    for s in enriched:
        sid = s.get("id")
        slug = s.get("fund_slug")
        if not slug:
            continue
        targets = s.get("target_companies")
        if not isinstance(targets, list) or not targets:
            continue

        for tc in targets:
            if not isinstance(tc, dict):
                continue
            name = (tc.get("name") or "").strip()
            action = tc.get("action")
            is_direct = bool(tc.get("is_direct_investment"))
            if not name or not is_direct:
                continue
            norm = _normalize_name(name)
            comp = _compact(name)
            exists = norm in normalized_portfolio[slug] or comp in compact_portfolio[slug]

            if action == "investment" and not exists:
                findings.append(Finding(
                    severity="high",
                    category="signal_to_portfolio_missing_investment",
                    signal_id=sid,
                    fund_slug=slug,
                    evidence=f"Target company not in portfolio for investment action: {name}",
                    recommended_fix="Re-run signal_to_portfolio or improve target-company matching/normalization.",
                ))

            if action == "exit" and exists:
                st = status_lookup[slug].get(norm)
                if st != "exited":
                    findings.append(Finding(
                        severity="medium",
                        category="signal_to_portfolio_exit_not_applied",
                        signal_id=sid,
                        fund_slug=slug,
                        evidence=f"Exit action found but portfolio status is not exited: {name} (status={st})",
                        recommended_fix="Ensure exit updates in signal_to_portfolio cover this matching case.",
                    ))

    # Deduplicate nearly identical findings.
    dedup_keyed = {}
    for f in findings:
        k = (f.category, f.signal_id, f.fund_slug, f.evidence[:120])
        if k not in dedup_keyed:
            dedup_keyed[k] = f
    findings = list(dedup_keyed.values())

    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda x: (sev_order.get(x.severity, 9), x.category, x.fund_slug or "", x.signal_id or ""))

    by_category = defaultdict(int)
    by_fund = defaultdict(int)
    by_severity = defaultdict(int)
    for f in findings:
        by_category[f.category] += 1
        by_fund[f.fund_slug or "unknown"] += 1
        by_severity[f.severity] += 1

    report = {
        "meta": {
            "signals_raw": len(raw),
            "signals_filtered": len(filtered),
            "signals_enriched": len(enriched),
            "portfolio_entries": sum(len(v) for v in portfolio.values()),
        },
        "summary": {
            "total_findings": len(findings),
            "by_severity": dict(sorted(by_severity.items())),
            "by_category_top10": sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:10],
            "by_fund_top10": sorted(by_fund.items(), key=lambda x: x[1], reverse=True)[:10],
        },
        "findings": [asdict(f) for f in findings[:250]],
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote audit report: {OUT}")
    print(f"Findings: {report['summary']['total_findings']}")
    print(f"Severity: {report['summary']['by_severity']}")
    print(f"Top categories: {report['summary']['by_category_top10'][:5]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
