#!/usr/bin/env python3
"""
Backfill URLS dicts into existing extractor files.

This script:
1. Loads fund_urls.json to get verified URLs for each fund
2. For each extractor file, matches its DOMAIN to fund_urls.json entries
3. Extracts the path from full URLs (e.g., "https://alcedo.it/news/" -> "/news/")
4. Inserts a URLS dict after the DOMAIN line if not already present

Usage:
    python scripts/backfill_extractor_urls.py --dry-run  # Preview changes
    python scripts/backfill_extractor_urls.py            # Apply changes
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


def normalize_domain(domain: str) -> str:
    """Normalize domain for matching (strip www., lowercase)."""
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def extract_path(full_url: str, base_url: str) -> str | None:
    """Extract the path from a full URL, relative to the base domain."""
    if not full_url:
        return None

    # Parse both URLs
    full_parsed = urlparse(full_url if full_url.startswith("http") else f"https://{full_url}")
    base_parsed = urlparse(base_url if base_url.startswith("http") else f"https://{base_url}")

    # Check if domains match (after normalization)
    full_domain = normalize_domain(full_parsed.netloc or full_parsed.path.split("/")[0])
    base_domain = normalize_domain(base_parsed.netloc or base_parsed.path.split("/")[0])

    if full_domain != base_domain:
        # URLs are on different domains - might be subdomain or different site
        # Return full URL in this case
        return full_url

    # Extract path
    path = full_parsed.path
    if not path or path == "/":
        return "/"

    return path


def load_fund_urls(fund_urls_path: Path) -> dict:
    """Load fund_urls.json and build domain -> URLs mapping."""
    with open(fund_urls_path) as f:
        fund_urls = json.load(f)

    domain_to_urls = {}
    for fund_slug, data in fund_urls.items():
        website = data.get("website", "")
        if not website:
            continue

        # Parse domain from website
        parsed = urlparse(website if website.startswith("http") else f"https://{website}")
        domain = normalize_domain(parsed.netloc or parsed.path.split("/")[0])

        urls = {}

        # Extract paths for each page type
        if data.get("portfolio"):
            urls["portfolio"] = extract_path(data["portfolio"], website)
        if data.get("team"):
            urls["team"] = extract_path(data["team"], website)
        if data.get("news"):
            urls["news"] = extract_path(data["news"], website)

        if urls:
            domain_to_urls[domain] = urls

    return domain_to_urls


def find_extractor_domain(content: str) -> str | None:
    """Extract the DOMAIN value from an extractor file."""
    match = re.search(r'^DOMAIN\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if match:
        return match.group(1)
    return None


def has_urls_declaration(content: str) -> bool:
    """Check if the file already has a URLS declaration."""
    return bool(re.search(r'^URLS\s*=', content, re.MULTILINE))


def build_urls_block(urls: dict) -> str:
    """Build the URLS dict block to insert."""
    lines = ["", "# URL paths for monitoring (auto-generated from fund_urls.json)"]
    lines.append("URLS = {")

    portfolio = urls.get("portfolio")
    team = urls.get("team")
    news = urls.get("news")

    if portfolio:
        lines.append(f'    "portfolio": "{portfolio}",')
    else:
        lines.append('    "portfolio": None,')

    if team:
        lines.append(f'    "team": "{team}",')
    else:
        lines.append('    "team": None,')

    if news:
        lines.append(f'    "news": "{news}",')
    else:
        lines.append('    "news": None,')

    lines.append("}")
    return "\n".join(lines)


def insert_urls_after_domain(content: str, urls_block: str) -> str:
    """Insert URLS block after the DOMAIN = ... line."""
    # Find the DOMAIN line and insert after it
    pattern = r'^(DOMAIN\s*=\s*["\'][^"\']+["\'])\s*\n'
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        insert_pos = match.end()
        return content[:insert_pos] + urls_block + "\n" + content[insert_pos:]
    return content


def process_extractor(extractor_path: Path, domain_to_urls: dict, dry_run: bool) -> dict:
    """Process a single extractor file."""
    content = extractor_path.read_text()
    result = {
        "file": extractor_path.name,
        "status": "skipped",
        "reason": None,
    }

    # Skip if already has URLS
    if has_urls_declaration(content):
        result["reason"] = "already has URLS"
        return result

    # Get domain from extractor
    domain = find_extractor_domain(content)
    if not domain:
        result["reason"] = "no DOMAIN found"
        return result

    # Normalize and look up in fund_urls
    norm_domain = normalize_domain(domain)
    urls = domain_to_urls.get(norm_domain)

    # Also try with www prefix
    if not urls and not norm_domain.startswith("www."):
        urls = domain_to_urls.get(f"www.{norm_domain}")

    if not urls:
        # No matching entry - create empty URLS
        urls = {}

    # Build URLS block
    urls_block = build_urls_block(urls)

    # Insert into content
    new_content = insert_urls_after_domain(content, urls_block)

    if new_content == content:
        result["reason"] = "failed to insert"
        return result

    result["status"] = "updated" if urls else "added_empty"
    result["urls"] = urls
    result["domain"] = domain

    if not dry_run:
        extractor_path.write_text(new_content)
        result["written"] = True
    else:
        result["written"] = False

    return result


def main():
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    # Get project root
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent

    # Paths
    fund_urls_path = project_root / "data" / "site_configs" / "fund_urls.json"
    extractors_dir = project_root / "apps" / "worker" / "fundradar_worker" / "strategies" / "extractors"

    if not fund_urls_path.exists():
        print(f"Error: fund_urls.json not found at {fund_urls_path}")
        sys.exit(1)

    if not extractors_dir.exists():
        print(f"Error: extractors directory not found at {extractors_dir}")
        sys.exit(1)

    print("Backfill Extractor URLS")
    print("=======================")
    if dry_run:
        print("DRY RUN - no files will be modified\n")
    else:
        print("LIVE RUN - files will be modified\n")

    # Load fund_urls.json
    print(f"Loading fund_urls.json...")
    domain_to_urls = load_fund_urls(fund_urls_path)
    print(f"  Found {len(domain_to_urls)} domains with URLs\n")

    # Process all extractors
    extractor_files = sorted(extractors_dir.glob("*.py"))
    extractor_files = [f for f in extractor_files if not f.name.startswith("_")]

    stats = {
        "total": len(extractor_files),
        "updated": 0,
        "added_empty": 0,
        "skipped_has_urls": 0,
        "skipped_no_domain": 0,
        "skipped_failed": 0,
    }

    print(f"Processing {len(extractor_files)} extractor files...\n")

    for extractor_path in extractor_files:
        result = process_extractor(extractor_path, domain_to_urls, dry_run)

        if result["status"] == "updated":
            stats["updated"] += 1
            if verbose or dry_run:
                print(f"  [UPDATE] {result['file']}: {result['urls']}")
        elif result["status"] == "added_empty":
            stats["added_empty"] += 1
            if verbose or dry_run:
                print(f"  [EMPTY]  {result['file']}: no matching URLs in fund_urls.json")
        elif result["reason"] == "already has URLS":
            stats["skipped_has_urls"] += 1
            if verbose:
                print(f"  [SKIP]   {result['file']}: already has URLS")
        elif result["reason"] == "no DOMAIN found":
            stats["skipped_no_domain"] += 1
            if verbose:
                print(f"  [SKIP]   {result['file']}: no DOMAIN constant found")
        else:
            stats["skipped_failed"] += 1
            if verbose:
                print(f"  [FAIL]   {result['file']}: {result['reason']}")

    # Print summary
    print("\nSummary:")
    print(f"  Total extractors: {stats['total']}")
    print(f"  Updated with URLs: {stats['updated']}")
    print(f"  Added empty URLS: {stats['added_empty']}")
    print(f"  Skipped (already has URLS): {stats['skipped_has_urls']}")
    print(f"  Skipped (no DOMAIN): {stats['skipped_no_domain']}")
    print(f"  Failed: {stats['skipped_failed']}")

    if dry_run:
        print("\nRun without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
