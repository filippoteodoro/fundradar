"""
Tests for Playwright fetcher module.

These tests use fixtures and mocks to run without network access,
making them suitable for CI environments.
"""

import gzip
import json
import os
import shutil
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Skip tests that require actual browser binaries (not available in CI)
requires_browser = pytest.mark.skipif(
    os.environ.get("CI") == "true" or not shutil.which("chromium") and not shutil.which("google-chrome") and not Path.home().joinpath(".cache/ms-playwright").exists(),
    reason="Playwright browsers not installed"
)

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    """Load a test fixture by name."""
    from collections import namedtuple
    FixtureData = namedtuple("FixtureData", ["html", "metadata", "name"])

    # Try compressed first, then uncompressed
    html_gz_path = FIXTURES_DIR / f"{name}.html.gz"
    html_path = FIXTURES_DIR / f"{name}.html"
    meta_path = FIXTURES_DIR / f"{name}.meta.json"

    if html_gz_path.exists():
        with gzip.open(html_gz_path, "rt", encoding="utf-8") as f:
            html = f.read()
    elif html_path.exists():
        html = html_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"Fixture HTML not found: {name}")

    if meta_path.exists():
        metadata = json.loads(meta_path.read_text())
    else:
        metadata = {}

    return FixtureData(html=html, metadata=metadata, name=name)


# Import modules under test
from fundradar_worker.playwright_pool import (
    PlaywrightPool,
    PoolConfig,
    PLAYWRIGHT_AVAILABLE,
)
from fundradar_worker.playwright_fetcher import (
    FetchOptions,
    CONSENT_SELECTORS,
)
from fundradar_worker.domain_policies import (
    detect_requires_headless,
    HeadlessDetectionResult,
)
from fundradar_worker.fetcher import FetchResult


class TestHeadlessDetection:
    """Tests for detect_requires_headless function."""

    def test_detect_static_html(self):
        """Static HTML should not require headless."""
        fixture = load_fixture("static_site")
        result = detect_requires_headless(fixture.html)

        assert not result.requires_headless
        assert result.confidence < 0.5
        assert result.framework_detected is None

    def test_detect_nextjs_prerendered(self):
        """Next.js with pre-rendered content should not require headless."""
        fixture = load_fixture("nextjs_portfolio")
        result = detect_requires_headless(fixture.html)

        # Should detect Next.js but not require headless since content is pre-rendered
        assert result.framework_detected == "next.js"
        # Content is sufficient, so shouldn't require headless
        assert result.confidence < 0.7  # May detect framework but content is there

    def test_detect_spa_requires_headless(self):
        """SPA with minimal content should require headless."""
        fixture = load_fixture("custom_spa")
        result = detect_requires_headless(fixture.html)

        assert result.requires_headless
        assert result.confidence >= 0.5
        assert "Minimal" in " ".join(result.reasons) or "text content" in " ".join(result.reasons).lower()

    def test_detect_wordpress_static(self):
        """WordPress pages should not require headless."""
        fixture = load_fixture("wordpress_news")
        result = detect_requires_headless(fixture.html)

        assert not result.requires_headless
        # WordPress indicator should reduce confidence
        assert "Static HTML" in " ".join(result.reasons) or result.confidence < 0.5

    def test_detect_empty_html(self):
        """Empty or very short HTML should require headless."""
        result = detect_requires_headless("<html><body></body></html>")

        assert result.requires_headless
        assert result.confidence >= 0.9
        assert "too short" in " ".join(result.reasons).lower()

    def test_detect_react_empty_root(self):
        """React app with empty root div should be detected."""
        html = '''
        <!DOCTYPE html>
        <html>
        <head><title>React App</title></head>
        <body>
            <div id="root"></div>
            <script src="/bundle.js"></script>
        </body>
        </html>
        '''
        result = detect_requires_headless(html)

        assert result.requires_headless
        assert result.framework_detected == "react"

    def test_detect_vue_app(self):
        """Vue app markers should be detected."""
        html = '''
        <!DOCTYPE html>
        <html>
        <head><title>Vue App</title></head>
        <body>
            <div id="app" v-cloak></div>
            <script src="/app.js"></script>
        </body>
        </html>
        '''
        result = detect_requires_headless(html)

        assert result.requires_headless
        assert result.framework_detected == "vue"

    def test_detect_angular_app(self):
        """Angular app markers should be detected."""
        html = '''
        <!DOCTYPE html>
        <html>
        <head><title>Angular App</title></head>
        <body>
            <app-root>Loading...</app-root>
        </body>
        </html>
        '''
        result = detect_requires_headless(html)

        assert result.requires_headless
        assert result.framework_detected == "angular"


class TestFetchOptions:
    """Tests for FetchOptions configuration."""

    def test_default_options(self):
        """Default options should have sensible values."""
        options = FetchOptions()

        assert options.wait_for_timeout == 5000
        assert options.dismiss_consent is True
        assert options.scroll_to_bottom is False
        assert options.max_scrolls == 10

    def test_portfolio_options(self):
        """Portfolio page options should enable scrolling."""
        options = FetchOptions(
            scroll_to_bottom=True,
            max_scrolls=5,
            scroll_pause_ms=800,
        )

        assert options.scroll_to_bottom is True
        assert options.max_scrolls == 5
        assert options.scroll_pause_ms == 800

    def test_custom_wait_selector(self):
        """Custom wait selector should be configurable."""
        options = FetchOptions(
            wait_for_selector=".portfolio-grid",
            wait_for_timeout=10000,
        )

        assert options.wait_for_selector == ".portfolio-grid"
        assert options.wait_for_timeout == 10000


class TestConsentSelectors:
    """Tests for consent modal selectors."""

    def test_consent_selectors_exist(self):
        """Consent selectors list should have entries."""
        assert len(CONSENT_SELECTORS) > 0

    def test_italian_consent_selectors(self):
        """Should include Italian consent button patterns."""
        italian_patterns = [s for s in CONSENT_SELECTORS if "Accett" in s]
        assert len(italian_patterns) > 0

    def test_common_consent_managers(self):
        """Should include common consent manager selectors."""
        # OneTrust
        onetrust = [s for s in CONSENT_SELECTORS if "onetrust" in s.lower()]
        assert len(onetrust) > 0

        # CookieBot
        cookiebot = [s for s in CONSENT_SELECTORS if "cookiebot" in s.lower()]
        assert len(cookiebot) > 0


class TestPoolConfig:
    """Tests for browser pool configuration."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = PoolConfig()

        assert config.max_browsers == 2
        assert config.max_contexts_per_browser == 5
        assert config.headless is True
        assert config.max_context_lifetime_seconds == 300.0

    def test_custom_config(self):
        """Custom config should override defaults."""
        config = PoolConfig(
            max_browsers=1,
            max_contexts_per_browser=3,
            headless=False,
        )

        assert config.max_browsers == 1
        assert config.max_contexts_per_browser == 3
        assert config.headless is False

    def test_stealth_settings(self):
        """Stealth settings should be present."""
        config = PoolConfig()

        assert "Chrome" in config.user_agent
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080
        assert "Rome" in config.timezone


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestPlaywrightPool:
    """Tests for PlaywrightPool (requires Playwright installed)."""

    @pytest.mark.asyncio
    async def test_pool_availability(self):
        """Pool should report availability correctly."""
        pool = PlaywrightPool()
        assert pool.is_available is True

    @requires_browser
    @pytest.mark.asyncio
    async def test_pool_start_stop(self):
        """Pool should start and stop cleanly."""
        pool = PlaywrightPool(PoolConfig(max_browsers=1))

        await pool.start()
        assert pool._started is True

        stats = await pool.get_stats()
        assert stats["started"] is True
        assert stats["browsers"] == 1

        await pool.stop()
        assert pool._started is False

    @requires_browser
    @pytest.mark.asyncio
    async def test_pool_context_manager(self):
        """Pool should work as async context manager."""
        async with PlaywrightPool(PoolConfig(max_browsers=1)) as pool:
            assert pool._started is True
            stats = await pool.get_stats()
            assert stats["browsers"] >= 1

        # After exiting, should be stopped
        assert pool._started is False


class TestFetchResultCompatibility:
    """Tests for FetchResult compatibility with existing fetcher."""

    def test_fetch_result_fields(self):
        """FetchResult should have all required fields."""
        result = FetchResult(
            url="https://example.com",
            status_code=200,
            html="<html></html>",
            text="",
            title="Test",
            content_hash="abc123",
        )

        assert result.url == "https://example.com"
        assert result.status_code == 200
        assert result.html == "<html></html>"
        assert result.title == "Test"
        assert result.content_hash == "abc123"
        assert result.error is None

    def test_fetch_result_error(self):
        """FetchResult should handle errors correctly."""
        result = FetchResult(
            url="https://example.com",
            status_code=0,
            html="",
            text="",
            title=None,
            content_hash="",
            error="Connection refused",
        )

        assert result.status_code == 0
        assert result.error == "Connection refused"


class TestFixtureLoading:
    """Tests for fixture loading infrastructure."""

    def test_load_static_fixture(self):
        """Should load static site fixture."""
        fixture = load_fixture("static_site")

        assert fixture.name == "static_site"
        assert len(fixture.html) > 0
        assert "TechItalia" in fixture.html
        assert fixture.metadata["type"] == "static"

    def test_load_nextjs_fixture(self):
        """Should load Next.js fixture."""
        fixture = load_fixture("nextjs_portfolio")

        assert fixture.name == "nextjs_portfolio"
        assert "__NEXT_DATA__" in fixture.html
        assert fixture.metadata["type"] == "nextjs"

    def test_load_wordpress_fixture(self):
        """Should load WordPress fixture."""
        fixture = load_fixture("wordpress_news")

        assert "wp-content" in fixture.html
        assert fixture.metadata["type"] == "wordpress"

    def test_load_spa_fixture(self):
        """Should load SPA fixture."""
        fixture = load_fixture("custom_spa")

        assert fixture.metadata["requires_headless"] is True

    def test_fixture_metadata(self):
        """Fixture metadata should contain expected fields."""
        fixture = load_fixture("static_site")
        meta = fixture.metadata

        assert "url" in meta
        assert "type" in meta
        assert "expected_extractions" in meta
        assert "requires_headless" in meta

    def test_nonexistent_fixture(self):
        """Loading nonexistent fixture should raise error."""
        with pytest.raises(FileNotFoundError):
            load_fixture("nonexistent_fixture")
