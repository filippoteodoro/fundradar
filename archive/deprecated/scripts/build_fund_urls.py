"""
Build fund_urls.json from site configs and extractors.

This is FAST - no HTTP requests needed. It reads:
1. Site configs (YAML) - for explicit url_path definitions
2. Extractors (Python) - to know which domains have custom extractors
3. db.json - to map website domains to fund slugs

Output: fund_urls.json with news/portfolio/team URLs for all funds
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
import yaml


def get_domain(url: str) -> str:
    """Extract domain from URL, stripping www."""
    if not url:
        return ""
    parsed = urlparse(url if url.startswith("http") else f"https://{url}")
    domain = parsed.netloc or parsed.path.split("/")[0]
    return domain.lower().replace("www.", "")


def load_db_funds(data_dir: Path) -> dict[str, dict]:
    """Load funds from db.json, keyed by domain."""
    db_path = data_dir / "db.json"
    with open(db_path) as f:
        db = json.load(f)

    # Build domain -> fund mapping
    domain_to_fund = {}
    for fund in db.get("funds", []):
        website = fund.get("website", "")
        if website:
            domain = get_domain(website)
            domain_to_fund[domain] = {
                "slug": fund.get("slug", ""),
                "name": fund.get("name", ""),
                "website": website,
            }
    return domain_to_fund


def load_site_configs(data_dir: Path) -> dict[str, dict]:
    """Load all site configs from YAML files."""
    configs_dir = data_dir / "site_configs"
    configs = {}

    for yaml_file in configs_dir.glob("*.yaml"):
        try:
            with open(yaml_file) as f:
                config = yaml.safe_load(f)
            if config and "domain" in config:
                domain = config["domain"].lower().replace("www.", "")
                configs[domain] = config
        except Exception as e:
            print(f"  Warning: Failed to parse {yaml_file.name}: {e}")

    return configs


def load_extractor_domains(worker_dir: Path) -> dict[str, list[str]]:
    """
    Load extractor domains and their supported types.
    Returns: domain -> list of supported types (news, portfolio, team)
    """
    extractors_dir = worker_dir / "fundradar_worker" / "strategies" / "extractors"
    domain_types = {}

    for py_file in extractors_dir.glob("*.py"):
        if py_file.name.startswith("_") or py_file.name == "__init__.py":
            continue

        try:
            content = py_file.read_text()

            # Extract DOMAIN constant
            domain_match = re.search(r'DOMAIN\s*=\s*["\']([^"\']+)["\']', content)
            if not domain_match:
                continue

            domain = domain_match.group(1).lower().replace("www.", "")

            # Check which extractors are defined
            types = []
            if "extract_news" in content and '"news"' in content:
                # Check it's not just "return []"
                news_match = re.search(r'def extract_news.*?(?=def |EXTRACTORS|$)', content, re.DOTALL)
                if news_match and "return []" not in news_match.group():
                    types.append("news")
            if "extract_portfolio" in content and '"portfolio"' in content:
                portfolio_match = re.search(r'def extract_portfolio.*?(?=def |EXTRACTORS|$)', content, re.DOTALL)
                if portfolio_match and "return []" not in portfolio_match.group():
                    types.append("portfolio")
            if "extract_team" in content and '"team"' in content:
                team_match = re.search(r'def extract_team.*?(?=def |EXTRACTORS|$)', content, re.DOTALL)
                if team_match and "return []" not in team_match.group():
                    types.append("team")

            if types:
                domain_types[domain] = types

        except Exception as e:
            print(f"  Warning: Failed to parse {py_file.name}: {e}")

    return domain_types


# Common URL patterns for different page types
NEWS_PATHS = ["/news", "/press", "/media", "/newsroom", "/press-release", "/press-releases",
              "/en/news", "/en/press", "/en/media", "/it/news", "/it/newsroom.page",
              "/publications/news.html", "/en/news-events"]
PORTFOLIO_PATHS = ["/portfolio", "/investments", "/companies", "/our-portfolio",
                   "/en/portfolio", "/it/portfolio", "/it/fondi.page", "/portfolio-companies"]
TEAM_PATHS = ["/team", "/about/team", "/people", "/our-team", "/management",
              "/en/team", "/it/team", "/it/management.page", "/about-us/team"]


def build_fund_urls(
    data_dir: Path,
    worker_dir: Path,
    existing_fund_urls: dict | None = None,
) -> dict:
    """
    Build fund_urls.json from all available sources.

    Priority:
    1. Existing verified URLs (preserved)
    2. Site config url_paths (explicit definitions)
    3. Extractor-supported types with common paths
    """
    # Load all data sources
    print("Loading data sources...")
    domain_to_fund = load_db_funds(data_dir)
    print(f"  Found {len(domain_to_fund)} funds with websites in db.json")

    site_configs = load_site_configs(data_dir)
    print(f"  Found {len(site_configs)} site configs")

    extractor_domains = load_extractor_domains(worker_dir)
    print(f"  Found {len(extractor_domains)} domains with extractors")

    # Start with existing or empty
    fund_urls = existing_fund_urls.copy() if existing_fund_urls else {}

    # Process each fund
    added = 0
    updated = 0

    for domain, fund_info in domain_to_fund.items():
        slug = fund_info["slug"]
        website = fund_info["website"]
        name = fund_info["name"]

        if not slug:
            continue

        # Get or create entry
        entry = fund_urls.get(slug, {})
        is_new = slug not in fund_urls

        entry["fund_name"] = name
        entry["website"] = website

        # Get config and extractor info for this domain
        config = site_configs.get(domain, {})
        extractor_types = extractor_domains.get(domain, [])

        # Also check with www prefix
        if not config:
            config = site_configs.get(f"www.{domain}", {})
        if not extractor_types:
            extractor_types = extractor_domains.get(f"www.{domain}", [])

        base_url = website.rstrip("/")

        # NEWS URL
        if entry.get("news_source") != "verified":
            news_url = None
            # From site config
            if config.get("news", {}).get("url_path"):
                news_url = f"{base_url}{config['news']['url_path']}"
                entry["news_source"] = "config"
            # From extractor (use common path)
            elif "news" in extractor_types:
                # Try to find a working path
                for path in NEWS_PATHS:
                    if domain in path.replace("/", "") or "en" in path or "it" in path:
                        news_url = f"{base_url}{path}"
                        break
                if not news_url:
                    news_url = f"{base_url}/news"
                entry["news_source"] = "extractor"

            if news_url:
                entry["news"] = news_url

        # PORTFOLIO URL
        if entry.get("portfolio_source") != "verified":
            portfolio_url = None
            if config.get("portfolio", {}).get("url_path"):
                portfolio_url = f"{base_url}{config['portfolio']['url_path']}"
                entry["portfolio_source"] = "config"
            elif "portfolio" in extractor_types:
                for path in PORTFOLIO_PATHS:
                    if domain in path.replace("/", "") or "en" in path or "it" in path:
                        portfolio_url = f"{base_url}{path}"
                        break
                if not portfolio_url:
                    portfolio_url = f"{base_url}/portfolio"
                entry["portfolio_source"] = "extractor"

            if portfolio_url:
                entry["portfolio"] = portfolio_url

        # TEAM URL
        if entry.get("team_source") != "verified":
            team_url = None
            if config.get("team", {}).get("url_path"):
                team_url = f"{base_url}{config['team']['url_path']}"
                entry["team_source"] = "config"
            elif "team" in extractor_types:
                for path in TEAM_PATHS:
                    if domain in path.replace("/", "") or "en" in path or "it" in path:
                        team_url = f"{base_url}{path}"
                        break
                if not team_url:
                    team_url = f"{base_url}/team"
                entry["team_source"] = "extractor"

            if team_url:
                entry["team"] = team_url

        # Only add if we have at least one URL
        if entry.get("news") or entry.get("portfolio") or entry.get("team"):
            fund_urls[slug] = entry
            if is_new:
                added += 1
            else:
                updated += 1

    print(f"\nResults: {added} new entries, {updated} updated")
    return fund_urls


def main():
    """Main entry point."""
    # Get paths
    project_root = Path(__file__).parent.parent.parent.parent
    data_dir = project_root / "data"
    worker_dir = project_root / "apps" / "worker"

    dry_run = "--dry-run" in sys.argv

    print("Building fund_urls.json from configs and extractors")
    print("=" * 50)

    # Load existing
    fund_urls_path = data_dir / "site_configs" / "fund_urls.json"
    existing = {}
    if fund_urls_path.exists():
        with open(fund_urls_path) as f:
            existing = json.load(f)
        print(f"Existing fund_urls.json has {len(existing)} entries")

    # Build new
    updated = build_fund_urls(data_dir, worker_dir, existing)

    # Count URLs
    news_count = sum(1 for e in updated.values() if e.get("news"))
    portfolio_count = sum(1 for e in updated.values() if e.get("portfolio"))
    team_count = sum(1 for e in updated.values() if e.get("team"))
    total_urls = news_count + portfolio_count + team_count

    print(f"\nFinal: {len(updated)} funds with URLs")
    print(f"  News: {news_count}")
    print(f"  Portfolio: {portfolio_count}")
    print(f"  Team: {team_count}")
    print(f"  Total URLs: {total_urls}")

    if not dry_run:
        with open(fund_urls_path, "w") as f:
            json.dump(updated, f, indent=2)
        print(f"\nSaved to {fund_urls_path}")
    else:
        print("\n[DRY RUN] No changes saved")


if __name__ == "__main__":
    main()
