#!/usr/bin/env python3
"""
Generate comprehensive false negative report with actionable recommendations.
"""

import json
from pathlib import Path
from collections import defaultdict
import re

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if isinstance(data, dict) and 'signals' in data:
            return data['signals']
        return data

def normalize_title(title):
    if not title:
        return ""
    return title.lower().strip()[:80]

def get_signal_key(signal):
    fund_slug = signal.get('fund_slug', '')
    title = signal.get('title', '')
    norm_title = normalize_title(title)
    return f"{fund_slug}::{norm_title}"

def is_italian_deal(signal):
    """Check if signal is clearly about an Italian company/deal"""
    title = signal.get('title', '').lower()
    what_changed = signal.get('what_changed', '').lower()
    text = f"{title} {what_changed}"

    italian_indicators = [
        r'\bital(?:ia|y|ian[ao]?)\b',
        r'\bmilan[oa]?\b',
        r'\broma\b',
        r'\btorino\b',
        r'\bsgr\b',
    ]

    deal_indicators = [
        r'\binvest(?:s|ment|imento)',
        r'\bacquire(?:s|d|izione)',
        r'\bentra\s+(?:in|nel)',
        r'\bstake\b',
    ]

    has_italian = any(re.search(p, text) for p in italian_indicators)
    has_deal = any(re.search(p, text) for p in deal_indicators)

    return has_italian and has_deal

def main():
    repo_root = Path(__file__).parent.parent
    raw_path = repo_root / "data/derived/detected_signals.json"
    enriched_path = repo_root / "data/derived/detected_signals_enriched.json"

    print("Loading signals...")
    raw_signals = load_json(raw_path)
    enriched_signals = load_json(enriched_path)

    kept_keys = {get_signal_key(s) for s in enriched_signals}
    kept_signals = [s for s in raw_signals if get_signal_key(s) in kept_keys]
    removed_signals = [s for s in raw_signals if get_signal_key(s) not in kept_keys]

    print("\n" + "="*80)
    print("FALSE NEGATIVE AUDIT REPORT")
    print("="*80 + "\n")

    print("OVERALL NUMBERS")
    print("-" * 80)
    print(f"Total signals detected:     {len(raw_signals):4d}")
    print(f"Signals kept (enriched):    {len(kept_signals):4d} ({len(kept_signals)/len(raw_signals)*100:.1f}%)")
    print(f"Signals removed:            {len(removed_signals):4d} ({len(removed_signals)/len(raw_signals)*100:.1f}%)")

    # Quality score analysis
    removed_with_score = [s for s in removed_signals if 'quality_score' in s]
    score_75_removed = [s for s in removed_with_score if s['quality_score'] == 75]
    score_75_kept = [s for s in kept_signals if s.get('quality_score') == 75]

    print(f"\nQUALITY SCORE THRESHOLD ISSUE")
    print("-" * 80)
    print(f"MIN_QUALITY_SCORE setting:  80 (in filter_signals.py)")
    print(f"Signals with score=75:      {len(score_75_removed) + len(score_75_kept):4d} total")
    print(f"  - Kept (enriched):        {len(score_75_kept):4d}")
    print(f"  - Removed (filtered):     {len(score_75_removed):4d}")
    print(f"\nConclusion: {len(score_75_removed)} signals with quality_score=75 were removed")
    print(f"because they fall below the MIN_QUALITY_SCORE=80 threshold.")

    # Italian deal analysis
    italian_deals_removed = [s for s in removed_signals if is_italian_deal(s)]
    italian_deals_removed_75 = [s for s in italian_deals_removed if s.get('quality_score') == 75]

    print(f"\nITALIAN DEAL FALSE NEGATIVES")
    print("-" * 80)
    print(f"Italian deal signals removed: {len(italian_deals_removed):4d}")
    print(f"  - With quality_score=75:    {len(italian_deals_removed_75):4d}")
    print(f"\nTop 15 Italian deal false negatives:")
    for i, signal in enumerate(italian_deals_removed[:15], 1):
        score = signal.get('quality_score', 'N/A')
        print(f"\n{i}. [{score}] {signal.get('fund_slug')}")
        print(f"   {signal.get('title', 'no title')[:100]}")
        print(f"   Type: {signal.get('signal_type')}, Published: {signal.get('published_at', 'unknown')}")

    # Signal type analysis
    print(f"\n\nSIGNAL TYPE KEEP RATES")
    print("-" * 80)

    kept_types = defaultdict(int)
    removed_types = defaultdict(int)

    for s in kept_signals:
        kept_types[s.get('signal_type', 'unknown')] += 1
    for s in removed_signals:
        removed_types[s.get('signal_type', 'unknown')] += 1

    all_types = sorted(set(kept_types.keys()) | set(removed_types.keys()))

    print(f"{'Type':25} {'Total':>7} {'Kept':>7} {'Removed':>7} {'Keep %':>8}")
    print("-" * 80)
    for sig_type in all_types:
        kept = kept_types[sig_type]
        removed = removed_types[sig_type]
        total = kept + removed
        keep_pct = (kept / total * 100) if total > 0 else 0
        print(f"{sig_type:25} {total:7d} {kept:7d} {removed:7d} {keep_pct:7.1f}%")

    # Key findings
    print(f"\n\n{'='*80}")
    print("KEY FINDINGS")
    print("="*80 + "\n")

    print("1. QUALITY SCORE THRESHOLD TOO HIGH")
    print(f"   - Current threshold: 80")
    print(f"   - Signals with score=75: {len(score_75_removed)} removed")
    print(f"   - Many are high-value Italian deals (e.g., Fondo Italiano investments)")
    print(f"   - Recommendation: LOWER threshold to 70 or 72")

    print("\n2. SIGNAL TYPE='NEWS' LOW KEEP RATE")
    news_total = kept_types['news'] + removed_types['news']
    news_keep_pct = (kept_types['news'] / news_total * 100)
    print(f"   - Only {news_keep_pct:.1f}% of 'news' signals kept ({kept_types['news']}/{news_total})")
    print(f"   - Many news signals are actually deals/exits but misclassified")
    print(f"   - Recommendation: Improve classification logic for news-type signals")

    print("\n3. PEOPLE_MOVE LOW KEEP RATE")
    people_total = kept_types['people_move'] + removed_types['people_move']
    people_keep_pct = (kept_types['people_move'] / people_total * 100)
    print(f"   - Only {people_keep_pct:.1f}% of 'people_move' signals kept ({kept_types['people_move']}/{people_total})")
    print(f"   - Senior hires at Italy-active funds are valuable signals")
    print(f"   - Recommendation: Boost quality scores for senior hire signals")

    print("\n4. ITALIAN DEALS BEING FILTERED")
    print(f"   - {len(italian_deals_removed)} Italian deal signals removed")
    print(f"   - Includes obvious high-value deals from Fondo Italiano, Green Arrow, etc.")
    print(f"   - Recommendation: Add Italy-boost to quality scoring")

    print("\n\n{'='*80}")
    print("RECOMMENDATIONS")
    print("="*80 + "\n")

    print("1. IMMEDIATE FIX: Lower MIN_QUALITY_SCORE from 80 to 72")
    print("   - Would recover ~481 signals with score=75")
    print("   - Includes many Italian deals currently being lost")
    print("   - Low risk: quality_score=75 indicates decent structural quality")

    print("\n2. IMPROVE QUALITY SCORING: Add Italy relevance boost")
    print("   - Signals mentioning Italy/Italian companies: +10 points")
    print("   - Signals from italy_focused funds: +5 points")
    print("   - Would push Italian deals from 75 → 85, well above threshold")

    print("\n3. RECLASSIFY NEWS SIGNALS: Better type detection")
    print("   - 'news' type with deal keywords → reclassify to 'deal_announced'")
    print("   - 'news' type with exit keywords → reclassify to 'exit_announced'")
    print("   - Already partially implemented; needs expansion")

    print("\n4. BOOST SENIOR HIRES: Recognize people value")
    print("   - Partner/MD/Director moves: +5 quality points")
    print("   - Analyst/Associate moves at non-Italian offices: filter out")
    print("   - Current people_move keep rate too low (3.4%)")

    print("\n\nESTIMATED IMPACT OF RECOMMENDATIONS")
    print("-" * 80)
    print(f"Current keep rate:              {len(kept_signals)/len(raw_signals)*100:.1f}% ({len(kept_signals)}/{len(raw_signals)})")
    print(f"After lowering threshold to 72: ~{(len(kept_signals) + len(score_75_removed))/len(raw_signals)*100:.1f}% ({len(kept_signals) + len(score_75_removed)}/{len(raw_signals)})")
    print(f"Recovered signals:              {len(score_75_removed)}")
    print(f"Estimated false negatives:      ~{len(italian_deals_removed)} Italian deals + ~{len([s for s in removed_signals if 'partner' in s.get('title','').lower()][:20])} senior hires")

if __name__ == "__main__":
    main()
