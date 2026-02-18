#!/usr/bin/env python3
"""
Find signals that should be classified as portfolio_update but are currently misclassified.
"""

import json
import re
from pathlib import Path

def get_repo_root():
    """Get repository root directory."""
    return Path(__file__).parent

# Patterns for portfolio company operational news
PORTFOLIO_OPERATIONAL_PATTERNS = [
    # Revenue and financial targets
    r'\bexpects?\s+revenues?\b',
    r'\btargets?\s+revenues?\b',
    r'\bforecasts?\s+revenues?\b',
    r'\bprevede\s+ricavi\b',
    r'\bobiettivo\s+di\s+fatturato\b',
    r'\braggiungere\s+.*\s+milion[ei]\b',

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
    r'\bcrescita\s+del\s+\d+%\b',

    # Operational activities
    r'\bhiring\s+\d+\s+people\b',
    r'\brecruiting\s+for\b',
    r'\bassume\s+\d+\b',
    r'\bpartnership\s+with\b',  # company partnerships (not fund partnerships)
    r'\baccordo\s+con\b',
    r'\bcontratto\s+con\b',
]

# Patterns that indicate portfolio company context
PORTFOLIO_COMPANY_PATTERNS = [
    r'\bportfolio\s+compan(?:y|ies)\b',
    r'\bportafoglio\b.*\bsociet[àa]\b',
    r'\bpartecipat[aeio]\b',
    r'\bin\s+cui\s+.*\s+ha\s+investito\b',
    r'\bsostenuta\s+da\b',
    r'\bcon\s+il\s+supporto\s+di\b',
]

# Patterns that indicate fund-level activity (NOT portfolio updates)
FUND_LEVEL_PATTERNS = [
    r'\b(fund|fondo)\s+(invests?|acquires?|sells?|exits?)\b',
    r'\b(completed|announced|signed)\s+.*\s+(investment|acquisition|deal)\b',
    r"\bha\s+(investito|acquisito|ceduto|venduto)\b",
    r"\bchiude\s+l['']investimento\b",
    r"\bfinalizza\s+l['']acquisizione\b.*\bdi\b",  # "finalizes acquisition OF company X"
]

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
            misclassified.append({
                'id': signal.get('id'),
                'fund_slug': signal.get('fund_slug'),
                'signal_type': signal_type,
                'title': signal.get('title', ''),
                'enriched_summary': signal.get('enriched_summary', '')[:150],
                'source_name': signal.get('source_name', ''),
            })

    return misclassified

def main():
    """Main function."""
    print("Analyzing enriched signals for misclassifications...")
    print("=" * 80)

    misclassified = analyze_signals()

    print(f"\nFound {len(misclassified)} signals that should be portfolio_update:\n")

    for i, signal in enumerate(misclassified, 1):
        print(f"{i}. ID: {signal['id']}")
        print(f"   Fund: {signal['fund_slug']}")
        print(f"   Current type: {signal['signal_type']}")
        print(f"   Source: {signal['source_name']}")
        print(f"   Title: {signal['title']}")
        print(f"   Summary: {signal['enriched_summary']}...")
        print()

    # Group by current signal_type
    by_type = {}
    for signal in misclassified:
        current_type = signal['signal_type']
        by_type.setdefault(current_type, []).append(signal)

    print("\n" + "=" * 80)
    print("Summary by current signal type:")
    for signal_type, signals in sorted(by_type.items()):
        print(f"  {signal_type}: {len(signals)} signals")

    print(f"\nTotal: {len(misclassified)} signals need reclassification")

if __name__ == '__main__':
    main()
