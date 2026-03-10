#!/usr/bin/env python3
"""
Cross-fund portfolio company normalization.

Finds companies that appear in multiple fund portfolios and normalizes
shared fields (name, website, sector, headquarters, description) to
the best available value across all entries.

Fund-specific fields are NEVER overwritten: status, confidence,
investment_date, entry_date, exit_date, data_source, source_url,
detail_page_url.

Usage:
    python apps/worker/scripts/normalize_portfolio_cross_fund.py [--dry-run]
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

# Add parent so we can import fundradar_worker
sys.path.insert(0, str(Path(__file__).parent.parent))

from fundradar_worker.paths import PROJECT_ROOT, DATA_DIR, DB_PATH, PORTFOLIO_FILE as PORTFOLIO_PATH, SECTOR_TAXONOMY
from fundradar_worker.io_utils import safe_json_write, backup_before_write
from fundradar_worker.portfolio_validation import clean_portfolio_name, is_valid_portfolio_entry
from fundradar_worker.url_utils import extract_domain

# ─── Configuration ────────────────────────────────────────────────────────────

MIN_NAME_LENGTH = 6  # Minimum normalized name length to group

# Short names that are different companies across funds — skip normalization
FALSE_POSITIVE_NAMES = frozenset({
    "eco", "one", "insight", "argenta", "aleph", "europa", "icon", "quick",
    "facile", "prima", "target", "delta", "next", "mosaico", "verde",
    "bravo", "alpha", "omega", "sigma", "genesis", "global", "impact",
    "aurora", "nova", "spring", "bridge", "pioneer", "summit", "horizon",
})

# Fields that are fund-specific and must NEVER be overwritten
FUND_SPECIFIC_FIELDS = frozenset({
    "status", "confidence", "investment_date", "entry_date", "exit_date",
    "data_source", "source_url", "detail_page_url",
})

_SECTOR_TAXONOMY_SET = frozenset(SECTOR_TAXONOMY)

# Legal suffixes to strip for normalization
LEGAL_SUFFIX_PATTERN = re.compile(
    r"(?:\s+|,\s*)(?:"
    r"S\.?p\.?A\.?|S\.?r\.?l\.?|S\.?a\.?s\.?|S\.?n\.?c\.?"
    r"|Ltd\.?|LLC\.?|Inc\.?|GmbH\.?|AG\.?|B\.?V\.?|N\.?V\.?"
    r"|PLC\.?|Corp\.?|Corporation|Company|Group|Holdings?|SE|SA|S\.?A\.?"
    r")\s*$",
    re.IGNORECASE,
)


# ─── Name normalization ──────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """Normalize a company name for grouping (lowercase, strip suffixes)."""
    if not name:
        return ""
    n = name.lower().strip()
    # Strip legal suffixes (may need multiple passes)
    for _ in range(3):
        prev = n
        n = LEGAL_SUFFIX_PATTERN.sub("", n).strip()
        if n == prev:
            break
    # Remove non-alphanumeric (keep spaces)
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


# ─── Fund domain detection ───────────────────────────────────────────────────

def _load_fund_domains() -> set[str]:
    """Load fund website domains from db.json for filtering."""
    domains = set()
    if not DB_PATH.exists():
        return domains
    try:
        with open(DB_PATH) as f:
            data = json.load(f)
        for fund in data.get("funds", []):
            website = fund.get("website", "")
            if website:
                domain = extract_domain(website)
                if domain:
                    domains.add(domain)
    except Exception:
        pass
    return domains


def _is_fund_page_url(url: str, fund_domains: set[str]) -> bool:
    """Check if a URL points to a fund's website (not the company's own site)."""
    if not url:
        return False
    domain = extract_domain(url)
    return domain in fund_domains


# ─── Best value selection ────────────────────────────────────────────────────

def pick_best_name(entries: list[dict]) -> str | None:
    """Pick the best display name from a group of entries.

    Prefers: proper-cased (not ALL CAPS), without legal suffixes,
    most common form.
    """
    names = [e.get("name", "") for e in entries if e.get("name")]
    if not names:
        return None

    # Filter out ALL CAPS versions if mixed-case alternatives exist
    non_upper = [n for n in names if n != n.upper()]
    candidates = non_upper if non_upper else names

    # Strip legal suffixes from candidates for comparison
    cleaned = []
    for name in candidates:
        c = LEGAL_SUFFIX_PATTERN.sub("", name).strip()
        cleaned.append(c if c else name)

    # Count occurrences of each cleaned form
    counter = Counter(cleaned)
    most_common_name, most_common_count = counter.most_common(1)[0]

    # If there's a clear winner, use it
    if most_common_count > 1:
        return most_common_name

    # Otherwise pick the longest proper-cased cleaned name
    return max(cleaned, key=len)


def pick_best_website(entries: list[dict], fund_domains: set[str]) -> str | None:
    """Pick the best website URL, preferring the company's own site."""
    urls = [e.get("website") for e in entries if e.get("website")]
    if not urls:
        return None

    # Filter out fund-page URLs
    company_urls = [u for u in urls if not _is_fund_page_url(u, fund_domains)]
    candidates = company_urls if company_urls else urls

    # Prefer shorter/cleaner URLs (company homepage vs deep links)
    # Sort by path length — shorter paths are more likely homepages
    def url_score(u: str) -> tuple[int, int]:
        try:
            parsed = urlparse(u if u.startswith("http") else "https://" + u)
            path_len = len(parsed.path.rstrip("/"))
            return (0 if path_len <= 1 else 1, len(u))
        except Exception:
            return (2, len(u))

    candidates.sort(key=url_score)
    return candidates[0]


def pick_best_sector(entries: list[dict]) -> str | None:
    """Pick the best sector, preferring canonical taxonomy values."""
    sectors = [e.get("sector") for e in entries if e.get("sector")]
    if not sectors:
        return None

    # Prefer canonical sectors
    canonical = [s for s in sectors if s in _SECTOR_TAXONOMY_SET]
    candidates = canonical if canonical else sectors

    # Most common
    counter = Counter(candidates)
    return counter.most_common(1)[0][0]


def pick_best_hq(entries: list[dict]) -> str | None:
    """Pick the most specific headquarters value."""
    hqs = [e.get("headquarters") for e in entries if e.get("headquarters")]
    if not hqs:
        return None

    # Prefer "City, Country" format over just "Country"
    city_country = [h for h in hqs if "," in h]
    candidates = city_country if city_country else hqs

    # Pick the longest (most specific)
    return max(candidates, key=len)


def pick_best_description(entries: list[dict]) -> str | None:
    """Pick the best description, avoiding pipe artifacts and short stubs."""
    descs = [e.get("description") for e in entries if e.get("description")]
    if not descs:
        return None

    # Clean pipe artifacts (e.g., "operatorEMEA|Transport")
    cleaned = []
    for d in descs:
        if "|" in d:
            # Strip everything from the first pipe onwards if it looks like artifact
            parts = d.split("|")
            # If first part is substantially longer, it's likely the real description
            if len(parts[0]) > 20:
                d = parts[0].strip()
            else:
                continue  # Skip entirely mangled descriptions
        # Skip very short descriptions that are likely stubs
        if len(d) < 15:
            continue
        # Skip descriptions that look like page metadata
        if d.startswith("Strategy:") or d.startswith("Sector:"):
            continue
        cleaned.append(d)

    if not cleaned:
        # Fall back to original if all were filtered
        return max(descs, key=len) if descs else None

    # Pick the longest clean description
    return max(cleaned, key=len)


def cleanup_invalid_entries(fund_portfolios: dict[str, list[dict]], dry_run: bool) -> dict[str, int]:
    """Drop invalid portfolio entries and normalize names with shared validation logic.

    Uses fundradar_worker.portfolio_validation as the single source of truth so
    cleanup remains aligned with monitor-time validation.
    """
    removed = 0
    renamed = 0

    for fund_slug, entries in list(fund_portfolios.items()):
        cleaned_entries: list[dict] = []

        for entry in entries:
            if entry.get("curation_locked"):
                cleaned_entries.append(entry)
                continue

            raw_name = (entry.get("name") or "").strip()
            if not raw_name:
                removed += 1
                continue

            normalized_name = clean_portfolio_name(raw_name)
            if not normalized_name or not is_valid_portfolio_entry(normalized_name, fund_slug):
                removed += 1
                continue

            if normalized_name != raw_name:
                renamed += 1
                if not dry_run:
                    entry["name"] = normalized_name
            cleaned_entries.append(entry)

        if not dry_run:
            fund_portfolios[fund_slug] = cleaned_entries

    return {"removed": removed, "renamed": renamed}


# ─── Main normalization ──────────────────────────────────────────────────────

def normalize_cross_fund(dry_run: bool = False) -> dict:
    """Run cross-fund normalization on portfolio_items.json.

    Returns stats dict with counts of changes made.
    """
    # Load data
    with open(PORTFOLIO_PATH) as f:
        data = json.load(f)

    fund_portfolios = data.get("fund_portfolios", {})
    fund_domains = _load_fund_domains()

    # Build groups: normalized_name -> list of (fund_slug, entry_index, entry)
    groups: dict[str, list[tuple[str, int, dict]]] = defaultdict(list)

    for slug, entries in fund_portfolios.items():
        for idx, entry in enumerate(entries):
            name = entry.get("name", "")
            if not name:
                continue
            norm = normalize_name(name)
            if len(norm) < MIN_NAME_LENGTH:
                continue
            if norm in FALSE_POSITIVE_NAMES:
                continue
            groups[norm].append((slug, idx, entry))

    # Filter to multi-fund groups only
    multi_fund_groups = {}
    for norm_name, members in groups.items():
        fund_slugs = set(slug for slug, _, _ in members)
        if len(fund_slugs) >= 2:
            multi_fund_groups[norm_name] = members

    stats = {
        "total_groups": len(multi_fund_groups),
        "entries_updated": 0,
        "invalid_entries_removed": 0,
        "names_cleaned": 0,
        "fields_updated": {
            "name": 0,
            "website": 0,
            "sector": 0,
            "headquarters": 0,
            "description": 0,
        },
    }

    # Process each group
    for norm_name, members in sorted(multi_fund_groups.items()):
        entries_only = [entry for _, _, entry in members]

        best_name = pick_best_name(entries_only)
        best_website = pick_best_website(entries_only, fund_domains)
        best_sector = pick_best_sector(entries_only)
        best_hq = pick_best_hq(entries_only)
        best_desc = pick_best_description(entries_only)

        # Apply best values to all entries in the group
        for fund_slug, entry_idx, entry in members:
            if entry.get("curation_locked"):
                # Do not mutate manually curated / locked entries.
                continue
            updated = False

            if best_name and entry.get("name") != best_name:
                if not dry_run:
                    fund_portfolios[fund_slug][entry_idx]["name"] = best_name
                stats["fields_updated"]["name"] += 1
                updated = True

            if best_website and entry.get("website") != best_website:
                if not dry_run:
                    fund_portfolios[fund_slug][entry_idx]["website"] = best_website
                stats["fields_updated"]["website"] += 1
                updated = True

            if best_sector and entry.get("sector") != best_sector:
                if not dry_run:
                    fund_portfolios[fund_slug][entry_idx]["sector"] = best_sector
                stats["fields_updated"]["sector"] += 1
                updated = True

            if best_hq and entry.get("headquarters") != best_hq:
                if not dry_run:
                    fund_portfolios[fund_slug][entry_idx]["headquarters"] = best_hq
                stats["fields_updated"]["headquarters"] += 1
                updated = True

            if best_desc and entry.get("description") != best_desc:
                if not dry_run:
                    fund_portfolios[fund_slug][entry_idx]["description"] = best_desc
                stats["fields_updated"]["description"] += 1
                updated = True

            if updated:
                stats["entries_updated"] += 1

    cleanup_stats = cleanup_invalid_entries(fund_portfolios, dry_run=dry_run)
    stats["invalid_entries_removed"] = cleanup_stats["removed"]
    stats["names_cleaned"] = cleanup_stats["renamed"]

    changes_written = (
        stats["entries_updated"] > 0
        or stats["invalid_entries_removed"] > 0
        or stats["names_cleaned"] > 0
    )

    # Write back
    if not dry_run and changes_written:
        backup_before_write(PORTFOLIO_PATH)
        safe_json_write(PORTFOLIO_PATH, data)

    return stats


def main():
    dry_run = "--dry-run" in sys.argv

    if not PORTFOLIO_PATH.exists():
        print(f"ERROR: {PORTFOLIO_PATH} not found")
        sys.exit(1)

    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"Cross-fund portfolio normalization ({mode})")
    print(f"  Portfolio: {PORTFOLIO_PATH}")
    print()

    stats = normalize_cross_fund(dry_run=dry_run)

    print(f"Results:")
    print(f"  Multi-fund company groups: {stats['total_groups']}")
    print(f"  Entries updated: {stats['entries_updated']}")
    print(f"  Invalid entries removed: {stats['invalid_entries_removed']}")
    print(f"  Names cleaned by validator: {stats['names_cleaned']}")
    print(f"  Field updates:")
    for field, count in stats["fields_updated"].items():
        print(f"    {field}: {count}")

    if dry_run:
        print(f"\n  (dry run — no changes written)")
    elif (
        stats["entries_updated"] > 0
        or stats["invalid_entries_removed"] > 0
        or stats["names_cleaned"] > 0
    ):
        print(f"\n  Written to {PORTFOLIO_PATH}")
    else:
        print(f"\n  No changes needed.")


if __name__ == "__main__":
    main()
