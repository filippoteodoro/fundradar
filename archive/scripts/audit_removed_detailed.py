#!/usr/bin/env python3
"""
Deep dive into specific false negatives to understand filter reasons.
"""

import json
from pathlib import Path

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if isinstance(data, dict) and 'signals' in data:
            return data['signals']
        return data

def main():
    repo_root = Path(__file__).parent.parent
    raw_path = repo_root / "data/derived/detected_signals.json"

    print("Loading raw signals...")
    raw_signals = load_json(raw_path)

    # Focus on the high-value Italian deals that were removed
    italian_deal_examples = [
        "Fondo Italiano d'Investimento entra nel capitale di Vetraco",
        "Fondo Italiano invests in Alimenta Produzioni",
        "Fondo Italiano d'Investimento and The Equity Club acquire Isoclima",
        "Fondo Italiano d'Investimento acquires NPO Torino S.r.l.",
    ]

    european_deal_examples = [
        "TPG to acquire majority stake in Conservice",
        "Charme invests in Tema Sinergie SpA",
        "Charme Capital Partners acquires Prism Healthcare",
    ]

    print("\n" + "="*80)
    print("DETAILED ANALYSIS OF KEY FALSE NEGATIVES")
    print("="*80 + "\n")

    # Find and analyze these signals
    for signal in raw_signals:
        title = signal.get('title', '')

        if any(ex in title for ex in italian_deal_examples):
            print(f"\nTITLE: {title}")
            print(f"Fund: {signal.get('fund_slug')}")
            print(f"Type: {signal.get('signal_type')}")
            print(f"Published: {signal.get('published_at')}")
            print(f"Source: {signal.get('source_name')}")
            print(f"Source URL: {signal.get('source_url', '')[:80]}")
            print(f"What changed: {signal.get('what_changed', '')[:200]}")

            # Check for quality scores or filter metadata
            if 'quality_score' in signal:
                print(f"Quality score: {signal['quality_score']}")
            if 'relevance_score' in signal:
                print(f"Relevance score: {signal['relevance_score']}")
            if 'italy_relevant' in signal:
                print(f"Italy relevant: {signal['italy_relevant']}")
            if 'filter_reason' in signal:
                print(f"Filter reason: {signal['filter_reason']}")
            if 'ml_prediction' in signal:
                print(f"ML prediction: {signal['ml_prediction']}")

            print("-" * 80)

        elif any(ex in title for ex in european_deal_examples):
            print(f"\nTITLE: {title}")
            print(f"Fund: {signal.get('fund_slug')}")
            print(f"Type: {signal.get('signal_type')}")
            print(f"Published: {signal.get('published_at')}")
            print(f"Source: {signal.get('source_name')}")
            print(f"What changed: {signal.get('what_changed', '')[:200]}")

            if 'quality_score' in signal:
                print(f"Quality score: {signal['quality_score']}")
            if 'relevance_score' in signal:
                print(f"Relevance score: {signal['relevance_score']}")
            if 'italy_relevant' in signal:
                print(f"Italy relevant: {signal['italy_relevant']}")

            print("-" * 80)

    # Count signals by type to understand what types got removed
    print("\n" + "="*80)
    print("SIGNAL TYPE DISTRIBUTION IN RAW DATA")
    print("="*80 + "\n")

    type_counts = {}
    for signal in raw_signals:
        sig_type = signal.get('signal_type', 'unknown')
        type_counts[sig_type] = type_counts.get(sig_type, 0) + 1

    for sig_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"{sig_type:25} {count:4d}")

if __name__ == "__main__":
    main()
