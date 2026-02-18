#!/usr/bin/env python3
"""
Audit removed signals for false negatives.
Compares raw signals to enriched signals and categorizes what was lost.
"""

import json
from pathlib import Path
from collections import defaultdict
import re

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # Handle wrapper structure
        if isinstance(data, dict) and 'signals' in data:
            return data['signals']
        return data

def normalize_title(title):
    """Normalize for dedup matching"""
    if not title:
        return ""
    return title.lower().strip()[:80]

def get_signal_key(signal):
    """Create dedup key matching filter_signals.py logic"""
    fund_slug = signal.get('fund_slug', '')
    title = signal.get('title', '')
    norm_title = normalize_title(title)
    return f"{fund_slug}::{norm_title}"

def is_valuable_signal(signal):
    """
    Check if signal appears to be valuable for Italian PE audience.
    Returns (bool, reason) tuple.
    """
    title = signal.get('title', '').lower()
    what_changed = signal.get('what_changed', '').lower()
    signal_type = signal.get('signal_type', '')

    # High-value signal types
    if signal_type in ['deal', 'exit_announced', 'fundraise', 'fund_launch', 'job_posting']:
        return True, f"High-value type: {signal_type}"

    # Deal keywords
    deal_keywords = [
        r'\binvest(?:s|ment|imento)',
        r'\bacquire(?:s|d|izione)',
        r'\bbuyout\b',
        r'\bstake\b',
        r'\bpartecipaziun[ei]\b',
        r'\bportfolio\s+compan',
        r'\bmilion[ie]?\b.*(?:euro|€|\$)',
        r'\bentr(?:a|ata)\s+(?:in|nel)',
    ]

    # Exit keywords
    exit_keywords = [
        r'\bexit\b',
        r'\bsell(?:s|ing)?\b',
        r'\bvendita\b',
        r'\bdivest(?:s|ment|iture)',
        r'\bcedut[ao]\b',
        r'\bdisinvestimento\b',
    ]

    # Fundraising keywords
    fundraise_keywords = [
        r'\bfund\s+close[sd]?\b',
        r'\bclosing\b.*\bmilion',
        r'\braccolt[ao]\b',
        r'\bprimo\s+closing\b',
        r'\bcapital\s+rais',
    ]

    # Senior hire keywords
    hire_keywords = [
        r'\bpartner\b',
        r'\bmanaging\s+director\b',
        r'\b(?:chief|head)\s+(?:investment|executive)',
        r'\bjoin(?:s|ed)\b.*\b(?:partner|team|board)\b',
        r'\bappoint(?:s|ment|ed)\b',
        r'\bnuovo\s+(?:partner|amministratore)',
    ]

    text = f"{title} {what_changed}"

    for pattern in deal_keywords:
        if re.search(pattern, text):
            return True, f"Deal keyword: {pattern}"

    for pattern in exit_keywords:
        if re.search(pattern, text):
            return True, f"Exit keyword: {pattern}"

    for pattern in fundraise_keywords:
        if re.search(pattern, text):
            return True, f"Fundraising keyword: {pattern}"

    for pattern in hire_keywords:
        if re.search(pattern, text):
            return True, f"Senior hire keyword: {pattern}"

    return False, "No high-value indicators"

def categorize_false_negative(signal):
    """Categorize type of false negative"""
    title = signal.get('title', '').lower()
    what_changed = signal.get('what_changed', '').lower()
    text = f"{title} {what_changed}"

    # Check for Italian company mentions or Italian geography
    italian_indicators = [
        r'\bital(?:ia|y|ian[ao]?)\b',
        r'\bmilan[oa]?\b',
        r'\broma\b',
        r'\btorino\b',
        r'\bmade\s+in\s+italy\b',
    ]
    has_italian = any(re.search(p, text) for p in italian_indicators)

    # Check deal patterns
    deal_patterns = [
        r'\binvest(?:s|ment|imento)',
        r'\bacquire(?:s|d|izione)',
        r'\bbuyout\b',
        r'\bstake\b',
    ]
    is_deal = any(re.search(p, text) for p in deal_patterns)

    # Check exit patterns
    exit_patterns = [
        r'\bexit\b',
        r'\bsell(?:s|ing)?\b',
        r'\bvendita\b',
        r'\bcedut[ao]\b',
    ]
    is_exit = any(re.search(p, text) for p in exit_patterns)

    # Check fundraise patterns
    fundraise_patterns = [
        r'\bclosing\b.*\bmilion',
        r'\braccolt[ao]\b',
        r'\bfund\s+close',
    ]
    is_fundraise = any(re.search(p, text) for p in fundraise_patterns)

    # Check hire patterns
    hire_patterns = [
        r'\bpartner\b',
        r'\bmanaging\s+director\b',
        r'\bjoin(?:s|ed)\b',
    ]
    is_hire = any(re.search(p, text) for p in hire_patterns)

    if is_deal:
        if has_italian:
            return "italian_deal"
        else:
            return "european_deal"
    elif is_exit:
        if has_italian:
            return "italian_exit"
        else:
            return "european_exit"
    elif is_fundraise:
        return "fundraising"
    elif is_hire:
        return "senior_hire"
    else:
        return "other_valuable"

def main():
    repo_root = Path(__file__).parent.parent
    raw_path = repo_root / "data/derived/detected_signals.json"
    enriched_path = repo_root / "data/derived/detected_signals_enriched.json"

    print("Loading signal files...")
    raw_signals = load_json(raw_path)
    enriched_signals = load_json(enriched_path)

    print(f"Raw signals: {len(raw_signals)}")
    print(f"Enriched signals: {len(enriched_signals)}")

    # Build set of kept signal keys
    kept_keys = {get_signal_key(s) for s in enriched_signals}

    # Find removed signals
    removed_signals = [s for s in raw_signals if get_signal_key(s) not in kept_keys]
    print(f"Removed signals: {len(removed_signals)}")

    # Analyze removed signals
    false_negatives = []
    categories = defaultdict(list)

    print("\nAnalyzing removed signals for false negatives...")
    for signal in removed_signals:
        is_valuable, reason = is_valuable_signal(signal)
        if is_valuable:
            category = categorize_false_negative(signal)
            false_negatives.append({
                'signal': signal,
                'reason': reason,
                'category': category
            })
            categories[category].append(signal)

    print(f"\n{'='*80}")
    print(f"FALSE NEGATIVE AUDIT RESULTS")
    print(f"{'='*80}\n")

    print(f"Total removed: {len(removed_signals)}")
    print(f"False negatives found: {len(false_negatives)}")
    print(f"False negative rate: {len(false_negatives)/len(removed_signals)*100:.1f}%\n")

    # Category breakdown
    print(f"CATEGORY BREAKDOWN:")
    print(f"{'-'*80}")
    for category, signals in sorted(categories.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"{category:25} {len(signals):4d} signals")
    print()

    # Show examples from each category
    for category in ['italian_deal', 'european_deal', 'italian_exit', 'european_exit',
                     'fundraising', 'senior_hire', 'other_valuable']:
        if category not in categories:
            continue

        print(f"\n{'='*80}")
        print(f"{category.upper().replace('_', ' ')} - {len(categories[category])} signals")
        print(f"{'='*80}\n")

        # Show top 10 examples
        for i, signal in enumerate(categories[category][:10], 1):
            print(f"{i}. Fund: {signal.get('fund_slug', 'unknown')}")
            print(f"   Type: {signal.get('signal_type', 'unknown')}")
            print(f"   Title: {signal.get('title', 'no title')[:120]}")
            print(f"   Changed: {signal.get('what_changed', '')[:120]}")
            if signal.get('published_at'):
                print(f"   Date: {signal.get('published_at')}")
            print()

        if len(categories[category]) > 10:
            print(f"   ... and {len(categories[category]) - 10} more\n")

    # Correctly removed estimate
    correctly_removed = len(removed_signals) - len(false_negatives)
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Removed signals: {len(removed_signals)}")
    print(f"False negatives: {len(false_negatives)} ({len(false_negatives)/len(removed_signals)*100:.1f}%)")
    print(f"Correctly removed (estimate): {correctly_removed} ({correctly_removed/len(removed_signals)*100:.1f}%)")
    print()

if __name__ == "__main__":
    main()
