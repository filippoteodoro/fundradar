#!/usr/bin/env python3
"""
Enrich fund investment sizes using OpenAI API.
Focuses on large funds missing average_investment data.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

DATA_FILE = Path(__file__).parent.parent / "data" / "db.json"

# Investment size buckets matching AIFI categories
INVESTMENT_BUCKETS = [
    "€0-1m",      # Seed/Angel
    "€1-5m",      # Early VC
    "€5-20m",     # Late VC / Small PE
    "€20-50m",    # Mid-market PE
    "€50-100m",   # Upper mid-market
    "€100m+",     # Large cap PE
]

def get_investment_size_prompt(fund: dict) -> str:
    """Generate prompt for OpenAI to determine investment size."""
    name = fund["name"]
    category = fund.get("category", "unknown")
    aum = fund.get("aum_eur")
    aum_str = f"€{aum/1e9:.1f}B" if aum and aum >= 1e9 else f"€{aum/1e6:.0f}M" if aum and aum >= 1e6 else "Unknown"

    return f"""What is the typical average investment size (equity check) for {name}?

Fund info:
- Category: {category}
- AUM: {aum_str}
- Website: {fund.get('website', 'N/A')}

Based on the fund's profile and typical deal sizes for this type of investor, select ONE primary investment size range:
- €0-1m (seed/angel investments)
- €1-5m (early-stage VC)
- €5-20m (late-stage VC, small buyouts)
- €20-50m (mid-market PE)
- €50-100m (upper mid-market PE)
- €100m+ (large-cap PE, mega-funds)

Respond with ONLY the range (e.g., "€50-100m") and nothing else. If truly unknown, respond "Unknown"."""


def enrich_fund(client: OpenAI, fund: dict) -> str | None:
    """Query OpenAI for fund's investment size."""
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "You are a private equity research analyst. Provide concise, accurate answers about fund investment sizes based on market knowledge."},
                {"role": "user", "content": get_investment_size_prompt(fund)}
            ],
            temperature=0.1,
            max_completion_tokens=50
        )
        answer = response.choices[0].message.content.strip()

        # Validate answer is a known bucket
        for bucket in INVESTMENT_BUCKETS:
            if bucket in answer:
                return bucket

        if "Unknown" in answer:
            return None

        print(f"  Unexpected response for {fund['name']}: {answer}")
        return None

    except Exception as e:
        print(f"  Error for {fund['name']}: {e}")
        return None


def main():
    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in .env")
        return

    client = OpenAI(api_key=api_key)

    # Load data
    with open(DATA_FILE) as f:
        data = json.load(f)

    funds = data.get("funds", [])

    # Find funds needing enrichment:
    # - Has AUM > €100M (significant fund)
    # - Missing or empty average_investment
    to_enrich = []
    for fund in funds:
        aum = fund.get("aum_eur") or 0
        avg_inv = fund.get("average_investment", [])

        if aum >= 100_000_000 and not avg_inv:
            to_enrich.append(fund)

    # Sort by AUM descending (prioritize largest)
    to_enrich.sort(key=lambda x: x.get("aum_eur", 0) or 0, reverse=True)

    print(f"Found {len(to_enrich)} funds needing investment size enrichment")
    print(f"Processing top 50 by AUM...\n")

    enriched_count = 0
    for fund in to_enrich[:50]:
        aum = fund.get("aum_eur", 0)
        aum_str = f"€{aum/1e9:.1f}B" if aum >= 1e9 else f"€{aum/1e6:.0f}M"
        print(f"Enriching: {fund['name']} (AUM: {aum_str})")

        size = enrich_fund(client, fund)
        if size:
            # Update fund in data
            for f in funds:
                if f["id"] == fund["id"]:
                    f["average_investment"] = [size]
                    f["average_investment_source"] = "openai_enriched"
                    enriched_count += 1
                    print(f"  -> {size}")
                    break
        else:
            print(f"  -> Unknown/skipped")

    # Save updated data
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nEnriched {enriched_count} funds. Data saved.")


if __name__ == "__main__":
    main()
