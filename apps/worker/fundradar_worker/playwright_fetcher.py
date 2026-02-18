"""
Playwright-based fetcher for JavaScript-heavy websites.

Returns FetchResult compatible with the existing fetcher.py interface,
enabling seamless integration with the monitoring pipeline.
"""

import asyncio
import logging
import random
import re
from dataclasses import dataclass
from typing import Callable

from .fetcher import FetchResult, extract_text_from_html, compute_content_hash
from .playwright_pool import PlaywrightPool, PoolConfig, PLAYWRIGHT_AVAILABLE

logger = logging.getLogger(__name__)

# Common cookie consent selectors to dismiss
CONSENT_SELECTORS = [
    # Generic accept buttons
    "button[id*='accept']",
    "button[class*='accept']",
    "button[id*='consent']",
    "button[class*='consent']",
    "a[id*='accept']",
    "a[class*='accept']",
    # Common consent manager patterns
    "[data-testid='cookie-policy-dialog-accept-button']",
    "#onetrust-accept-btn-handler",
    ".onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#CybotCookiebotDialogBodyButtonAccept",
    ".cc-accept",
    ".cc-btn.cc-dismiss",
    "#cookie-accept",
    "#cookie-consent-accept",
    ".cookie-accept",
    ".cookie-consent-accept",
    # Italian patterns
    "button:has-text('Accetta')",
    "button:has-text('Accetto')",
    "button:has-text('Accetta tutti')",
    "button:has-text('Accetta tutto')",
    "a:has-text('Accetta')",
    # English patterns
    "button:has-text('Accept')",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('I Accept')",
    "button:has-text('Allow all')",
    "button:has-text('Allow All')",
    # GDPR banner close buttons
    ".gdpr-banner button",
    ".cookie-banner button",
    "[class*='cookie-banner'] button",
    "[class*='gdpr'] button[class*='accept']",
]


@dataclass
class FetchOptions:
    """Options for Playwright-based fetching."""

    # Wait conditions
    wait_for_selector: str | None = None
    wait_for_timeout: int = 5000  # ms to wait for page load
    wait_for_network_idle: bool = True
    network_idle_timeout: int = 10000  # ms

    # Scrolling
    scroll_to_bottom: bool = False
    scroll_pause_ms: int = 500
    max_scrolls: int = 10

    # Consent handling
    dismiss_consent: bool = True
    consent_timeout: int = 3000  # ms to wait for consent modal

    # Timing randomization (stealth)
    random_delay_ms: tuple[int, int] = (100, 500)

    # Click-to-load pagination (e.g., "Load more" buttons)
    click_to_load_selector: str | None = None
    click_to_load_max_clicks: int = 50

    # Retry
    retry_count: int = 1

    # Screenshot for debugging
    screenshot_on_error: bool = False


async def _random_delay(options: FetchOptions):
    """Add random delay for stealth."""
    if options.random_delay_ms:
        delay = random.randint(*options.random_delay_ms) / 1000
        await asyncio.sleep(delay)


async def _dismiss_consent(page, options: FetchOptions) -> bool:
    """
    Try to dismiss cookie consent modals.

    Returns True if a consent modal was found and dismissed.
    """
    for selector in CONSENT_SELECTORS:
        try:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
                await element.click()
                logger.debug(f"Dismissed consent modal with selector: {selector}")
                await _random_delay(options)
                return True
        except Exception:
            continue
    return False


async def _scroll_to_bottom(page, options: FetchOptions) -> int:
    """
    Scroll to the bottom of the page to trigger lazy loading.

    Returns the number of scroll iterations performed.
    """
    scroll_count = 0
    previous_height = 0

    for _ in range(options.max_scrolls):
        # Get current scroll height
        current_height = await page.evaluate("document.body.scrollHeight")

        if current_height == previous_height:
            # No new content loaded
            break

        previous_height = current_height

        # Scroll to bottom
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        scroll_count += 1

        # Wait for new content to load
        await asyncio.sleep(options.scroll_pause_ms / 1000)
        await _random_delay(options)

    logger.debug(f"Scrolled {scroll_count} times")
    return scroll_count


async def _click_to_load_all(page, options: FetchOptions) -> int:
    """
    Click a "Load more" button repeatedly until all content is loaded.

    Returns the number of clicks performed.
    """
    selector = options.click_to_load_selector
    if not selector:
        return 0

    clicks = 0
    for _ in range(options.click_to_load_max_clicks):
        try:
            button = await page.query_selector(selector)
            if not button:
                logger.debug("Click-to-load: button not found, done")
                break

            if not await button.is_visible():
                logger.debug("Click-to-load: button not visible, done")
                break

            await button.click()
            clicks += 1

            # Wait for new content to load
            await asyncio.sleep(1)
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            await _random_delay(options)

        except Exception as e:
            logger.debug(f"Click-to-load stopped after {clicks} clicks: {e}")
            break

    logger.debug(f"Click-to-load: {clicks} clicks performed")
    return clicks


async def fetch_with_playwright(
    url: str,
    pool: PlaywrightPool | None = None,
    options: FetchOptions | None = None,
) -> FetchResult:
    """
    Fetch a URL using Playwright for JavaScript-heavy sites.

    Args:
        url: The URL to fetch
        pool: Browser pool to use (creates temporary one if None)
        options: Fetch options for wait conditions, scrolling, etc.

    Returns:
        FetchResult compatible with the standard fetcher interface
    """
    if not PLAYWRIGHT_AVAILABLE:
        return FetchResult(
            url=url,
            status_code=0,
            html="",
            text="",
            title=None,
            content_hash="",
            error="Playwright is not installed",
        )

    options = options or FetchOptions()
    own_pool = pool is None

    try:
        if own_pool:
            pool = PlaywrightPool()
            await pool.start()

        async with pool.get_page() as page:
            # Navigate to the page
            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=options.network_idle_timeout,
                )

                if response is None:
                    return FetchResult(
                        url=url,
                        status_code=0,
                        html="",
                        text="",
                        title=None,
                        content_hash="",
                        error="No response received",
                    )

                status_code = response.status
                final_url = page.url

            except Exception as e:
                error_msg = str(e)
                if "Timeout" in error_msg or "timeout" in error_msg:
                    error_msg = "Timeout"
                return FetchResult(
                    url=url,
                    status_code=0,
                    html="",
                    text="",
                    title=None,
                    content_hash="",
                    error=error_msg,
                )

            # Random delay after navigation
            await _random_delay(options)

            # Try to dismiss consent modals
            if options.dismiss_consent:
                try:
                    await asyncio.wait_for(
                        _dismiss_consent(page, options),
                        timeout=options.consent_timeout / 1000,
                    )
                except asyncio.TimeoutError:
                    pass

            # Wait for network idle if requested
            if options.wait_for_network_idle:
                try:
                    await page.wait_for_load_state(
                        "networkidle",
                        timeout=options.network_idle_timeout,
                    )
                except Exception:
                    # Network may never go idle for some sites
                    logger.debug(f"Network idle timeout for {url}")

            # Wait for specific selector if provided
            if options.wait_for_selector:
                try:
                    await page.wait_for_selector(
                        options.wait_for_selector,
                        timeout=options.wait_for_timeout,
                    )
                except Exception as e:
                    logger.debug(f"Selector wait failed: {options.wait_for_selector}: {e}")

            # Additional wait timeout
            if options.wait_for_timeout > 0:
                await page.wait_for_timeout(min(options.wait_for_timeout, 3000))

            # Scroll to bottom if needed (for lazy-loaded content)
            if options.scroll_to_bottom:
                await _scroll_to_bottom(page, options)

            # Click "load more" button repeatedly if configured
            if options.click_to_load_selector:
                await _click_to_load_all(page, options)

            # Get page content
            html = await page.content()
            title = await page.title()

            # Extract text and compute hash
            text, extracted_title = extract_text_from_html(html)
            content_hash = compute_content_hash(text)

            return FetchResult(
                url=url,
                status_code=status_code,
                html=html,
                text=text,
                title=title or extracted_title,
                content_hash=content_hash,
                final_url=final_url if final_url != url else None,
            )

    except Exception as e:
        logger.error(f"Playwright fetch error for {url}: {e}")
        return FetchResult(
            url=url,
            status_code=0,
            html="",
            text="",
            title=None,
            content_hash="",
            error=str(e),
        )

    finally:
        if own_pool and pool:
            await pool.stop()


def fetch_with_playwright_sync(
    url: str,
    options: FetchOptions | None = None,
) -> FetchResult:
    """
    Synchronous wrapper for fetch_with_playwright.

    Useful for integration with synchronous code.
    """
    return asyncio.run(fetch_with_playwright(url, options=options))


class PlaywrightFetcher:
    """
    Stateful Playwright fetcher with persistent browser pool.

    Usage:
        fetcher = PlaywrightFetcher()
        await fetcher.start()

        result = await fetcher.fetch(url)

        await fetcher.stop()

    Or as context manager:
        async with PlaywrightFetcher() as fetcher:
            result = await fetcher.fetch(url)
    """

    def __init__(self, pool_config: PoolConfig | None = None):
        self.pool_config = pool_config or PoolConfig()
        self._pool: PlaywrightPool | None = None

    @property
    def is_available(self) -> bool:
        """Check if Playwright is available."""
        return PLAYWRIGHT_AVAILABLE

    async def start(self):
        """Start the browser pool."""
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available, fetcher will return errors")
            return

        self._pool = PlaywrightPool(self.pool_config)
        await self._pool.start()

    async def stop(self):
        """Stop the browser pool."""
        if self._pool:
            await self._pool.stop()
            self._pool = None

    async def fetch(
        self,
        url: str,
        options: FetchOptions | None = None,
    ) -> FetchResult:
        """
        Fetch a URL using the browser pool.

        Args:
            url: The URL to fetch
            options: Fetch options

        Returns:
            FetchResult compatible with standard fetcher
        """
        return await fetch_with_playwright(url, pool=self._pool, options=options)

    async def get_stats(self) -> dict:
        """Get pool statistics."""
        if self._pool:
            return await self._pool.get_stats()
        return {"available": PLAYWRIGHT_AVAILABLE, "started": False}

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()


# Convenience functions for common use cases

async def fetch_spa_page(
    url: str,
    wait_for: str | None = None,
    scroll: bool = False,
) -> FetchResult:
    """
    Convenience function for fetching SPA pages.

    Args:
        url: The URL to fetch
        wait_for: Optional CSS selector to wait for
        scroll: Whether to scroll to load lazy content

    Returns:
        FetchResult with rendered content
    """
    options = FetchOptions(
        wait_for_selector=wait_for,
        wait_for_network_idle=True,
        scroll_to_bottom=scroll,
    )
    return await fetch_with_playwright(url, options=options)


async def fetch_portfolio_page(url: str) -> FetchResult:
    """
    Fetch a portfolio page, optimized for common portfolio layouts.

    Handles infinite scroll and lazy-loaded images/cards.
    """
    options = FetchOptions(
        wait_for_network_idle=True,
        scroll_to_bottom=True,
        max_scrolls=5,
        scroll_pause_ms=800,
    )
    return await fetch_with_playwright(url, options=options)


async def fetch_team_page(url: str) -> FetchResult:
    """
    Fetch a team page, optimized for team member listings.

    May include scroll for large teams.
    """
    options = FetchOptions(
        wait_for_network_idle=True,
        scroll_to_bottom=True,
        max_scrolls=3,
        scroll_pause_ms=500,
    )
    return await fetch_with_playwright(url, options=options)
