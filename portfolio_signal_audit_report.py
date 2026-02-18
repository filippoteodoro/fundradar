#!/usr/bin/env python3
"""
Comprehensive audit of signals that should be classified as portfolio_update.
"""

import json
import re
from pathlib import Path
from collections import defaultdict

def get_repo_root():
    """Get repository root directory."""
    return Path(__file__).parent

# Patterns for portfolio company operational news
PORTFOLIO_OPERATIONAL_PATTERNS = [
    # Revenue and financial targets
    r'\bexpects?\s+revenues?\b',
    r'\btargets?\s+revenues?\b',
    r'\bforecasts?\s+revenues?\b',
    r"\bprevede\s+ricavi\b",
    r"\bobiettivo\s+di\s+fatturato\b",
    r"\braggiungere\s+.*\s+milion[ei]\b",

    # Growth and expansion
    r'\bplans?\s+to\s+(expand|grow|launch|open|hire)\b',
    r'\bexpands?\s+into\b',
    r'\bopens?\s+new\b',
    r'\blaunches?\s+(new\s+)?(product|service|initiative)\b',
    r'\benters?\s+new\s+market\b',
    r"\bsi\s+espande\b",
    r"\bapre\s+nuov[oi]\b",
    r"\blancia\s+(nuovo|nuova)\b",

    # Business milestones
    r'\b(achieves?|reaches?|hits?)\s+(milestone|target|goal)\b',
    r"\braggiunge\s+l['']obiettivo\b",
    r'\bcompletes?\s+(acquisition|merger|integration)\b',
    r"\bfinalizza\s+l['']acquisizione\b",

    # Company-level metrics
    r'\b\d+\s*(million|billion|milion[ei]|miliard[oi])\s+(euros?|eur|dollars?|usd)\s+(revenue|turnover|ricavi|fatturato)\b',
    r'\b(revenue|turnover|ricavi|fatturato)\s+of\s+\d+\b',
    r'\bgrowth\s+of\s+\d+%\b',
    r"\bcrescita\s+del\s+\d+%\b",

    # Operational activities
    r'\bhiring\s+\d+\s+people\b',
    r'\brecruiting\s+for\b',
    r"\bassume\s+\d+\b",
    r'\bpartnership\s+with\b',
    r"\baccordo\s+con\b",
    r"\bcontratto\s+con\b",
]

# Patterns that indicate portfolio company context
PORTFOLIO_COMPANY_PATTERNS = [
    r'\bportfolio\s+compan(?:y|ies)\b',
    r"\bportafoglio\b.*\bsociet[àa]\b",
    r"\bpartecipat[aeio]\b",
    r"\bin\s+cui\s+.*\s+ha\s+investito\b",
    r"\bsostenuta\s+da\b",
    r"\bcon\s+il\s+supporto\s+di\b",
]

# Patterns that indicate fund-level activity (NOT portfolio updates)
FUND_LEVEL_PATTERNS = [
    r'\b(fund|fondo)\s+(invests?|acquires?|sells?|exits?)\b',
    r'\b(completed|announced|signed)\s+.*\s+(investment|acquisition|deal)\b',
    r"\bha\s+(investito|acquisito|ceduto|venduto)\b",
    r"\bchiude\s+l['']investimento\b",
    r"\bfinalizza\s+l['']acquisizione\b.*\bdi\b",  # "finalizes acquisition OF company X"
]

def classify_reason(signal):
    """Determine why signal should be portfolio_update."""
    text = (signal.get('title', '') + ' ' + signal.get('enriched_summary', '')).lower()
    reasons = []

    # Check for portfolio company indicators
    for pattern in PORTFOLIO_COMPANY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            reasons.append("Has portfolio company context")
            break

    # Check for operational news patterns
    for pattern in PORTFOLIO_OPERATIONAL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            reasons.append(f"Operational news: {match.group()}")
            break

    # Check for revenue/metrics
    if re.search(r'\b\d+\s*(million|billion|milion[ei]|miliard[oi]|mln|mld)\b', text):
        reasons.append("Contains financial metrics")

    # Check for company expansion
    if re.search(r'\b(espande|expands?|opens?|apre|lancia|launches?)\b', text):
        reasons.append("Company expansion/launch activity")

    return reasons

def should_be_portfolio_update(signal):
    """Check if a signal should be classified as portfolio_update."""
    text = (signal.get('title', '') + ' ' + signal.get('enriched_summary', '')).lower()

    # Skip if clearly fund-level activity
    for pattern in FUND_LEVEL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False

    # Check for portfolio company indicators
    has_portfolio_context = any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in PORTFOLIO_COMPANY_PATTERNS
    )

    # Check for operational news patterns
    has_operational_news = any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in PORTFOLIO_OPERATIONAL_PATTERNS
    )

    # Signal should be portfolio_update if:
    # 1. Has explicit portfolio context, OR
    # 2. Has operational news patterns (company doing something, not fund doing something)
    return has_portfolio_context or has_operational_news

def analyze_signals():
    """Analyze enriched signals for misclassifications."""
    repo_root = get_repo_root()
    signals_path = repo_root / 'data' / 'derived' / 'detected_signals_enriched.json'

    with open(signals_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    signals = data.get('signals', [])

    # Find misclassified signals
    misclassified = []

    for signal in signals:
        signal_type = signal.get('signal_type', '')

        # Only check signals that are NOT already portfolio_update
        if signal_type == 'portfolio_update':
            continue

        # Check if signal should be portfolio_update
        if should_be_portfolio_update(signal):
            reasons = classify_reason(signal)
            misclassified.append({
                'id': signal.get('id'),
                'fund_slug': signal.get('fund_slug'),
                'signal_type': signal_type,
                'title': signal.get('title', ''),
                'enriched_summary': signal.get('enriched_summary', '')[:150],
                'source_name': signal.get('source_name', ''),
                'reasons': reasons,
            })

    return misclassified

def main():
    """Main function."""
    print("=" * 100)
    print("PORTFOLIO_UPDATE SIGNAL AUDIT REPORT")
    print("=" * 100)
    print("\nAnalyzing all signals for potential portfolio_update reclassification...")

    misclassified = analyze_signals()

    print(f"\n>>> FOUND {len(misclassified)} SIGNALS THAT SHOULD BE portfolio_update <<<\n")

    # Group by current signal_type
    by_type = defaultdict(list)
    for signal in misclassified:
        by_type[signal['signal_type']].append(signal)

    print("\nSUMMARY BY CURRENT SIGNAL TYPE:")
    print("-" * 100)
    for signal_type in sorted(by_type.keys()):
        print(f"  {signal_type:25s}: {len(by_type[signal_type]):3d} signals")
    print("-" * 100)
    print(f"  {'TOTAL':25s}: {len(misclassified):3d} signals\n")

    # Print detailed list
    print("\n" + "=" * 100)
    print("DETAILED LIST")
    print("=" * 100)

    for i, signal in enumerate(misclassified, 1):
        print(f"\n{i}. ID: {signal['id']}")
        print(f"   Fund Slug:     {signal['fund_slug']}")
        print(f"   Current Type:  {signal['signal_type']}")
        print(f"   Source:        {signal['source_name']}")
        print(f"   Title:         {signal['title']}")
        print(f"   Summary:       {signal['enriched_summary']}...")
        print(f"   Reasons:       {', '.join(signal['reasons']) if signal['reasons'] else 'No specific reason'}")

    # Special section for 'other' signals
    other_signals = by_type.get('other', [])
    if other_signals:
        print("\n" + "=" * 100)
        print(f"FOCUS: 'other' SIGNALS ({len(other_signals)} signals)")
        print("=" * 100)
        print("\nThese signals are currently classified as 'other' but show clear portfolio company activity:\n")
        for i, signal in enumerate(other_signals, 1):
            print(f"{i}. {signal['fund_slug']:30s} | {signal['title'][:60]}")

    # Special section for 'partnership' signals
    partnership_signals = by_type.get('partnership', [])
    if partnership_signals:
        print("\n" + "=" * 100)
        print(f"FOCUS: 'partnership' SIGNALS ({len(partnership_signals)} signals)")
        print("=" * 100)
        print("\nThese signals are about portfolio company partnerships, not fund-level partnerships:\n")
        for i, signal in enumerate(partnership_signals, 1):
            print(f"{i}. {signal['fund_slug']:30s} | {signal['title'][:60]}")

    # Special section for 'deal_announced' signals
    deal_signals = by_type.get('deal_announced', [])
    if deal_signals:
        print("\n" + "=" * 100)
        print(f"FOCUS: 'deal_announced' SIGNALS ({len(deal_signals)} signals)")
        print("=" * 100)
        print("\nThese signals are about portfolio companies making deals, not the fund making new investments:\n")
        for i, signal in enumerate(deal_signals, 1):
            print(f"{i}. {signal['fund_slug']:30s} | {signal['title'][:60]}")

    print("\n" + "=" * 100)
    print("END OF REPORT")
    print("=" * 100)

if __name__ == '__main__':
    main()
