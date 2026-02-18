#!/usr/bin/env python3
"""
Audit script to detect suspiciously short enriched_summary fields.

Checks for cases where what_changed has substantial content but
enriched_summary is very brief (possible under-summarization).
"""

import json
from pathlib import Path
from typing import List, Dict


def get_repo_root() -> Path:
    """Find repo root by looking for pnpm-workspace.yaml."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    raise RuntimeError("Could not find repo root (no pnpm-workspace.yaml found)")


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
    print(f"Analyzing {len(signals)} signals for under-summarization...\n")

    # Find signals where summary is very short relative to what_changed
    suspicious = []

    for signal in signals:
        signal_id = signal.get('id', 'unknown')
        fund_slug = signal.get('fund_slug', 'unknown')
        enriched_summary = signal.get('enriched_summary', '')
        what_changed = signal.get('what_changed', '')

        summary_len = len(enriched_summary)
        what_changed_len = len(what_changed)

        # Skip if no what_changed or very short what_changed
        if what_changed_len < 100:
            continue

        # Flag if:
        # 1. Summary is < 50 chars and what_changed > 200
        # 2. Summary is < 100 chars and what_changed > 500
        # 3. Ratio is > 5x (what_changed is 5x longer than summary)

        is_suspicious = False
        reason = []

        if summary_len < 50 and what_changed_len > 200:
            is_suspicious = True
            reason.append(f"very_short_summary (summary={summary_len}, source={what_changed_len})")

        if summary_len < 100 and what_changed_len > 500:
            is_suspicious = True
            reason.append(f"short_summary_long_source (summary={summary_len}, source={what_changed_len})")

        ratio = what_changed_len / summary_len if summary_len > 0 else 0
        if ratio > 5 and summary_len < 200:
            is_suspicious = True
            reason.append(f"high_compression_ratio ({ratio:.1f}x)")

        if is_suspicious:
            suspicious.append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'summary': enriched_summary,
                'what_changed_preview': what_changed[:300],
                'summary_len': summary_len,
                'what_changed_len': what_changed_len,
                'ratio': ratio,
                'reasons': reason
            })

    # Report
    print("=" * 80)
    print(f"SHORT SUMMARY AUDIT REPORT")
    print("=" * 80)
    print(f"\nTotal signals analyzed: {len(signals)}")
    print(f"Signals with suspiciously short summaries: {len(suspicious)}")
    if len(signals) > 0:
        print(f"Percentage: {len(suspicious) / len(signals) * 100:.1f}%\n")

    if not suspicious:
        print("\nNo suspiciously short summaries found. All signals appear well-summarized.")
        return

    # Sort by ratio (highest compression first)
    suspicious.sort(key=lambda x: -x['ratio'])

    print("\n" + "=" * 80)
    print("DETAILED LIST")
    print("=" * 80)

    for i, sig in enumerate(suspicious, 1):
        print(f"\n{i}. Signal ID: {sig['id']}")
        print(f"   Fund: {sig['fund_slug']}")
        print(f"   Reasons: {'; '.join(sig['reasons'])}")
        print(f"   Lengths: summary={sig['summary_len']}, "
              f"what_changed={sig['what_changed_len']}, ratio={sig['ratio']:.1f}x")
        print(f"   Summary: \"{sig['summary']}\"")
        print(f"   What changed (first 300): \"{sig['what_changed_preview']}...\"")

    print("\n" + "=" * 80)
    print(f"END OF REPORT")
    print("=" * 80)


if __name__ == '__main__':
    main()
