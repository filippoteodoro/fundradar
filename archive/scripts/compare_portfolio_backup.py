#!/usr/bin/env python3
"""Compare portfolio_items.json backup vs current to identify data loss."""

import json
import re
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CURRENT = os.path.join(REPO, "data/derived/portfolio_items.json")
BACKUP = os.path.join(REPO, "data/derived/portfolio_items.json.bak")

def normalize(name):
    """Simple normalize for comparison."""
    if not name:
        return ""
    n = name.lower().strip()
    # Strip common suffixes
    for suffix in [" s.p.a.", " s.r.l.", " s.a.s.", " spa", " srl", " sas", " s.a.", " ltd", " inc", " group", " holding"]:
        if n.endswith(suffix):
            n = n[:-len(suffix)].strip()
    # Remove non-alphanumeric
    n = re.sub(r'[^a-z0-9 ]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

# Known garbage patterns
GARBAGE_PATTERNS = [
    # Abenex real estate
    r"résidence|centre commercial|rue |avenue |boulevard |parc de|pôle|programme",
    # CDP Equity FoF
    r"^(eqt|permira|cinven|apax|ardian|carlyle|kkr|bridgepoint|charterhouse|cvc|pai|silver lake|warburg|bc partners|advent|bain capital|hellman|hg capital|montagu|nordic|pai europe|providence|thoma bravo|vista equity)\s+(vi+i*|[ivx]+|fund|capital)\b",
    # Sienna fund strategies
    r"pan european|absolute return|long.?short|credit fund|equity fund|global macro|fixed income|multi.?strategy|systematic|convertible|event driven|merger arbitrage|volatility",
    # SEFEA ALL CAPS
    r"^[A-Z\s]{8,}$",
    # Government programs
    r"nuova sabatini|sabatini|incentivo|agevolazione|bando|contributo",
    # Union/association names
    r"\bcisl\b|\bcgil\b|\buil\b|sindacato|first cisl|società partecipate",
    # Duplicate words
    r"^(\w+)\s+\1$",
    # CTA/navigation
    r"scopri di più|scopri di piu|leggi tutto|read more|continua a leggere",
    # FKA/AKA patterns
    r"\((?:fka|aka|formerly|previously)\s+",
    # Charme misattributed domains
    r"^(tata|medtronic|livingbridge|cassina|cappellini|tata communications)$",
    # KKR misattributed
    r"^(ensora health|karo healthcare|korean battery ess)$",
]

def is_known_garbage(name):
    """Check if a name matches known garbage patterns."""
    if not name:
        return True
    n = name.strip()
    for pattern in GARBAGE_PATTERNS:
        if re.search(pattern, n, re.IGNORECASE):
            return True
    return False


def main():
    with open(BACKUP, 'r') as f:
        backup_data = json.load(f)
    with open(CURRENT, 'r') as f:
        current_data = json.load(f)

    backup_portfolios = backup_data.get("fund_portfolios", {})
    current_portfolios = current_data.get("fund_portfolios", {})

    cat_a_garbage = []  # Known garbage removals
    cat_b_renamed = []  # Exist under different name
    cat_c_missing = []  # Actually missing - potential data loss
    sector_diffs = []   # Entries with sector changes

    all_slugs = set(list(backup_portfolios.keys()) + list(current_portfolios.keys()))

    for slug in sorted(all_slugs):
        backup_entries = backup_portfolios.get(slug, [])
        current_entries = current_portfolios.get(slug, [])

        # Build lookup for current entries
        current_names = {e.get("name", ""): e for e in current_entries}
        current_normalized = {normalize(e.get("name", "")): e for e in current_entries if e.get("name")}

        for bentry in backup_entries:
            bname = bentry.get("name", "")
            if not bname:
                continue

            # Check exact match
            if bname in current_names:
                # Entry exists - check for field differences
                centry = current_names[bname]
                bsector = bentry.get("sector")
                csector = centry.get("sector")
                if bsector and csector and bsector != csector:
                    sector_diffs.append({
                        "slug": slug,
                        "name": bname,
                        "old_sector": bsector,
                        "new_sector": csector,
                    })
                # Check for lost enrichment fields
                for field in ["description", "website", "headquarters", "sector_source_url", "data_source_url"]:
                    bval = bentry.get(field)
                    cval = centry.get(field)
                    if bval and not cval:
                        cat_c_missing.append({
                            "slug": slug,
                            "name": bname,
                            "issue": f"FIELD_LOST: {field} was '{bval[:80]}...' now None",
                            "backup_entry": bentry,
                            "type": "field_loss",
                        })
                continue

            # Check normalized match
            bnorm = normalize(bname)
            if bnorm in current_normalized:
                cat_b_renamed.append({
                    "slug": slug,
                    "backup_name": bname,
                    "current_name": current_normalized[bnorm].get("name", ""),
                })
                continue

            # Check substring match (backup name is longer version)
            found_match = False
            for cname, centry in current_names.items():
                cnorm = normalize(cname)
                if len(bnorm) >= 4 and len(cnorm) >= 4:
                    if bnorm in cnorm or cnorm in bnorm:
                        cat_b_renamed.append({
                            "slug": slug,
                            "backup_name": bname,
                            "current_name": cname,
                        })
                        found_match = True
                        break
            if found_match:
                continue

            # Not found - classify
            if is_known_garbage(bname):
                cat_a_garbage.append({
                    "slug": slug,
                    "name": bname,
                })
            else:
                cat_c_missing.append({
                    "slug": slug,
                    "name": bname,
                    "backup_entry": bentry,
                    "type": "entry_missing",
                })

    # Print results
    print("=" * 80)
    print("PORTFOLIO BACKUP vs CURRENT COMPARISON")
    print("=" * 80)

    print(f"\n## Category A - Known Garbage Removals (INTENTIONAL): {len(cat_a_garbage)}")
    for item in cat_a_garbage:
        print(f"  [{item['slug']}] {item['name']}")

    print(f"\n## Category B - Renamed/Cleaned Entries: {len(cat_b_renamed)}")
    for item in cat_b_renamed:
        print(f"  [{item['slug']}] '{item['backup_name']}' → '{item['current_name']}'")

    # Separate field losses from missing entries
    field_losses = [x for x in cat_c_missing if x.get("type") == "field_loss"]
    entry_missing = [x for x in cat_c_missing if x.get("type") == "entry_missing"]

    print(f"\n## FIELD LOSSES (entry exists but lost enrichment): {len(field_losses)}")
    for item in field_losses:
        print(f"  [{item['slug']}] {item['name']}: {item['issue']}")

    print(f"\n## Category C - ACTUALLY MISSING ENTRIES (potential data loss): {len(entry_missing)}")
    for item in entry_missing:
        e = item["backup_entry"]
        enriched = []
        if e.get("sector"): enriched.append(f"sector={e['sector']}")
        if e.get("website"): enriched.append(f"website={e['website']}")
        if e.get("description"): enriched.append(f"desc={e['description'][:50]}...")
        if e.get("headquarters"): enriched.append(f"hq={e['headquarters']}")
        if e.get("sector_source_url"): enriched.append("has_sector_source")
        enriched_str = " | ".join(enriched) if enriched else "no enrichment"
        print(f"  [{item['slug']}] {item['name']} ({enriched_str})")

    print(f"\n## Sector Changes: {len(sector_diffs)}")
    # Show a sample of 20
    for item in sector_diffs[:20]:
        print(f"  [{item['slug']}] {item['name']}: '{item['old_sector']}' → '{item['new_sector']}'")
    if len(sector_diffs) > 20:
        print(f"  ... and {len(sector_diffs) - 20} more")

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Garbage removals (intentional):  {len(cat_a_garbage)}")
    print(f"  Renamed/cleaned entries:         {len(cat_b_renamed)}")
    print(f"  Field losses (enrichment lost):  {len(field_losses)}")
    print(f"  MISSING entries (data loss):     {len(entry_missing)}")
    print(f"  Sector changes:                  {len(sector_diffs)}")

    # Write Category C entries to a restoration file
    if entry_missing:
        restore_file = os.path.join(REPO, "scripts/entries_to_restore.json")
        restore_data = {}
        for item in entry_missing:
            slug = item["slug"]
            if slug not in restore_data:
                restore_data[slug] = []
            restore_data[slug].append(item["backup_entry"])
        with open(restore_file, 'w') as f:
            json.dump(restore_data, f, indent=2, ensure_ascii=False)
        print(f"\n  Category C entries saved to: {restore_file}")

    if field_losses:
        field_file = os.path.join(REPO, "scripts/fields_to_restore.json")
        field_data = {}
        for item in field_losses:
            slug = item["slug"]
            if slug not in field_data:
                field_data[slug] = []
            field_data[slug].append({
                "name": item["name"],
                "backup_entry": item["backup_entry"],
            })
        with open(field_file, 'w') as f:
            json.dump(field_data, f, indent=2, ensure_ascii=False)
        print(f"  Field losses saved to: {field_file}")


if __name__ == "__main__":
    main()
