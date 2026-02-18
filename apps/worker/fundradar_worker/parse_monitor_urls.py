"""
Parse monitor URLs and create a structured configuration file.

Reads from data/monitor-urls.md (human-authored source list).
Writes to data/derived/monitor_urls.json (config for monitor).
Optionally writes data/derived/monitor_urls_report.json (stats and diagnostics).
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .slug_normalizer import get_slug_normalizer

# Entity type indicators based on URL patterns and keywords
ENTITY_PATTERNS = {
    "pe": [
        "privateequity", "pe", "buyout", "clessidra", "investindustrial",
        "progressio", "charme", "21invest", "alto", "alcedo"
    ],
    "vc": [
        "venture", "vc", "startup", "p101", "united", "360capital",
        "primo", "cdp-venture", "speedinvest"
    ],
    "infrastructure": [
        "infra", "f2i", "antin", "infrastructure", "energy", "renewable",
        "tages", "meridiam", "stonepeak", "macquarie"
    ],
    "debt": [
        "debt", "credit", "lending", "anthilia", "muzinich", "amco",
        "pillarstone", "illimity"
    ],
    "holding": [
        "holding", "tip", "exor", "italmobiliare", "edizione", "mittel"
    ],
    "sgr": ["sgr"],
    "international": [
        "kkr", "carlyle", "blackstone", "apollo", "bain", "permira",
        "bc partners", "cvc", "advent", "cinven", "eqt", "pai", "apax"
    ],
}


def extract_urls_from_markdown(content: str) -> list[str]:
    """
    Extract URLs from markdown content.

    Args:
        content: Raw markdown text

    Returns:
        List of unique URLs found
    """
    url_pattern = r"https?://[^\s<>\"'\\]+"
    urls = re.findall(url_pattern, content)
    return list(set(urls))  # Deduplicate


def extract_name_from_url(url: str) -> str:
    """Extract a readable name from a URL."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Remove www. prefix
    if domain.startswith("www."):
        domain = domain[4:]

    # Remove common TLDs and suffixes
    tlds = [".com", ".it", ".eu", ".co.uk", ".de", ".fr", ".es", ".ch", ".be", ".se", ".fi"]
    for suffix in tlds:
        if domain.endswith(suffix):
            domain = domain[:-len(suffix)]
            break

    # Handle subdomains and special paths
    if "/" in parsed.path and len(parsed.path) > 1:
        path_parts = [p for p in parsed.path.split("/") if p and len(p) > 2]
        skip_paths = ["en", "it", "de", "fr", "about", "contact", "news", "team"]
        if path_parts and path_parts[0] not in skip_paths:
            domain = f"{domain}-{path_parts[0]}"

    # Clean up and format
    name = domain.replace("-", " ").replace("_", " ").title()
    name = re.sub(r"\s+", " ", name).strip()

    return name


def classify_entity(url: str, name: str) -> str:
    """Classify entity type based on URL and name patterns."""
    text = f"{url} {name}".lower()

    for entity_type, patterns in ENTITY_PATTERNS.items():
        for pattern in patterns:
            if pattern in text:
                return entity_type

    return "pe"  # Default to PE


def normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy matching."""
    text = text.lower()
    # Remove common suffixes
    suffixes = ["sgr", "spa", "srl", "s.p.a.", "s.r.l.", "sa", "partners", "capital", "group"]
    for suffix in suffixes:
        text = text.replace(suffix, "")
    # Remove non-alphanumeric
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


def match_to_investors(url_name: str, investors: list[dict]) -> dict | None:
    """Try to match a URL-derived name to existing investors."""
    normalized_url = normalize_for_matching(url_name)

    for investor in investors:
        normalized_inv = normalize_for_matching(investor["name"])
        slug = investor["slug"].replace("-", "")

        # Exact match
        if normalized_url == normalized_inv or normalized_url == slug:
            return investor

        # Partial match (one contains the other)
        if len(normalized_url) >= 4 and len(normalized_inv) >= 4:
            if normalized_url in normalized_inv or normalized_inv in normalized_url:
                return investor

    return None


def parse_urls_to_entities(
    urls: list[str],
    investors: list[dict] | None = None,
) -> tuple[list[dict], dict]:
    """
    Parse URLs into entity records.

    Args:
        urls: List of URLs to parse
        investors: Optional list of PEM investors for matching

    Returns:
        Tuple of (entities list, stats dict)
    """
    if investors is None:
        investors = []

    entities = []
    matched_count = 0
    unmatched_count = 0

    for url in sorted(urls):
        name = extract_name_from_url(url)
        entity_type = classify_entity(url, name)
        matched = match_to_investors(name, investors) if investors else None

        entity = {
            "url": url,
            "name": matched["name"] if matched else name,
            "slug": matched["slug"] if matched else None,
            "type": entity_type,
            "pem_matched": matched is not None,
            "pem_deal_count": matched["deal_count"] if matched else 0,
            # Only monitor the base URL by default - do not auto-generate subpages
            # Use validated_urls for explicit subpage monitoring
            "validated_urls": [{"url": url, "page_type": "home"}],
            "active": True,
        }
        entities.append(entity)

        if matched:
            matched_count += 1
        else:
            unmatched_count += 1

    # Sort by PEM deal count (matched first) then alphabetically
    entities.sort(key=lambda e: (-e["pem_deal_count"], e["name"]))

    # Count by type
    by_type: dict[str, int] = {}
    for entity in entities:
        t = entity["type"]
        by_type[t] = by_type.get(t, 0) + 1

    stats = {
        "total_urls": len(entities),
        "matched_to_pem": matched_count,
        "unmatched": unmatched_count,
        "by_type": by_type,
    }

    return entities, stats


def parse_monitor_urls(
    urls_content: str,
    investors: list[dict] | None = None,
) -> tuple[dict, dict]:
    """
    Parse monitor URLs markdown content and create output structures.

    Args:
        urls_content: Raw markdown content with URLs
        investors: Optional list of PEM investors for matching

    Returns:
        Tuple of (config dict for monitor_urls.json, report dict)
    """
    # Extract URLs
    urls = extract_urls_from_markdown(urls_content)

    # Parse into entities
    entities, stats = parse_urls_to_entities(urls, investors)

    # Canonicalize slugs against db.json
    normalizer = get_slug_normalizer()
    canonical_matched = 0
    canonical_unmatched = 0
    for entity in entities:
        result = normalizer.normalize(
            slug=entity.get("slug"),
            name=entity.get("name"),
            source_url=entity.get("url"),
        )
        if result.slug:
            entity["slug"] = result.slug
            canonical_matched += 1
        else:
            entity["slug"] = None
            entity["active"] = False
            canonical_unmatched += 1
        entity["canonical_reason"] = result.reason

    # Create config output
    config = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_urls": stats["total_urls"],
        "matched_to_pem": stats["matched_to_pem"],
        "by_type": stats["by_type"],
        "canonical_matched": canonical_matched,
        "canonical_unmatched": canonical_unmatched,
        "entities": entities,
    }

    # Create report output
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_urls": stats["total_urls"],
            "matched_to_pem": stats["matched_to_pem"],
            "unmatched": stats["unmatched"],
            "by_type": stats["by_type"],
            "canonical_matched": canonical_matched,
            "canonical_unmatched": canonical_unmatched,
        },
        "unmatched_entities": [
            {"url": e["url"], "name": e["name"], "type": e["type"]}
            for e in entities if not e["pem_matched"]
        ],
        "matched_entities": [
            {"url": e["url"], "name": e["name"], "slug": e["slug"], "deal_count": e["pem_deal_count"]}
            for e in entities if e["pem_matched"]
        ],
    }

    return config, report


def main():
    """Entry point for parsing monitor URLs."""
    project_root = Path(__file__).parent.parent.parent.parent
    data_dir = project_root / "data"
    derived_dir = data_dir / "derived"

    # Input: human-authored source in data/, output: derived files in data/derived/
    urls_file = data_dir / "monitor-urls.md"
    investors_file = derived_dir / "pem_investors.json"
    output_file = derived_dir / "monitor_urls.json"
    report_file = derived_dir / "monitor_urls_report.json"

    print("Fundradar Monitor URL Parser")
    print("=" * 40)

    # Check input files
    if not urls_file.exists():
        print(f"Error: URLs file not found: {urls_file}")
        return 1

    # Read URLs markdown
    with open(urls_file) as f:
        urls_content = f.read()
    print(f"Read {len(urls_content)} bytes from {urls_file.name}")

    # Load investors if available
    investors: list[dict] = []
    if investors_file.exists():
        with open(investors_file) as f:
            investors_data = json.load(f)
        investors = investors_data.get("investors", [])
        print(f"Loaded {len(investors)} PEM investors")
    else:
        print("Warning: No PEM investors file found, skipping matching")

    # Parse URLs
    config, report = parse_monitor_urls(urls_content, investors)

    # Write outputs
    derived_dir.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\nConfig written to: {output_file}")

    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report written to: {report_file}")

    # Print summary
    print(f"\nSummary:")
    print(f"  Total URLs: {config['total_urls']}")
    print(f"  Matched to PEM: {config['matched_to_pem']}")
    print(f"  By type: {config['by_type']}")

    return 0


if __name__ == "__main__":
    exit(main())
