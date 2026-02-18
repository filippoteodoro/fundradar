#!/usr/bin/env python3
"""
Script to update site_extractors.json and monitor_urls.json with verified URLs.
"""

import json
from pathlib import Path
from urllib.parse import urlparse

DATA_DIR = Path(__file__).parent.parent / "data" / "derived"


def update_site_extractors():
    """Update site_extractors.json with verified selectors."""
    verified_path = DATA_DIR / "verified_urls.json"
    extractors_path = DATA_DIR / "site_extractors.json"

    with open(verified_path) as f:
        verified = json.load(f)

    with open(extractors_path) as f:
        extractors = json.load(f)

    # Update sites section with verified selectors
    for slug, data in verified.items():
        if "error" in data:
            continue

        base_url = data.get("base_url", "")
        domain = urlparse(base_url).netloc

        if not domain:
            continue

        # Create site entry if not exists
        if domain not in extractors["sites"]:
            extractors["sites"][domain] = {}

        # Update news config
        news_data = data.get("news", {})
        if news_data.get("exists") and news_data.get("selectors"):
            selectors = news_data["selectors"]
            extractors["sites"][domain]["news"] = {
                "list_url": urlparse(news_data.get("url", "")).path or "/news/",
                "item_selector": selectors.get("item", "article"),
                "title_selector": selectors.get("title", "h2 a"),
                "date_selector": selectors.get("date", "time"),
                "link_selector": selectors.get("link", "a"),
            }

        # Update portfolio config
        portfolio_data = data.get("portfolio", {})
        if portfolio_data.get("exists"):
            extractors["sites"][domain]["portfolio"] = {
                "list_url": urlparse(portfolio_data.get("url", "")).path or "/portfolio/",
            }

        # Update team config
        team_data = data.get("team", {})
        if team_data.get("exists"):
            extractors["sites"][domain]["team"] = {
                "list_url": urlparse(team_data.get("url", "")).path or "/team/",
            }

    # Save updated extractors
    with open(extractors_path, "w") as f:
        json.dump(extractors, f, indent=2)

    print(f"Updated {extractors_path}")
    print(f"  Sites with configs: {len(extractors['sites'])}")


def update_monitor_urls():
    """Update monitor_urls.json with validated URLs."""
    verified_path = DATA_DIR / "verified_urls.json"
    monitor_path = DATA_DIR / "monitor_urls.json"

    with open(verified_path) as f:
        verified = json.load(f)

    with open(monitor_path) as f:
        monitor = json.load(f)

    # Create a lookup by slug
    verified_by_slug = {slug: data for slug, data in verified.items() if "error" not in data}

    # Update entities with validated URLs
    updated_count = 0
    for entity in monitor.get("entities", []):
        slug = entity.get("slug", "")

        if slug in verified_by_slug:
            data = verified_by_slug[slug]

            # Create validated_urls list
            validated_urls = []

            # Add news URL
            news_data = data.get("news", {})
            if news_data.get("exists") and news_data.get("url"):
                validated_urls.append({
                    "url": news_data["url"],
                    "category": "NEWS",
                    "page_type": "news",
                    "verified": True,
                })

            # Add portfolio URL
            portfolio_data = data.get("portfolio", {})
            if portfolio_data.get("exists") and portfolio_data.get("url"):
                validated_urls.append({
                    "url": portfolio_data["url"],
                    "category": "PORTFOLIO",
                    "page_type": "portfolio",
                    "verified": True,
                })

            # Add team URL
            team_data = data.get("team", {})
            if team_data.get("exists") and team_data.get("url"):
                validated_urls.append({
                    "url": team_data["url"],
                    "category": "TEAM",
                    "page_type": "team",
                    "verified": True,
                })

            if validated_urls:
                entity["validated_urls"] = validated_urls
                updated_count += 1

    # Save updated monitor config
    with open(monitor_path, "w") as f:
        json.dump(monitor, f, indent=2)

    print(f"Updated {monitor_path}")
    print(f"  Entities with validated URLs: {updated_count}")


def main():
    """Update both config files."""
    print("Updating configs from verified URLs...\n")

    update_site_extractors()
    print()
    update_monitor_urls()

    print("\nDone!")


if __name__ == "__main__":
    main()
