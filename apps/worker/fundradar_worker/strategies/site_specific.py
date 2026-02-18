"""
Site-specific extraction strategies for Italian PE/VC funds.

All domain extractors live in the extractors/ directory as one file per domain.
This module provides the lookup function used by the rest of the codebase.

See extractors/__init__.py for the auto-discovery mechanism.
"""

import logging

from .extractors import ALL_EXTRACTORS

logger = logging.getLogger(__name__)

# The merged registry: every domain extractor auto-loaded from extractors/
SITE_EXTRACTORS: dict[str, dict] = dict(ALL_EXTRACTORS)

logger.info(f"Site-specific registry: {len(SITE_EXTRACTORS)} domains loaded")


def get_site_extractor(domain: str, data_type: str):
    """
    Get a site-specific extractor if available.

    Args:
        domain: Website domain (e.g., "www.progressiosgr.it")
        data_type: Type of data ("portfolio", "team", "news")

    Returns:
        Extractor function or None if no site-specific extractor exists
    """
    site_config = SITE_EXTRACTORS.get(domain, {})
    return site_config.get(data_type)


def get_site_extractors() -> dict[str, dict]:
    """Return the full registry of site-specific extractors."""
    return SITE_EXTRACTORS
