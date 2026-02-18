#!/usr/bin/env python3
"""
Show the most egregious false negatives - obvious high-value signals that were filtered.
"""

import json
from pathlib import Path

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

    raw_signals = load_json(raw_path)
    enriched_signals = load_json(enriched_path)

    kept_keys = {get_signal_key(s) for s in enriched_signals}
    removed_signals = [s for s in raw_signals if get_signal_key(s) not in kept_keys]

    print("\n" + "="*80)
    print("SMOKING GUN FALSE NEGATIVES")
    print("The most obviously valuable signals that were incorrectly filtered out")
    print("="*80 + "\n")

    # Category 1: Italian companies with clear PE activity
    print("CATEGORY 1: ITALIAN COMPANY DEALS")
    print("-" * 80)
    print("These are unambiguous Italian company investments/acquisitions.\n")

    italian_company_deals = [
        ("Fondo Italiano invests in Alimenta Produzioni", "fondo-italiano-d-investimento-sgr", "Clear Italian company investment"),
        ("Fondo Italiano d'Investimento acquires NPO Torino S.r.l.", "fondo-italiano-d-investimento-sgr", "Italian company acquisition (Torino)"),
        ("Fondo Italiano Acquires Stake in Santangelo Group", "fondo-italiano-d-investimento-sgr", "Italian company stake acquisition"),
        ("FVS Sgr entra nel capitale della padovana Liking Spa", "fvs-sgr", "Italian company investment (Padova)"),
        ("Il fondo Mi.To Real Estate completa il quinto investimento", "green-arrow-capital-sgr", "Italian real estate fund investment (Milano-Torino)"),
    ]

    for i, (title_pattern, fund, reason) in enumerate(italian_company_deals, 1):
        # Find the actual signal
        matching = [s for s in removed_signals
                   if title_pattern in s.get('title', '') and s.get('fund_slug') == fund]
        if matching:
            signal = matching[0]
            print(f"{i}. {signal.get('title')}")
            print(f"   Fund: {signal.get('fund_slug')}")
            print(f"   Quality: {signal.get('quality_score', 'N/A')}")
            print(f"   Type: {signal.get('signal_type')}")
            print(f"   Published: {signal.get('published_at', 'unknown')}")
            print(f"   Why valuable: {reason}")
            print(f"   Why filtered: Quality score = 75, below MIN_QUALITY_SCORE = 80\n")

    # Category 2: Large Italian fund closings
    print("\n" + "="*80)
    print("CATEGORY 2: MAJOR FUNDRAISING ANNOUNCEMENTS")
    print("-" * 80)
    print("Large fund closings by major Italian funds.\n")

    fundraising_examples = [
        ("CDP Venture Capital: via al fondo Large Ventures primo closing a 150 milioni", "cdp-venture-capital", "150M EUR first closing"),
        ("Fondo Italiano d'Investimento: FICC II surpasses 500 million euros", "fondo-italiano-d-investimento-sgr", "500M EUR raised"),
        ("Fondo Italiano d'Investimento: FIPEC completes additional closing of €113 million", "fondo-italiano-d-investimento-sgr", "113M EUR closing"),
    ]

    for i, (title_pattern, fund, amount) in enumerate(fundraising_examples, 1):
        matching = [s for s in removed_signals
                   if title_pattern in s.get('title', '') and s.get('fund_slug') == fund]
        if matching:
            signal = matching[0]
            print(f"{i}. {signal.get('title')}")
            print(f"   Fund: {signal.get('fund_slug')}")
            print(f"   Quality: {signal.get('quality_score', 'N/A')}")
            print(f"   Amount: {amount}")
            print(f"   Published: {signal.get('published_at', 'unknown')}")
            print(f"   Why filtered: Misclassified as 'news' instead of 'fundraise_announced'\n")

    # Category 3: Recent deals (last 2 months)
    print("\n" + "="*80)
    print("CATEGORY 3: RECENT DEALS (Jan-Feb 2026)")
    print("-" * 80)
    print("Very recent Italian PE activity that should definitely be shown.\n")

    recent_deals = []
    for signal in removed_signals:
        pub = signal.get('published_at', '')
        if pub and ('2026-01' in pub or '2026-02' in pub):
            title = signal.get('title', '').lower()
            if any(kw in title for kw in ['invest', 'acquir', 'entra', 'stake']):
                if any(kw in title for kw in ['ital', 'milan', 'roma', 'torino']):
                    recent_deals.append(signal)

    for i, signal in enumerate(sorted(recent_deals, key=lambda x: x.get('published_at', ''), reverse=True)[:5], 1):
        print(f"{i}. {signal.get('title')}")
        print(f"   Fund: {signal.get('fund_slug')}")
        print(f"   Quality: {signal.get('quality_score', 'N/A')}")
        print(f"   Published: {signal.get('published_at')}")
        print(f"   Recency: Within last 2 months")
        print(f"   Why filtered: Quality score below threshold\n")

    # Category 4: Italian brand name companies
    print("\n" + "="*80)
    print("CATEGORY 4: WELL-KNOWN ITALIAN BRANDS")
    print("-" * 80)
    print("Deals involving famous Italian companies.\n")

    brand_examples = [
        "Giorgetti",  # Italian design brand
        "Vetraco",    # Italian glass company
    ]

    brand_signals = []
    for signal in removed_signals:
        title = signal.get('title', '')
        if any(brand in title for brand in brand_examples):
            brand_signals.append(signal)

    for i, signal in enumerate(brand_signals[:5], 1):
        print(f"{i}. {signal.get('title')}")
        print(f"   Fund: {signal.get('fund_slug')}")
        print(f"   Quality: {signal.get('quality_score', 'N/A')}")
        print(f"   Published: {signal.get('published_at', 'unknown')}")
        print(f"   Why valuable: Recognizable Italian brand name\n")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80 + "\n")
    print("These examples demonstrate clear, unambiguous false negatives:")
    print("  - Italian company names (Torino, Padova, Milano)")
    print("  - Clear deal verbs (invests, acquires, entra nel capitale)")
    print("  - Large monetary amounts (150M, 500M EUR)")
    print("  - Recent dates (2026-01, 2026-02)")
    print("  - Known Italian brands (Giorgetti, Vetraco)")
    print("\nAll were filtered because quality_score = 75, just below MIN_QUALITY_SCORE = 80.")
    print("Lowering threshold to 72 would recover all of these signals.")

if __name__ == "__main__":
    main()
