#!/usr/bin/env python3
"""
Comprehensive fund data cleanup using OpenAI API.
Reviews: categories, names, AUM, and other fields.
"""

import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DATA_FILE = Path(__file__).parent.parent / "data" / "db.json"

VALID_CATEGORIES = [
    "pe", "vc", "growth", "infra", "debt", "real_estate",
    "holdings", "fund_of_funds", "multi_strategy", "sovereign",
    "bank", "asset_manager", "unknown"
]

CATEGORY_LABELS = {
    "pe": "Private Equity",
    "vc": "Venture Capital",
    "growth": "Growth Equity",
    "infra": "Infrastructure",
    "debt": "Private Debt",
    "real_estate": "Real Estate",
    "holdings": "Holdings",
    "fund_of_funds": "Fund of Funds",
    "multi_strategy": "Multi-Strategy",
    "sovereign": "Sovereign/State",
    "bank": "Bank",
    "asset_manager": "Asset Manager",
    "unknown": "Unknown"
}


def round_aum(aum: float) -> float:
    """Round AUM to sensible round numbers."""
    if aum is None:
        return None

    if aum >= 100_000_000_000:  # 100B+
        return round(aum / 10_000_000_000) * 10_000_000_000  # Round to 10B
    elif aum >= 10_000_000_000:  # 10B+
        return round(aum / 1_000_000_000) * 1_000_000_000  # Round to 1B
    elif aum >= 1_000_000_000:  # 1B+
        return round(aum / 100_000_000) * 100_000_000  # Round to 100M
    elif aum >= 100_000_000:  # 100M+
        return round(aum / 10_000_000) * 10_000_000  # Round to 10M
    elif aum >= 10_000_000:  # 10M+
        return round(aum / 1_000_000) * 1_000_000  # Round to 1M
    else:
        return round(aum / 100_000) * 100_000  # Round to 100K


def get_review_prompt(fund: dict) -> str:
    """Generate prompt for OpenAI to review fund data."""
    name = fund["name"]
    category = fund.get("category", "unknown")
    aum = fund.get("aum_eur")
    aum_str = f"€{aum/1e9:.1f}B" if aum and aum >= 1e9 else f"€{aum/1e6:.0f}M" if aum and aum >= 1e6 else "Unknown"

    return f"""Review this fund's data for accuracy:

Name: {name}
Category: {category} ({CATEGORY_LABELS.get(category, 'Unknown')})
AUM: {aum_str}
Website: {fund.get('website', 'N/A')}
HQ: {fund.get('hq_city', 'Unknown')}, {fund.get('hq_region', 'Unknown')}

Please provide corrections in JSON format:
{{
  "short_name": "shorter display name if current is too long (max 30 chars), or null if OK",
  "correct_category": "correct category code if wrong, or null if OK",
  "category_reason": "brief reason if category changed",
  "is_sovereign_or_state": true/false (is this a sovereign wealth fund, state-owned, or government development bank?),
  "notes": "any other data quality issues noticed"
}}

Valid categories: pe (Private Equity buyout), vc (Venture Capital), growth (Growth Equity), infra (Infrastructure), debt (Private Debt), real_estate, holdings (Family office/Holding), fund_of_funds, multi_strategy, sovereign (Sovereign wealth/State-owned/Development bank), bank, asset_manager

IMPORTANT:
- CDP (Cassa Depositi e Prestiti) entities are Italian state-owned -> sovereign
- Names like "XXX SGR SpA Gestore EuVECA Società Benefit" should be shortened to just "XXX"
- Branch names like "XXX (Ireland) Limited - Milan Branch" -> just "XXX"
- Long legal suffixes should be removed for display

Respond with ONLY the JSON, no other text."""


def review_fund(client: OpenAI, fund: dict) -> dict | None:
    """Query OpenAI to review fund data."""
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "You are a private equity data analyst. Review fund data for accuracy and provide corrections in JSON format only."},
                {"role": "user", "content": get_review_prompt(fund)}
            ],
            temperature=0.1,
            max_completion_tokens=300
        )
        answer = response.choices[0].message.content.strip()

        # Parse JSON from response
        # Handle markdown code blocks
        if "```json" in answer:
            answer = answer.split("```json")[1].split("```")[0]
        elif "```" in answer:
            answer = answer.split("```")[1].split("```")[0]

        return json.loads(answer)

    except json.JSONDecodeError as e:
        print(f"  JSON parse error for {fund['name']}: {e}")
        return None
    except Exception as e:
        print(f"  Error for {fund['name']}: {e}")
        return None


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in .env")
        return

    client = OpenAI(api_key=api_key)

    with open(DATA_FILE) as f:
        data = json.load(f)

    funds = data.get("funds", [])

    # Track changes
    changes = {
        "names_shortened": [],
        "categories_fixed": [],
        "aum_rounded": [],
        "other_issues": []
    }

    print(f"Reviewing {len(funds)} funds...\n")

    # First pass: Round all AUM values
    print("=== Rounding AUM values ===")
    for fund in funds:
        aum = fund.get("aum_eur")
        if aum:
            rounded = round_aum(aum)
            if rounded != aum:
                old_str = f"€{aum/1e9:.2f}B" if aum >= 1e9 else f"€{aum/1e6:.1f}M"
                new_str = f"€{rounded/1e9:.1f}B" if rounded >= 1e9 else f"€{rounded/1e6:.0f}M"
                changes["aum_rounded"].append(f"{fund['name']}: {old_str} -> {new_str}")
                fund["aum_eur"] = rounded

    print(f"Rounded {len(changes['aum_rounded'])} AUM values\n")

    # Second pass: Review funds with OpenAI (focus on problematic ones)
    print("=== Reviewing funds with OpenAI ===")

    # Prioritize funds that likely need review:
    # - Long names (> 40 chars)
    # - Known state entities
    # - Multi-strategy that might be miscategorized
    to_review = []
    for fund in funds:
        name = fund["name"]
        needs_review = (
            len(name) > 40 or
            "cdp" in name.lower() or
            "cassa depositi" in name.lower() or
            "sgr spa" in name.lower().replace(" ", "") or
            "limited" in name.lower() or
            "branch" in name.lower() or
            "società benefit" in name.lower() or
            fund.get("category") in ["multi_strategy", "unknown"] or
            "state" in name.lower() or
            "governo" in name.lower()
        )
        if needs_review:
            to_review.append(fund)

    print(f"Found {len(to_review)} funds needing detailed review\n")

    for i, fund in enumerate(to_review):
        print(f"[{i+1}/{len(to_review)}] Reviewing: {fund['name'][:50]}...")

        review = review_fund(client, fund)
        if not review:
            continue

        # Apply short name if suggested
        if review.get("short_name"):
            old_name = fund["name"]
            fund["name"] = review["short_name"]
            fund["legal_name"] = old_name  # Keep original as legal name
            changes["names_shortened"].append(f"{old_name} -> {review['short_name']}")
            print(f"  Name: {old_name} -> {review['short_name']}")

        # Apply category fix if suggested
        if review.get("correct_category") and review["correct_category"] in VALID_CATEGORIES:
            if review["correct_category"] != fund.get("category"):
                old_cat = fund.get("category")
                fund["category"] = review["correct_category"]
                reason = review.get("category_reason", "")
                changes["categories_fixed"].append(f"{fund['name']}: {old_cat} -> {review['correct_category']} ({reason})")
                print(f"  Category: {old_cat} -> {review['correct_category']} ({reason})")

        # Mark sovereign if identified
        if review.get("is_sovereign_or_state") and fund.get("category") != "sovereign":
            old_cat = fund.get("category")
            fund["category"] = "sovereign"
            changes["categories_fixed"].append(f"{fund['name']}: {old_cat} -> sovereign (state-owned)")
            print(f"  Category: {old_cat} -> sovereign (state-owned)")

        # Note other issues
        if review.get("notes") and review["notes"] not in ["None", "null", ""]:
            changes["other_issues"].append(f"{fund['name']}: {review['notes']}")

    # Save updated data
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY OF CHANGES")
    print("="*60)

    print(f"\nNames shortened ({len(changes['names_shortened'])}):")
    for c in changes["names_shortened"]:
        print(f"  - {c}")

    print(f"\nCategories fixed ({len(changes['categories_fixed'])}):")
    for c in changes["categories_fixed"]:
        print(f"  - {c}")

    print(f"\nAUM rounded ({len(changes['aum_rounded'])}):")
    for c in changes["aum_rounded"][:10]:  # Show first 10
        print(f"  - {c}")
    if len(changes["aum_rounded"]) > 10:
        print(f"  ... and {len(changes['aum_rounded']) - 10} more")

    if changes["other_issues"]:
        print(f"\nOther issues noted ({len(changes['other_issues'])}):")
        for c in changes["other_issues"][:10]:
            print(f"  - {c}")

    print("\nData saved to db.json")


if __name__ == "__main__":
    main()
