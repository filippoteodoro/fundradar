"""
Team member extractor.

Extracts team members from fund websites using multiple strategies
and the strategy orchestrator.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from ..site_config_schema import SiteConfig, site_config_from_dict
from ..strategy_orchestrator import StrategyOrchestrator, ExtractedTeamMember
from ..noise_filter import remove_noise

logger = logging.getLogger(__name__)


# Re-export the dataclass for convenience
ExtractedTeamMember = ExtractedTeamMember


class TeamExtractor:
    """
    Extracts team members from HTML content.

    Uses the strategy orchestrator to try multiple extraction strategies
    and return the best results.

    Usage:
        extractor = TeamExtractor()
        members = extractor.extract(html, url)

        # With site-specific config
        members = extractor.extract(html, url, config=site_config)

        # Save results
        extractor.save_results(members, "fund-slug", output_dir)
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
    ) -> list[ExtractedTeamMember]:
        """
        Extract team members from HTML.

        Args:
            html: Raw HTML content
            url: Page URL
            config: Optional site configuration

        Returns:
            List of ExtractedTeamMember objects
        """
        # Get config from stored configs if not provided
        if config is None:
            config = self._get_site_config(url)

        # Run orchestrated extraction
        members = self.orchestrator.extract_team(html, url, config)

        # Post-process results
        members = self._post_process(members)

        return members

    def _post_process(self, members: list[ExtractedTeamMember]) -> list[ExtractedTeamMember]:
        """
        Post-process extracted team members.

        - Validates data
        - Normalizes fields
        - Filters low-quality results
        """
        valid = []

        for member in members:
            # Must have a name
            if not member.name or len(member.name) < 3:
                continue

            # Validate name looks like a person's name
            if not self._is_valid_name(member.name):
                continue

            # Clean up name
            member.name = member.name.strip()

            # Clean up LinkedIn URL
            if member.linkedin:
                if not member.linkedin.startswith("http"):
                    member.linkedin = "https://" + member.linkedin
                # Normalize LinkedIn URL
                member.linkedin = self._normalize_linkedin(member.linkedin)

            # Clean up email
            if member.email:
                member.email = member.email.lower().strip()

            # Clean up title
            if member.title:
                member.title = member.title.strip()

            valid.append(member)

        return valid

    def _is_valid_name(self, name: str) -> bool:
        """Check if name looks like a person's name."""
        words = name.split()

        # Should have 2-5 words
        if len(words) < 2 or len(words) > 5:
            return False

        # Skip all-caps names (usually section headers like "PARTNER TEAM")
        if name.isupper():
            return False

        # First word should be capitalized
        if not words[0][0].isupper():
            return False

        # Filter common non-name patterns
        name_lower = name.lower()

        # Completely skip if it's a section/department header
        section_patterns = [
            "partner team", "investment team", "portfolio development",
            "finance team", "corporate team", "advisory board",
            "management team", "leadership team", "executive team"
        ]
        if any(pattern in name_lower for pattern in section_patterns):
            return False

        # Filter if mostly noise words
        noise_words = {
            "cookie", "privacy", "contact", "about", "news", "team",
            "our", "read", "more", "learn", "view", "see", "all",
            "partner", "company", "investment", "fund", "development"
        }
        words_lower = [w.lower() for w in words]
        noise_count = sum(1 for w in words_lower if w in noise_words)
        if noise_count >= len(words) - 1:  # All but one word is noise
            return False

        return True

    def _normalize_linkedin(self, url: str) -> str:
        """Normalize LinkedIn URL."""
        import re

        # Extract profile path
        match = re.search(r'linkedin\.com/in/([^/?#]+)', url)
        if match:
            return f"https://www.linkedin.com/in/{match.group(1)}/"

        return url

    def extract_with_diff(
        self,
        html: str,
        url: str,
        previous_members: list[dict],
        config: SiteConfig | None = None,
    ) -> tuple[list[ExtractedTeamMember], list[ExtractedTeamMember], list[ExtractedTeamMember]]:
        """
        Extract members and compare with previous extraction.

        Args:
            html: Raw HTML content
            url: Page URL
            previous_members: Previously extracted members (as dicts)
            config: Optional site configuration

        Returns:
            Tuple of (all_members, new_members, removed_members)
        """
        current = self.extract(html, url, config)

        # Build lookup by normalized name
        current_names = {self._normalize(m.name) for m in current}
        previous_names = {self._normalize(p.get("name", "")) for p in previous_members if p.get("name")}

        # Find new and removed
        new_members = [m for m in current if self._normalize(m.name) not in previous_names]
        removed_names = previous_names - current_names

        # Reconstruct removed members from previous data
        removed_members = []
        for prev in previous_members:
            name = prev.get("name", "")
            if self._normalize(name) in removed_names:
                removed_members.append(ExtractedTeamMember(
                    name=name,
                    title=prev.get("title"),
                    role=prev.get("role"),
                    linkedin=prev.get("linkedin"),
                    confidence=prev.get("confidence", 0.5),
                ))

        return current, new_members, removed_members

    def _normalize(self, name: str) -> str:
        """Normalize name for comparison."""
        if not name:
            return ""
        return name.lower().strip()

    def save_results(
        self,
        members: list[ExtractedTeamMember],
        fund_slug: str,
        output_dir: Path,
    ) -> Path:
        """
        Save extraction results to JSON file.

        Args:
            members: Extracted team members
            fund_slug: Fund identifier
            output_dir: Output directory

        Returns:
            Path to saved file
        """
        # Create fund directory
        fund_dir = output_dir / fund_slug
        fund_dir.mkdir(parents=True, exist_ok=True)

        # Save team data
        path = fund_dir / "team.json"
        self._save_json(path, members, fund_slug)

        return path

    def _save_json(
        self,
        path: Path,
        members: list[ExtractedTeamMember],
        fund_slug: str,
    ):
        """Save members to JSON file."""
        data = {
            "fund_slug": fund_slug,
            "data_type": "team",
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "count": len(members),
            "members": [asdict(m) for m in members],
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {len(members)} team members to {path}")


def extract_team_members(
    html: str,
    url: str,
    config: SiteConfig | None = None,
) -> list[ExtractedTeamMember]:
    """
    Convenience function to extract team members.

    Args:
        html: Raw HTML content
        url: Page URL
        config: Optional site configuration

    Returns:
        List of ExtractedTeamMember objects
    """
    extractor = TeamExtractor()
    return extractor.extract(html, url, config)
