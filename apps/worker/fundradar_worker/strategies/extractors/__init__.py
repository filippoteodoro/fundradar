"""
Auto-load all domain extractors.

This module automatically discovers and loads all extractor files in this directory.
Each extractor file should export:
  - DOMAIN: str - the domain this extractor handles (e.g., "www.permira.com")
  - EXTRACTORS: dict - mapping of data_type to extractor function
  - URLS: dict (optional) - mapping of page_type to URL path(s)

Example extractor file (extractors/permira.py):
    DOMAIN = "www.permira.com"

    URLS = {
        "portfolio": "/investments",
        "team": "/team",
        "news": None,
    }

    def extract_portfolio(html: str, base_url: str) -> list[dict]:
        ...

    EXTRACTORS = {
        "portfolio": extract_portfolio,
        "team": extract_team,
    }
"""
import importlib
import logging
import pkgutil
from pathlib import Path

logger = logging.getLogger(__name__)

ALL_EXTRACTORS: dict[str, dict] = {}
ALL_URLS: dict[str, dict] = {}  # Maps domain -> {page_type: path(s)}
ALWAYS_EXTRACT: set[str] = set()  # Domains that fetch own data (bypass HTML hash check)

# Auto-discover and load all extractor modules
_package_dir = Path(__file__).parent

for _, module_name, _ in pkgutil.iter_modules([str(_package_dir)]):
    if module_name.startswith('_'):
        continue
    try:
        module = importlib.import_module(f'.{module_name}', package=__name__)
        if hasattr(module, 'DOMAIN') and hasattr(module, 'EXTRACTORS'):
            domain = getattr(module, 'DOMAIN')
            extractors = getattr(module, 'EXTRACTORS')
            ALL_EXTRACTORS[domain] = extractors
            # Collect URLS if present
            if hasattr(module, 'URLS'):
                ALL_URLS[domain] = getattr(module, 'URLS')
            # Track extractors that fetch their own data (API-based)
            if getattr(module, 'ALWAYS_EXTRACT', False):
                ALWAYS_EXTRACT.add(domain)
            logger.debug(f"Loaded extractor for {domain} from {module_name}.py")
        else:
            logger.warning(f"Extractor module {module_name} missing DOMAIN or EXTRACTORS")
    except Exception as e:
        logger.error(f"Failed to load extractor module {module_name}: {e}")

logger.info(f"Auto-loaded {len(ALL_EXTRACTORS)} domain extractors, {len(ALL_URLS)} with URLS")
