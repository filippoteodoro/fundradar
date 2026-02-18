"""
Apify API client wrapper for LinkedIn scraping.

Provides a clean interface to Apify actors for company profiles,
posts, employees, and individual profiles.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Default Apify actors for LinkedIn scraping
# See: https://apify.com/store for available actors
ACTORS = {
    "company_scraper": "curious_coder/linkedin-company-scraper",
    "company_posts": "apimaestro/linkedin-post-search-scraper",
    "company_employees": "harvestapi/linkedin-company-employees",
    "profile_scraper": "supreme_coder/linkedin-profile-scraper",
}


@dataclass
class ApifyConfig:
    """Configuration for Apify API access."""

    api_token: str
    base_url: str = "https://api.apify.com/v2"
    timeout: int = 300  # 5 minutes for actor runs
    poll_interval: int = 5  # Seconds between status checks
    max_items: int = 100  # Default max items per request

    @classmethod
    def from_env(cls) -> "ApifyConfig":
        """Create config from environment variables."""
        token = os.environ.get("APIFY_API_TOKEN")
        if not token:
            raise ValueError(
                "APIFY_API_TOKEN environment variable is required. "
                "Get your token from https://console.apify.com/account/integrations"
            )
        return cls(api_token=token)


@dataclass
class ActorRunResult:
    """Result from an Apify actor run."""

    run_id: str
    status: str  # READY, RUNNING, SUCCEEDED, FAILED, etc.
    items: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    cost_usd: float = 0.0
    duration_secs: float = 0.0


class ApifyClient:
    """
    Client for interacting with Apify actors.

    Handles API authentication, actor execution, and result retrieval.
    """

    def __init__(self, config: ApifyConfig | None = None):
        self.config = config or ApifyConfig.from_env()
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {self.config.api_token}"

    def _api_url(self, endpoint: str) -> str:
        """Build full API URL."""
        return f"{self.config.base_url}{endpoint}"

    def _run_actor(
        self,
        actor_id: str,
        input_data: dict[str, Any],
        wait_for_finish: bool = True,
    ) -> ActorRunResult:
        """
        Run an Apify actor and optionally wait for completion.

        Args:
            actor_id: The actor ID (e.g., "logical_scrapers/linkedin-company-scraper")
            input_data: Input parameters for the actor
            wait_for_finish: Whether to wait for the actor to complete

        Returns:
            ActorRunResult with status and items
        """
        # Apify API requires ~ separator between username/actor-name
        api_actor_id = actor_id.replace("/", "~")
        url = self._api_url(f"/acts/{api_actor_id}/runs")

        logger.info(f"Starting actor run: {actor_id}")
        logger.debug(f"Input: {json.dumps(input_data, indent=2)}")

        try:
            response = self._session.post(
                url,
                json=input_data,
                timeout=30,
            )
            response.raise_for_status()
            run_data = response.json()["data"]
            run_id = run_data["id"]

            logger.info(f"Actor run started: {run_id}")

            if wait_for_finish:
                return self._wait_for_run(run_id)
            else:
                return ActorRunResult(
                    run_id=run_id,
                    status=run_data.get("status", "RUNNING"),
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to start actor: {e}")
            return ActorRunResult(
                run_id="",
                status="FAILED",
                error=str(e),
            )

    def _wait_for_run(self, run_id: str) -> ActorRunResult:
        """Wait for an actor run to complete and retrieve results."""
        start_time = time.time()
        status_url = self._api_url(f"/actor-runs/{run_id}")

        while True:
            elapsed = time.time() - start_time
            if elapsed > self.config.timeout:
                logger.error(f"Actor run timed out after {elapsed:.0f}s")
                return ActorRunResult(
                    run_id=run_id,
                    status="TIMEOUT",
                    error=f"Timed out after {self.config.timeout}s",
                    duration_secs=elapsed,
                )

            try:
                response = self._session.get(status_url, timeout=30)
                response.raise_for_status()
                run_data = response.json()["data"]

                status = run_data.get("status")
                logger.debug(f"Run {run_id} status: {status} ({elapsed:.0f}s elapsed)")

                if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                    break

                time.sleep(self.config.poll_interval)

            except requests.exceptions.RequestException as e:
                logger.warning(f"Error checking run status: {e}")
                time.sleep(self.config.poll_interval)

        # Get final results
        duration = time.time() - start_time
        stats = run_data.get("stats", {})

        if status != "SUCCEEDED":
            return ActorRunResult(
                run_id=run_id,
                status=status,
                error=run_data.get("errorMessage", f"Run ended with status: {status}"),
                stats=stats,
                duration_secs=duration,
                cost_usd=stats.get("computeUnits", 0) * 0.25,  # Approximate cost
            )

        # Fetch dataset items
        items = self._get_dataset_items(run_data.get("defaultDatasetId"))

        return ActorRunResult(
            run_id=run_id,
            status=status,
            items=items,
            stats=stats,
            duration_secs=duration,
            cost_usd=stats.get("computeUnits", 0) * 0.25,
        )

    def _get_dataset_items(self, dataset_id: str | None) -> list[dict[str, Any]]:
        """Retrieve all items from a dataset."""
        if not dataset_id:
            return []

        items = []
        offset = 0
        limit = 1000

        while True:
            url = self._api_url(f"/datasets/{dataset_id}/items")
            try:
                response = self._session.get(
                    url,
                    params={"offset": offset, "limit": limit},
                    timeout=30,
                )
                response.raise_for_status()
                batch = response.json()

                if not batch:
                    break

                items.extend(batch)
                logger.debug(f"Retrieved {len(batch)} items (total: {len(items)})")

                if len(batch) < limit:
                    break

                offset += limit

            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to retrieve dataset items: {e}")
                break

        return items

    def scrape_company_profile(self, company_url: str) -> ActorRunResult:
        """
        Scrape a LinkedIn company profile.

        Args:
            company_url: LinkedIn company URL (e.g., "https://www.linkedin.com/company/investindustrial")

        Returns:
            ActorRunResult with company profile data
        """
        return self._run_actor(
            ACTORS["company_scraper"],
            {"urls": [company_url]},
        )

    def scrape_company_profiles_batch(
        self, company_urls: list[str]
    ) -> ActorRunResult:
        """Scrape multiple company profiles in a single run."""
        return self._run_actor(
            ACTORS["company_scraper"],
            {"urls": company_urls},
        )

    def scrape_company_posts(
        self,
        company_url: str,
        max_posts: int = 10,
    ) -> ActorRunResult:
        """
        Scrape recent posts from a company's LinkedIn feed.

        Args:
            company_url: LinkedIn company URL
            max_posts: Maximum number of posts to retrieve

        Returns:
            ActorRunResult with post data
        """
        return self._run_actor(
            ACTORS["company_posts"],
            {
                "url": company_url,
                "maxPosts": max_posts,
            },
        )

    def scrape_company_posts_batch(
        self,
        company_urls: list[str],
        max_posts_per_company: int = 10,
    ) -> ActorRunResult:
        """Scrape posts from multiple companies."""
        return self._run_actor(
            ACTORS["company_posts"],
            {
                "urls": company_urls,
                "maxPosts": max_posts_per_company,
            },
        )

    def scrape_company_employees(
        self,
        company_url: str,
        max_employees: int = 100,
        output_type: str = "full",
    ) -> ActorRunResult:
        """
        Scrape employee list from a company.

        Args:
            company_url: LinkedIn company URL
            max_employees: Maximum number of employees to retrieve
            output_type: "short" ($4/1k) or "full" ($8/1k) for detailed profiles

        Returns:
            ActorRunResult with employee list (names, titles, profile URLs, experience, education)
        """
        return self._run_actor(
            ACTORS["company_employees"],
            {
                "companies": [company_url],
                "maxItems": max_employees,
                "outputType": output_type,
            },
        )

    def scrape_profile(self, profile_url: str) -> ActorRunResult:
        """
        Scrape an individual LinkedIn profile.

        Args:
            profile_url: LinkedIn profile URL

        Returns:
            ActorRunResult with profile data (education, experience, etc.)
        """
        return self._run_actor(
            ACTORS["profile_scraper"],
            {"urls": [{"url": profile_url}]},
        )

    def scrape_profiles_batch(self, profile_urls: list[str]) -> ActorRunResult:
        """Scrape multiple profiles in a single run."""
        return self._run_actor(
            ACTORS["profile_scraper"],
            {"urls": [{"url": u} for u in profile_urls]},
        )

    def get_run_status(self, run_id: str) -> ActorRunResult:
        """Check the status of a running actor."""
        url = self._api_url(f"/actor-runs/{run_id}")
        try:
            response = self._session.get(url, timeout=30)
            response.raise_for_status()
            run_data = response.json()["data"]

            return ActorRunResult(
                run_id=run_id,
                status=run_data.get("status", "UNKNOWN"),
                stats=run_data.get("stats", {}),
            )
        except requests.exceptions.RequestException as e:
            return ActorRunResult(
                run_id=run_id,
                status="ERROR",
                error=str(e),
            )


def save_raw_data(
    items: list[dict[str, Any]],
    output_path: Path,
    data_type: str,
) -> None:
    """
    Save raw Apify results to JSON file.

    Args:
        items: List of items from Apify actor
        output_path: Path to save JSON file
        data_type: Type of data (for logging)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "data_type": data_type,
        "item_count": len(items),
        "items": items,
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved {len(items)} {data_type} items to {output_path}")
