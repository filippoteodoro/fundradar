#!/usr/bin/env python3
"""
Script to find correct news/portfolio URLs for Italian PE/VC funds using Gemini API.
"""

import json
import time
import requests
from pathlib import Path
from urllib.parse import urlparse

# Gemini API configuration
GEMINI_API_KEY = "REDACTED_GEMINI_KEY"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"

# Priority funds to check (by deal count, deduplicated by slug)
PRIORITY_FUNDS = [
    {"name": "Fondo Italiano d'Investimento SGR", "url": "https://www.fondoitaliano.it/", "slug": "fondo-italiano-d-investimento-sgr"},
    {"name": "Clessidra SGR", "url": "https://www.clessidrasgr.it/", "slug": "clessidra-sgr"},
    {"name": "Investindustrial", "url": "https://www.investindustrial.com/", "slug": "investindustrial"},
    {"name": "Wise SGR", "url": "https://www.wisesgr.com/", "slug": "wise-equity-sgr"},
    {"name": "Alcedo SGR", "url": "https://www.alcedo.it/", "slug": "alcedo-sgr"},
    {"name": "Alto Partners SGR", "url": "https://www.altopartners.it/", "slug": "alto-partners-sgr"},
    {"name": "Ambienta SGR", "url": "https://www.ambientasgr.com/", "slug": "ambienta-sgr"},
    {"name": "Alternative Capital Partners SGR", "url": "https://alternativecapital.partners/", "slug": "alternative-capital-partners-sgr"},
    {"name": "Gradiente SGR", "url": "https://www.gradientesgr.it/", "slug": "gradiente-sgr"},
    {"name": "BC Partners", "url": "https://www.bcpartners.com/", "slug": "bc-partners"},
    {"name": "Green Arrow Capital SGR", "url": "https://www.greenarrow-capital.com/", "slug": "green-arrow-capital-sgr"},
    {"name": "Quadrivio SGR", "url": "https://www.quadriviogroup.com/", "slug": "quadrivio-group"},
    {"name": "Apax Partners", "url": "https://www.apax.com/", "slug": "apax-partners"},
    {"name": "Consilium SGR", "url": "https://www.consiliumsgr.it/", "slug": "consilium-sgr"},
    {"name": "Equinox", "url": "https://www.equinox-investments.com/", "slug": "equinox-aifm"},
    {"name": "Progressio SGR", "url": "https://www.progressiosgr.it/", "slug": "progressio-sgr"},
    {"name": "Tages Capital SGR", "url": "https://www.tagescapital.com/", "slug": "tages-capital-sgr"},
    {"name": "Tikehau Capital", "url": "https://www.tikehaucapital.com/", "slug": "tikehau-capital"},
    {"name": "FSI", "url": "https://www.fsi.it/", "slug": "fsi"},
    {"name": "21 Investimenti", "url": "https://www.21invest.com/", "slug": "21-invest"},
    {"name": "F2i SGR", "url": "https://www.f2isgr.it/", "slug": "f2i-sgr"},
    {"name": "Nextalia SGR", "url": "https://www.nextasgr.com/", "slug": "nextalia-sgr"},
    {"name": "Riello Investimenti SGR", "url": "https://www.rielloinvestimenti.it/", "slug": "riello-investimenti-sgr"},
    {"name": "Three Hills", "url": "https://www.threehillscapital.com/", "slug": "three-hills"},
    {"name": "PM&Partners SGR", "url": "https://pm-partners.it/", "slug": "pm-partners-sgr"},
]


def ask_gemini(prompt: str) -> str:
    """Call Gemini API with a prompt."""
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
        }
    }

    response = requests.post(
        f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
        headers=headers,
        json=data,
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"Gemini API error: {response.status_code} - {response.text}")

    result = response.json()
    return result["candidates"][0]["content"]["parts"][0]["text"]


def find_urls_for_fund(fund: dict) -> dict:
    """Find correct news and portfolio URLs for a fund."""
    prompt = f"""You are helping find the correct URLs for an Italian private equity/venture capital fund's website.

Fund name: {fund['name']}
Website: {fund['url']}

Please search for and verify the ACTUAL working URLs for:
1. News/Press releases page
2. Portfolio/Investments page
3. Team page

For each, provide:
- The exact full URL (not just path)
- Whether it exists (yes/no)
- The CSS selectors commonly used for news items (if news page)

IMPORTANT: Only provide URLs that actually exist on the website. If you cannot verify, say "unknown".

Respond in this exact JSON format:
{{
    "news": {{
        "url": "full URL or null",
        "exists": true/false,
        "selectors": {{
            "item": "CSS selector for news items",
            "title": "CSS selector for title",
            "date": "CSS selector for date",
            "link": "CSS selector for article link"
        }}
    }},
    "portfolio": {{
        "url": "full URL or null",
        "exists": true/false
    }},
    "team": {{
        "url": "full URL or null",
        "exists": true/false
    }},
    "notes": "any relevant notes about the site"
}}

Only respond with valid JSON, no other text."""

    try:
        response = ask_gemini(prompt)
        # Extract JSON from response
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]

        return json.loads(response.strip())
    except Exception as e:
        return {"error": str(e)}


def main():
    """Main function to find URLs for priority funds."""
    results = {}

    print(f"Finding correct URLs for {len(PRIORITY_FUNDS)} priority funds...\n")

    for i, fund in enumerate(PRIORITY_FUNDS):
        print(f"[{i+1}/{len(PRIORITY_FUNDS)}] {fund['name']}...")

        try:
            result = find_urls_for_fund(fund)
            results[fund['slug']] = {
                "name": fund['name'],
                "base_url": fund['url'],
                **result
            }

            if "error" in result:
                print(f"  Error: {result['error']}")
            else:
                news_url = result.get("news", {}).get("url", "N/A")
                portfolio_url = result.get("portfolio", {}).get("url", "N/A")
                print(f"  News: {news_url}")
                print(f"  Portfolio: {portfolio_url}")
        except Exception as e:
            print(f"  Error: {e}")
            results[fund['slug']] = {"name": fund['name'], "base_url": fund['url'], "error": str(e)}

        # Rate limiting
        time.sleep(1)

    # Save results
    output_path = Path(__file__).parent.parent / "data" / "derived" / "verified_urls.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")

    # Summary
    print("\n=== Summary ===")
    verified = sum(1 for r in results.values() if "error" not in r)
    print(f"Verified: {verified}/{len(PRIORITY_FUNDS)}")


if __name__ == "__main__":
    main()
