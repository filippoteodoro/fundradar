"""
Generate monitored URLs from extractor declarations.

This module builds the URL list directly from extractors' URLS constants,
eliminating the need for a separate fund_urls.json file.

Each extractor declares both what to extract (EXTRACTORS) and where to fetch (URLS).
"""
from urllib.parse import urljoin, urlparse
import logging

logger = logging.getLogger(__name__)


def normalize_domain(domain: str) -> str:
    """Normalize domain for matching (strip www., lowercase)."""
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def get_urls_for_domain(domain: str, urls_dict: dict, scheme: str = "https") -> dict[str, list[str]]:
    """
    Build full URLs from an extractor's URLS paths.

    Args:
        domain: The domain (e.g., "www.alcedo.it")
        urls_dict: The URLS dict from the extractor (e.g., {"portfolio": "/investments"})
        scheme: URL scheme to use (default "https")

    Returns:
        Dict mapping page_type to list of full URLs
    """
    base = f"{scheme}://{domain}"
    result = {}

    for page_type in ["portfolio", "team", "news"]:
        path = urls_dict.get(page_type)
        if path is None:
            result[page_type] = []
        elif isinstance(path, str):
            # Single path
            result[page_type] = [urljoin(base, path)]
        elif isinstance(path, list):
            # Multiple paths
            result[page_type] = [urljoin(base, p) for p in path if p]
        else:
            result[page_type] = []

    return result


def generate_all_monitored_urls() -> dict[str, dict[str, list[str]]]:
    """
    Generate URLs for all domains with extractors that have URLS declared.

    Returns:
        Dict mapping domain -> {page_type: [urls]}
    """
    from .strategies.extractors import ALL_EXTRACTORS, ALL_URLS

    result = {}
    for domain in ALL_EXTRACTORS:
        if domain in ALL_URLS:
            result[domain] = get_urls_for_domain(domain, ALL_URLS[domain])
        else:
            # Extractor exists but no URLS declared - return empty
            result[domain] = {"portfolio": [], "team": [], "news": []}

    return result


def get_extractor_coverage_stats() -> dict:
    """
    Get statistics about extractor URL coverage.

    Returns:
        Dict with coverage statistics
    """
    from .strategies.extractors import ALL_EXTRACTORS, ALL_URLS

    total_extractors = len(ALL_EXTRACTORS)
    with_urls = len(ALL_URLS)

    # Count by page type
    with_portfolio = 0
    with_team = 0
    with_news = 0

    for domain, urls in ALL_URLS.items():
        if urls.get("portfolio"):
            with_portfolio += 1
        if urls.get("team"):
            with_team += 1
        if urls.get("news"):
            with_news += 1

    return {
        "total_extractors": total_extractors,
        "extractors_with_urls": with_urls,
        "extractors_without_urls": total_extractors - with_urls,
        "with_portfolio_url": with_portfolio,
        "with_team_url": with_team,
        "with_news_url": with_news,
    }


if __name__ == "__main__":
    # Print coverage stats when run directly
    stats = get_extractor_coverage_stats()
    print("Extractor URL Coverage:")
    print(f"  Total extractors: {stats['total_extractors']}")
    print(f"  With URLS declared: {stats['extractors_with_urls']}")
    print(f"  Without URLS: {stats['extractors_without_urls']}")
    print(f"  With portfolio URL: {stats['with_portfolio_url']}")
    print(f"  With team URL: {stats['with_team_url']}")
    print(f"  With news URL: {stats['with_news_url']}")
