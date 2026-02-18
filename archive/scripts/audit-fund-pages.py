#!/usr/bin/env python3
"""
Fund Page Credibility Audit

Reads portfolio, PEM deals, fund database, and aliases.
Outputs data/derived/fund_page_audit.json + console summary.

Usage:
    python3 scripts/audit-fund-pages.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- Paths ---

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
DERIVED = DATA / "derived"

PORTFOLIO_PATH = DERIVED / "portfolio_items.json"
PEM_DEALS_PATH = DERIVED / "pem_deals.json"
DB_PATH = DATA / "db.json"
ALIASES_PATH = DERIVED / "fund_aliases.json"
OUTPUT_PATH = DERIVED / "fund_page_audit.json"

# --- Garbage detection patterns ---

GARBAGE_PATTERNS = [
    "portfolio", "our investments", "back to top", "read more",
    "cookie policy", "privacy policy", "contact us", "learn more",
    "view all", "see more", "load more", "show more", "next page",
    "soluzioni di investimento", "you may want to visit",
    "private equity", "venture capital", "home", "about us",
    "terms of use", "disclaimer", "subscribe", "newsletter",
]

# --- Helpers ---

def load_json(path: Path) -> dict:
    """Load a JSON file, exit with error if missing."""
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_name(name: str) -> str:
    """Minimal name normalization for comparison."""
    import re
    s = name.lower().strip()
    # Strip parenthetical
    s = re.sub(r"\s*\(.*?\)", "", s)
    # Strip legal suffixes
    s = re.sub(r"\b(s\.?p\.?a\.?|s\.?r\.?l\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?s\.?)\b", "", s)
    # Strip trailing group/technologies
    s = re.sub(r"\s+(group|technologies)\s*$", "", s)
    # Non-alphanumeric to space, collapse
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def names_match(a: str, b: str) -> bool:
    """Check if two company names match using the 4 strategies from data.ts."""
    na = normalize_name(a)
    nb = normalize_name(b)
    if not na or not nb:
        return False
    # Strategy 1: exact normalized
    if na == nb:
        return True
    # Strategy 2: compact (no spaces)
    if na.replace(" ", "") == nb.replace(" ", ""):
        return True
    # Strategy 3: group-stripped
    na_ng = na.replace("group", "").strip()
    nb_ng = nb.replace("group", "").strip()
    if na_ng and nb_ng and na_ng == nb_ng:
        return True
    # Strategy 4: substring (>=5 chars, word boundary)
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 5 and shorter in longer:
        idx = longer.index(shorter)
        end = idx + len(shorter)
        start_ok = idx == 0 or longer[idx - 1] == " "
        end_ok = end == len(longer) or longer[end] == " "
        if start_ok and end_ok:
            return True
    return False


def is_garbage(name: str) -> bool:
    """Check if a portfolio entry name looks like scrape garbage."""
    low = name.lower().strip()
    if len(low) < 3 or len(low) > 80:
        return True
    if "|" in low:
        return True
    for pat in GARBAGE_PATTERNS:
        if low == pat or low.startswith(pat + " "):
            return True
    return False


def is_exit_signal(deal: dict) -> bool:
    """Check if a PEM deal's origination suggests the fund sold/exited."""
    orig = (deal.get("deal_origination") or "").lower()
    return any(kw in orig for kw in ["exit", "ipo", "trade sale"])


def is_old_deal(deal: dict, threshold: int = 2020) -> bool:
    """Check if a PEM deal is old enough to likely be exited."""
    return (deal.get("source_year") or 9999) < threshold


# --- Main logic ---

def build_fund_lookup(db: dict) -> dict:
    """Build slug → fund info dict from db.json."""
    funds = {}
    for f in db.get("funds", []):
        slug = f.get("slug") or f.get("id")
        if slug:
            funds[slug] = {
                "name": f.get("name", slug),
                "aum_eur": f.get("aum_eur"),
                "category": f.get("category"),
                "website": f.get("website"),
                "hq_city": f.get("hq_city"),
            }
    return funds


def build_pem_index(deals: list, aliases: dict) -> dict:
    """Build slug → [deal, ...] index. Check lead_investor_slug, co_investors, and aliases."""
    alias_map = aliases.get("aliases", {})
    reverse_map = aliases.get("reverse_lookup", {})

    index = {}
    for deal in deals:
        # Map lead investor slug to canonical
        lead_slug = deal.get("lead_investor_slug", "")
        canonical = alias_map.get(lead_slug, lead_slug)
        if canonical:
            index.setdefault(canonical, []).append(deal)

        # Also index under co_investors (slugified)
        for co in (deal.get("co_investors") or []):
            co_slug = co.lower().replace(" ", "-").replace(".", "")
            co_canonical = alias_map.get(co_slug, co_slug)
            if co_canonical:
                index.setdefault(co_canonical, []).append(deal)

    return index


def compute_credibility_score(fund_info: dict, portfolio_entries: list) -> int:
    """Compute a credibility score (0-160) for how a fund page looks to an expert."""
    aum = fund_info.get("aum_eur") or 0
    total = len(portfolio_entries)
    if total == 0:
        return 0

    current = sum(1 for e in portfolio_entries if e.get("status") == "current")
    null_sector = sum(1 for e in portfolio_entries if e.get("sector") is None)
    null_desc = sum(1 for e in portfolio_entries if e.get("description") is None)
    high_conf = sum(1 for e in portfolio_entries if (e.get("confidence") or 0) >= 0.8)

    score = 0
    # Current entries matter most (up to 100 for 10+)
    score += min(current, 10) * 10
    # Sector coverage (up to 30)
    score += int((total - null_sector) / total * 30)
    # Description coverage (up to 20)
    score += int((total - null_desc) / total * 20)
    # Confidence level (up to 10)
    score += int(high_conf / total * 10)

    # Penalty for too few entries relative to AUM
    if aum > 10_000_000_000 and current < 3:
        score = int(score * 0.5)
    elif aum > 5_000_000_000 and current < 3:
        score = int(score * 0.6)

    return score


def audit_fund(slug: str, fund_info: dict, portfolio_entries: list, pem_deals: list) -> dict:
    """Audit a single fund and return its audit record."""
    name = fund_info["name"]
    aum = fund_info.get("aum_eur")
    category = fund_info.get("category")
    website = fund_info.get("website")

    total = len(portfolio_entries)
    current = sum(1 for e in portfolio_entries if e.get("status") == "current")
    exited = sum(1 for e in portfolio_entries if e.get("status") == "exited")
    null_status = sum(1 for e in portfolio_entries if e.get("status") is None)
    pem_count = len(pem_deals)

    # Credibility score
    cred_score = compute_credibility_score(fund_info, portfolio_entries)

    # --- Red flags ---
    red_flags = []

    # 1. ALL_NULL_STATUS
    if null_status > 0:
        pct = null_status / total * 100 if total > 0 else 0
        if null_status == total and total > 0:
            red_flags.append(
                f"ALL_NULL_STATUS: {null_status} entries with null status shown as current"
            )
        elif pct >= 50 and null_status > 3:
            red_flags.append(
                f"MOSTLY_NULL_STATUS: {null_status}/{total} entries ({pct:.0f}%) have null status"
            )

    # 2. MAJOR_FUND_FEW_ENTRIES
    if aum and aum > 5_000_000_000 and total < 10:
        aum_b = aum / 1_000_000_000
        red_flags.append(
            f"MAJOR_FUND_FEW_ENTRIES: €{aum_b:.0f}B AUM but only {total} portfolio entries"
        )

    # 3. PEM_EXIT_MISMATCH — portfolio entry exists but PEM says likely exited
    for deal in pem_deals:
        target = deal.get("target_company", "")
        if not target:
            continue
        for entry in portfolio_entries:
            ename = entry.get("name", "")
            if not ename:
                continue
            if names_match(target, ename):
                # Check if this looks like an exit
                if is_exit_signal(deal):
                    red_flags.append(
                        f"PEM_EXIT_MISMATCH: {ename} appears current but PEM deal_origination suggests exit"
                    )
                elif is_old_deal(deal):
                    year = deal.get("source_year", "?")
                    red_flags.append(
                        f"PEM_EXIT_MISMATCH: {ename} appears current but PEM shows {year} deal (likely exited)"
                    )
                break

    # 4. NO_CURRENT_PORTFOLIO
    if pem_count > 0 and current == 0 and null_status == 0:
        red_flags.append(
            f"NO_CURRENT_PORTFOLIO: {pem_count} PEM deals but 0 current portfolio entries"
        )

    # 5. GARBAGE_ENTRIES
    garbage_names = [e["name"] for e in portfolio_entries if is_garbage(e.get("name", ""))]
    if garbage_names:
        sample = garbage_names[:3]
        red_flags.append(
            f"GARBAGE_ENTRIES: {len(garbage_names)} suspicious entries (e.g. {', '.join(sample)})"
        )

    # 6. STALE_DATA
    stale_entries = []
    for e in portfolio_entries:
        inv_date = e.get("investment_date")
        if inv_date and inv_date < "2015" and e.get("status") != "exited":
            stale_entries.append(e.get("name", "?"))
    if stale_entries:
        sample = stale_entries[:3]
        red_flags.append(
            f"STALE_DATA: {len(stale_entries)} entries with pre-2015 dates, not marked exited (e.g. {', '.join(sample)})"
        )

    # --- Tier assignment ---
    tier = None
    if aum and aum > 5_000_000_000 and (current + null_status < 10 or null_status > 5):
        tier = 1
    elif null_status > 3 or (pem_count > 3 and current < 3):
        tier = 2
    elif current < 5 and pem_count > 0:
        tier = 3

    # 7. MISSING_SECTORS
    null_sector = sum(1 for e in portfolio_entries if e.get("sector") is None)
    if null_sector > 0 and total > 0:
        pct = null_sector / total * 100
        if pct >= 50:
            red_flags.append(
                f"MISSING_SECTORS: {null_sector}/{total} entries ({pct:.0f}%) have no sector"
            )

    # 8. MISSING_DESCRIPTIONS
    null_desc = sum(1 for e in portfolio_entries if e.get("description") is None)
    if null_desc > 0 and total > 0:
        pct = null_desc / total * 100
        if pct >= 80:
            red_flags.append(
                f"MISSING_DESCRIPTIONS: {null_desc}/{total} entries ({pct:.0f}%) have no description"
            )

    # --- Suggested actions ---
    actions = []
    if null_status > 0:
        actions.append("Set status=exited for entries with old PEM deals and no current evidence")
        actions.append("Set status=current for entries confirmed on fund website")
    if aum and aum > 5_000_000_000 and total < 10:
        actions.append("Research current Italian portfolio from fund website")
        actions.append("Add 5-10 current investments from official sources")
    if pem_count > 0 and current == 0:
        actions.append("Cross-reference PEM deals against fund website to determine status")
    if garbage_names:
        actions.append("Remove garbage entries (navigation text, section headers)")
    if null_sector > total * 0.5:
        actions.append("Add sector classifications from fund website or standard PE categories")
    if null_desc > total * 0.8:
        actions.append("Add one-sentence descriptions for key portfolio companies")

    return {
        "slug": slug,
        "name": name,
        "aum_eur": aum,
        "category": category,
        "website": website,
        "tier": tier,
        "credibility_score": cred_score,
        "portfolio_count": total,
        "current_count": current,
        "exited_count": exited,
        "null_status_count": null_status,
        "pem_deal_count": pem_count,
        "null_sector_count": null_sector,
        "null_description_count": null_desc,
        "red_flags": red_flags,
        "portfolio_entries": [
            {
                "name": e.get("name"),
                "status": e.get("status"),
                "sector": e.get("sector"),
                "investment_date": e.get("investment_date"),
            }
            for e in portfolio_entries
        ],
        "pem_deals": [
            {
                "target_company": d.get("target_company"),
                "source_year": d.get("source_year"),
                "investment_stage": d.get("investment_stage"),
                "deal_origination": d.get("deal_origination"),
            }
            for d in pem_deals
        ],
        "suggested_actions": actions,
    }


def main():
    print("Loading data files...")
    portfolio_data = load_json(PORTFOLIO_PATH)
    pem_data = load_json(PEM_DEALS_PATH)
    db_data = load_json(DB_PATH)
    aliases_data = load_json(ALIASES_PATH)

    fund_lookup = build_fund_lookup(db_data)
    pem_index = build_pem_index(pem_data.get("deals", []), aliases_data)
    fund_portfolios = portfolio_data.get("fund_portfolios", {})

    # Collect all slugs: ONLY real funds from fund_lookup + portfolios
    # DO NOT include PEM-only entities (leads to 600+ fake fund entries)
    all_slugs = set(fund_lookup.keys())
    all_slugs.update(fund_portfolios.keys())

    # Resolve aliases: ensure canonical slugs are used
    alias_map = aliases_data.get("aliases", {})

    print(f"Auditing {len(all_slugs)} fund slugs...")
    results = []
    total_null = 0
    total_pem = 0
    tier_counts = {1: 0, 2: 0, 3: 0}

    for slug in sorted(all_slugs):
        # Skip alias slugs — only audit canonical
        if slug in alias_map:
            continue

        fund_info = fund_lookup.get(slug, {
            "name": slug,
            "aum_eur": None,
            "category": None,
            "website": None,
            "hq_city": None,
        })

        entries = fund_portfolios.get(slug, [])
        deals = pem_index.get(slug, [])

        # Skip funds with zero data
        if not entries and not deals:
            continue

        record = audit_fund(slug, fund_info, entries, deals)
        results.append(record)

        total_null += record["null_status_count"]
        total_pem += record["pem_deal_count"]
        if record["tier"]:
            tier_counts[record["tier"]] += 1

    # Sort: tier 1 first, then 2, then 3, then untiered; within tier by AUM desc
    def sort_key(r):
        tier = r["tier"] if r["tier"] else 99
        aum = -(r["aum_eur"] or 0)
        return (tier, aum, r["slug"])

    results.sort(key=sort_key)

    # Compute credibility stats
    cred_scores = [r["credibility_score"] for r in results]
    avg_cred = sum(cred_scores) / len(cred_scores) if cred_scores else 0
    below_50 = sum(1 for s in cred_scores if s < 50)
    total_null_sector = sum(r.get("null_sector_count", 0) for r in results)
    total_null_desc = sum(r.get("null_description_count", 0) for r in results)

    # --- Output JSON ---
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_funds_audited": len(results),
            "tier1_count": tier_counts[1],
            "tier2_count": tier_counts[2],
            "tier3_count": tier_counts[3],
            "total_null_status": total_null,
            "total_pem_deals": total_pem,
            "avg_credibility_score": round(avg_cred),
            "funds_below_50_credibility": below_50,
            "total_null_sectors": total_null_sector,
            "total_null_descriptions": total_null_desc,
        },
        "funds": results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nWrote: {OUTPUT_PATH}")

    # --- Console summary ---
    print(f"\n{'='*72}")
    print(f"FUND PAGE CREDIBILITY AUDIT")
    print(f"{'='*72}")
    print(f"Total funds audited:             {len(results)}")
    print(f"Tier 1 (major credibility risk): {tier_counts[1]}")
    print(f"Tier 2 (data accuracy risk):     {tier_counts[2]}")
    print(f"Tier 3 (incomplete picture):     {tier_counts[3]}")
    print(f"Total null-status entries:       {total_null}")
    print(f"Total PEM deals indexed:         {total_pem}")
    print(f"Avg credibility score:           {avg_cred:.0f}/160")
    print(f"Funds with credibility < 50:     {below_50}")
    print(f"Total missing sectors:           {total_null_sector}")
    print(f"Total missing descriptions:      {total_null_desc}")

    # Show lowest credibility funds first
    by_cred = sorted(results, key=lambda r: (r["credibility_score"], -(r["aum_eur"] or 0)))
    low_cred = [r for r in by_cred if r["credibility_score"] < 50]
    if low_cred:
        print(f"\n{'─'*72}")
        print(f"LOWEST CREDIBILITY (score < 50) — fix these first")
        print(f"{'─'*72}")
        print(f"  {'Slug':<40} {'AUM':>8} {'Cred':>4} {'Curr':>4} {'Exit':>4} {'NoSec':>5}")
        print(f"  {'-'*40} {'---':>8} {'---':>4} {'---':>4} {'---':>4} {'---':>5}")
        for r in low_cred:
            aum_str = ""
            if r["aum_eur"]:
                aum_b = r["aum_eur"] / 1_000_000_000
                if aum_b >= 1:
                    aum_str = f"€{aum_b:.0f}B"
                else:
                    aum_m = r["aum_eur"] / 1_000_000
                    aum_str = f"€{aum_m:.0f}M"
            print(f"  {r['slug']:<40} {aum_str:>8} {r['credibility_score']:>4} "
                  f"{r['current_count']:>4} {r['exited_count']:>4} "
                  f"{r.get('null_sector_count', 0):>5}")

    # Show tier details
    for tier_num in [1, 2, 3]:
        tier_funds = [r for r in results if r["tier"] == tier_num]
        if not tier_funds:
            continue
        print(f"\n{'─'*72}")
        print(f"TIER {tier_num}")
        print(f"{'─'*72}")
        for r in tier_funds[:10]:  # Show top 10 per tier
            aum_str = ""
            if r["aum_eur"]:
                aum_b = r["aum_eur"] / 1_000_000_000
                if aum_b >= 1:
                    aum_str = f" (€{aum_b:.0f}B)"
                else:
                    aum_m = r["aum_eur"] / 1_000_000
                    aum_str = f" (€{aum_m:.0f}M)"

            print(f"\n  {r['slug']}{aum_str}  [cred: {r['credibility_score']}]")
            print(f"    portfolio: {r['portfolio_count']} total, "
                  f"{r['current_count']} current, "
                  f"{r['exited_count']} exited, "
                  f"{r['null_status_count']} null-status")
            print(f"    PEM deals: {r['pem_deal_count']}")
            for flag in r["red_flags"][:3]:
                print(f"    ! {flag}")
        remaining = len(tier_funds) - 10
        if remaining > 0:
            print(f"\n  ... and {remaining} more tier {tier_num} funds")

    print(f"\n{'='*72}")
    print("Done. See data/derived/fund_page_audit.json for full details.")


if __name__ == "__main__":
    main()
