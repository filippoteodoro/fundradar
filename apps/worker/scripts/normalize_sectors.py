#!/usr/bin/env python3
"""
Normalize all sector data to a canonical 30-sector taxonomy.

Updates both:
  - db.json fund-level sector_tags (AIFI → canonical)
  - portfolio_items.json company-level sectors (free-text → canonical)

Uses deterministic keyword mapping (SECTOR_KEYWORDS dict). No AI calls.
If new unmapped sectors appear, add keywords to SECTOR_KEYWORDS.

Usage:
    python apps/worker/scripts/normalize_sectors.py [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

from fundradar_worker.io_utils import safe_json_write
from fundradar_worker.paths import DB_PATH as DB_FILE, PORTFOLIO_FILE, SECTOR_TAXONOMY

SECTOR_SET = set(SECTOR_TAXONOMY)

# ─── AIFI fund tag → canonical mapping ─────────────────────────────────────
# Maps all 46 known AIFI sector_tags to canonical sectors.
# Some AIFI tags map to the same canonical sector.

AIFI_TO_CANONICAL = {
    # Core matches
    "Healthcare": "Healthcare",
    "Biotech": "Biotech & Pharma",
    "Medtech": "Healthcare",
    "Industrial": "Industrial Manufacturing",
    "Industrials": "Industrial Manufacturing",
    "Specialized Industrials": "Industrial Manufacturing",
    "Manufacturing": "Industrial Manufacturing",
    "Other-Manufacturing": "Industrial Manufacturing",
    "Mechanics": "Industrial Manufacturing",
    "Information-And-Telco": "Technology",
    "Technology": "Technology",
    "Digital": "Technology",
    "Digital Infrastructure": "Technology",
    "Technology-Based B2B Services": "Technology",
    "Software": "Software",
    "Food-And-Beverage": "Food & Beverage",
    "Food": "Food & Beverage",
    "Energy-And-Environment": "Energy",
    "Energy": "Energy",
    "Energy Transition": "Renewable Energy",
    "Renewable Energy": "Renewable Energy",
    "Financial-And-Insurance": "Financial Services",
    "Financial Services": "Financial Services",
    "Insurance": "Insurance",
    "Credit": "Financial Services",
    "Chemicals-And-Materials": "Chemicals",
    "Consumer": "Consumer Goods",
    "Fashion": "Fashion & Luxury",
    "Retail": "Retail",
    "Furniture": "Industrial Manufacturing",
    "Agriculture": "Agriculture",
    "Transportation": "Transportation & Logistics",
    "Aerospace": "Aerospace & Defense",
    "Construction": "Construction",
    "Infrastructure": "Construction",
    "Real Estate": "Real Estate",
    "Education": "Education",
    "Tourism": "Hospitality & Tourism",
    "Gaming": "Media & Entertainment",
    "Sustainability": "Environmental Services",
    "Utilities": "Water & Utilities",
    "Business Services": "Professional Services",
    # Meta/catch-all tags — drop these
    "Other": None,
    "Multi-sector": None,
    "Private Markets": None,
    "International Expansion": None,
}

# ─── Company sector keyword mapping ────────────────────────────────────────
# Extended from enrich_portfolio_sectors.py with Italian translations
# and additional patterns found in portfolio_items.json.

SECTOR_KEYWORDS = {
    # Software / Technology
    "software": "Software",
    "saas": "Software",
    "cloud": "Software",
    "cybersecurity": "Software",
    "it services": "Technology",
    "information technology": "Technology",
    "tech": "Technology",
    "digital": "Technology",
    "artificial intelligence": "Technology",
    "ai ": "Technology",
    "data analytics": "Technology",
    "ict": "Technology",
    "informatica": "Technology",
    "tecnologia": "Technology",
    "automazione": "Technology",
    "digitale": "Technology",
    "elettronica": "Technology",
    # Financial
    "fintech": "Financial Services",
    "banking": "Financial Services",
    "financial": "Financial Services",
    "asset management": "Financial Services",
    "payment": "Financial Services",
    "servizi finanziari": "Financial Services",
    "finanziario": "Financial Services",
    "credito": "Financial Services",
    # Insurance
    "insurance": "Insurance",
    "insurtech": "Insurance",
    "assicurazion": "Insurance",
    # Healthcare
    "healthcare": "Healthcare",
    "medical": "Healthcare",
    "health": "Healthcare",
    "hospital": "Healthcare",
    "diagnostic": "Healthcare",
    "clinics": "Healthcare",
    "clinical": "Healthcare",
    "dental": "Healthcare",
    "veterinar": "Healthcare",
    "sanità": "Healthcare",
    "sanitari": "Healthcare",
    "diagnostica": "Healthcare",
    "ospedale": "Healthcare",
    "medico": "Healthcare",
    "medical device": "Healthcare",
    "medtech": "Healthcare",
    # Biotech & Pharma
    "pharma": "Biotech & Pharma",
    "biotech": "Biotech & Pharma",
    "life science": "Biotech & Pharma",
    "farmaceutic": "Biotech & Pharma",
    "bioscienz": "Biotech & Pharma",
    "cdmo": "Biotech & Pharma",
    "cmo": "Biotech & Pharma",
    # Consumer Goods
    "consumer good": "Consumer Goods",
    "consumer product": "Consumer Goods",
    "fmcg": "Consumer Goods",
    "cosmetic": "Consumer Goods",
    "personal care": "Consumer Goods",
    "beni di consumo": "Consumer Goods",
    "prodotti di consumo": "Consumer Goods",
    "cosmetici": "Consumer Goods",
    "baby": "Consumer Goods",
    "pet ": "Consumer Goods",
    # Retail
    "retail": "Retail",
    "e-commerce": "Retail",
    "ecommerce": "Retail",
    "commercio": "Retail",
    "distribuzione": "Retail",
    "gdo": "Retail",
    # Food & Beverage
    "food": "Food & Beverage",
    "beverage": "Food & Beverage",
    "restaurant": "Food & Beverage",
    "catering": "Food & Beverage",
    "alimentar": "Food & Beverage",
    "ristorazione": "Food & Beverage",
    "dolciari": "Food & Beverage",
    "salumi": "Food & Beverage",
    "pasta": "Food & Beverage",
    "piadine": "Food & Beverage",
    "gnocchi": "Food & Beverage",
    "lattiero": "Food & Beverage",
    "gelato": "Food & Beverage",
    "bakery": "Food & Beverage",
    "confectioner": "Food & Beverage",
    "wine": "Food & Beverage",
    "vino": "Food & Beverage",
    "cibo": "Food & Beverage",
    "surgelat": "Food & Beverage",
    "caseario": "Food & Beverage",
    "caffè": "Food & Beverage",
    "coffee": "Food & Beverage",
    "flavour": "Food & Beverage",
    "ingredient": "Food & Beverage",
    # Industrial Manufacturing
    "industrial": "Industrial Manufacturing",
    "manufacturing": "Industrial Manufacturing",
    "machinery": "Industrial Manufacturing",
    "manifattur": "Industrial Manufacturing",
    "meccanica": "Industrial Manufacturing",
    "meccanico": "Industrial Manufacturing",
    "siderurgic": "Industrial Manufacturing",
    "stampaggio": "Industrial Manufacturing",
    "componenti": "Industrial Manufacturing",
    "produzione": "Industrial Manufacturing",
    "arredamento": "Industrial Manufacturing",
    "furniture": "Industrial Manufacturing",
    "ceramica": "Industrial Manufacturing",
    "ceramic": "Industrial Manufacturing",
    "glass": "Industrial Manufacturing",
    "vetro": "Industrial Manufacturing",
    "plastic": "Industrial Manufacturing",
    "rubber": "Industrial Manufacturing",
    # Automotive
    "automotive": "Automotive",
    "vehicle": "Automotive",
    "auto ": "Automotive",
    "motori": "Automotive",
    # Aerospace & Defense
    "aerospace": "Aerospace & Defense",
    "defense": "Aerospace & Defense",
    "defence": "Aerospace & Defense",
    "aerospaziale": "Aerospace & Defense",
    "difesa": "Aerospace & Defense",
    # Energy
    "energy": "Energy",
    "oil": "Energy",
    "gas ": "Energy",
    "petrolio": "Energy",
    "energia": "Energy",
    "power": "Energy",
    # Renewable Energy
    "renewable": "Renewable Energy",
    "solar": "Renewable Energy",
    "wind energy": "Renewable Energy",
    "clean energy": "Renewable Energy",
    "fotovoltaic": "Renewable Energy",
    "rinnovabil": "Renewable Energy",
    "green energy": "Renewable Energy",
    # Telecommunications
    "telecom": "Telecommunications",
    "tlc": "Telecommunications",
    "fiber": "Telecommunications",
    "fibra": "Telecommunications",
    "telecomunicazion": "Telecommunications",
    "broadband": "Telecommunications",
    # Media & Entertainment
    "media": "Media & Entertainment",
    "entertainment": "Media & Entertainment",
    "gaming": "Media & Entertainment",
    "publishing": "Media & Entertainment",
    "editoria": "Media & Entertainment",
    "editore": "Media & Entertainment",
    "comunicazione": "Media & Entertainment",
    # Education
    "education": "Education",
    "edtech": "Education",
    "training": "Education",
    "formazione": "Education",
    "istruzione": "Education",
    # Real Estate
    "real estate": "Real Estate",
    "property": "Real Estate",
    "immobiliar": "Real Estate",
    # Construction
    "construction": "Construction",
    "building": "Construction",
    "costruzion": "Construction",
    "edilizia": "Construction",
    "infrastruttur": "Construction",
    "infrastructure": "Construction",
    # Transportation & Logistics
    "transport": "Transportation & Logistics",
    "logistics": "Transportation & Logistics",
    "shipping": "Transportation & Logistics",
    "freight": "Transportation & Logistics",
    "logistic": "Transportation & Logistics",
    "trasport": "Transportation & Logistics",
    "spedizion": "Transportation & Logistics",
    "navigazione": "Transportation & Logistics",
    # Agriculture
    "agriculture": "Agriculture",
    "agri": "Agriculture",
    "farming": "Agriculture",
    "agricol": "Agriculture",
    # Chemicals
    "chemical": "Chemicals",
    "chimic": "Chemicals",
    # Environmental Services
    "environmental": "Environmental Services",
    "ambiente": "Environmental Services",
    "ambientale": "Environmental Services",
    # Professional Services
    "consulting": "Professional Services",
    "professional services": "Professional Services",
    "advisory": "Professional Services",
    "accounting": "Professional Services",
    "legal": "Professional Services",
    "staffing": "Professional Services",
    "human resources": "Professional Services",
    "hr ": "Professional Services",
    "payroll": "Professional Services",
    "servizi professionali": "Professional Services",
    "business services": "Professional Services",
    "services": "Professional Services",
    "outsourcing": "Professional Services",
    "testing": "Professional Services",
    "inspection": "Professional Services",
    "certification": "Professional Services",
    # Hospitality & Tourism
    "hospitality": "Hospitality & Tourism",
    "hotel": "Hospitality & Tourism",
    "tourism": "Hospitality & Tourism",
    "travel": "Hospitality & Tourism",
    "turismo": "Hospitality & Tourism",
    "alberghier": "Hospitality & Tourism",
    "camping": "Hospitality & Tourism",
    # Fashion & Luxury
    "fashion": "Fashion & Luxury",
    "luxury": "Fashion & Luxury",
    "apparel": "Fashion & Luxury",
    "moda": "Fashion & Luxury",
    "abbigliamento": "Fashion & Luxury",
    "lusso": "Fashion & Luxury",
    "eyewear": "Fashion & Luxury",
    "jewelry": "Fashion & Luxury",
    "gioiell": "Fashion & Luxury",
    "calzatur": "Fashion & Luxury",
    "footwear": "Fashion & Luxury",
    "tessile": "Fashion & Luxury",
    "textile": "Fashion & Luxury",
    "pelletter": "Fashion & Luxury",
    # Packaging
    "packaging": "Packaging",
    "imballaggio": "Packaging",
    "scatolificio": "Packaging",
    # Waste Management
    "waste": "Waste Management",
    "recycling": "Waste Management",
    "rifiuti": "Waste Management",
    "riciclo": "Waste Management",
    # Water & Utilities
    "water": "Water & Utilities",
    "utility": "Water & Utilities",
    "utilities": "Water & Utilities",
    "idrico": "Water & Utilities",
    "acqua": "Water & Utilities",
    # Mining & Metals
    "mining": "Mining & Metals",
    "metal": "Mining & Metals",
    "steel": "Mining & Metals",
    "acciaio": "Mining & Metals",
    "alluminio": "Mining & Metals",
    "minerario": "Mining & Metals",
}

# ─── Garbage patterns — sectors that should be set to null ──────────────────

GARBAGE_SECTORS = {
    "-", "read more", "elevate", "n/a", "other", "other,", "rmb",
    "latin america", "americas", "asia pacific", "emea", "europe",
    "not specified", "unknown", "tbd", "various",
}


def is_garbage_sector(sector: str) -> bool:
    """Check if a sector value is garbage and should be set to null."""
    if not sector or len(sector) < 2:
        return True
    lower = sector.lower().strip()
    if lower in GARBAGE_SECTORS:
        return True
    # Full sentences / descriptions (>80 chars with spaces)
    if len(sector) > 80 and " " in sector:
        return True
    # Starts with "SECTOR" prefix (scrape artifact)
    if sector.startswith("SECTOR"):
        return True
    # Contains "tecnologiaAi" or similar concatenation artifacts
    if "tecnologia" in lower and "," in lower:
        return True
    return False


def map_to_canonical(sector: str) -> str | None:
    """Map a free-text sector to canonical taxonomy using keyword matching."""
    if not sector:
        return None

    if is_garbage_sector(sector):
        return None

    # Strip "SECTOR" prefix if present
    clean = sector
    if clean.startswith("SECTOR"):
        clean = clean[6:].strip()

    # Direct match
    if clean in SECTOR_SET:
        return clean

    # Case-insensitive direct match
    lower = clean.lower().strip()
    for canonical in SECTOR_TAXONOMY:
        if canonical.lower() == lower:
            return canonical

    # Keyword matching (longest keyword first for better precision)
    sorted_keywords = sorted(SECTOR_KEYWORDS.keys(), key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in lower:
            return SECTOR_KEYWORDS[keyword]

    return None  # Unmapped


def normalize_aifi_tags(tags: list[str]) -> list[str]:
    """Convert AIFI sector_tags to canonical taxonomy, deduplicating.

    Preserves tags that are already canonical (e.g. from portfolio derivation).
    Only maps AIFI-format tags through AIFI_TO_CANONICAL.
    """
    canonical = []
    seen = set()
    for tag in tags:
        if tag in SECTOR_SET:
            # Already canonical — keep as-is
            if tag not in seen:
                canonical.append(tag)
                seen.add(tag)
        elif tag in AIFI_TO_CANONICAL:
            mapped = AIFI_TO_CANONICAL[tag]
            if mapped and mapped not in seen:
                canonical.append(mapped)
                seen.add(mapped)
        # else: unknown non-canonical tag — drop it
    return sorted(canonical)


def main():
    parser = argparse.ArgumentParser(description="Normalize sectors to canonical taxonomy")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes")
    args = parser.parse_args()

    # ─── 1. Normalize fund-level sector_tags in db.json ─────────────────────
    print("=" * 60)
    print("STEP 1: Normalize fund-level sector_tags (db.json)")
    print("=" * 60)

    db = json.loads(DB_FILE.read_text())
    funds = db.get("funds", [])

    fund_changes = 0
    tags_before = set()
    tags_after = set()

    for fund in funds:
        old_tags = fund.get("sector_tags", [])
        tags_before.update(old_tags)

        new_tags = normalize_aifi_tags(old_tags)
        tags_after.update(new_tags)

        if old_tags != new_tags:
            fund_changes += 1
            if fund_changes <= 5:  # Show first 5 examples
                print(f"  {fund['name']}:")
                print(f"    OLD: {old_tags}")
                print(f"    NEW: {new_tags}")
            fund["sector_tags"] = new_tags

    print(f"\n  Funds changed: {fund_changes}/{len(funds)}")
    print(f"  Unique tags before: {len(tags_before)} → after: {len(tags_after)}")
    print(f"  Tags after: {sorted(tags_after)}")

    # ─── 1b. Derive fund sector_tags from portfolio when empty ──────────────
    # Build a slug→fund index for step 1b (after portfolio normalization applies)
    fund_by_slug = {f["slug"]: f for f in funds if f.get("slug")}

    # ─── 2. Normalize company-level sectors in portfolio_items.json ──────────
    print("\n" + "=" * 60)
    print("STEP 2: Normalize company-level sectors (portfolio_items.json)")
    print("=" * 60)

    portfolio_data = json.loads(PORTFOLIO_FILE.read_text())
    fund_portfolios = portfolio_data.get("fund_portfolios", {})

    total_entries = 0
    mapped_by_keyword = 0
    already_canonical = 0
    set_to_null = 0
    locked_skipped = 0
    unmapped_list = []  # (original_sector, company_name) for OpenAI
    unmapped_unique = {}  # original → [(fund_slug, company_name)]

    for fund_slug, companies in fund_portfolios.items():
        for company in companies:
            total_entries += 1
            if company.get("curation_locked"):
                locked_skipped += 1
                continue
            sector = company.get("sector")
            if not sector:
                continue

            # Check if already canonical
            if sector in SECTOR_SET:
                already_canonical += 1
                continue

            # Try keyword mapping
            canonical = map_to_canonical(sector)
            if canonical:
                company["sector"] = canonical
                mapped_by_keyword += 1
                continue

            # Check garbage
            if is_garbage_sector(sector):
                company["sector"] = None
                set_to_null += 1
                continue

            # Unmapped — collect for OpenAI
            name = company.get("name", company.get("company_name", "unknown"))
            if sector not in unmapped_unique:
                unmapped_unique[sector] = []
            unmapped_unique[sector].append((fund_slug, name))

    print(f"\n  Total entries: {total_entries}")
    print(f"  Already canonical: {already_canonical}")
    print(f"  Mapped by keyword: {mapped_by_keyword}")
    print(f"  Set to null (garbage): {set_to_null}")
    print(f"  Locked entries skipped: {locked_skipped}")
    print(f"  Unmapped unique values: {len(unmapped_unique)}")

    # ─── 3. Report unmapped sectors (add to SECTOR_KEYWORDS to fix) ─────────
    if unmapped_unique:
        print("\n" + "=" * 60)
        print("STEP 3: Unmapped sectors — add to SECTOR_KEYWORDS to resolve")
        print("=" * 60)
        for sector, entries in sorted(unmapped_unique.items()):
            print(f"    \"{sector}\" ({len(entries)} entries, e.g. {entries[0][1]})")

    # ─── 4. Final stats ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("FINAL STATS")
    print("=" * 60)

    final_sectors = set()
    final_null = 0
    final_total = 0
    for companies in fund_portfolios.values():
        for company in companies:
            final_total += 1
            sector = company.get("sector")
            if sector:
                final_sectors.add(sector)
            else:
                final_null += 1

    canonical_count = sum(1 for s in final_sectors if s in SECTOR_SET)
    non_canonical = final_sectors - SECTOR_SET
    print(f"  Total entries: {final_total}")
    print(f"  Entries with sector: {final_total - final_null}")
    print(f"  Entries null sector: {final_null}")
    print(f"  Unique sectors: {len(final_sectors)}")
    print(f"  Canonical: {canonical_count}")
    if non_canonical:
        print(f"  Non-canonical ({len(non_canonical)}):")
        for s in sorted(non_canonical):
            print(f"    \"{s}\"")

    # ─── 5. Derive fund sector_tags from portfolio companies ─────────────────
    # Portfolio sectors are ground truth — AIFI tags are often incomplete/wrong.
    # For any fund with enough portfolio sector data, replace sector_tags entirely.
    print("\n" + "=" * 60)
    print("STEP 5: Derive fund sector_tags from portfolio companies")
    print("=" * 60)

    derived_count = 0
    kept_aifi = 0
    for fund in funds:
        slug = fund.get("slug", "")
        companies = fund_portfolios.get(slug, [])

        # Count sector occurrences across portfolio companies
        sector_counts: dict[str, int] = {}
        for company in companies:
            sector = company.get("sector")
            if sector and sector in SECTOR_SET:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1

        if not sector_counts:
            kept_aifi += 1
            continue  # No portfolio sector data — keep existing tags

        # Take top sectors (up to 5), sorted by frequency then alphabetically
        top_sectors = sorted(sector_counts.keys(), key=lambda s: (-sector_counts[s], s))[:5]
        old_tags = fund.get("sector_tags", [])
        if old_tags != top_sectors:
            fund["sector_tags"] = top_sectors
            derived_count += 1
            if derived_count <= 15:
                print(f"  {fund['name']}:")
                print(f"    was:  {old_tags}")
                print(f"    now:  {top_sectors} (from {len(companies)} companies)")

    empty_remaining = sum(1 for f in funds if not f.get("sector_tags"))
    print(f"\n  Updated from portfolio: {derived_count} funds")
    print(f"  Kept existing (no portfolio data): {kept_aifi} funds")
    print(f"  Still empty: {empty_remaining} funds")

    # ─── 6. Write results ───────────────────────────────────────────────────
    if args.dry_run:
        print("\n  DRY RUN — no files written")
    else:
        print("\n  Writing db.json...")
        safe_json_write(DB_FILE, db)

        print("  Writing portfolio_items.json...")
        safe_json_write(PORTFOLIO_FILE, portfolio_data)
        print("  Done!")


if __name__ == "__main__":
    main()
