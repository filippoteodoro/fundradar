"""
Strategy orchestrator for coordinating multiple extraction strategies.

Tries different extraction strategies based on site configuration and
combines results with confidence scoring.
"""

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .site_config_schema import ExtractionStrategy, SiteConfig, SelectorConfig
from .noise_filter import get_clean_soup

logger = logging.getLogger(__name__)


@dataclass
class ExtractedCompany:
    """A portfolio company extracted from a website."""
    name: str
    sector: str | None = None
    website: str | None = None
    description: str | None = None
    status: str | None = None  # "current" | "exited" | None (unknown)
    logo_url: str | None = None
    entry_year: int | None = None
    exit_year: int | None = None
    confidence: float = 0.5
    sources: list[str] = field(default_factory=list)
    # Phase 6: Detail page enrichment fields
    detail_page_url: str | None = None
    headquarters: str | None = None
    investment_date: str | None = None
    investment_thesis: str | None = None


@dataclass
class ExtractedTeamMember:
    """A team member extracted from a website."""
    name: str
    title: str | None = None
    role: str | None = None
    linkedin: str | None = None
    email: str | None = None
    photo_url: str | None = None
    bio: str | None = None
    confidence: float = 0.5
    sources: list[str] = field(default_factory=list)


@dataclass
class ExtractedNewsItem:
    """A news item extracted from a website."""
    title: str
    url: str | None = None
    date: str | None = None
    description: str | None = None
    company_mentioned: str | None = None
    deal_type: str | None = None
    deal_value: str | None = None
    confidence: float = 0.5
    sources: list[str] = field(default_factory=list)


class StrategyOrchestrator:
    """
    Coordinates multiple extraction strategies and merges results.

    Given a site configuration and HTML content, tries strategies in
    priority order and combines results with confidence scoring.
    """

    # Base confidence scores for each strategy
    STRATEGY_CONFIDENCE = {
        ExtractionStrategy.NEXT_DATA: 0.9,  # Very reliable structured data
        ExtractionStrategy.JSON_LD: 0.85,   # Structured schema.org data
        ExtractionStrategy.HTML_CARDS: 0.7,  # Standard card layouts
        ExtractionStrategy.TEAM_CARDS: 0.7,
        ExtractionStrategy.LOGO_GRID: 0.6,  # Image-based, less reliable
        ExtractionStrategy.LINK_LIST: 0.5,
        ExtractionStrategy.TABLE_ROWS: 0.65,
        ExtractionStrategy.H3_WITH_TITLE: 0.6,
    }

    # Confidence for site-specific extractors (very high as they're custom-built)
    SITE_SPECIFIC_CONFIDENCE = 0.95

    # Minimum confidence to include in results
    MIN_CONFIDENCE = 0.3

    def __init__(self):
        # Lazy import strategies to avoid circular imports
        self._strategies_loaded = False
        self._site_specific_loaded = False

    def _load_strategies(self):
        """Load strategy modules."""
        if self._strategies_loaded:
            return

        from .strategies import (
            extract_from_next_data,
            extract_portfolio_from_next_data,
            extract_team_from_next_data,
            extract_from_html_cards,
            extract_portfolio_from_cards,
            extract_team_from_cards,
            extract_from_logo_grid,
            extract_companies_from_logos,
            extract_from_json_ld,
            extract_organizations_from_json_ld,
            extract_people_from_json_ld,
        )

        self._next_data = extract_from_next_data
        self._next_data_portfolio = extract_portfolio_from_next_data
        self._next_data_team = extract_team_from_next_data
        self._html_cards = extract_from_html_cards
        self._html_cards_portfolio = extract_portfolio_from_cards
        self._html_cards_team = extract_team_from_cards
        self._logo_grid = extract_from_logo_grid
        self._logo_grid_companies = extract_companies_from_logos
        self._json_ld = extract_from_json_ld
        self._json_ld_orgs = extract_organizations_from_json_ld
        self._json_ld_people = extract_people_from_json_ld

        self._strategies_loaded = True

    def _load_site_specific(self):
        """Load site-specific extractors."""
        if self._site_specific_loaded:
            return

        from .strategies.site_specific import get_site_extractor
        self._get_site_extractor = get_site_extractor
        self._site_specific_loaded = True

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()

    def extract_portfolio(
        self,
        html: str,
        url: str,
        config: SiteConfig | None = None,
    ) -> list[ExtractedCompany]:
        """
        Extract portfolio companies using configured strategies.

        Args:
            html: Raw HTML content
            url: Page URL
            config: Site configuration

        Returns:
            List of ExtractedCompany objects
        """
        self._load_strategies()
        self._load_site_specific()

        # Clean HTML first
        soup, noise_removed = get_clean_soup(html)
        clean_html = str(soup)
        logger.debug(f"Removed {noise_removed} noise elements")

        results: list[dict] = []

        # Try site-specific extractor first
        domain = self._get_domain(url)
        site_extractor = self._get_site_extractor(domain, "portfolio")

        if site_extractor:
            try:
                # Use raw HTML for site-specific extractors - they know the exact structure
                site_results = site_extractor(html, url)
                logger.info(f"Site-specific extractor for {domain} returned {len(site_results)} companies")
                for item in site_results:
                    item["_strategy"] = "site_specific"
                results.extend(site_results)
            except Exception as e:
                logger.warning(f"Site-specific portfolio extractor for {domain} failed: {e}")

        # Get strategies from config or use defaults
        strategies = []
        selectors = {}

        if config and config.portfolio:
            strategies = config.portfolio.strategies or []
            selectors = _selector_config_to_dict(config.portfolio.selectors)

        # Default strategies if none configured
        if not strategies:
            strategies = [
                ExtractionStrategy.NEXT_DATA,
                ExtractionStrategy.JSON_LD,
                ExtractionStrategy.HTML_CARDS,
                ExtractionStrategy.LOGO_GRID,
            ]

        # Only run generic strategies if site-specific extractor returned nothing
        site_specific_results = [r for r in results if r.get("_strategy") == "site_specific"]
        if site_specific_results:
            logger.info(f"Skipping generic strategies — site-specific extractor returned {len(site_specific_results)} results for {domain}")
        else:
            for strategy in strategies:
                try:
                    items = self._run_portfolio_strategy(strategy, clean_html, url, selectors)
                    for item in items:
                        item["_strategy"] = strategy.value
                    results.extend(items)
                except Exception as e:
                    logger.warning(f"Strategy {strategy.value} failed: {e}")

        # Dedupe and score
        companies = self._dedupe_and_score_companies(results)

        # Filter by confidence
        companies = [c for c in companies if c.confidence >= self.MIN_CONFIDENCE]

        # Add detail page URLs for known site patterns
        companies = self._add_detail_page_urls(companies, url, domain)

        logger.info(f"Extracted {len(companies)} companies (from {len(results)} raw)")
        return companies

    def extract_team(
        self,
        html: str,
        url: str,
        config: SiteConfig | None = None,
    ) -> list[ExtractedTeamMember]:
        """
        Extract team members using configured strategies.

        Args:
            html: Raw HTML content
            url: Page URL
            config: Site configuration

        Returns:
            List of ExtractedTeamMember objects
        """
        self._load_strategies()
        self._load_site_specific()

        # Clean HTML first
        soup, noise_removed = get_clean_soup(html)
        clean_html = str(soup)

        results: list[dict] = []

        # Try site-specific extractor first
        domain = self._get_domain(url)
        site_extractor = self._get_site_extractor(domain, "team")

        if site_extractor:
            try:
                # Use raw HTML for site-specific extractors - they know the exact structure
                site_results = site_extractor(html, url)
                logger.info(f"Site-specific extractor for {domain} returned {len(site_results)} team members")
                for item in site_results:
                    item["_strategy"] = "site_specific"
                results.extend(site_results)
            except Exception as e:
                logger.warning(f"Site-specific team extractor for {domain} failed: {e}")

        # Get strategies from config or use defaults
        strategies = []
        selectors = {}

        if config and config.team:
            strategies = config.team.strategies or []
            selectors = _selector_config_to_dict(config.team.selectors)

        # Default strategies
        if not strategies:
            strategies = [
                ExtractionStrategy.NEXT_DATA,
                ExtractionStrategy.JSON_LD,
                ExtractionStrategy.TEAM_CARDS,
                ExtractionStrategy.H3_WITH_TITLE,
            ]

        # Only run generic strategies if site-specific extractor returned nothing
        site_specific_results = [r for r in results if r.get("_strategy") == "site_specific"]
        if site_specific_results:
            logger.info(f"Skipping generic team strategies — site-specific extractor returned {len(site_specific_results)} results for {domain}")
        else:
            for strategy in strategies:
                try:
                    items = self._run_team_strategy(strategy, clean_html, url, selectors)
                    for item in items:
                        item["_strategy"] = strategy.value
                    results.extend(items)
                except Exception as e:
                    logger.warning(f"Strategy {strategy.value} failed: {e}")

        # Dedupe and score
        members = self._dedupe_and_score_team(results)

        # Filter by confidence
        members = [m for m in members if m.confidence >= self.MIN_CONFIDENCE]

        logger.info(f"Extracted {len(members)} team members (from {len(results)} raw)")
        return members

    def extract_news(
        self,
        html: str,
        url: str,
        config: SiteConfig | None = None,
    ) -> list[ExtractedNewsItem]:
        """
        Extract news items from HTML content.

        Uses site-specific extractors when available, otherwise falls back
        to generic NewsExtractor from extractors module.

        Args:
            html: Raw HTML content
            url: Source URL (for resolving relative links)
            config: Optional site configuration

        Returns:
            List of ExtractedNewsItem with confidence scores
        """
        self._load_site_specific()

        # Try site-specific extractor first
        domain = self._get_domain(url)
        site_extractor = self._get_site_extractor(domain, "news")

        result = []

        if site_extractor:
            try:
                site_results = site_extractor(html, url)
                logger.info(f"Site-specific news extractor for {domain} returned {len(site_results)} items")

                # Convert to ExtractedNewsItem
                for item in site_results:
                    result.append(ExtractedNewsItem(
                        title=item.get("title", ""),
                        url=item.get("url"),
                        date=item.get("date") or item.get("published_at"),
                        description=item.get("description") or item.get("summary"),
                        company_mentioned=item.get("company_mentioned"),
                        deal_type=item.get("deal_type"),
                        confidence=item.get("confidence", 0.85),
                    ))

                if result:
                    logger.info(f"Extracted {len(result)} news items from site-specific extractor")
                    return result
            except Exception as e:
                logger.warning(f"Site-specific news extractor for {domain} failed: {e}")

        # Fall back to generic extractor
        from .extractors import NewsExtractor as NewsExtractorClass

        extractor = NewsExtractorClass()
        items = extractor.extract(html, url)

        # Convert to our ExtractedNewsItem format
        for item in items:
            result.append(ExtractedNewsItem(
                title=item.title,
                url=item.url,
                date=item.date,
                description=item.description,
                company_mentioned=item.company_mentioned,
                deal_type=item.deal_type,
                confidence=item.confidence,
            ))

        logger.info(f"Extracted {len(result)} news items")
        return result

    def _run_portfolio_strategy(
        self,
        strategy: ExtractionStrategy,
        html: str,
        url: str,
        selectors: dict,
    ) -> list[dict]:
        """Run a single portfolio extraction strategy."""
        if strategy == ExtractionStrategy.NEXT_DATA:
            return self._next_data_portfolio(html)
        elif strategy == ExtractionStrategy.JSON_LD:
            return self._json_ld_orgs(html)
        elif strategy == ExtractionStrategy.HTML_CARDS:
            return self._html_cards_portfolio(html, url, selectors)
        elif strategy == ExtractionStrategy.LOGO_GRID:
            return self._logo_grid_companies(html, url, selectors)
        else:
            logger.debug(f"No handler for portfolio strategy: {strategy}")
            return []

    def _run_team_strategy(
        self,
        strategy: ExtractionStrategy,
        html: str,
        url: str,
        selectors: dict,
    ) -> list[dict]:
        """Run a single team extraction strategy."""
        if strategy == ExtractionStrategy.NEXT_DATA:
            return self._next_data_team(html)
        elif strategy == ExtractionStrategy.JSON_LD:
            return self._json_ld_people(html)
        elif strategy in (ExtractionStrategy.TEAM_CARDS, ExtractionStrategy.HTML_CARDS):
            return self._html_cards_team(html, url, selectors)
        else:
            logger.debug(f"No handler for team strategy: {strategy}")
            return []

    # Site patterns for constructing detail page URLs
    # Maps domain -> (url_pattern, slug_generator)
    DETAIL_URL_PATTERNS = {
        "www.21invest.com": {
            "pattern": "/en/{slug}/",
            "base": "https://www.21invest.com",
        },
        "www.fondoitaliano.it": {
            "pattern": "/investimenti/{slug}/",
            "base": "https://www.fondoitaliano.it",
        },
    }

    def _add_detail_page_urls(
        self,
        companies: list["ExtractedCompany"],
        url: str,
        domain: str,
    ) -> list["ExtractedCompany"]:
        """
        Add detail_page_url for sites with known URL patterns.

        For sites like 21invest where company detail pages follow a predictable
        pattern (e.g., /en/company-name/), we construct the URL from the name.
        """
        if domain not in self.DETAIL_URL_PATTERNS:
            return companies

        config = self.DETAIL_URL_PATTERNS[domain]
        pattern = config["pattern"]
        base = config["base"]

        import re
        from urllib.parse import urljoin

        for company in companies:
            if company.detail_page_url:
                continue  # Already has a detail URL

            # Convert name to slug
            # "Forno d'Asolo" -> "forno-d-asolo"
            name = company.name
            slug = name.lower()
            slug = re.sub(r"[''`]", "", slug)  # Remove apostrophes
            slug = re.sub(r"[^a-z0-9]+", "-", slug)  # Replace non-alphanumeric
            slug = slug.strip("-")

            # Construct detail URL
            detail_path = pattern.format(slug=slug)
            company.detail_page_url = urljoin(base, detail_path)

        return companies

    def _dedupe_and_score_companies(
        self,
        items: list[dict],
    ) -> list[ExtractedCompany]:
        """
        Deduplicate companies and assign confidence scores.

        Companies with similar names are merged, and confidence is
        boosted when multiple strategies agree.
        """
        if not items:
            return []

        # Group by normalized name
        groups: dict[str, list[dict]] = {}
        for item in items:
            name = item.get("name", "")
            if not name:
                continue

            key = _normalize_name(name)
            if key not in groups:
                groups[key] = []
            groups[key].append(item)

        # Merge groups
        results = []
        for key, group in groups.items():
            merged = self._merge_company_group(group)
            results.append(merged)

        # Sort by confidence
        results.sort(key=lambda c: c.confidence, reverse=True)

        return results

    def _merge_company_group(self, items: list[dict]) -> ExtractedCompany:
        """Merge a group of similar company entries."""
        # Calculate confidence based on agreement
        base_confidence = 0.0
        sources = []

        for item in items:
            strategy = item.get("_strategy", "unknown")
            sources.append(strategy)

            # Get strategy confidence
            if strategy == "site_specific":
                base_confidence += self.SITE_SPECIFIC_CONFIDENCE
            else:
                try:
                    strat_enum = ExtractionStrategy(strategy)
                    base_confidence += self.STRATEGY_CONFIDENCE.get(strat_enum, 0.5)
                except ValueError:
                    base_confidence += 0.5

        # Normalize and boost for agreement
        confidence = min(base_confidence / len(items), 1.0)
        if len(items) > 1:
            confidence = min(confidence + 0.1 * (len(items) - 1), 1.0)

        # Merge fields (prefer non-null, longer descriptions)
        company = ExtractedCompany(
            name=items[0].get("name", ""),
            sources=list(set(sources)),
            confidence=confidence,
        )

        for item in items:
            if not company.sector and item.get("sector"):
                company.sector = item["sector"]
            if not company.website and item.get("website"):
                company.website = item["website"]
            if item.get("description"):
                if not company.description or len(item["description"]) > len(company.description):
                    company.description = item["description"]
            if not company.logo_url and item.get("logo_url"):
                company.logo_url = item["logo_url"]
            if item.get("status") in ("exited", "current"):
                # Prefer "exited" over "current" (if any source says exited, trust it)
                if item["status"] == "exited" or company.status is None:
                    company.status = item["status"]
            if item.get("entry_year"):
                company.entry_year = item["entry_year"]
            if item.get("exit_year"):
                company.exit_year = item["exit_year"]
            # Phase 6: Detail page enrichment fields
            if not company.detail_page_url and item.get("detail_page_url"):
                company.detail_page_url = item["detail_page_url"]
            if not company.headquarters and item.get("headquarters"):
                company.headquarters = item["headquarters"]
            if not company.investment_date and item.get("investment_date"):
                company.investment_date = item["investment_date"]
            if item.get("investment_thesis"):
                if not company.investment_thesis or len(item["investment_thesis"]) > len(company.investment_thesis):
                    company.investment_thesis = item["investment_thesis"]

        return company

    def _dedupe_and_score_team(
        self,
        items: list[dict],
    ) -> list[ExtractedTeamMember]:
        """
        Deduplicate team members and assign confidence scores.
        """
        if not items:
            return []

        # Group by normalized name
        groups: dict[str, list[dict]] = {}
        for item in items:
            name = item.get("name", "")
            if not name:
                continue

            key = _normalize_name(name)
            if key not in groups:
                groups[key] = []
            groups[key].append(item)

        # Merge groups
        results = []
        for key, group in groups.items():
            merged = self._merge_team_group(group)
            results.append(merged)

        # Sort by confidence
        results.sort(key=lambda m: m.confidence, reverse=True)

        return results

    def _merge_team_group(self, items: list[dict]) -> ExtractedTeamMember:
        """Merge a group of similar team member entries."""
        # Calculate confidence
        base_confidence = 0.0
        sources = []

        for item in items:
            strategy = item.get("_strategy", "unknown")
            sources.append(strategy)

            if strategy == "site_specific":
                base_confidence += self.SITE_SPECIFIC_CONFIDENCE
            else:
                try:
                    strat_enum = ExtractionStrategy(strategy)
                    base_confidence += self.STRATEGY_CONFIDENCE.get(strat_enum, 0.5)
                except ValueError:
                    base_confidence += 0.5

        confidence = min(base_confidence / len(items), 1.0)
        if len(items) > 1:
            confidence = min(confidence + 0.1 * (len(items) - 1), 1.0)

        # Merge fields
        member = ExtractedTeamMember(
            name=items[0].get("name", ""),
            sources=list(set(sources)),
            confidence=confidence,
        )

        for item in items:
            if not member.title and item.get("title"):
                member.title = item["title"]
            if not member.role and item.get("role"):
                member.role = item["role"]
            if not member.linkedin and item.get("linkedin"):
                member.linkedin = item["linkedin"]
            if not member.email and item.get("email"):
                member.email = item["email"]
            if not member.photo_url and item.get("photo_url"):
                member.photo_url = item["photo_url"]
            if item.get("bio"):
                if not member.bio or len(item["bio"]) > len(member.bio):
                    member.bio = item["bio"]

        return member


def _normalize_name(name: str) -> str:
    """
    Normalize a name for comparison.

    Lowercases, strips whitespace, and removes common suffixes.
    """
    if not name:
        return ""

    name = name.lower().strip()

    # Remove fund investment suffixes (common in Italian fund portfolio pages)
    # e.g., "Scatolificio del garda investimento diretto fondo italiano" -> "Scatolificio del garda"
    fund_patterns = [
        " investimento diretto fondo italiano",
        " investimento fondo italiano",
        " fondo italiano",
        " portfolio company",
        " exit",
    ]
    for pattern in fund_patterns:
        if pattern in name:
            name = name.replace(pattern, "")

    # Remove common company suffixes
    suffixes = [" spa", " srl", " ltd", " inc", " llc", " plc", " sa", " ag"]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]

    # Normalize whitespace
    name = " ".join(name.split())

    return name


def _selector_config_to_dict(config: SelectorConfig | None) -> dict:
    """Convert SelectorConfig to dictionary."""
    if not config:
        return {}

    return {
        "container": config.container,
        "item": config.item,
        "name": config.name,
        "description": config.description,
        "sector": config.sector,
        "website": config.website,
        "status": config.status,
        "image": config.image,
        "title": config.title,
        "role": config.role,
        "linkedin": config.linkedin,
        "email": config.email,
    }


# Global orchestrator instance
_orchestrator: StrategyOrchestrator | None = None


def get_orchestrator() -> StrategyOrchestrator:
    """Get the global strategy orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = StrategyOrchestrator()
    return _orchestrator
