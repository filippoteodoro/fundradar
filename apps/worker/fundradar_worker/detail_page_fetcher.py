"""
Detail page fetcher for enriching portfolio companies.

Fetches company detail pages and extracts additional data like:
- Full descriptions
- Headquarters/location
- Investment dates
- Investment thesis

IMPORTANT: Per CLAUDE.md rules, NEVER extracts IRR, TVPI, or valuations.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .strategy_orchestrator import ExtractedCompany
from .fetcher import fetch_url

# Try to import Playwright for JS-heavy sites
try:
    from .playwright_fetcher import PlaywrightFetcher, FetchOptions
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    PlaywrightFetcher = None
    FetchOptions = None

logger = logging.getLogger(__name__)


@dataclass
class DetailPageResult:
    """Result of fetching and parsing a detail page."""

    url: str
    success: bool
    description: str | None = None
    headquarters: str | None = None
    investment_date: str | None = None
    investment_thesis: str | None = None
    website: str | None = None
    sector: str | None = None
    error: str | None = None


# Type for site-specific detail extractors
DetailExtractor = Callable[[str, str], DetailPageResult]


class DetailPageFetcher:
    """
    Fetches company detail pages and extracts additional data.

    Supports both HTTP and Playwright fetching for JS-heavy sites.
    Uses site-specific extractors when available.
    """

    # Default timeout for fetches (ms)
    DEFAULT_TIMEOUT = 15000

    # Delay between requests to same domain (ms)
    DOMAIN_DELAY_MS = 1000

    def __init__(
        self,
        use_playwright: bool = False,
        max_concurrent: int = 3,
    ):
        """
        Initialize fetcher.

        Args:
            use_playwright: Whether to use Playwright for JS-heavy sites
            max_concurrent: Maximum concurrent requests
        """
        self._use_playwright = use_playwright and PLAYWRIGHT_AVAILABLE
        self._max_concurrent = max_concurrent
        self._playwright_fetcher: "PlaywrightFetcher" | None = None
        self._domain_extractors: dict[str, DetailExtractor] = {}
        self._semaphore: asyncio.Semaphore | None = None

    def register_extractor(self, domain: str, extractor: DetailExtractor):
        """
        Register a site-specific detail page extractor.

        Args:
            domain: The domain (e.g., "www.21invest.com")
            extractor: Function(html, url) -> DetailPageResult
        """
        self._domain_extractors[domain] = extractor
        logger.info(f"Registered detail extractor for {domain}")

    async def _get_playwright_fetcher(self) -> "PlaywrightFetcher":
        """Get or create Playwright fetcher."""
        if self._playwright_fetcher is None:
            self._playwright_fetcher = PlaywrightFetcher()
            await self._playwright_fetcher.start()
        return self._playwright_fetcher

    async def _shutdown_playwright(self):
        """Shutdown Playwright if running."""
        if self._playwright_fetcher:
            await self._playwright_fetcher.stop()
            self._playwright_fetcher = None

    async def _fetch_page(self, url: str) -> tuple[str | None, str | None]:
        """
        Fetch a page's HTML content.

        Returns:
            (html, error) tuple
        """
        try:
            if self._use_playwright:
                fetcher = await self._get_playwright_fetcher()
                options = FetchOptions(
                    wait_for_network_idle=True,
                    dismiss_consent=True,
                )
                result = await fetcher.fetch(url, options)
            else:
                # Use synchronous HTTP fetch
                result = fetch_url(url, timeout=self.DEFAULT_TIMEOUT / 1000)

            if result.error:
                return None, result.error

            # Be lenient with status codes - some servers return 404 but still serve content
            # Only reject if we have no HTML or it looks like a real error page
            if result.status_code not in (200, 404) or not result.html:
                return None, f"HTTP {result.status_code}"

            # Check if the page looks like a real 404 error (small content, error keywords)
            if result.status_code == 404:
                html_lower = result.html[:2000].lower()
                is_real_404 = (
                    len(result.html) < 10000 and
                    ("page not found" in html_lower or
                     "404" in html_lower and "error" in html_lower or
                     "pagina non trovata" in html_lower)
                )
                if is_real_404:
                    return None, "HTTP 404"
                # Otherwise, log but continue with the content
                logger.debug(f"Got 404 status but valid content from {url}")

            return result.html, None

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None, str(e)

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        return urlparse(url).netloc.lower()

    def _extract_generic(self, html: str, url: str) -> DetailPageResult:
        """
        Generic detail page extraction.

        Extracts common fields that apply to most sites.
        """
        soup = BeautifulSoup(html, "html.parser")
        result = DetailPageResult(url=url, success=True)

        # Extract description from common patterns
        description = None

        # Try meta description first
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            description = meta_desc.get("content", "").strip()

        # Try og:description
        if not description:
            og_desc = soup.find("meta", attrs={"property": "og:description"})
            if og_desc:
                description = og_desc.get("content", "").strip()

        # Try finding main content area
        if not description:
            # Common content selectors
            for selector in [".company-description", ".description", ".content", "article", "main"]:
                content = soup.select_one(selector)
                if content:
                    text = content.get_text(" ", strip=True)
                    if len(text) > 50:
                        description = text[:1000]  # Limit length
                        break

        result.description = description

        # Extract headquarters/location
        location_patterns = [
            r"(?:sede|headquarters|location|based in|headquartered in)[:\s]+([A-Za-z\s,]+?)(?:\.|$|<)",
            r"(?:città|city)[:\s]+([A-Za-z\s,]+?)(?:\.|$|<)",
        ]
        full_text = soup.get_text(" ", strip=True)
        for pattern in location_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                result.headquarters = match.group(1).strip()[:100]
                break

        # Extract investment date
        date_patterns = [
            r"(?:data investimento|investment date|invested|year)[:\s]+(\d{4})",
            r"(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(\d{4})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                result.investment_date = match.group(1) if match.lastindex == 1 else match.group(0)
                break

        # Extract external website link
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if href.startswith("http") and self._get_domain(url) not in href:
                link_text = link.get_text(strip=True).lower()
                if any(word in link_text for word in ["sito web", "website", "visit", "visita"]):
                    result.website = href
                    break

        return result

    async def fetch_detail_page(self, url: str) -> DetailPageResult:
        """
        Fetch and extract data from a company detail page.

        Args:
            url: The detail page URL

        Returns:
            DetailPageResult with extracted data
        """
        # Fetch the page
        html, error = await self._fetch_page(url)

        if error:
            return DetailPageResult(url=url, success=False, error=error)

        if not html:
            return DetailPageResult(url=url, success=False, error="Empty response")

        # Check for site-specific extractor
        domain = self._get_domain(url)
        if domain in self._domain_extractors:
            try:
                result = self._domain_extractors[domain](html, url)
                # Convert dict to DetailPageResult if needed
                if isinstance(result, dict):
                    return DetailPageResult(
                        url=url,
                        success=result.get("success", True),
                        description=result.get("description"),
                        headquarters=result.get("headquarters"),
                        investment_date=result.get("investment_date"),
                        investment_thesis=result.get("investment_thesis"),
                        website=result.get("website"),
                        sector=result.get("sector"),
                        error=result.get("error"),
                    )
                return result
            except Exception as e:
                logger.warning(f"Site-specific extractor failed for {domain}: {e}")
                # Fall through to generic extraction

        # Use generic extraction
        return self._extract_generic(html, url)

    async def _enrich_company(
        self,
        company: ExtractedCompany,
        fund_url: str,
    ) -> ExtractedCompany:
        """
        Enrich a single company with detail page data.

        Args:
            company: The company to enrich
            fund_url: Base URL of the fund site (for constructing detail URLs)

        Returns:
            Enriched company (modified in place)
        """
        # Skip if no detail page URL
        if not company.detail_page_url:
            return company

        # Ensure full URL
        if not company.detail_page_url.startswith("http"):
            company.detail_page_url = urljoin(fund_url, company.detail_page_url)

        # Acquire semaphore for rate limiting
        if self._semaphore:
            async with self._semaphore:
                result = await self.fetch_detail_page(company.detail_page_url)
                # Add delay between requests
                await asyncio.sleep(self.DOMAIN_DELAY_MS / 1000)
        else:
            result = await self.fetch_detail_page(company.detail_page_url)

        if not result.success:
            logger.warning(f"Failed to fetch detail page for {company.name}: {result.error}")
            return company

        # Merge data (only if not already set)
        if result.description and not company.description:
            company.description = result.description
        elif result.description and company.description:
            # Prefer longer description
            if len(result.description) > len(company.description):
                company.description = result.description

        if result.headquarters and not company.headquarters:
            company.headquarters = result.headquarters

        if result.investment_date and not company.investment_date:
            company.investment_date = result.investment_date

        if result.investment_thesis and not company.investment_thesis:
            company.investment_thesis = result.investment_thesis

        if result.website and not company.website:
            company.website = result.website

        if result.sector and not company.sector:
            company.sector = result.sector

        logger.debug(f"Enriched {company.name} with detail page data")
        return company

    async def enrich_portfolio(
        self,
        companies: list[ExtractedCompany],
        fund_url: str,
        max_concurrent: int | None = None,
    ) -> list[ExtractedCompany]:
        """
        Enrich multiple companies by fetching their detail pages.

        Args:
            companies: List of companies to enrich
            fund_url: Base URL of the fund site
            max_concurrent: Override default max concurrent requests

        Returns:
            List of enriched companies
        """
        concurrent = max_concurrent or self._max_concurrent

        # Filter to companies with detail URLs
        to_enrich = [c for c in companies if c.detail_page_url]
        logger.info(f"Enriching {len(to_enrich)}/{len(companies)} companies with detail pages")

        if not to_enrich:
            return companies

        # Set up semaphore for rate limiting
        self._semaphore = asyncio.Semaphore(concurrent)

        try:
            # Create tasks for all companies
            tasks = [
                self._enrich_company(company, fund_url)
                for company in to_enrich
            ]

            # Run concurrently
            await asyncio.gather(*tasks)

        finally:
            self._semaphore = None

        return companies

    async def cleanup(self):
        """Clean up resources."""
        await self._shutdown_playwright()


# Synchronous wrapper for non-async code
def enrich_portfolio_sync(
    companies: list[ExtractedCompany],
    fund_url: str,
    max_concurrent: int = 3,
    use_playwright: bool = False,
) -> list[ExtractedCompany]:
    """
    Synchronous wrapper for portfolio enrichment.

    Args:
        companies: List of companies to enrich
        fund_url: Base URL of the fund site
        max_concurrent: Maximum concurrent requests
        use_playwright: Whether to use Playwright

    Returns:
        List of enriched companies
    """
    fetcher = DetailPageFetcher(
        use_playwright=use_playwright,
        max_concurrent=max_concurrent,
    )

    try:
        # Run async code
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create new loop in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    fetcher.enrich_portfolio(companies, fund_url, max_concurrent)
                )
                return future.result()
        else:
            return loop.run_until_complete(
                fetcher.enrich_portfolio(companies, fund_url, max_concurrent)
            )
    finally:
        # Cleanup
        try:
            asyncio.run(fetcher.cleanup())
        except RuntimeError:
            pass
