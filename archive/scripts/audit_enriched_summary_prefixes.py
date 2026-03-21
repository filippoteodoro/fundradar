#!/usr/bin/env python3
"""
Audit script to find signals where enriched_summary starts with source_name or fund_name prefix.
"""

import json
import re
from pathlib import Path


def get_repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).parent


def load_signals(signals_path: Path) -> list[dict]:
    """Load signals from JSON file."""
    with open(signals_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # Handle both direct list and wrapped in 'signals' key
        if isinstance(data, dict) and 'signals' in data:
            return data['signals']
        return data


def load_funds(db_path: Path) -> dict[str, str]:
    """Load fund slug -> name mapping."""
    with open(db_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return {fund['slug']: fund['name'] for fund in data.get('funds', [])}


def check_prefix_match(summary: str, prefix: str) -> bool:
    """
    Check if summary starts with prefix (case-insensitive).
    Handles variations:
    - "Prefix:"
    - "Prefix :"
    - "Prefix: "
    """
    if not summary or not prefix:
        return False

    summary_lower = summary.lower().strip()
    prefix_lower = prefix.lower().strip()

    # Check exact prefix with colon (with/without spaces)
    patterns = [
        f"{prefix_lower}:",
        f"{prefix_lower} :",
    ]

    for pattern in patterns:
        if summary_lower.startswith(pattern):
            return True

    return False


def main():
    repo_root = get_repo_root()
    signals_path = repo_root / "data" / "derived" / "detected_signals_enriched.json"
    db_path = repo_root / "data" / "db.json"

    print(f"Loading signals from: {signals_path}")
    signals = load_signals(signals_path)

    print(f"Loading fund names from: {db_path}")
    fund_names = load_funds(db_path)

    print(f"\nTotal signals to check: {len(signals)}\n")

    # Track findings
    source_name_matches = []
    fund_name_matches = []
    common_source_prefixes = []  # BeBeez, FinanceCommunity, Il Sole 24 Ore, etc.

    # Common RSS source names to check
    common_sources = [
        "BeBeez", "Finance Community", "FinanceCommunity", "Il Sole 24 Ore",
        "Milano Finanza", "Corriere della Sera", "La Repubblica",
        "Reuters", "Bloomberg", "Financial Times"
    ]

    for signal in signals:
        signal_id = signal.get('id', 'unknown')
        fund_slug = signal.get('fund_slug', 'unknown')
        source_name = signal.get('source_name', '')
        enriched_summary = signal.get('enriched_summary', '')

        # Check source_name prefix
        if source_name and enriched_summary:
            if check_prefix_match(enriched_summary, source_name):
                source_name_matches.append({
                    'id': signal_id,
                    'fund_slug': fund_slug,
                    'source_name': source_name,
                    'summary_preview': enriched_summary[:150],
                    'full_summary': enriched_summary
                })

        # Check fund_name prefix
        fund_name = fund_names.get(fund_slug, '')
        if fund_name and enriched_summary:
            if check_prefix_match(enriched_summary, fund_name):
                fund_name_matches.append({
                    'id': signal_id,
                    'fund_slug': fund_slug,
                    'fund_name': fund_name,
                    'summary_preview': enriched_summary[:150],
                    'full_summary': enriched_summary
                })

        # Check common RSS source prefixes
        if enriched_summary:
            for common_source in common_sources:
                if check_prefix_match(enriched_summary, common_source):
                    common_source_prefixes.append({
                        'id': signal_id,
                        'fund_slug': fund_slug,
                        'matched_prefix': common_source,
                        'actual_source_name': source_name,
                        'summary_preview': enriched_summary[:150],
                        'full_summary': enriched_summary
                    })

    # Report findings
    print("=" * 100)
    print("FINDINGS: Signals with source_name prefix in enriched_summary")
    print("=" * 100)

    if source_name_matches:
        print(f"\nFound {len(source_name_matches)} signals with source_name prefix:\n")
        for i, match in enumerate(source_name_matches, 1):
            print(f"{i}. Signal ID: {match['id']}")
            print(f"   Fund Slug: {match['fund_slug']}")
            print(f"   Source Name: {match['source_name']}")
            print(f"   Summary Preview: {match['summary_preview']}")
            print(f"   Full Summary: {match['full_summary']}")
            print()
    else:
        print("\n✓ No signals found with source_name prefix in enriched_summary\n")

    print("=" * 100)
    print("FINDINGS: Signals with fund_name prefix in enriched_summary")
    print("=" * 100)

    if fund_name_matches:
        print(f"\nFound {len(fund_name_matches)} signals with fund_name prefix:\n")
        for i, match in enumerate(fund_name_matches, 1):
            print(f"{i}. Signal ID: {match['id']}")
            print(f"   Fund Slug: {match['fund_slug']}")
            print(f"   Fund Name: {match['fund_name']}")
            print(f"   Summary Preview: {match['summary_preview']}")
            print(f"   Full Summary: {match['full_summary']}")
            print()
    else:
        print("\n✓ No signals found with fund_name prefix in enriched_summary\n")

    print("=" * 100)
    print("FINDINGS: Signals with common RSS source prefixes (BeBeez, FinanceCommunity, etc.)")
    print("=" * 100)

    if common_source_prefixes:
        print(f"\nFound {len(common_source_prefixes)} signals with common source prefixes:\n")
        for i, match in enumerate(common_source_prefixes, 1):
            print(f"{i}. Signal ID: {match['id']}")
            print(f"   Fund Slug: {match['fund_slug']}")
            print(f"   Matched Prefix: {match['matched_prefix']}")
            print(f"   Actual Source Name: {match['actual_source_name']}")
            print(f"   Summary Preview: {match['summary_preview']}")
            print(f"   Full Summary: {match['full_summary']}")
            print()
    else:
        print("\n✓ No signals found with common RSS source prefixes in enriched_summary\n")

    # Summary
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total signals checked: {len(signals)}")
    print(f"Signals with source_name prefix: {len(source_name_matches)}")
    print(f"Signals with fund_name prefix: {len(fund_name_matches)}")
    print(f"Signals with common RSS source prefix: {len(common_source_prefixes)}")
    print()


if __name__ == "__main__":
    main()
