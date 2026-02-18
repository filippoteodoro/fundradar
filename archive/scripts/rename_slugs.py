#!/usr/bin/env python3
"""
Rename fund slugs across all data files.

Usage:
    python scripts/rename_slugs.py          # dry-run (default)
    python scripts/rename_slugs.py --apply  # actually write changes
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DERIVED_DIR = DATA_DIR / "derived"
LINKEDIN_DIR = DERIVED_DIR / "linkedin"

# ── Rename mapping: old_slug → new_slug ────────────────────────────────
RENAMES: dict[str, str] = {
    "h-i-g-european-capital-partners-italy": "h-i-g-capital",
    "avm-sgr-spa-gestore-euveca-societa-benefit": "avm",
    "real-estate-asset-management-sgr-ream-sgr": "ream-sgr",
    "equiter-investimenti-per-il-territorio": "equiter",
    "macquarie-mam": "macquarie",
    "clessidra-private-equity-sgr": "clessidra-sgr",
    "eurizon-capital-real-asset-sgr": "eurizon-real-asset",
    "cdp-venture-capital-sgr": "cdp-venture-capital",
    "polis-sgr-gruppo-lbo-france": "polis-sgr",
    "permira-associati": "permira",
}

BACKUP_DIR = DERIVED_DIR / "backups_rename"


def backup_file(path: Path, dry_run: bool) -> None:
    """Create a timestamped backup of a file."""
    if dry_run or not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_path = BACKUP_DIR / f"{path.name}.pre_rename_{ts}"
    shutil.copy2(path, backup_path)
    print(f"  Backed up {path.name} → {backup_path.name}")


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        print(f"  [SKIP] {path} does not exist")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict | list, dry_run: bool) -> None:
    if dry_run:
        print(f"  [DRY-RUN] Would write {path.name}")
        return
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    print(f"  Wrote {path.name}")


# ── Individual file updaters ───────────────────────────────────────────

def update_db_json(dry_run: bool) -> int:
    """Update slug field on renamed funds in db.json."""
    path = DATA_DIR / "db.json"
    print(f"\n{'='*60}\nUpdating {path.name}")
    data = load_json(path)
    if data is None:
        return 0
    count = 0
    for fund in data.get("funds", []):
        old = fund.get("slug", "")
        if old in RENAMES:
            new = RENAMES[old]
            print(f"  {old} → {new}  (fund: {fund.get('name', '?')})")
            fund["slug"] = new
            count += 1
    if count:
        backup_file(path, dry_run)
        write_json(path, data, dry_run)
    print(f"  Updated {count} fund slugs")
    return count


def update_portfolio_items(dry_run: bool) -> int:
    """Rename keys in fund_portfolios dict."""
    path = DERIVED_DIR / "portfolio_items.json"
    print(f"\n{'='*60}\nUpdating {path.name}")
    data = load_json(path)
    if data is None:
        return 0

    count = 0
    # Handle both possible structures
    portfolios = data.get("fund_portfolios", data.get("portfolios", {}))
    keys_to_rename = [k for k in portfolios if k in RENAMES]
    for old_key in keys_to_rename:
        new_key = RENAMES[old_key]
        print(f"  Key: {old_key} → {new_key}  ({len(portfolios[old_key])} entries)")
        portfolios[new_key] = portfolios.pop(old_key)
        # Also update fund_slug inside each entry
        for entry in portfolios[new_key]:
            if entry.get("fund_slug") == old_key:
                entry["fund_slug"] = new_key
        count += 1

    # Also rename in sub-dicts (both camelCase and snake_case variants)
    for section_key in ("geoScopes", "sourceUrls", "portfolioNotes",
                        "geo_scopes", "fund_source_urls", "fund_geo_scopes",
                        "fund_portfolio_notes"):
        section = data.get(section_key, {})
        for old_key in list(section.keys()):
            if old_key in RENAMES:
                section[RENAMES[old_key]] = section.pop(old_key)

    if count:
        backup_file(path, dry_run)
        write_json(path, data, dry_run)
    print(f"  Renamed {count} portfolio keys")
    return count


def update_signals_file(filename: str, dry_run: bool) -> int:
    """Update fund_slug field in a signals JSON file."""
    path = DERIVED_DIR / filename
    print(f"\n{'='*60}\nUpdating {filename}")
    data = load_json(path)
    if data is None:
        return 0

    signals = data.get("signals", [])
    count = 0
    for sig in signals:
        old = sig.get("fund_slug", "")
        if old in RENAMES:
            sig["fund_slug"] = RENAMES[old]
            count += 1

    if count:
        backup_file(path, dry_run)
        write_json(path, data, dry_run)
    print(f"  Updated {count} signal fund_slugs")
    return count


def update_pem_deals(dry_run: bool) -> int:
    """Update fund_slug field in pem_deals.json."""
    path = DERIVED_DIR / "pem_deals.json"
    print(f"\n{'='*60}\nUpdating pem_deals.json")
    data = load_json(path)
    if data is None:
        return 0

    deals = data.get("deals", [])
    count = 0
    for deal in deals:
        old = deal.get("fund_slug", "")
        if old in RENAMES:
            deal["fund_slug"] = RENAMES[old]
            count += 1

    if count:
        backup_file(path, dry_run)
        write_json(path, data, dry_run)
    print(f"  Updated {count} deal fund_slugs")
    return count


def update_fund_people_stats(dry_run: bool) -> int:
    """Rename keys in fund_people_stats.json."""
    path = LINKEDIN_DIR / "fund_people_stats.json"
    print(f"\n{'='*60}\nUpdating fund_people_stats.json")
    data = load_json(path)
    if data is None:
        return 0

    funds = data.get("funds", {})
    count = 0
    keys_to_rename = [k for k in funds if k in RENAMES]
    for old_key in keys_to_rename:
        new_key = RENAMES[old_key]
        print(f"  Key: {old_key} → {new_key}")
        entry = funds.pop(old_key)
        entry["fund_slug"] = new_key
        funds[new_key] = entry
        count += 1

    if count:
        backup_file(path, dry_run)
        write_json(path, data, dry_run)
    print(f"  Renamed {count} fund keys")
    return count


def update_fund_aliases(dry_run: bool) -> int:
    """Add old→new mappings to aliases, update reverse_lookup."""
    path = DERIVED_DIR / "fund_aliases.json"
    print(f"\n{'='*60}\nUpdating fund_aliases.json")
    data = load_json(path)
    if data is None:
        return 0

    aliases = data.get("aliases", {})
    reverse = data.get("reverse_lookup", {})
    count = 0

    for old_slug, new_slug in RENAMES.items():
        # 1. Add the old→new alias
        aliases[old_slug] = new_slug
        print(f"  Alias: {old_slug} → {new_slug}")
        count += 1

        # 2. Migrate existing aliases that pointed to the old slug
        for alias_key, alias_target in list(aliases.items()):
            if alias_target == old_slug and alias_key != old_slug:
                aliases[alias_key] = new_slug
                print(f"  Migrated alias: {alias_key} → {new_slug} (was → {old_slug})")

        # 3. Update reverse_lookup: move old entry to new key, add old slug
        old_reverse = reverse.pop(old_slug, [])
        if new_slug not in reverse:
            reverse[new_slug] = []
        # Add old slug itself to reverse lookup
        if old_slug not in reverse[new_slug]:
            reverse[new_slug].append(old_slug)
        # Move over any existing reverse entries
        for alias in old_reverse:
            if alias not in reverse[new_slug]:
                reverse[new_slug].append(alias)

    backup_file(path, dry_run)
    write_json(path, data, dry_run)
    print(f"  Added {count} alias mappings")
    return count


def update_linkedin_urls(dry_run: bool) -> int:
    """Update slug field in fund_linkedin_urls.json."""
    path = LINKEDIN_DIR / "fund_linkedin_urls.json"
    print(f"\n{'='*60}\nUpdating fund_linkedin_urls.json")
    data = load_json(path)
    if data is None:
        return 0

    companies = data.get("companies", [])
    count = 0
    for company in companies:
        old = company.get("slug", "")
        if old in RENAMES:
            print(f"  {old} → {RENAMES[old]}  ({company.get('name', '?')})")
            company["slug"] = RENAMES[old]
            count += 1

    if count:
        backup_file(path, dry_run)
        write_json(path, data, dry_run)
    print(f"  Updated {count} linkedin URL slugs")
    return count


def update_monitor_urls(dry_run: bool) -> int:
    """Update slug field in monitor_urls.json entities."""
    path = DERIVED_DIR / "monitor_urls.json"
    print(f"\n{'='*60}\nUpdating monitor_urls.json")
    data = load_json(path)
    if data is None:
        return 0

    entities = data.get("entities", [])
    count = 0
    for entity in entities:
        old = entity.get("slug", "")
        if old in RENAMES:
            entity["slug"] = RENAMES[old]
            count += 1

    if count:
        backup_file(path, dry_run)
        write_json(path, data, dry_run)
    print(f"  Updated {count} monitor URL slugs")
    return count


def update_ancillary_json(filename: str, dry_run: bool) -> int:
    """Update slugs in ancillary JSON files that use slug as key or field.

    Handles files like: extractor_work_queue.json, signal_work_queue.json,
    fund_page_audit.json, fund_extraction_audit.json, etc.
    """
    path = DERIVED_DIR / filename
    if not path.exists():
        return 0

    print(f"\n{'='*60}\nUpdating {filename}")
    data = load_json(path)
    if data is None:
        return 0

    count = 0
    text = json.dumps(data)
    for old_slug, new_slug in RENAMES.items():
        # Only replace exact slug matches (surrounded by quotes)
        old_pattern = f'"{old_slug}"'
        new_pattern = f'"{new_slug}"'
        occurrences = text.count(old_pattern)
        if occurrences:
            text = text.replace(old_pattern, new_pattern)
            count += occurrences
            print(f"  Replaced {occurrences}x: {old_slug} → {new_slug}")

    if count:
        data = json.loads(text)
        backup_file(path, dry_run)
        write_json(path, data, dry_run)
    print(f"  Updated {count} slug references")
    return count


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Rename fund slugs across all data files")
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run)")
    args = parser.parse_args()
    dry_run = not args.apply

    if dry_run:
        print("=" * 60)
        print("DRY-RUN MODE — no files will be modified")
        print("Run with --apply to write changes")
        print("=" * 60)
    else:
        print("=" * 60)
        print("APPLYING CHANGES — files will be modified")
        print("=" * 60)

    total = 0

    # Core data files
    total += update_db_json(dry_run)
    total += update_portfolio_items(dry_run)
    total += update_signals_file("detected_signals.json", dry_run)
    total += update_signals_file("detected_signals_filtered.json", dry_run)
    total += update_signals_file("detected_signals_enriched.json", dry_run)
    total += update_pem_deals(dry_run)
    total += update_fund_people_stats(dry_run)
    total += update_fund_aliases(dry_run)
    total += update_linkedin_urls(dry_run)
    total += update_monitor_urls(dry_run)

    # Ancillary files that reference slugs
    ancillary_files = [
        "extractor_work_queue.json",
        "signal_work_queue.json",
        "fund_page_audit.json",
        "fund_extraction_audit.json",
        "fund_quality_audit.json",
        "bulk_extraction_audit.json",
        "signal_audit_report.json",
        "signal_summary_report.json",
        "monitor_urls_report.json",
        "enrichment_progress.json",
        "enrichment_data_progress.json",
        "enrichment_portfolio_full_progress.json",
        "portfolio_enrichment_progress.json",
        "quality_baselines.json",
        "aifi_refresh_queue.json",
        "fund_coordinates.json",
        "entity_links.json",
        "team_items.json",
        "news_items.json",
        "asset_status_audit.json",
        "pem_status_audit.json",
        "aifi_members_enriched.json",
        "aifi_members.json",
    ]
    for f in ancillary_files:
        total += update_ancillary_json(f, dry_run)

    # LinkedIn ancillary
    for f in ["manual_profiles.json", "fund_linkedin_urls_prioritized.json"]:
        p = LINKEDIN_DIR / f
        if p.exists():
            total += update_ancillary_json(f"linkedin/{f}", dry_run)

    print(f"\n{'='*60}")
    print(f"Total slug references updated: {total}")
    if dry_run:
        print("Re-run with --apply to write changes")
    else:
        print("All changes applied successfully")
    print("=" * 60)


if __name__ == "__main__":
    main()
