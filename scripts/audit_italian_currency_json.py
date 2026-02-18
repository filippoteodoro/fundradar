#!/usr/bin/env python3
"""
Export Italian currency audit results to JSON for easier processing.
"""

import json
from pathlib import Path
from audit_italian_currency import (
    get_repo_root,
    load_enriched_signals,
    find_italian_currency_patterns,
)

def main():
    signals = load_enriched_signals()

    results = []

    for signal in signals:
        matches = find_italian_currency_patterns(signal)

        if matches:
            results.append({
                "id": signal.get("id"),
                "fund_slug": signal.get("fund_slug"),
                "type": signal.get("type"),
                "title": signal.get("title"),
                "enriched_summary": signal.get("enriched_summary"),
                "patterns_found": matches,
            })

    output = {
        "total_signals_checked": len(signals),
        "signals_with_italian_currency": len(results),
        "total_pattern_matches": sum(len(r["patterns_found"]) for r in results),
        "results": results,
    }

    output_path = get_repo_root() / "scripts" / "italian_currency_audit_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Saved results to: {output_path}")
    print(f"\nSummary:")
    print(f"  Total signals checked: {output['total_signals_checked']}")
    print(f"  Signals with Italian currency: {output['signals_with_italian_currency']}")
    print(f"  Total pattern matches: {output['total_pattern_matches']}")

if __name__ == "__main__":
    main()
