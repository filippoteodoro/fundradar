"""
Standalone News Signal Generator.

Bypasses the monitor pipeline gap by directly:
1. Reading fund_urls.json for news URLs
2. Fetching news pages
3. Running extractors' extract_news functions
4. Outputting signals to detected_signals.json

Usage:
    python -m fundradar_worker.news_signal_generator [--dry-run] [--fund SLUG]
"""

import argparse
import hashlib
import importlib.util
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DERIVED_DIR = DATA_DIR / "derived"
EXTRACTORS_DIR = Path(__file__).parent / "strategies" / "extractors"


def load_fund_urls() -> dict:
    """Load fund_urls.json."""
    path = DATA_DIR / "site_configs" / "fund_urls.json"
    if not path.exists():
        logger.error(f"fund_urls.json not found at {path}")
        return {}
    with open(path) as f:
        return json.load(f)


def load_db() -> dict:
    """Load db.json for fund info."""
    path = DATA_DIR / "db.json"
    if not path.exists():
        logger.error(f"db.json not found at {path}")
        return {}
    with open(path) as f:
        return json.load(f)


def load_existing_signals() -> dict:
    """Load existing signals to avoid duplicates."""
    path = DERIVED_DIR / "detected_signals.json"
    if not path.exists():
        return {"signals": []}
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"signals": []}


def get_extractor_for_domain(domain: str) -> dict | None:
    """
    Find and load the extractor module for a domain.
    Returns dict with extract_news function if available.
    """
    # Normalize domain (remove www.)
    domain_normalized = domain.lower().replace("www.", "")
    domain_with_www = f"www.{domain_normalized}"

    # Search through extractor files
    for py_file in EXTRACTORS_DIR.glob("*.py"):
        if py_file.name == "__init__.py" or py_file.name == "_template.py":
            continue

        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Check DOMAIN attribute
            extractor_domain = getattr(module, "DOMAIN", None)
            if not extractor_domain:
                continue

            extractor_domain_normalized = extractor_domain.lower().replace("www.", "")

            # Match domain
            if extractor_domain_normalized == domain_normalized or \
               extractor_domain.lower() == domain_with_www or \
               extractor_domain.lower() == domain_normalized:

                # Get EXTRACTORS dict
                extractors = getattr(module, "EXTRACTORS", {})
                if "news" in extractors:
                    return {
                        "file": py_file.name,
                        "domain": extractor_domain,
                        "extract_news": extractors["news"],
                    }
        except Exception as e:
            logger.debug(f"Error loading {py_file.name}: {e}")
            continue

    return None


def fetch_page(url: str, timeout: int = 30) -> str | None:
    """Fetch a page with proper headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def generate_signal_id(prefix: str = "news") -> str:
    """Generate a unique signal ID."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    hash_part = hashlib.md5(f"{timestamp}{id(object())}".encode()).hexdigest()[:8]
    return f"{prefix}-signal-{timestamp}-{hash_part}"


def generate_fingerprint(title: str, url: str) -> str:
    """Generate a fingerprint for deduplication."""
    content = f"{title.lower()}|{url.lower()}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def news_item_to_signal(
    news_item: dict,
    fund_slug: str,
    fund_name: str,
    base_url: str,
) -> dict:
    """Convert an extracted news item to a signal."""
    now = datetime.now(timezone.utc).isoformat()
    title = news_item.get("title", "")[:200]  # Truncate long titles
    url = news_item.get("url") or base_url
    date = news_item.get("date")

    return {
        "id": generate_signal_id("news"),
        "fund_id": "",
        "fund_slug": fund_slug,
        "signal_type": "news",
        "title": title,
        "what_changed": f"News: {title}",
        "source_url": url,
        "source_name": fund_name,
        "published_at": date,
        "observed_at": now,
        "created_at": now,
        "fingerprint": generate_fingerprint(title, url),
        "extraction_source": "news_signal_generator",
        "page_category": "NEWS",
        "page_type": "NEWS",
        "quality_score": 75,  # Default score, will be adjusted by noise_filter
    }


def safe_json_write(path: Path, data: Any) -> None:
    """Atomic JSON write using temp file + rename."""
    import tempfile
    import os

    # Write to temp file first
    fd, temp_path = tempfile.mkstemp(suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Atomic rename
        os.replace(temp_path, path)
        logger.info(f"Wrote {path}")
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def run_generator(
    dry_run: bool = False,
    fund_filter: str | None = None,
    max_funds: int | None = None,
) -> dict:
    """
    Main generator function.

    Args:
        dry_run: If True, don't write output
        fund_filter: Only process this fund slug
        max_funds: Limit number of funds to process

    Returns:
        Summary stats dict
    """
    stats = {
        "funds_processed": 0,
        "funds_with_news_url": 0,
        "funds_with_extractor": 0,
        "pages_fetched": 0,
        "news_items_extracted": 0,
        "signals_generated": 0,
        "errors": [],
    }

    # Load data
    fund_urls = load_fund_urls()
    db = load_db()
    existing = load_existing_signals()

    # Build fund name lookup
    fund_names = {}
    for fund in db.get("funds", []):
        slug = fund.get("slug", "")
        name = fund.get("name", slug)
        fund_names[slug] = name

    # Get existing fingerprints for deduplication
    existing_fingerprints = set()
    for signal in existing.get("signals", []):
        fp = signal.get("fingerprint")
        if fp:
            existing_fingerprints.add(fp)

    new_signals = []
    processed = 0

    for fund_slug, urls_data in fund_urls.items():
        # Filter check
        if fund_filter and fund_slug != fund_filter:
            continue

        # Max check
        if max_funds and processed >= max_funds:
            break

        processed += 1
        stats["funds_processed"] += 1

        news_url = urls_data.get("news")
        if not news_url or news_url == "-":
            continue

        stats["funds_with_news_url"] += 1

        # Get domain from website or news URL
        website = urls_data.get("website", "")
        if website:
            domain = urlparse(website).netloc
        else:
            domain = urlparse(news_url).netloc

        if not domain:
            continue

        # Find extractor
        extractor = get_extractor_for_domain(domain)
        if not extractor:
            logger.debug(f"No news extractor for {fund_slug} ({domain})")
            continue

        stats["funds_with_extractor"] += 1
        fund_name = fund_names.get(fund_slug, fund_slug)

        logger.info(f"Processing {fund_slug} ({extractor['file']})")

        # Fetch the news page
        html = fetch_page(news_url)
        if not html:
            stats["errors"].append(f"Failed to fetch {news_url}")
            continue

        stats["pages_fetched"] += 1

        # Extract news
        try:
            news_items = extractor["extract_news"](html, news_url)
            stats["news_items_extracted"] += len(news_items)

            for item in news_items:
                signal = news_item_to_signal(item, fund_slug, fund_name, news_url)

                # Deduplicate
                if signal["fingerprint"] in existing_fingerprints:
                    continue

                existing_fingerprints.add(signal["fingerprint"])
                new_signals.append(signal)
                stats["signals_generated"] += 1

        except Exception as e:
            logger.error(f"Extraction error for {fund_slug}: {e}")
            stats["errors"].append(f"Extraction error for {fund_slug}: {str(e)}")

    # Output
    if not dry_run and new_signals:
        # Merge with existing
        all_signals = existing.get("signals", []) + new_signals
        output = {
            "signals": all_signals,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_count": len(all_signals),
        }
        safe_json_write(DERIVED_DIR / "detected_signals.json", output)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Generate signals from news extractors")
    parser.add_argument("--dry-run", action="store_true", help="Don't write output")
    parser.add_argument("--fund", type=str, help="Only process this fund slug")
    parser.add_argument("--max", type=int, help="Max funds to process")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting news signal generator...")
    stats = run_generator(
        dry_run=args.dry_run,
        fund_filter=args.fund,
        max_funds=args.max,
    )

    # Print summary
    print("\n=== Summary ===")
    print(f"Funds processed: {stats['funds_processed']}")
    print(f"Funds with news URL: {stats['funds_with_news_url']}")
    print(f"Funds with extractor: {stats['funds_with_extractor']}")
    print(f"Pages fetched: {stats['pages_fetched']}")
    print(f"News items extracted: {stats['news_items_extracted']}")
    print(f"New signals generated: {stats['signals_generated']}")

    if stats["errors"]:
        print(f"\nErrors ({len(stats['errors'])}):")
        for err in stats["errors"][:10]:
            print(f"  - {err}")
        if len(stats["errors"]) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
