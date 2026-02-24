"""
Playwright browser pool manager for Fundradar.

Manages browser lifecycle with configurable concurrency, context reuse,
and memory leak prevention.
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

# Check if Playwright is available
PLAYWRIGHT_AVAILABLE = False
STEALTH_AVAILABLE = False
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning("Playwright not installed. Headless fetching will be unavailable.")
    Browser = None
    BrowserContext = None
    Page = None
    Playwright = None

try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    Stealth = None


@dataclass
class PoolConfig:
    """Configuration for the browser pool."""

    max_browsers: int = 2
    max_contexts_per_browser: int = 5
    max_context_lifetime_seconds: float = 300.0  # 5 minutes
    max_context_pages: int = 50  # Max pages before context refresh
    headless: bool = True
    slow_mo: int = 0  # Milliseconds to slow down operations (for debugging)

    # Stealth settings
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "en-US,it-IT"
    timezone: str = "Europe/Rome"


@dataclass
class ContextInfo:
    """Tracks metadata for a browser context."""

    context: "BrowserContext"
    created_at: float = field(default_factory=time.time)
    page_count: int = 0
    in_use: bool = False

    def is_expired(self, max_lifetime: float, max_pages: int) -> bool:
        """Check if context should be recycled."""
        age = time.time() - self.created_at
        return age > max_lifetime or self.page_count >= max_pages


@dataclass
class BrowserInfo:
    """Tracks metadata for a browser instance."""

    browser: "Browser"
    contexts: list[ContextInfo] = field(default_factory=list)
    in_use: bool = False


class PlaywrightPool:
    """
    Manages a pool of Playwright browser instances with context reuse.

    Usage:
        async with PlaywrightPool() as pool:
            async with pool.get_page() as page:
                await page.goto(url)
                html = await page.content()

    Features:
    - Configurable browser concurrency (1-3 browsers)
    - Context reuse to reduce overhead
    - Automatic cleanup of expired contexts
    - Memory leak prevention via max lifetime/pages
    - Graceful degradation if Playwright not installed
    """

    def __init__(self, config: PoolConfig | None = None):
        self.config = config or PoolConfig()
        self._playwright: "Playwright" | None = None
        self._browsers: list[BrowserInfo] = []
        self._lock = asyncio.Lock()
        self._started = False

        # Override headless from environment
        if os.environ.get("PLAYWRIGHT_HEADLESS", "").lower() == "false":
            self.config.headless = False

    @property
    def is_available(self) -> bool:
        """Check if Playwright is available."""
        return PLAYWRIGHT_AVAILABLE

    async def start(self):
        """Initialize the browser pool."""
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Cannot start pool: Playwright not installed")
            return

        if self._started:
            return

        async with self._lock:
            if self._started:
                return

            logger.info("Starting Playwright pool...")
            self._playwright = await async_playwright().start()

            # Launch initial browser
            browser = await self._launch_browser()
            self._browsers.append(BrowserInfo(browser=browser))

            self._started = True
            logger.info(f"Playwright pool started with 1 browser (max: {self.config.max_browsers})")

    async def stop(self):
        """Shut down the browser pool."""
        if not self._started:
            return

        async with self._lock:
            logger.info("Stopping Playwright pool...")

            # Close all contexts and browsers
            for browser_info in self._browsers:
                for ctx_info in browser_info.contexts:
                    try:
                        await ctx_info.context.close()
                    except Exception as e:
                        logger.debug(f"Error closing context: {e}")

                try:
                    await browser_info.browser.close()
                except Exception as e:
                    logger.debug(f"Error closing browser: {e}")

            self._browsers.clear()

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            self._started = False
            logger.info("Playwright pool stopped")

    async def _launch_browser(self) -> "Browser":
        """Launch a new browser instance with stealth settings."""
        browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
            ],
        )
        return browser

    async def _create_context(self, browser: "Browser") -> "BrowserContext":
        """Create a new browser context with stealth settings."""
        context = await browser.new_context(
            user_agent=self.config.user_agent,
            viewport={"width": self.config.viewport_width, "height": self.config.viewport_height},
            locale=self.config.locale,
            timezone_id=self.config.timezone,
            # Additional stealth settings
            java_script_enabled=True,
            ignore_https_errors=False,
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            },
        )

        # Use playwright-stealth for comprehensive bot evasion (webdriver,
        # chrome.runtime, permissions, plugins, languages, WebGL, etc.)
        if STEALTH_AVAILABLE and Stealth is not None:
            stealth = Stealth()
            await stealth.apply_stealth_async(context)
        else:
            # Fallback: basic stealth scripts
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
            """)

        return context

    async def _get_or_create_context(self) -> tuple[BrowserInfo, ContextInfo]:
        """Get an available context or create a new one."""
        async with self._lock:
            # First, try to find an available context in existing browsers
            for browser_info in self._browsers:
                for ctx_info in browser_info.contexts:
                    if not ctx_info.in_use and not ctx_info.is_expired(
                        self.config.max_context_lifetime_seconds,
                        self.config.max_context_pages,
                    ):
                        ctx_info.in_use = True
                        return browser_info, ctx_info

            # Clean up expired contexts
            for browser_info in self._browsers:
                expired = [
                    ctx for ctx in browser_info.contexts
                    if ctx.is_expired(
                        self.config.max_context_lifetime_seconds,
                        self.config.max_context_pages,
                    ) and not ctx.in_use
                ]
                for ctx_info in expired:
                    try:
                        await ctx_info.context.close()
                    except Exception:
                        pass
                    browser_info.contexts.remove(ctx_info)
                    logger.debug("Cleaned up expired context")

            # Find a browser with capacity for a new context
            for browser_info in self._browsers:
                if len(browser_info.contexts) < self.config.max_contexts_per_browser:
                    context = await self._create_context(browser_info.browser)
                    ctx_info = ContextInfo(context=context, in_use=True)
                    browser_info.contexts.append(ctx_info)
                    logger.debug(f"Created new context (browser has {len(browser_info.contexts)} contexts)")
                    return browser_info, ctx_info

            # Need to launch a new browser
            if len(self._browsers) < self.config.max_browsers:
                browser = await self._launch_browser()
                browser_info = BrowserInfo(browser=browser)
                self._browsers.append(browser_info)

                context = await self._create_context(browser)
                ctx_info = ContextInfo(context=context, in_use=True)
                browser_info.contexts.append(ctx_info)

                logger.info(f"Launched new browser (pool has {len(self._browsers)} browsers)")
                return browser_info, ctx_info

            # Pool at capacity - wait for an available context
            logger.warning("Browser pool at capacity, waiting for available context...")
            # Release lock and wait

        # Retry after short delay (outside lock)
        await asyncio.sleep(0.1)
        return await self._get_or_create_context()

    def _release_context(self, ctx_info: ContextInfo):
        """Mark a context as available for reuse."""
        ctx_info.in_use = False
        ctx_info.page_count += 1

    @asynccontextmanager
    async def get_page(self) -> AsyncGenerator["Page", None]:
        """
        Get a page from the pool for fetching.

        Usage:
            async with pool.get_page() as page:
                await page.goto(url)
                html = await page.content()
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed")

        if not self._started:
            await self.start()

        browser_info, ctx_info = await self._get_or_create_context()
        page = None

        try:
            page = await ctx_info.context.new_page()
            yield page
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            self._release_context(ctx_info)

    async def get_stats(self) -> dict:
        """Get pool statistics for monitoring."""
        async with self._lock:
            browsers = len(self._browsers)
            total_contexts = sum(len(b.contexts) for b in self._browsers)
            in_use_contexts = sum(
                sum(1 for c in b.contexts if c.in_use)
                for b in self._browsers
            )

            return {
                "available": PLAYWRIGHT_AVAILABLE,
                "started": self._started,
                "browsers": browsers,
                "max_browsers": self.config.max_browsers,
                "total_contexts": total_contexts,
                "in_use_contexts": in_use_contexts,
                "max_contexts_per_browser": self.config.max_contexts_per_browser,
            }

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()


# Module-level singleton for shared use
_default_pool: PlaywrightPool | None = None
_pool_lock = asyncio.Lock()


async def get_default_pool(config: PoolConfig | None = None) -> PlaywrightPool:
    """
    Get the default browser pool singleton.

    Creates the pool on first call. Pass config only on first call.
    """
    global _default_pool

    async with _pool_lock:
        if _default_pool is None:
            _default_pool = PlaywrightPool(config)
            await _default_pool.start()
        return _default_pool


async def shutdown_default_pool():
    """Shut down the default browser pool."""
    global _default_pool

    async with _pool_lock:
        if _default_pool:
            await _default_pool.stop()
            _default_pool = None
