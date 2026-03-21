#!/usr/bin/env python3
"""Audit enriched_summary text quality for all signals."""

import json
import re
from collections import defaultdict
from pathlib import Path

# Italian stopwords for language detection
ITALIAN_STOPWORDS = {
    'il', 'la', 'del', 'della', 'nel', 'nella', 'che', 'per', 'con', 'è',
    'una', 'uno', 'gli', 'dei', 'delle', 'nei', 'nelle', 'dal', 'dalla',
    'sul', 'sulla', 'al', 'alla', 'di', 'da', 'in', 'su', 'e', 'ed'
}

# Common newspaper/source names to detect leaks
SOURCE_KEYWORDS = [
    'bebeez', 'il sole 24 ore', 'financecommunity', 'reuters', 'bloomberg',
    'source:', 'fonte:', 'according to', 'secondo', 'reports', 'riporta'
]

def strip_prefix(text):
    """Remove common prefixes like 'Deal update:' to get core content."""
    prefixes = [
        'Deal update:', 'Investment update:', 'Exit update:', 'Fundraise update:',
        'Team update:', 'Partnership update:', 'Report update:', 'Event update:',
        'Update:', 'News:', 'Announcement:'
    ]
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text

def has_italian_words(text):
    """Check if text contains Italian stopwords."""
    words = re.findall(r'\b\w+\b', text.lower())
    italian_count = sum(1 for word in words if word in ITALIAN_STOPWORDS)
    # Consider it Italian if more than 2 stopwords found
    return italian_count > 2

def detect_repetition(text):
    """Detect if text repeats the same information."""
    # Split into sentences
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) < 2:
        return False

    # Check for very similar consecutive sentences
    for i in range(len(sentences) - 1):
        s1_words = set(re.findall(r'\b\w+\b', sentences[i].lower()))
        s2_words = set(re.findall(r'\b\w+\b', sentences[i+1].lower()))

        if not s1_words or not s2_words:
            continue

        # Jaccard similarity
        intersection = len(s1_words & s2_words)
        union = len(s1_words | s2_words)

        if union > 0 and intersection / union > 0.7:
            return True

    return False

def is_boilerplate(text):
    """Check if text is generic boilerplate."""
    boilerplate_patterns = [
        r'^New (investment|deal|partnership) involving',
        r'^The (fund|company) (announced|completed)',
        r'^(Investment|Deal|Exit) (announced|completed|finalized)',
        r'^A new (investment|partnership|deal)',
    ]

    for pattern in boilerplate_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            # Check if there's more specific info after
            if len(text.split()) < 15:
                return True

    return False

def has_encoding_issues(text):
    """Check for encoding problems."""
    # HTML entities
    if re.search(r'&[a-z]+;|&#\d+;', text):
        return True

    # Common mojibake patterns
    if re.search(r'â€™|Ã |â€"', text):
        return True

    return False

def check_factual_consistency(summary, title, signal_type):
    """Check if summary contradicts title/type."""
    summary_lower = summary.lower()
    title_lower = title.lower()

    # Exit mentioned in title but investment in summary
    exit_words = ['exit', 'sell', 'sold', 'disposal', 'cede', 'vendita']
    invest_words = ['investment', 'invests', 'acquires', 'acquire', 'investimento']

    title_has_exit = any(word in title_lower for word in exit_words)
    title_has_invest = any(word in title_lower for word in invest_words)

    summary_has_exit = any(word in summary_lower for word in exit_words)
    summary_has_invest = any(word in summary_lower for word in invest_words)

    # Check for contradiction
    if title_has_exit and summary_has_invest and not summary_has_exit:
        return "Title suggests exit but summary suggests investment"

    if title_has_invest and summary_has_exit and not summary_has_invest:
        return "Title suggests investment but summary suggests exit"

    # Check signal type consistency
    if signal_type == 'exit' and summary_has_invest and not summary_has_exit:
        return "Signal type is 'exit' but summary suggests investment"

    if signal_type == 'deal' and summary_has_exit and not summary_has_invest:
        return "Signal type is 'deal' but summary suggests exit"

    return None

def has_source_leak(text):
    """Check if newspaper/source name appears in summary."""
    text_lower = text.lower()
    for keyword in SOURCE_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def audit_signals():
    """Main audit function."""
    data_path = Path(__file__).parent / 'data' / 'derived' / 'detected_signals_enriched.json'

    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    signals = data.get('signals', [])

    print(f"Auditing {len(signals)} signals...\n")

    issues = []
    lengths = []
    issue_counts = defaultdict(int)

    for signal in signals:
        signal_id = signal.get('id', 'unknown')
        fund_slug = signal.get('fund_slug', 'unknown')
        title = signal.get('title', '')
        signal_type = signal.get('type', '')
        summary = signal.get('enriched_summary', '')

        if not summary:
            continue

        # Calculate length after stripping prefix
        core_summary = strip_prefix(summary)
        core_length = len(core_summary)
        lengths.append(core_length)

        # Check TOO SHORT
        if core_length < 60:
            issues.append({
                'category': 'TOO SHORT',
                'fund_slug': fund_slug,
                'signal_id': signal_id,
                'description': f"{core_length} chars: {core_summary[:80]}"
            })
            issue_counts['TOO SHORT'] += 1

        # Check TOO LONG
        if len(summary) > 400:
            issues.append({
                'category': 'TOO LONG',
                'fund_slug': fund_slug,
                'signal_id': signal_id,
                'description': f"{len(summary)} chars: {summary[:80]}..."
            })
            issue_counts['TOO LONG'] += 1

        # Check REPETITIVE
        if detect_repetition(summary):
            issues.append({
                'category': 'REPETITIVE',
                'fund_slug': fund_slug,
                'signal_id': signal_id,
                'description': summary[:100]
            })
            issue_counts['REPETITIVE'] += 1

        # Check WRONG LANGUAGE
        if has_italian_words(summary):
            issues.append({
                'category': 'WRONG LANGUAGE',
                'fund_slug': fund_slug,
                'signal_id': signal_id,
                'description': summary[:100]
            })
            issue_counts['WRONG LANGUAGE'] += 1

        # Check BOILERPLATE
        if is_boilerplate(summary):
            issues.append({
                'category': 'BOILERPLATE',
                'fund_slug': fund_slug,
                'signal_id': signal_id,
                'description': summary[:100]
            })
            issue_counts['BOILERPLATE'] += 1

        # Check FACTUAL INCONSISTENCY
        inconsistency = check_factual_consistency(summary, title, signal_type)
        if inconsistency:
            issues.append({
                'category': 'FACTUAL INCONSISTENCY',
                'fund_slug': fund_slug,
                'signal_id': signal_id,
                'description': f"{inconsistency} | Title: {title[:60]}"
            })
            issue_counts['FACTUAL INCONSISTENCY'] += 1

        # Check SOURCE LEAK
        if has_source_leak(summary):
            issues.append({
                'category': 'SOURCE LEAK',
                'fund_slug': fund_slug,
                'signal_id': signal_id,
                'description': summary[:100]
            })
            issue_counts['SOURCE LEAK'] += 1

        # Check ENCODING ISSUES
        if has_encoding_issues(summary):
            issues.append({
                'category': 'ENCODING ISSUES',
                'fund_slug': fund_slug,
                'signal_id': signal_id,
                'description': summary[:100]
            })
            issue_counts['ENCODING ISSUES'] += 1

        # Check GARBLED/NONSENSE (basic heuristic)
        word_count = len(re.findall(r'\b\w+\b', summary))
        if word_count > 0:
            # Check for excessive punctuation
            punct_ratio = len(re.findall(r'[^\w\s]', summary)) / len(summary)
            if punct_ratio > 0.3:
                issues.append({
                    'category': 'GARBLED/NONSENSE',
                    'fund_slug': fund_slug,
                    'signal_id': signal_id,
                    'description': f"High punctuation ratio: {summary[:80]}"
                })
                issue_counts['GARBLED/NONSENSE'] += 1

    # Print issues
    print("=" * 120)
    print("ISSUES FOUND")
    print("=" * 120)

    for issue in issues:
        print(f"ISSUE | {issue['category']:20s} | {issue['fund_slug']:25s} | {issue['signal_id']:30s} | {issue['description']}")

    # Print statistics
    print("\n" + "=" * 120)
    print("SUMMARY STATISTICS")
    print("=" * 120)

    if lengths:
        lengths_sorted = sorted(lengths)
        n = len(lengths_sorted)
        print(f"\nLength Distribution (after stripping prefix):")
        print(f"  Min:    {lengths_sorted[0]} chars")
        print(f"  P25:    {lengths_sorted[n//4]} chars")
        print(f"  Median: {lengths_sorted[n//2]} chars")
        print(f"  P75:    {lengths_sorted[3*n//4]} chars")
        print(f"  Max:    {lengths_sorted[-1]} chars")

    print(f"\nIssue Counts:")
    total_issues = sum(issue_counts.values())
    for category in sorted(issue_counts.keys()):
        count = issue_counts[category]
        pct = (count / len(signals)) * 100
        print(f"  {category:25s}: {count:4d} ({pct:5.1f}%)")

    print(f"\nTotal Issues:     {total_issues}")
    print(f"Total Signals:    {len(signals)}")
    print(f"Signals w/ Issues: {len(set(i['signal_id'] for i in issues))} ({len(set(i['signal_id'] for i in issues))/len(signals)*100:.1f}%)")

if __name__ == '__main__':
    audit_signals()
