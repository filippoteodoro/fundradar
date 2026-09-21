#!/usr/bin/env python3
"""
Audit signal classification accuracy by checking event_type against title/what_changed/enriched_summary.
"""

import json
from pathlib import Path
import re
from collections import defaultdict
from typing import List, Dict, Tuple

# Signal type definitions
SIGNAL_TYPES = {
    'deal_announced': 'Fund INVESTS in / ACQUIRES a company. Portfolio company raises a round.',
    'exit_announced': 'Fund SELLS / DIVESTS a portfolio company',
    'fundraise_announced': 'The FUND ITSELF raises capital from LPs',
    'fundraise_closed': 'The FUND ITSELF closes fundraising from LPs',
    'fund_launch': 'New FUND VEHICLE created (fondo, fund, comparto, veicolo)',
    'people_move': 'Key hire, appointment, board change',
    'partnership': 'Collaboration/agreement between fund and another entity',
    'report': 'Annual report, sustainability report, financial results',
    'job_posting': 'Hiring/career opportunity',
    'other': 'Events, conferences, generic news, strategic initiatives',
    'website_change': 'Generic website updates'
}

# Pattern definitions for classification
PATTERNS = {
    'deal': [
        r'\b(invests? in|acquires?|acquisition|invested?|investimento|investe|entra nel capitale|sostiene|partnership)\b',
        r'\braises?\s+[\€\$]?\d+[\.,\d]*\s*(m|M|million|milion[ie]|k|K)\b',  # startup raises
        r'\b(round|serie[sA-Z]|series\s+[A-Z]|finanziamento)\b',
        r'\b(finalizzat[oa]|concessi)\b',
    ],
    'exit': [
        r'\b(sells?|sold|vendut[oa]|vend[eono]|cede|cession[ei]|exit|divestment|divest)\b',
        r'\b(acquistat[oa]\s+da|bought\s+by|acquired\s+by)\b',
    ],
    'fundraise': [
        r'\b(fund\s+(raises?|raised|chiude|raccoglie|close[ds]?|closing)|raccoglie\s+[\€\$]?\d+)',
        r'\b(first\s+close?|primo\s+closing|final\s+close?|target\s+fund|fondo.*obiettivo)\b',
        r'\b(limited\s+partner|LP|sottoscrittori|sottoscrizione)\b',
    ],
    'fund_launch': [
        r'\b(lancia|launch|nuovo\s+fondo|new\s+fund|nasce.*fondo|nascita.*fondo)\b',
        r'\b(fondo.*costituito|fondo.*creato|fund.*created|veicolo)\b',
    ],
    'accelerator_not_fund': [
        r'\b(lancia|launch).*(accelerat|programma|hub|polo|incubat|academy)\b',
        r'\b(accelerat|programma|hub|polo|incubat|academy).*(lancia|launch|nasce)\b',
    ],
    'people_move': [
        r'\b(appoint|nomina|hire|assume|join|entra\s+in|nuovo\s+(ceo|cfo|cda|consiglio|managing\s+director|partner))\b',
        r'\b(board|consiglio|cda|management\s+team)\b',
    ],
    'partnership': [
        r'\b(partnership|collabora|accordo|agreement|alleanza|memorandum)\b',
    ],
    'report': [
        r'\b(annual\s+report|bilancio|sustainability|esg|financial\s+results|report|relazione)\b',
    ],
    'job_posting': [
        r'\b(lavora\s+con\s+noi|posizione\s+apert|cerchiamo|selezione|hiring|job|career)\b',
    ],
    'event': [
        r'\b(conferenz|evento|summit|convegno|forum|incontro|partecipa|speak|panel)\b',
    ]
}

def check_patterns(text: str, pattern_list: List[str]) -> bool:
    """Check if any pattern matches the text (case-insensitive)."""
    if not text:
        return False
    text_lower = text.lower()
    for pattern in pattern_list:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False

def classify_signal(signal: Dict) -> Tuple[str, str]:
    """
    Classify a signal based on its content.
    Returns (predicted_type, reasoning)
    """
    title = signal.get('title', '')
    what_changed = signal.get('what_changed', '')
    summary = signal.get('enriched_summary', '')

    # Combine all text for analysis
    full_text = f"{title} {what_changed} {summary}"

    # Check for accelerator/program (should be 'other', NOT 'fund_launch')
    if check_patterns(full_text, PATTERNS['accelerator_not_fund']):
        if 'fondo' in full_text.lower() or 'fund' in full_text.lower():
            # Has both fund and accelerator - could be fund_launch if genuine fund
            pass
        else:
            return 'other', 'Accelerator/program/hub launch (not a fund vehicle)'

    # Check for fund_launch
    if check_patterns(full_text, PATTERNS['fund_launch']):
        return 'fund_launch', 'New fund vehicle launch detected'

    # Check for exit
    if check_patterns(full_text, PATTERNS['exit']):
        return 'exit_announced', 'Exit/sale language detected'

    # Check for fundraise (fund itself raising)
    if check_patterns(full_text, PATTERNS['fundraise']):
        # Disambiguate: is it the fund or a portfolio company?
        if 'startup' in full_text.lower() or 'company' in full_text.lower():
            # Likely a portfolio company raise
            return 'deal_announced', 'Portfolio company raise (detected as deal)'
        return 'fundraise_announced', 'Fund raising from LPs'

    # Check for deal
    if check_patterns(full_text, PATTERNS['deal']):
        return 'deal_announced', 'Investment/acquisition language detected'

    # Check for people_move
    if check_patterns(full_text, PATTERNS['people_move']):
        return 'people_move', 'Hire/appointment language detected'

    # Check for partnership
    if check_patterns(full_text, PATTERNS['partnership']):
        return 'partnership', 'Partnership/collaboration language detected'

    # Check for report
    if check_patterns(full_text, PATTERNS['report']):
        return 'report', 'Report/financial results language detected'

    # Check for job_posting
    if check_patterns(full_text, PATTERNS['job_posting']):
        return 'job_posting', 'Job posting language detected'

    # Check for event
    if check_patterns(full_text, PATTERNS['event']):
        return 'other', 'Event/conference detected'

    return 'other', 'No clear classification pattern matched'

def audit_signals(file_path: str):
    """Audit all signals in the file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    signals = data.get('signals', [])
    total = len(signals)

    misclassified = []
    misclass_categories = defaultdict(list)

    for signal in signals:
        signal_id = signal.get('id', 'unknown')
        current_type = signal.get('signal_type', 'unknown')
        title = signal.get('title', '')

        # Predict correct type
        predicted_type, reasoning = classify_signal(signal)

        # Check if misclassified
        if current_type != predicted_type:
            # Build category key
            category = f"{predicted_type}_as_{current_type}"

            misclass_info = {
                'id': signal_id,
                'current_type': current_type,
                'correct_type': predicted_type,
                'title': title[:100],  # First 100 chars
                'reasoning': reasoning,
                'fund_slug': signal.get('fund_slug', ''),
                'source_name': signal.get('source_name', '')
            }

            misclassified.append(misclass_info)
            misclass_categories[category].append(misclass_info)

    # Calculate accuracy
    accuracy = ((total - len(misclassified)) / total * 100) if total > 0 else 0

    # Print results
    print(f"\n{'='*80}")
    print(f"SIGNAL CLASSIFICATION AUDIT RESULTS")
    print(f"{'='*80}\n")

    print(f"Total signals checked: {total}")
    print(f"Correctly classified: {total - len(misclassified)}")
    print(f"Misclassified: {len(misclassified)}")
    print(f"Overall accuracy: {accuracy:.1f}%\n")

    if misclassified:
        print(f"{'='*80}")
        print(f"MISCLASSIFICATION PATTERNS (grouped by category)")
        print(f"{'='*80}\n")

        # Sort categories by count
        sorted_categories = sorted(misclass_categories.items(), key=lambda x: len(x[1]), reverse=True)

        for category, items in sorted_categories:
            print(f"\n{category.upper()}: {len(items)} signals")
            print(f"{'-'*80}")

            # Show first 5 examples from each category
            for i, item in enumerate(items[:5], 1):
                print(f"\n  {i}. Signal ID: {item['id']}")
                print(f"     Fund: {item['fund_slug']}")
                print(f"     Current: {item['current_type']} → Correct: {item['correct_type']}")
                print(f"     Title: {item['title']}")
                print(f"     Reasoning: {item['reasoning']}")

            if len(items) > 5:
                print(f"\n  ... and {len(items) - 5} more")

        print(f"\n{'='*80}")
        print(f"TOP MISCLASSIFICATION CATEGORIES")
        print(f"{'='*80}\n")

        for i, (category, items) in enumerate(sorted_categories[:10], 1):
            print(f"{i}. {category}: {len(items)} signals ({len(items)/len(misclassified)*100:.1f}% of errors)")

    else:
        print("All signals are correctly classified!")

    print(f"\n{'='*80}\n")

    # Distribution by current type
    type_dist = defaultdict(int)
    for signal in signals:
        type_dist[signal.get('signal_type', 'unknown')] += 1

    print(f"DISTRIBUTION BY SIGNAL TYPE (current classification)")
    print(f"{'-'*80}")
    for sig_type, count in sorted(type_dist.items(), key=lambda x: x[1], reverse=True):
        print(f"{sig_type:25s}: {count:4d} ({count/total*100:5.1f}%)")

if __name__ == '__main__':
    file_path = Path(__file__).resolve().parents[2] / 'data/derived/detected_signals_enriched.json'
    audit_signals(file_path)
