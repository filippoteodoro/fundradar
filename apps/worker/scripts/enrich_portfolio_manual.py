#!/usr/bin/env python3
"""
Enrich portfolio data for funds with thin coverage.

Uses web search (via OpenAI) + gpt-5-mini to find and verify Italian portfolio companies
for funds that have too few entries relative to their size.

Every entry added must have a verified source_url.

Usage:
    python apps/worker/scripts/enrich_portfolio_manual.py [--dry-run] [--slugs slug1,slug2]
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv, dotenv_values

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH, override=False)
if ENV_PATH.exists() and not os.environ.get("OPENAI_API_KEY"):
    env_vars = dotenv_values(ENV_PATH)
    if env_vars.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = env_vars["OPENAI_API_KEY"]

DB_FILE = PROJECT_ROOT / "data" / "db.json"
PORTFOLIO_FILE = PROJECT_ROOT / "data" / "derived" / "portfolio_items.json"
PEM_FILE = PROJECT_ROOT / "data" / "derived" / "pem_deals.json"

CANONICAL_SECTORS = [
    "Technology", "Software", "Healthcare", "Biotech & Pharma",
    "Financial Services", "Insurance", "Consumer Goods", "Retail",
    "Food & Beverage", "Industrial Manufacturing", "Automotive",
    "Aerospace & Defense", "Energy", "Renewable Energy",
    "Telecommunications", "Media & Entertainment", "Education",
    "Real Estate", "Construction", "Transportation & Logistics",
    "Agriculture", "Chemicals", "Environmental Services",
    "Professional Services", "Hospitality & Tourism",
    "Fashion & Luxury", "Packaging", "Waste Management",
    "Water & Utilities", "Mining & Metals",
]
SECTOR_SET = set(CANONICAL_SECTORS)

MODEL = "gpt-5-mini"


def verify_url(url: str) -> bool:
    """Check if a URL is reachable (returns 2xx/3xx)."""
    if not url or not url.startswith("http"):
        return False
    try:
        req = urllib.request.Request(url, method="HEAD", headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status < 400
    except Exception:
        # Try GET as fallback (some servers reject HEAD)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            })
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.status < 400
        except Exception:
            return False


def find_funds_needing_enrichment(db, portfolio_data, pem_data):
    """Find funds with thin portfolio data relative to their size."""
    fund_portfolios = portfolio_data.get("fund_portfolios", {})

    pem_counts = {}
    for deal in pem_data.get("deals", []):
        slug = deal.get("fund_slug", "")
        if slug:
            pem_counts[slug] = pem_counts.get(slug, 0) + 1

    needs_enrichment = []
    for fund in db.get("funds", []):
        slug = fund.get("slug", "")
        aum = fund.get("aum_eur") or 0
        aum_b = aum / 1e9
        companies = fund_portfolios.get(slug, [])
        current = [c for c in companies if c.get("status") == "current"]

        needs_more = False
        if aum_b >= 50 and len(current) < 10:
            needs_more = True
        elif aum_b >= 10 and len(current) < 5:
            needs_more = True
        elif aum_b >= 2 and len(current) < 3:
            needs_more = True
        elif aum_b >= 0.1 and len(current) == 0:
            needs_more = True

        if needs_more:
            needs_enrichment.append({
                "slug": slug,
                "name": fund.get("name", ""),
                "aum_b": round(aum_b, 1),
                "category": fund.get("category", ""),
                "website": fund.get("website", ""),
                "current_count": len(current),
                "existing_names": [c.get("name", "") for c in current],
            })

    return sorted(needs_enrichment, key=lambda x: -x["aum_b"])


def search_fund_portfolio(client, fund: dict) -> list[dict]:
    """Use gpt-5-mini web search (Responses API) to find Italian portfolio companies for a fund."""

    existing_str = ", ".join(fund["existing_names"]) if fund["existing_names"] else "none"

    prompt = f"""Research the current Italian portfolio of {fund['name']} ({fund['website']}).

This is a {fund['category']} fund with €{fund['aum_b']}B AUM. They currently have these Italian portfolio companies in our database: [{existing_str}].

Find ALL additional current (not exited) portfolio companies that are either:
- Based in Italy
- Have significant Italian operations
- Italian companies they've invested in

Search Italian PE news sources (BeBeez, Il Sole 24 Ore, MF Milano Finanza, Private Equity Italia), the fund's own website, and financial databases.

For EACH company found, you MUST provide:
1. Official company name
2. What it does (1 sentence)
3. Sector from ONLY this list: {', '.join(CANONICAL_SECTORS)}
4. City in Italy where headquartered
5. A real source URL where the investment is documented (fund website, press release, news article)
6. Approximate investment year

IMPORTANT:
- Do NOT include companies already listed above
- Do NOT include exited/sold investments
- Every entry MUST have a real, verifiable source URL
- If the fund is a credit/debt fund, include significant Italian companies they've provided financing to
- For Italian SGRs, check fund reports and AIFI data

Respond ONLY in JSON (no markdown, no code fences):
{{
  "companies": [
    {{
      "name": "Company Name",
      "sector": "Canonical Sector",
      "description": "What it does",
      "headquarters": "City, Italy",
      "website": "https://company.com",
      "source_url": "https://real-news-or-fund-page-url",
      "investment_date": "YYYY-01-01",
      "confidence": 0.9
    }}
  ]
}}

Return empty companies array if you cannot find any verified Italian investments."""

    try:
        response = client.responses.create(
            model=MODEL,
            tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
            input=prompt,
        )
        # Extract text from response output
        text = response.output_text
        # Strip markdown code fences if present
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0]
        text = text.strip()
        result = json.loads(text)
        return result.get("companies", [])
    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}")
        # Try to find JSON object in the response
        try:
            text = response.output_text
            start = text.index("{")
            end = text.rindex("}") + 1
            result = json.loads(text[start:end])
            return result.get("companies", [])
        except Exception:
            print(f"    Could not extract JSON from response")
            return []
    except Exception as e:
        print(f"    API error: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Enrich thin fund portfolios")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes")
    parser.add_argument("--slugs", type=str, help="Comma-separated fund slugs to process")
    parser.add_argument("--skip-verify", action="store_true", help="Skip URL verification")
    args = parser.parse_args()

    from openai import OpenAI
    client = OpenAI()

    db = json.loads(DB_FILE.read_text())
    portfolio_data = json.loads(PORTFOLIO_FILE.read_text())
    pem_data = json.loads(PEM_FILE.read_text())
    fund_portfolios = portfolio_data.get("fund_portfolios", {})

    # Find funds to enrich
    all_funds = find_funds_needing_enrichment(db, portfolio_data, pem_data)

    if args.slugs:
        slug_filter = set(args.slugs.split(","))
        all_funds = [f for f in all_funds if f["slug"] in slug_filter]

    print(f"Funds to enrich: {len(all_funds)}")

    total_added = 0
    total_verified = 0
    total_rejected = 0

    for i, fund in enumerate(all_funds):
        print(f"\n[{i+1}/{len(all_funds)}] {fund['name']} (€{fund['aum_b']}B, {fund['current_count']} current)")

        # Search for companies
        companies = search_fund_portfolio(client, fund)

        if not companies:
            print("    No new companies found")
            continue

        print(f"    Found {len(companies)} candidates")

        existing = fund_portfolios.get(fund["slug"], [])
        existing_lower = {c.get("name", "").lower().strip() for c in existing}

        added = 0
        for company in companies:
            name = company.get("name", "").strip()
            if not name:
                continue

            name_lower = name.lower().strip()

            # Skip duplicates
            is_dup = name_lower in existing_lower
            if not is_dup:
                for en in existing_lower:
                    if (len(name_lower) > 4 and name_lower in en) or (len(en) > 4 and en in name_lower):
                        is_dup = True
                        break
            if is_dup:
                continue

            # Validate sector
            sector = company.get("sector")
            if sector and sector not in SECTOR_SET:
                sector = None

            # Validate source URL
            source_url = company.get("source_url", "")
            if not source_url or not source_url.startswith("http"):
                print(f"    SKIP {name}: no source URL")
                total_rejected += 1
                continue

            if not args.skip_verify:
                if verify_url(source_url):
                    total_verified += 1
                    print(f"    OK   {name:35s} {sector or '?':25s} source verified")
                else:
                    print(f"    SKIP {name:35s} source URL unreachable: {source_url[:60]}")
                    total_rejected += 1
                    continue
            else:
                print(f"    ADD  {name:35s} {sector or '?':25s} (unverified)")

            entry = {
                "name": name,
                "sector": sector,
                "status": "current",
                "confidence": company.get("confidence", 0.8),
                "website": company.get("website"),
                "description": company.get("description"),
                "detail_page_url": None,
                "headquarters": company.get("headquarters"),
                "investment_date": company.get("investment_date"),
                "source_url": source_url,
            }
            existing.append(entry)
            existing_lower.add(name_lower)
            added += 1
            total_added += 1

        fund_portfolios[fund["slug"]] = existing
        total_now = len([c for c in existing if c.get("status") == "current"])
        print(f"    Result: +{added} added, {total_now} current total")

        # Write incrementally after each fund (prevents data loss on timeout)
        if not args.dry_run and added > 0:
            portfolio_data["fund_portfolios"] = fund_portfolios
            PORTFOLIO_FILE.write_text(
                json.dumps(portfolio_data, indent=2, ensure_ascii=False) + "\n"
            )
            print(f"    Written to {PORTFOLIO_FILE.name}")

        time.sleep(1)  # Rate limit

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Added: {total_added}")
    print(f"  Verified URLs: {total_verified}")
    print(f"  Rejected (bad URL/no URL): {total_rejected}")

    if args.dry_run:
        print(f"  DRY RUN — no files written")
    elif total_added > 0:
        print(f"  All changes written incrementally to {PORTFOLIO_FILE.name}")
    else:
        print(f"  No changes to write")


if __name__ == "__main__":
    main()
