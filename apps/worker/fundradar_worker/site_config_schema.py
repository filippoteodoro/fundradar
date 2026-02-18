"""
Site-specific scraping configuration schema for Fundradar.

Defines the YAML schema for per-site scraping configurations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PaginationType(str, Enum):
    """Supported pagination types."""

    NONE = "none"
    URL_BASED = "url_based"
    CLICK_TO_LOAD = "click_to_load"
    INFINITE_SCROLL = "infinite_scroll"


class ExtractionStrategy(str, Enum):
    """Portfolio/team extraction strategies."""

    # Portfolio strategies
    NEXT_DATA = "next_data"
    NUXT_DATA = "nuxt_data"
    JSON_LD = "json_ld"
    HTML_CARDS = "html_cards"
    LOGO_GRID = "logo_grid"
    LINK_LIST = "link_list"
    HEADINGS_IN_CONTEXT = "headings_in_context"
    TABLE_ROWS = "table_rows"
    ATTRIBUTES = "attributes"
    SVG_TITLES = "svg_titles"
    NOSCRIPT = "noscript"
    ANCHOR_WRAPPERS = "anchor_wrappers"

    # Team strategies
    TEAM_CARDS = "team_cards"
    H3_WITH_TITLE = "h3_with_title"
    JSON_LD_PERSON = "json_ld_person"


@dataclass
class SelectorConfig:
    """CSS selector configuration for extraction."""

    # Container selector (parent element holding all items)
    container: str | None = None

    # Item selector (individual items within container)
    item: str | None = None

    # Field selectors (relative to item)
    name: str | None = None
    description: str | None = None
    sector: str | None = None
    website: str | None = None
    status: str | None = None  # current/exited
    image: str | None = None

    # Team-specific
    title: str | None = None  # Job title
    role: str | None = None
    linkedin: str | None = None
    email: str | None = None


@dataclass
class WaitConfig:
    """Wait conditions for page loading."""

    # Wait for specific selector to appear
    for_selector: str | None = None

    # Wait for network idle
    for_network_idle: bool = True

    # Fixed timeout in milliseconds
    timeout_ms: int = 10000

    # Wait after page load before extraction
    delay_ms: int = 0


@dataclass
class ScrollConfig:
    """Scrolling configuration for lazy-loaded content."""

    enabled: bool = False
    max_scrolls: int = 10
    pause_ms: int = 500
    scroll_to_selector: str | None = None  # Scroll until this appears


@dataclass
class PaginationConfig:
    """Pagination configuration."""

    type: PaginationType = PaginationType.NONE

    # For URL-based pagination
    url_pattern: str | None = None  # e.g., "/portfolio?page={page}"
    start_page: int = 1
    max_pages: int = 10

    # For click-to-load
    load_more_selector: str | None = None
    max_clicks: int = 10

    # For infinite scroll (uses scroll config)
    # Detection
    no_more_items_selector: str | None = None  # e.g., ".no-more-results"
    no_more_items_text: str | None = None  # e.g., "No more items"


@dataclass
class PortfolioConfig:
    """Portfolio extraction configuration."""

    # Page URL pattern (relative to domain)
    url_path: str | None = None  # e.g., "/portfolio", "/investments"

    # Selectors for extraction
    selectors: SelectorConfig = field(default_factory=SelectorConfig)

    # Extraction strategy priority (first that works wins)
    strategies: list[ExtractionStrategy] = field(default_factory=list)

    # Pagination
    pagination: PaginationConfig = field(default_factory=PaginationConfig)

    # Filter patterns
    exclude_patterns: list[str] = field(default_factory=list)  # Regex to exclude

    # Status detection
    exited_section_selector: str | None = None
    exited_indicator: str | None = None  # CSS class or text


@dataclass
class TeamConfig:
    """Team extraction configuration."""

    # Page URL pattern
    url_path: str | None = None  # e.g., "/team", "/people"

    # Selectors
    selectors: SelectorConfig = field(default_factory=SelectorConfig)

    # Extraction strategies
    strategies: list[ExtractionStrategy] = field(default_factory=list)

    # Pagination
    pagination: PaginationConfig = field(default_factory=PaginationConfig)

    # Sections (e.g., "Partners", "Investment Team")
    section_selector: str | None = None
    section_title_selector: str | None = None


@dataclass
class NewsConfig:
    """News/press extraction configuration."""

    # Page URL pattern
    url_path: str | None = None

    # Selectors
    article_selector: str | None = None
    title_selector: str | None = None
    date_selector: str | None = None
    link_selector: str | None = None
    summary_selector: str | None = None

    # Date format (for parsing)
    date_format: str | None = None  # e.g., "%d %B %Y"

    # Pagination
    pagination: PaginationConfig = field(default_factory=PaginationConfig)


@dataclass
class ConsentConfig:
    """Cookie consent handling configuration."""

    # Custom accept button selector
    accept_selector: str | None = None

    # Wait for consent modal
    wait_for_modal: bool = True
    modal_timeout_ms: int = 3000

    # Skip consent handling entirely
    skip: bool = False


@dataclass
class SiteConfig:
    """
    Complete site-specific scraping configuration.

    This is the top-level configuration object loaded from YAML files.
    """

    # Domain this config applies to (without protocol)
    domain: str

    # Human-readable name
    name: str | None = None

    # Notes about the site
    notes: str | None = None

    # Requires headless browser
    requires_headless: bool = False

    # Wait conditions
    wait: WaitConfig = field(default_factory=WaitConfig)

    # Scrolling
    scroll: ScrollConfig = field(default_factory=ScrollConfig)

    # Consent handling
    consent: ConsentConfig = field(default_factory=ConsentConfig)

    # Page-specific configurations
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    team: TeamConfig = field(default_factory=TeamConfig)
    news: NewsConfig = field(default_factory=NewsConfig)

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)


def site_config_from_dict(data: dict) -> SiteConfig:
    """
    Create a SiteConfig from a dictionary (parsed YAML).

    This handles nested object creation and default values.
    """

    def _parse_selectors(d: dict | None) -> SelectorConfig:
        if not d:
            return SelectorConfig()
        return SelectorConfig(**d)

    def _parse_wait(d: dict | None) -> WaitConfig:
        if not d:
            return WaitConfig()
        return WaitConfig(**d)

    def _parse_scroll(d: dict | None) -> ScrollConfig:
        if not d:
            return ScrollConfig()
        return ScrollConfig(**d)

    def _parse_pagination(d: dict | None) -> PaginationConfig:
        if not d:
            return PaginationConfig()
        d = dict(d)
        if "type" in d:
            d["type"] = PaginationType(d["type"])
        return PaginationConfig(**d)

    def _parse_consent(d: dict | None) -> ConsentConfig:
        if not d:
            return ConsentConfig()
        return ConsentConfig(**d)

    def _parse_portfolio(d: dict | None) -> PortfolioConfig:
        if not d:
            return PortfolioConfig()
        d = dict(d)
        d["selectors"] = _parse_selectors(d.get("selectors"))
        d["pagination"] = _parse_pagination(d.get("pagination"))
        if "strategies" in d:
            d["strategies"] = [ExtractionStrategy(s) for s in d["strategies"]]
        return PortfolioConfig(**{k: v for k, v in d.items() if k in PortfolioConfig.__dataclass_fields__})

    def _parse_team(d: dict | None) -> TeamConfig:
        if not d:
            return TeamConfig()
        d = dict(d)
        d["selectors"] = _parse_selectors(d.get("selectors"))
        d["pagination"] = _parse_pagination(d.get("pagination"))
        if "strategies" in d:
            d["strategies"] = [ExtractionStrategy(s) for s in d["strategies"]]
        return TeamConfig(**{k: v for k, v in d.items() if k in TeamConfig.__dataclass_fields__})

    def _parse_news(d: dict | None) -> NewsConfig:
        if not d:
            return NewsConfig()
        d = dict(d)
        d["pagination"] = _parse_pagination(d.get("pagination"))
        return NewsConfig(**{k: v for k, v in d.items() if k in NewsConfig.__dataclass_fields__})

    return SiteConfig(
        domain=data["domain"],
        name=data.get("name"),
        notes=data.get("notes"),
        requires_headless=data.get("requires_headless", False),
        wait=_parse_wait(data.get("wait")),
        scroll=_parse_scroll(data.get("scroll")),
        consent=_parse_consent(data.get("consent")),
        portfolio=_parse_portfolio(data.get("portfolio")),
        team=_parse_team(data.get("team")),
        news=_parse_news(data.get("news")),
        metadata=data.get("metadata", {}),
    )


def site_config_to_dict(config: SiteConfig) -> dict:
    """Convert a SiteConfig to a dictionary for YAML serialization."""
    from dataclasses import asdict

    def _enum_to_str(obj):
        if isinstance(obj, dict):
            return {k: _enum_to_str(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_enum_to_str(v) for v in obj]
        elif isinstance(obj, Enum):
            return obj.value
        return obj

    return _enum_to_str(asdict(config))


# Example config for reference
EXAMPLE_CONFIG = """
# Example site configuration for Fundradar
domain: example-fund.it
name: Example Fund
notes: |
  This is a Next.js SPA with infinite scroll on the portfolio page.
  Cookie consent uses OneTrust.

requires_headless: true

wait:
  for_selector: ".portfolio-grid"
  for_network_idle: true
  timeout_ms: 15000

scroll:
  enabled: true
  max_scrolls: 5
  pause_ms: 800

consent:
  accept_selector: "#onetrust-accept-btn-handler"

portfolio:
  url_path: /portfolio
  selectors:
    container: ".portfolio-grid"
    item: ".portfolio-card"
    name: "h3"
    sector: ".tag"
    website: "a[target='_blank']"
  strategies:
    - next_data
    - html_cards
  pagination:
    type: infinite_scroll

team:
  url_path: /team
  selectors:
    container: ".team-grid"
    item: ".team-card"
    name: "h3"
    title: ".title"
    linkedin: "a.linkedin"
  strategies:
    - team_cards
    - h3_with_title
"""
