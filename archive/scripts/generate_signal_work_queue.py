#!/usr/bin/env python3
"""
Generate a prioritized work queue for signal quality improvement.

Reads:
  - data/db.json — fund list with slugs, websites, categories
  - data/derived/detected_signals_filtered.json — current signals per fund
  - apps/worker/fundradar_worker/strategies/extractors/ — which have extract_news

Outputs: data/derived/signal_work_queue.json

Usage:
    python3 scripts/generate_signal_work_queue.py
"""
import ast
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "db.json"
SIGNALS_PATH = REPO_ROOT / "data" / "derived" / "detected_signals_filtered.json"
EXTRACTORS_DIR = REPO_ROOT / "apps" / "worker" / "fundradar_worker" / "strategies" / "extractors"
OUTPUT_PATH = REPO_ROOT / "data" / "derived" / "signal_work_queue.json"


def load_funds() -> list[dict]:
    """Load all funds from db.json."""
    with open(DB_PATH, "r") as f:
        db = json.load(f)
    funds = db if isinstance(db, list) else db.get("funds", [])
    return funds


def load_signals() -> dict[str, list[dict]]:
    """Load filtered signals, grouped by fund_slug."""
    if not SIGNALS_PATH.exists():
        return {}
    with open(SIGNALS_PATH, "r") as f:
        data = json.load(f)
    signals = data.get("signals", []) if isinstance(data, dict) else data
    by_slug: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        slug = s.get("fund_slug", "")
        if slug:
            by_slug[slug].append(s)
    return dict(by_slug)


def scan_extractors() -> dict[str, dict]:
    """
    Scan extractor files to determine which have extract_news.

    Returns: {domain: {"file": filename, "has_news": bool, "has_portfolio": bool, "has_team": bool}}
    """
    results = {}
    for filepath in sorted(EXTRACTORS_DIR.glob("*.py")):
        if filepath.name.startswith("_"):
            continue

        try:
            source = filepath.read_text()
        except Exception:
            continue

        # Extract DOMAIN constant
        domain_match = re.search(r'^DOMAIN\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
        if not domain_match:
            continue
        domain = domain_match.group(1)

        # Check which extract functions exist in EXTRACTORS dict
        has_news = bool(re.search(r'["\']news["\']\s*:', source))
        has_portfolio = bool(re.search(r'["\']portfolio["\']\s*:', source))
        has_team = bool(re.search(r'["\']team["\']\s*:', source))

        # Also check if extract_news function is defined (even if not in EXTRACTORS)
        has_news_func = bool(re.search(r'^def\s+extract_news\s*\(', source, re.MULTILINE))

        results[domain] = {
            "file": filepath.name,
            "has_news": has_news or has_news_func,
            "has_portfolio": has_portfolio,
            "has_team": has_team,
        }

    return results


def domain_from_url(url: str) -> str:
    """Extract domain from URL, normalizing www."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    return parsed.netloc.lower()


def domain_variants(domain: str) -> list[str]:
    """Return domain with and without www prefix."""
    if domain.startswith("www."):
        return [domain, domain[4:]]
    return [domain, "www." + domain]


def find_extractor(fund_website: str, extractors: dict[str, dict]) -> dict | None:
    """Find extractor info for a fund's website domain."""
    domain = domain_from_url(fund_website)
    if not domain:
        return None
    for variant in domain_variants(domain):
        if variant in extractors:
            return extractors[variant]
    return None


def compute_signal_stats(signals: list[dict]) -> dict:
    """Compute signal stats matching fundQuality.ts scoring dimensions."""
    if not signals:
        return {
            "count": 0,
            "types": [],
            "has_deal_exit": False,
            "avg_quality": 0,
            "italy_relevant_pct": 0,
            "avg_relevance": 0,
            "freshest_date": None,
            "all_have_source_url": False,
        }

    types = list(set(s.get("signal_type", "other") for s in signals))
    has_deal_exit = any(
        s.get("signal_type") in ("deal_announced", "exit_announced")
        for s in signals
    )

    quality_scores = [s.get("quality_score", 0) for s in signals if s.get("quality_score")]
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0

    italy_relevant = [s for s in signals if s.get("italy_relevant")]
    italy_pct = len(italy_relevant) / len(signals) * 100 if signals else 0

    relevance_scores = [s.get("relevance_score", 0) for s in signals if s.get("relevance_score")]
    avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0

    dates = []
    for s in signals:
        for field in ("published_at", "observed_at"):
            d = s.get(field)
            if d:
                dates.append(d)
                break
    freshest = max(dates) if dates else None

    all_have_url = all(s.get("source_url") for s in signals)

    return {
        "count": len(signals),
        "types": types,
        "has_deal_exit": has_deal_exit,
        "avg_quality": round(avg_quality, 1),
        "italy_relevant_pct": round(italy_pct, 1),
        "avg_relevance": round(avg_relevance, 3),
        "freshest_date": freshest,
        "all_have_source_url": all_have_url,
    }


def estimate_signal_score(stats: dict) -> int:
    """Estimate signal score out of 100 (matching fundQuality.ts logic)."""
    score = 0
    count = stats["count"]
    types = stats["types"]

    # Tier A: Quantity & Diversity (40 pts)
    if count > 0:
        score += 10
    if count >= 10:
        score += 10
    elif count >= 5:
        score += 6
    elif count >= 1:
        score += 3

    n_types = len(types)
    if n_types >= 4:
        score += 10
    elif n_types >= 3:
        score += 8
    elif n_types >= 2:
        score += 5
    elif n_types >= 1:
        score += 2

    if stats["has_deal_exit"]:
        score += 10

    # Tier B: Quality (35 pts)
    if stats["avg_quality"] >= 70:
        score += 10
    if stats["avg_quality"] >= 85:
        score += 5
    if stats["italy_relevant_pct"] >= 50:
        score += 10
    if stats["avg_relevance"] >= 0.2:
        score += 5
    # what_changed quality — assume ok if signals exist
    if count > 0:
        score += 5

    # Tier C: Freshness (25 pts)
    if stats["freshest_date"]:
        try:
            freshest_str = stats["freshest_date"][:10]
            freshest_dt = datetime.strptime(freshest_str, "%Y-%m-%d")
            now = datetime.now()
            months_ago = (now.year - freshest_dt.year) * 12 + (now.month - freshest_dt.month)
            if months_ago <= 6:
                score += 15
            elif months_ago <= 12:
                score += 5
        except (ValueError, TypeError):
            pass

    if stats["all_have_source_url"]:
        score += 5

    return min(score, 100)


def category_sort_key(category: str) -> int:
    """Sort funds by category: pe/vc first."""
    order = {"pe": 0, "vc": 1, "pd": 2}
    return order.get(category, 3)


def generate_queue():
    """Generate the signal work queue."""
    funds = load_funds()
    signals_by_slug = load_signals()
    extractors = scan_extractors()

    needs_news_extractor = []  # Priority A: extractor exists, no extract_news
    has_news_no_signals = []   # Priority B: has extract_news but 0 signals
    needs_new_extractor = []   # Priority C: no extractor at all
    has_signals = []           # Already working (has some signals)
    no_website = []            # No website URL — skip

    for fund in funds:
        slug = fund.get("slug", fund.get("id", ""))
        name = fund.get("name", slug)
        website = fund.get("website", "")
        category = fund.get("category", "unknown")
        domain = domain_from_url(website)

        if not website or not domain:
            no_website.append({
                "slug": slug,
                "name": name,
                "reason": "no_website",
            })
            continue

        fund_signals = signals_by_slug.get(slug, [])
        stats = compute_signal_stats(fund_signals)
        signal_score = estimate_signal_score(stats)
        extractor_info = find_extractor(website, extractors)

        entry = {
            "slug": slug,
            "name": name,
            "domain": domain,
            "website": website,
            "category": category,
            "current_signal_count": stats["count"],
            "current_signal_score": signal_score,
            "signal_types": stats["types"],
        }

        if stats["count"] > 0:
            # Fund has signals — it's working to some degree
            has_signals.append({**entry, "priority": "working"})
        elif extractor_info and not extractor_info["has_news"]:
            # Extractor exists but no extract_news — Priority A (just add function)
            needs_news_extractor.append({
                **entry,
                "priority": "A",
                "extractor_file": extractor_info["file"],
                "has_portfolio": extractor_info["has_portfolio"],
                "has_team": extractor_info["has_team"],
            })
        elif extractor_info and extractor_info["has_news"]:
            # Has extract_news but no signals — Priority B (broken, needs fixing)
            has_news_no_signals.append({
                **entry,
                "priority": "B",
                "extractor_file": extractor_info["file"],
            })
        else:
            # No extractor at all — Priority C (create from scratch)
            needs_new_extractor.append({
                **entry,
                "priority": "C",
            })

    # Sort within each priority: pe/vc first, then alphabetical
    for lst in [needs_news_extractor, has_news_no_signals, needs_new_extractor]:
        lst.sort(key=lambda x: (category_sort_key(x["category"]), x["slug"]))

    queue = {
        "phase": "signal_quality_improvement",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_funds": len(funds),
            "needs_news_extractor": len(needs_news_extractor),
            "has_news_no_signals": len(has_news_no_signals),
            "needs_new_extractor": len(needs_new_extractor),
            "has_signals": len(has_signals),
            "no_website": len(no_website),
        },
        "needs_news_extractor": needs_news_extractor,
        "has_news_no_signals": has_news_no_signals,
        "needs_new_extractor": needs_new_extractor,
        "in_progress": {},
        "completed": [],
        "skipped": [],
        "has_signals": has_signals,
        "no_website": no_website,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(queue, f, indent=2)

    # Print summary
    print("=" * 60)
    print("SIGNAL WORK QUEUE GENERATED")
    print("=" * 60)
    print()
    print(f"Total funds:              {len(funds)}")
    print(f"Priority A (add news fn): {len(needs_news_extractor)}")
    print(f"Priority B (fix broken):  {len(has_news_no_signals)}")
    print(f"Priority C (new extract): {len(needs_new_extractor)}")
    print(f"Already has signals:      {len(has_signals)}")
    print(f"No website (skip):        {len(no_website)}")
    print()
    print(f"Output: {OUTPUT_PATH}")
    print()

    if needs_news_extractor:
        print("Top 5 Priority A (add extract_news to existing extractor):")
        for item in needs_news_extractor[:5]:
            print(f"  {item['slug']}: {item['extractor_file']} ({item['category']})")

    if has_news_no_signals:
        print()
        print("Top 5 Priority B (fix broken extract_news):")
        for item in has_news_no_signals[:5]:
            print(f"  {item['slug']}: {item['extractor_file']} ({item['category']})")

    if needs_new_extractor:
        print()
        print("Top 5 Priority C (create new extractor):")
        for item in needs_new_extractor[:5]:
            print(f"  {item['slug']}: {item['domain']} ({item['category']})")


if __name__ == "__main__":
    generate_queue()
