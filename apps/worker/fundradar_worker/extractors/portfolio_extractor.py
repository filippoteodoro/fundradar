"""
Portfolio company extractor.

Extracts portfolio companies from fund websites using multiple strategies
and the strategy orchestrator.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..site_config_schema import SiteConfig, site_config_from_dict
from ..strategy_orchestrator import StrategyOrchestrator, ExtractedCompany
from ..noise_filter import remove_noise

logger = logging.getLogger(__name__)


# Re-export the dataclass for convenience
ExtractedCompany = ExtractedCompany


class PortfolioExtractor:
    """
    Extracts portfolio companies from HTML content.

    Uses the strategy orchestrator to try multiple extraction strategies
    and return the best results.

    Usage:
        extractor = PortfolioExtractor()
        companies = extractor.extract(html, url)

        # With site-specific config
        companies = extractor.extract(html, url, config=site_config)

        # Save results
        extractor.save_results(companies, "fund-slug", output_dir)
    """

    def __init__(self, config_path: Path | None = None):
        """
        Initialize the extractor.

        Args:
            config_path: Optional path to site_extractors.json for additional config
        """
        self.orchestrator = StrategyOrchestrator()
        self._site_configs: dict[str, dict] = {}

        if config_path and config_path.exists():
            self._load_site_configs(config_path)

    def _load_site_configs(self, config_path: Path):
        """Load site-specific configurations."""
        try:
            with open(config_path) as f:
                data = json.load(f)
                self._site_configs = data.get("sites", {})
        except Exception as e:
            logger.warning(f"Failed to load site configs: {e}")

    def _get_site_config(self, url: str) -> SiteConfig | None:
        """Get site configuration for a URL."""
        from urllib.parse import urlparse

        domain = urlparse(url).netloc.lower()

        if domain in self._site_configs:
            site_data = self._site_configs[domain]
            # Convert to SiteConfig
            config_dict = {
                "domain": domain,
                "portfolio": site_data.get("portfolio", {}),
                "team": site_data.get("team", {}),
                "news": site_data.get("news", {}),
            }
            return site_config_from_dict(config_dict)

        return None

    def extract(
        self,
        html: str,
        url: str,
        config: SiteConfig | None = None,
    ) -> list[ExtractedCompany]:
        """
        Extract portfolio companies from HTML.

        Args:
            html: Raw HTML content
            url: Page URL
            config: Optional site configuration

        Returns:
            List of ExtractedCompany objects
        """
        # Get config from stored configs if not provided
        if config is None:
            config = self._get_site_config(url)

        # Run orchestrated extraction
        companies = self.orchestrator.extract_portfolio(html, url, config)

        # Post-process results
        companies = self._post_process(companies)

        return companies

    def _post_process(self, companies: list[ExtractedCompany]) -> list[ExtractedCompany]:
        """
        Post-process extracted companies.

        - Validates data
        - Normalizes fields
        - Filters low-quality results
        - Infers 'current' status only when the fund provides status info
        """
        valid = []

        for company in companies:
            # Must have a name
            if not company.name or len(company.name) < 2:
                continue

            # Clean up name
            company.name = company.name.strip()

            # Clean up website
            if company.website:
                if not company.website.startswith(("http://", "https://")):
                    company.website = "https://" + company.website

            # Clean up sector
            if company.sector:
                company.sector = company.sector.strip()

            # Normalize invalid status values to None
            if company.status not in ("current", "exited", None):
                company.status = None

            valid.append(company)

        # If ANY company has an explicit status, the fund provides status info.
        # In that case, companies without status can be inferred as "current"
        # (the fund marks exits, so unmarked = current).
        # If NO company has status, leave all as None (unknown).
        fund_provides_status = any(c.status in ("current", "exited") for c in valid)
        if fund_provides_status:
            for company in valid:
                if company.status is None:
                    company.status = "current"

        return valid

    def extract_with_diff(
        self,
        html: str,
        url: str,
        previous_companies: list[dict],
        config: SiteConfig | None = None,
    ) -> tuple[list[ExtractedCompany], list[ExtractedCompany], list[ExtractedCompany]]:
        """
        Extract companies and compare with previous extraction.

        Args:
            html: Raw HTML content
            url: Page URL
            previous_companies: Previously extracted companies (as dicts)
            config: Optional site configuration

        Returns:
            Tuple of (all_companies, new_companies, removed_companies)
        """
        current = self.extract(html, url, config)

        # Build lookup by normalized name
        current_names = {self._normalize(c.name) for c in current}
        previous_names = {self._normalize(p.get("name", "")) for p in previous_companies if p.get("name")}

        # Find new and removed
        new_companies = [c for c in current if self._normalize(c.name) not in previous_names]
        removed_names = previous_names - current_names

        # Reconstruct removed companies from previous data
        removed_companies = []
        for prev in previous_companies:
            name = prev.get("name", "")
            if self._normalize(name) in removed_names:
                removed_companies.append(ExtractedCompany(
                    name=name,
                    sector=prev.get("sector"),
                    website=prev.get("website"),
                    status=prev.get("status"),
                    confidence=prev.get("confidence", 0.5),
                ))

        return current, new_companies, removed_companies

    def _normalize(self, name: str) -> str:
        """Normalize name for comparison."""
        if not name:
            return ""
        return name.lower().strip()

    def save_results(
        self,
        companies: list[ExtractedCompany],
        fund_slug: str,
        output_dir: Path,
    ) -> tuple[Path, Path]:
        """
        Save extraction results to JSON files.

        Args:
            companies: Extracted companies
            fund_slug: Fund identifier
            output_dir: Output directory

        Returns:
            Tuple of (current_path, exited_path)
        """
        # Create fund directory
        fund_dir = output_dir / fund_slug
        fund_dir.mkdir(parents=True, exist_ok=True)

        # Split by status (unknown status = not exited, include with current)
        current = [c for c in companies if c.status != "exited"]
        exited = [c for c in companies if c.status == "exited"]

        # Save current portfolio (includes unknown-status companies)
        current_path = fund_dir / "portfolio.json"
        self._save_json(current_path, current, fund_slug, "portfolio")

        # Save exited portfolio
        exited_path = fund_dir / "portfolio_exited.json"
        self._save_json(exited_path, exited, fund_slug, "portfolio_exited")

        return current_path, exited_path

    def _save_json(
        self,
        path: Path,
        companies: list[ExtractedCompany],
        fund_slug: str,
        data_type: str,
    ):
        """Save companies to JSON file."""
        data = {
            "fund_slug": fund_slug,
            "data_type": data_type,
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "count": len(companies),
            "companies": [asdict(c) for c in companies],
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {len(companies)} companies to {path}")


def extract_portfolio_companies(
    html: str,
    url: str,
    config: SiteConfig | None = None,
) -> list[ExtractedCompany]:
    """
    Convenience function to extract portfolio companies.

    Args:
        html: Raw HTML content
        url: Page URL
        config: Optional site configuration

    Returns:
        List of ExtractedCompany objects
    """
    extractor = PortfolioExtractor()
    return extractor.extract(html, url, config)
