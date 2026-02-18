#!/usr/bin/env python3
"""
Audit script to detect truncated enriched_summary fields in signals.

Detects:
1. Summaries ending with "..." (explicit truncation)
2. Summaries ending mid-word
3. Summaries ending without terminal punctuation
4. Summaries ending with comma, dash, or preposition
5. Summaries ending with articles, conjunctions, or incomplete clauses
6. Cases where what_changed is significantly longer than summary (mechanical truncation)
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def get_repo_root() -> Path:
    """Find repo root by looking for pnpm-workspace.yaml."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    raise RuntimeError("Could not find repo root (no pnpm-workspace.yaml found)")


# Common word patterns that indicate truncation
TRUNCATION_WORDS = {
    # Articles
    'a', 'an', 'the', 'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'una', 'uno',
    # Prepositions
    'of', 'in', 'to', 'for', 'on', 'at', 'by', 'with', 'from', 'about',
    'di', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra',
    # Conjunctions
    'and', 'or', 'but', 'nor', 'yet', 'so',
    'e', 'o', 'ma', 'però', 'quindi',
    # Common incomplete endings
    'that', 'which', 'who', 'where', 'when', 'how', 'why',
    'che', 'cui', 'quale', 'dove', 'quando', 'come', 'perché',
}


def ends_with_truncation_word(text: str) -> bool:
    """Check if text ends with a word that shouldn't be at sentence end."""
    # Get last word (remove trailing punctuation first)
    text = text.rstrip('.,;:!?-–—')
    if not text:
        return False

    # Split and get last word, lowercased
    words = text.split()
    if not words:
        return False

    last_word = words[-1].lower().strip("'\"")
    return last_word in TRUNCATION_WORDS


def analyze_summary(summary: str, what_changed: str) -> Dict[str, any]:
    """Analyze a summary for truncation issues."""
    if not summary:
        return {'is_truncated': False, 'reasons': []}

    reasons = []

    # 1. Explicit "..." truncation
    if summary.endswith('...'):
        reasons.append('explicit_ellipsis')

    # 2. Ends mid-word (no space before end, but has letters)
    # Skip if ends with punctuation
    if summary and summary[-1].isalpha():
        # Check if likely cut off (no terminal punctuation and ends with letter)
        reasons.append('ends_mid_word')

    # 3. No terminal punctuation
    if summary and summary[-1] not in '.!?…':
        # Also check if it ends with quote then punctuation
        if not (len(summary) >= 2 and summary[-2] in '.!?' and summary[-1] in '\'"'):
            reasons.append('no_terminal_punctuation')

    # 4. Ends with comma, dash, or weak punctuation
    if summary and summary[-1] in ',-–—;:':
        reasons.append('weak_ending_punctuation')

    # 5. Ends with truncation word (article, preposition, etc.)
    if ends_with_truncation_word(summary):
        reasons.append('ends_with_truncation_word')

    # 6. Mechanical truncation check
    # If what_changed is significantly longer and summary doesn't end properly,
    # likely mechanical truncation
    summary_len = len(summary)
    what_changed_len = len(what_changed) if what_changed else 0

    if what_changed_len > summary_len * 1.5 and what_changed_len > 200:
        # Only flag if summary also has truncation indicators
        if reasons:
            reasons.append('mechanical_truncation_suspected')

    # Deduplicate reasons
    reasons = list(dict.fromkeys(reasons))

    return {
        'is_truncated': len(reasons) > 0,
        'reasons': reasons,
        'summary_len': summary_len,
        'what_changed_len': what_changed_len,
        'ratio': what_changed_len / summary_len if summary_len > 0 else 0
    }


def main():
    repo_root = get_repo_root()
    enriched_path = repo_root / "data" / "derived" / "detected_signals_enriched.json"

    if not enriched_path.exists():
        print(f"ERROR: {enriched_path} not found")
        return

    print(f"Loading enriched signals from: {enriched_path}")
    with open(enriched_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    signals = data.get('signals', [])
    print(f"Analyzing {len(signals)} signals...\n")

    # Analyze all signals
    truncated_signals = []

    for signal in signals:
        signal_id = signal.get('id', 'unknown')
        fund_slug = signal.get('fund_slug', 'unknown')
        enriched_summary = signal.get('enriched_summary', '')
        what_changed = signal.get('what_changed', '')

        analysis = analyze_summary(enriched_summary, what_changed)

        if analysis['is_truncated']:
            truncated_signals.append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'enriched_summary': enriched_summary,
                'what_changed_preview': what_changed[:200] if what_changed else '',
                'analysis': analysis
            })

    # Report findings
    print("=" * 80)
    print(f"TRUNCATED SUMMARIES AUDIT REPORT")
    print("=" * 80)
    print(f"\nTotal signals analyzed: {len(signals)}")
    print(f"Signals with truncation issues: {len(truncated_signals)}")
    print(f"Percentage: {len(truncated_signals) / len(signals) * 100:.1f}%\n")

    # Group by reason
    reason_counts = {}
    for sig in truncated_signals:
        for reason in sig['analysis']['reasons']:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    print("TRUNCATION PATTERNS:")
    print("-" * 80)
    for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
        print(f"  {reason:35s}: {count:4d} signals")

    print("\n" + "=" * 80)
    print("DETAILED SIGNAL LIST")
    print("=" * 80)

    # Sort by severity (more reasons = more severe)
    truncated_signals.sort(key=lambda x: -len(x['analysis']['reasons']))

    for i, sig in enumerate(truncated_signals, 1):
        print(f"\n{i}. Signal ID: {sig['id']}")
        print(f"   Fund: {sig['fund_slug']}")
        print(f"   Reasons: {', '.join(sig['analysis']['reasons'])}")
        print(f"   Lengths: summary={sig['analysis']['summary_len']}, "
              f"what_changed={sig['analysis']['what_changed_len']}, "
              f"ratio={sig['analysis']['ratio']:.1f}x")

        # Show last 100 chars to highlight the truncation
        summary = sig['enriched_summary']
        if len(summary) > 100:
            print(f"   Summary (last 100 chars): \"...{summary[-100:]}\"")
        else:
            print(f"   Summary: \"{summary}\"")

        if sig['what_changed_preview']:
            print(f"   What changed (first 200): \"{sig['what_changed_preview']}...\"")

    print("\n" + "=" * 80)
    print(f"END OF REPORT - {len(truncated_signals)} truncated summaries found")
    print("=" * 80)


if __name__ == '__main__':
    main()
