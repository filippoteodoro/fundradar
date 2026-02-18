#!/usr/bin/env python3
"""
Audit enriched signals for Italian monetary expressions that should be in English/€ format.
Searches enriched_summary field for patterns like:
- "milioni di euro", "mln euro", "mln di euro", "milioni euro"
- "miliardi di euro", "mld euro", "mld di euro"
- "migliaia di euro"
- Numbers followed by Italian currency words
- "oltre" (meaning "over")
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any

def get_repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).parent.parent

def load_enriched_signals() -> List[Dict[str, Any]]:
    """Load enriched signals from JSON file."""
    signals_path = get_repo_root() / "data" / "derived" / "detected_signals_enriched.json"
    with open(signals_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        # File is a dict with 'signals' key containing the list
        return data.get("signals", [])

def find_italian_currency_patterns(signal: Dict[str, Any]) -> List[str]:
    """
    Find Italian currency patterns in enriched_summary.
    Returns list of matched patterns.
    """
    enriched_summary = signal.get("enriched_summary", "")
    if not enriched_summary:
        return []

    matches = []

    # Pattern 1: "milioni di euro" and variants
    patterns_millions = [
        r'\d+(?:[,.]\d+)?\s+milioni\s+di\s+euro',
        r'\d+(?:[,.]\d+)?\s+mln\s+(?:di\s+)?euro',
        r'\d+(?:[,.]\d+)?\s+milioni\s+euro',
        r'milioni\s+di\s+euro',  # without number
    ]

    # Pattern 2: "miliardi di euro" and variants
    patterns_billions = [
        r'\d+(?:[,.]\d+)?\s+miliardi\s+di\s+euro',
        r'\d+(?:[,.]\d+)?\s+mld\s+(?:di\s+)?euro',
        r'miliardi\s+di\s+euro',  # without number
    ]

    # Pattern 3: "migliaia di euro"
    patterns_thousands = [
        r'\d+(?:[,.]\d+)?\s+migliaia\s+di\s+euro',
        r'migliaia\s+di\s+euro',  # without number
    ]

    # Pattern 4: "oltre" (meaning "over")
    patterns_oltre = [
        r'\boltre\s+\d+(?:[,.]\d+)?\s+mil',  # oltre X mil...
        r'\boltre\s+(?:i\s+)?\d+\s+mil',     # oltre i X mil...
    ]

    # Combine all patterns
    all_patterns = (
        patterns_millions +
        patterns_billions +
        patterns_thousands +
        patterns_oltre
    )

    for pattern in all_patterns:
        found = re.findall(pattern, enriched_summary, re.IGNORECASE)
        if found:
            matches.extend(found)

    # Deduplicate while preserving order
    seen = set()
    unique_matches = []
    for match in matches:
        if match.lower() not in seen:
            seen.add(match.lower())
            unique_matches.append(match)

    return unique_matches

def extract_context(text: str, match: str, context_chars: int = 80) -> str:
    """Extract context around a matched pattern."""
    match_lower = match.lower()
    text_lower = text.lower()

    idx = text_lower.find(match_lower)
    if idx == -1:
        return match  # Fallback if not found

    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(match) + context_chars)

    context = text[start:end]

    # Add ellipsis if truncated
    if start > 0:
        context = "..." + context
    if end < len(text):
        context = context + "..."

    return context

def main():
    print("Loading enriched signals...")
    signals = load_enriched_signals()
    print(f"Loaded {len(signals)} signals\n")

    print("Searching for Italian currency patterns...\n")
    print("=" * 100)

    found_count = 0
    total_matches = 0

    for signal in signals:
        matches = find_italian_currency_patterns(signal)

        if matches:
            found_count += 1
            total_matches += len(matches)

            signal_id = signal.get("id", "N/A")
            fund_slug = signal.get("fund_slug", "N/A")
            signal_type = signal.get("type", "N/A")
            enriched_summary = signal.get("enriched_summary", "")
            title = signal.get("title", "N/A")

            print(f"\nSignal ID: {signal_id}")
            print(f"Fund Slug: {fund_slug}")
            print(f"Type: {signal_type}")
            print(f"Title: {title}")
            print(f"Matches found: {len(matches)}")
            print("-" * 100)

            print(f"Full enriched_summary:")
            print(f"  {enriched_summary}")
            print()

            print("Pattern matches:")
            for match in matches:
                context = extract_context(enriched_summary, match, context_chars=100)
                print(f"  - Pattern: {match}")
                print(f"    Context: {context}")
            print()

            print("=" * 100)

    print(f"\n\nSUMMARY:")
    print(f"Total signals with Italian currency: {found_count}")
    print(f"Total pattern matches: {total_matches}")
    print(f"Signals without Italian currency: {len(signals) - found_count}")

if __name__ == "__main__":
    main()
