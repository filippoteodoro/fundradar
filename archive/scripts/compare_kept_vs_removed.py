#!/usr/bin/env python3
"""
Compare kept vs removed signals to find the filter threshold.
"""

import json
from pathlib import Path
from collections import defaultdict

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

def main():
    repo_root = Path(__file__).parent.parent
    raw_path = repo_root / "data/derived/detected_signals.json"
    enriched_path = repo_root / "data/derived/detected_signals_enriched.json"

    print("Loading signals...")
    raw_signals = load_json(raw_path)
    enriched_signals = load_json(enriched_path)

    # Build lookup
    kept_keys = {get_signal_key(s) for s in enriched_signals}
    kept_signals = [s for s in raw_signals if get_signal_key(s) in kept_keys]
    removed_signals = [s for s in raw_signals if get_signal_key(s) not in kept_keys]

    print(f"Kept: {len(kept_signals)}")
    print(f"Removed: {len(removed_signals)}")

    # Analyze quality scores
    print("\n" + "="*80)
    print("QUALITY SCORE ANALYSIS")
    print("="*80 + "\n")

    kept_with_score = [s for s in kept_signals if 'quality_score' in s]
    removed_with_score = [s for s in removed_signals if 'quality_score' in s]

    if kept_with_score:
        scores = [s['quality_score'] for s in kept_with_score]
        print(f"KEPT signals with quality_score: {len(kept_with_score)}")
        print(f"  Min: {min(scores)}")
        print(f"  Max: {max(scores)}")
        print(f"  Avg: {sum(scores)/len(scores):.1f}")

    if removed_with_score:
        scores = [s['quality_score'] for s in removed_with_score]
        print(f"\nREMOVED signals with quality_score: {len(removed_with_score)}")
        print(f"  Min: {min(scores)}")
        print(f"  Max: {max(scores)}")
        print(f"  Avg: {sum(scores)/len(scores):.1f}")

        # Show distribution
        score_buckets = defaultdict(int)
        for score in scores:
            bucket = (score // 10) * 10
            score_buckets[bucket] += 1

        print(f"\n  Score distribution:")
        for bucket in sorted(score_buckets.keys()):
            print(f"    {bucket:3d}-{bucket+9:3d}: {score_buckets[bucket]:4d} signals")

    # Check italy_relevant field
    print("\n" + "="*80)
    print("ITALY RELEVANCE ANALYSIS")
    print("="*80 + "\n")

    kept_italy_relevant = [s for s in kept_signals if s.get('italy_relevant') == True]
    kept_not_relevant = [s for s in kept_signals if s.get('italy_relevant') == False]
    removed_italy_relevant = [s for s in removed_signals if s.get('italy_relevant') == True]
    removed_not_relevant = [s for s in removed_signals if s.get('italy_relevant') == False]

    print(f"KEPT signals:")
    print(f"  italy_relevant=True:  {len(kept_italy_relevant)}")
    print(f"  italy_relevant=False: {len(kept_not_relevant)}")
    print(f"  No italy_relevant:    {len(kept_signals) - len(kept_italy_relevant) - len(kept_not_relevant)}")

    print(f"\nREMOVED signals:")
    print(f"  italy_relevant=True:  {len(removed_italy_relevant)}")
    print(f"  italy_relevant=False: {len(removed_not_relevant)}")
    print(f"  No italy_relevant:    {len(removed_signals) - len(removed_italy_relevant) - len(removed_not_relevant)}")

    # Check signal types
    print("\n" + "="*80)
    print("SIGNAL TYPE COMPARISON")
    print("="*80 + "\n")

    kept_types = defaultdict(int)
    removed_types = defaultdict(int)

    for s in kept_signals:
        kept_types[s.get('signal_type', 'unknown')] += 1
    for s in removed_signals:
        removed_types[s.get('signal_type', 'unknown')] += 1

    all_types = sorted(set(kept_types.keys()) | set(removed_types.keys()))

    print(f"{'Type':25} {'Kept':>8} {'Removed':>8} {'Keep %':>8}")
    print("-" * 80)
    for sig_type in all_types:
        kept = kept_types[sig_type]
        removed = removed_types[sig_type]
        total = kept + removed
        keep_pct = (kept / total * 100) if total > 0 else 0
        print(f"{sig_type:25} {kept:8d} {removed:8d} {keep_pct:7.1f}%")

    # Show some high-quality removed signals
    print("\n" + "="*80)
    print("HIGH-QUALITY REMOVED SIGNALS (score >= 75)")
    print("="*80 + "\n")

    high_quality_removed = [s for s in removed_signals
                           if s.get('quality_score', 0) >= 75]
    high_quality_removed.sort(key=lambda x: x.get('quality_score', 0), reverse=True)

    for i, signal in enumerate(high_quality_removed[:20], 1):
        print(f"{i}. [{signal.get('quality_score')}] {signal.get('fund_slug')} / {signal.get('signal_type')}")
        print(f"   {signal.get('title', 'no title')[:100]}")
        if signal.get('italy_relevant') is not None:
            print(f"   italy_relevant: {signal.get('italy_relevant')}")
        if signal.get('relevance_score') is not None:
            print(f"   relevance_score: {signal.get('relevance_score')}")
        print()

if __name__ == "__main__":
    main()
