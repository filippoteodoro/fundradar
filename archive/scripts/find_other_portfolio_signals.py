#!/usr/bin/env python3
"""
Find signals classified as 'other' that should be portfolio_update.
"""

import json
import re
from pathlib import Path

def get_repo_root():
    """Get repository root directory."""
    return Path(__file__).parent

# Company operational indicators
COMPANY_OPERATIONAL_KEYWORDS = [
    'revenue', 'ricavi', 'fatturato', 'turnover',
    'growth', 'crescita',
    'expansion', 'espansione', 'espande',
    'target', 'obiettivo', 'targets',
    'milestone', 'traguardo',
    'forecast', 'previsione', 'prevede',
    'expects', 'aspetta',
    'plans to', 'pianifica',
    'launches', 'lancia',
    'opens', 'apre',
    'enters', 'entra',
    'hiring', 'assume',
    'recruiting', 'ricerca',
    'partnership', 'accordo', 'contratto',
    'product launch', 'lancio prodotto',
    'market expansion', 'espansione mercato',
    'new market', 'nuovo mercato',
    'acquisition of', 'acquisizione di',  # Company acquiring someone
    'acquires', 'acquisisce',
    'completes', 'completa',
    'announces', 'annuncia',
]

# Portfolio company indicators
PORTFOLIO_INDICATORS = [
    'portfolio company', 'portfolio companies',
    'società in portafoglio', 'partecipata',
    'backed by', 'sostenuta da',
    'supported by', 'supporto di',
    'investee', 'investita',
]

def analyze_other_signals():
    """Analyze signals classified as 'other'."""
    repo_root = get_repo_root()
    signals_path = repo_root / 'data' / 'derived' / 'detected_signals_enriched.json'

    with open(signals_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    signals = data.get('signals', [])

    # Find 'other' signals that look like portfolio updates
    candidates = []

    for signal in signals:
        signal_type = signal.get('signal_type', '')

        # Only check 'other' signals
        if signal_type != 'other':
            continue

        title = signal.get('title', '').lower()
        summary = signal.get('enriched_summary', '').lower()
        text = title + ' ' + summary

        # Check for portfolio indicators
        has_portfolio_indicator = any(
            indicator.lower() in text
            for indicator in PORTFOLIO_INDICATORS
        )

        # Check for operational keywords
        has_operational_keywords = any(
            keyword.lower() in text
            for keyword in COMPANY_OPERATIONAL_KEYWORDS
        )

        # Check for company-level business metrics
        has_metrics = bool(re.search(
            r'\b\d+\s*(million|billion|milion[ei]|miliard[oi]|mln|mld)\b',
            text
        ))

        # Check if it mentions specific company names (usually caps)
        # and business activities
        has_company_activity = bool(re.search(
            r'\b[A-Z][a-z]+\s+(launches|announces|expands|opens|completes|acquires|enters|targets|expects|plans)\b',
            title + ' ' + signal.get('enriched_summary', '')
        ))

        # Include if it has any strong indicators
        if (has_portfolio_indicator or
            (has_operational_keywords and has_metrics) or
            has_company_activity):

            candidates.append({
                'id': signal.get('id'),
                'fund_slug': signal.get('fund_slug'),
                'signal_type': signal_type,
                'title': signal.get('title', ''),
                'enriched_summary': signal.get('enriched_summary', '')[:200],
                'source_name': signal.get('source_name', ''),
                'has_portfolio_indicator': has_portfolio_indicator,
                'has_operational_keywords': has_operational_keywords,
                'has_metrics': has_metrics,
                'has_company_activity': has_company_activity,
            })

    return candidates

def main():
    """Main function."""
    print("Analyzing 'other' signals for potential portfolio_update reclassification...")
    print("=" * 80)

    candidates = analyze_other_signals()

    print(f"\nFound {len(candidates)} 'other' signals that might be portfolio_update:\n")

    for i, signal in enumerate(candidates, 1):
        print(f"{i}. ID: {signal['id']}")
        print(f"   Fund: {signal['fund_slug']}")
        print(f"   Source: {signal['source_name']}")
        print(f"   Indicators: ", end="")
        flags = []
        if signal['has_portfolio_indicator']:
            flags.append("PORTFOLIO")
        if signal['has_operational_keywords']:
            flags.append("OPERATIONAL")
        if signal['has_metrics']:
            flags.append("METRICS")
        if signal['has_company_activity']:
            flags.append("COMPANY_ACTIVITY")
        print(", ".join(flags))
        print(f"   Title: {signal['title']}")
        print(f"   Summary: {signal['enriched_summary']}...")
        print()

    print(f"\nTotal: {len(candidates)} 'other' signals need review")

if __name__ == '__main__':
    main()
