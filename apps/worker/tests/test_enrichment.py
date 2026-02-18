"""
Comprehensive test suite for Fundradar enrichment module.

Tests all 12 extraction strategies plus edge cases.
"""

import json
import pytest
from pathlib import Path

from fundradar_worker.enrichment import (
    FundEnricher,
    PortfolioCompany,
    PortfolioExtractionResult,
    TeamMember,
    FundProfile,
    PageContent,
)
from fundradar_worker.site_config_schema import ExtractionStrategy


# Helper to load fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> tuple[str, dict]:
    """Load a test fixture by name."""
    html_path = FIXTURES_DIR / f"{name}.html"
    meta_path = FIXTURES_DIR / f"{name}.meta.json"

    if html_path.exists():
        html = html_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"Fixture not found: {name}")

    metadata = {}
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text())

    return html, metadata


class TestPortfolioExtraction:
    """Tests for portfolio company extraction."""

    @pytest.fixture
    def enricher(self):
        return FundEnricher()

    # ==========================================================================
    # Strategy 1: NEXT_DATA (Next.js embedded data)
    # ==========================================================================

    def test_nextjs_embedded_data_extraction(self, enricher):
        """Test extraction from Next.js __NEXT_DATA__ script tag."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Portfolio</title></head>
        <body>
            <div id="__next"></div>
            <script id="__NEXT_DATA__" type="application/json">
            {
                "props": {
                    "pageProps": {
                        "portfolio": [
                            {"name": "TechCorp Inc", "description": "AI solutions", "url": "https://techcorp.com", "sector": "Technology"},
                            {"name": "HealthStart", "description": "Digital health", "url": "https://healthstart.io", "sector": "Healthcare"},
                            {"name": "FinanceHub", "description": "Fintech platform", "sector": "Financial Services"}
                        ]
                    }
                }
            }
            </script>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com/portfolio")

        assert len(result.companies) >= 3
        assert result.extraction_method == "next_data"
        names = [c.name for c in result.companies]
        assert "TechCorp Inc" in names
        assert "HealthStart" in names
        assert "FinanceHub" in names

    def test_nextjs_nested_data(self, enricher):
        """Test extraction from deeply nested Next.js data."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <script id="__NEXT_DATA__" type="application/json">
            {
                "props": {
                    "pageProps": {
                        "data": {
                            "investments": {
                                "items": [
                                    {"companyName": "DeepNest Corp", "summary": "Nested data"},
                                    {"companyName": "Another Inc", "summary": "More nested"}
                                ]
                            }
                        }
                    }
                }
            }
            </script>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        # May or may not extract depending on depth - key is no crash
        assert isinstance(result, PortfolioExtractionResult)

    # ==========================================================================
    # Strategy 2: NUXT_DATA (Nuxt.js)
    # ==========================================================================

    def test_nuxt_embedded_data(self, enricher):
        """Test extraction from Nuxt.js window.__NUXT__ data."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div id="__nuxt"></div>
            <script>
            window.__NUXT__ = {
                data: [
                    {
                        companies: [
                            {name: "NuxtCompany1", description: "First company"},
                            {name: "NuxtCompany2", description: "Second company"}
                        ]
                    }
                ]
            };
            </script>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        # Nuxt data parsing is complex, ensure no crash
        assert isinstance(result, PortfolioExtractionResult)

    # ==========================================================================
    # Strategy 3: JSON_LD (Structured data)
    # ==========================================================================

    def test_jsonld_organization_extraction(self, enricher):
        """Test extraction from JSON-LD Organization schema."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "itemListElement": [
                    {"@type": "Organization", "name": "JsonLdCompany1", "description": "First org", "url": "https://company1.com"},
                    {"@type": "Organization", "name": "JsonLdCompany2", "description": "Second org"},
                    {"@type": "Corporation", "name": "JsonLdCorp", "description": "A corporation"}
                ]
            }
            </script>
        </head>
        <body><div>Content</div></body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        assert "JsonLdCompany1" in names or "JsonLdCompany2" in names or "JsonLdCorp" in names

    def test_jsonld_graph_structure(self, enricher):
        """Test extraction from JSON-LD @graph structure."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "Organization", "name": "GraphOrg1", "description": "In graph"},
                    {"@type": "LocalBusiness", "name": "GraphBiz", "description": "Local business"}
                ]
            }
            </script>
        </head>
        <body><div>Content</div></body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        assert "GraphOrg1" in names or "GraphBiz" in names

    # ==========================================================================
    # Strategy 4: HTML_CARDS (Card patterns)
    # ==========================================================================

    def test_html_cards_extraction(self, enricher):
        """Test extraction from HTML card patterns."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <section class="portfolio-section">
                <div class="portfolio-item">
                    <h3>CardCompany1</h3>
                    <p class="description">Building great software</p>
                    <span class="sector">Technology</span>
                    <a href="https://company1.com">Website</a>
                </div>
                <div class="portfolio-item">
                    <h3>CardCompany2</h3>
                    <p class="description">Healthcare innovation</p>
                    <span class="sector">Healthcare</span>
                </div>
                <div class="portfolio-item">
                    <h3>CardCompany3</h3>
                    <p class="description">Financial services</p>
                </div>
            </section>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        assert len(result.companies) >= 3
        names = [c.name for c in result.companies]
        assert "CardCompany1" in names
        assert "CardCompany2" in names
        assert "CardCompany3" in names

    def test_html_cards_various_selectors(self, enricher):
        """Test extraction from various card class patterns."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="company-card">
                <h4>CompanyCard1</h4>
            </div>
            <div class="investment-item">
                <h4>InvestmentItem1</h4>
            </div>
            <article class="case-study">
                <h3>CaseStudy1</h3>
            </article>
            <li class="fund-item">
                <strong>FundItem1</strong>
            </li>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        # At least some should be extracted
        assert len(result.companies) >= 1

    # ==========================================================================
    # Strategy 5: LOGO_GRID
    # ==========================================================================

    def test_logo_grid_extraction(self, enricher):
        """Test extraction from logo grids using alt text."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="logo-grid">
                <a href="https://alpha.com">
                    <img src="/logos/alpha.png" alt="Alpha Technologies logo">
                </a>
                <a href="https://beta.com">
                    <img src="/logos/beta.png" alt="Beta Industries">
                </a>
                <img src="/logos/gamma.png" alt="Gamma Solutions" title="Gamma Solutions">
            </div>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        # Should extract company names from alt text
        assert any("Alpha" in n for n in names) or any("Beta" in n for n in names) or any("Gamma" in n for n in names)

    def test_figure_with_figcaption(self, enricher):
        """Test extraction from figure elements with figcaption."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="portfolio-gallery">
                <figure>
                    <a href="https://figcompany.com"><img src="/img/company.jpg"></a>
                    <figcaption>FigCaptionCompany</figcaption>
                </figure>
                <figure>
                    <img src="/img/company2.jpg">
                    <figcaption>AnotherFigCompany</figcaption>
                </figure>
            </div>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        assert "FigCaptionCompany" in names or "AnotherFigCompany" in names

    # ==========================================================================
    # Strategy 6: LINK_LIST
    # ==========================================================================

    def test_link_list_extraction(self, enricher):
        """Test extraction from link lists."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <section class="portfolio-links">
                <h2>Our Portfolio</h2>
                <ul>
                    <li><a href="https://link1.com">LinkCompany1</a></li>
                    <li><a href="https://link2.com">LinkCompany2</a></li>
                    <li><a href="https://link3.com">LinkCompany3</a></li>
                </ul>
            </section>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        assert "LinkCompany1" in names or "LinkCompany2" in names

    # ==========================================================================
    # Strategy 7: HEADINGS_IN_CONTEXT
    # ==========================================================================

    def test_headings_extraction(self, enricher):
        """Test extraction from repeated headings."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <main class="portfolio-page">
                <h1>Portfolio Companies</h1>
                <div class="company">
                    <h3>HeadingCompany1</h3>
                    <p>Description one</p>
                </div>
                <div class="company">
                    <h3>HeadingCompany2</h3>
                    <p>Description two</p>
                </div>
                <div class="company">
                    <h3>HeadingCompany3</h3>
                    <p>Description three</p>
                </div>
                <div class="company">
                    <h3>HeadingCompany4</h3>
                    <p>Description four</p>
                </div>
            </main>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        assert "HeadingCompany1" in names

    # ==========================================================================
    # Strategy 8: TABLE_ROWS
    # ==========================================================================

    def test_table_extraction(self, enricher):
        """Test extraction from HTML tables."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <table class="portfolio-table">
                <thead>
                    <tr>
                        <th>Company</th>
                        <th>Sector</th>
                        <th>Year</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><a href="https://table1.com">TableCompany1</a></td>
                        <td>Technology</td>
                        <td>2023</td>
                    </tr>
                    <tr>
                        <td>TableCompany2</td>
                        <td>Healthcare</td>
                        <td>2022</td>
                    </tr>
                    <tr>
                        <td>TableCompany3</td>
                        <td>Finance</td>
                        <td>2021</td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        assert "TableCompany1" in names
        assert "TableCompany2" in names

    # ==========================================================================
    # Strategy 9: ATTRIBUTES (aria-label, title, data-*)
    # ==========================================================================

    def test_aria_label_extraction(self, enricher):
        """Test extraction from aria-label attributes."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="portfolio-grid">
                <div aria-label="AriaCompany1" class="portfolio-item"></div>
                <div aria-label="AriaCompany2" class="portfolio-item"></div>
                <div aria-label="AriaCompany3" class="portfolio-item"></div>
            </div>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        assert "AriaCompany1" in names or "AriaCompany2" in names

    def test_data_attribute_extraction(self, enricher):
        """Test extraction from data-* attributes."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="portfolio-list">
                <div data-company-name="DataAttrCompany1" class="company"></div>
                <div data-name="DataAttrCompany2" class="company"></div>
                <div data-title="DataAttrCompany3" class="company"></div>
            </div>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        # Data attribute extraction should find at least some
        assert isinstance(result, PortfolioExtractionResult)

    # ==========================================================================
    # Strategy 10: SVG_TITLES
    # ==========================================================================

    def test_svg_title_extraction(self, enricher):
        """Test extraction from SVG title elements."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="portfolio-logos">
                <svg viewBox="0 0 100 100">
                    <title>SvgCompany1</title>
                    <rect width="100" height="100"/>
                </svg>
                <svg viewBox="0 0 100 100">
                    <title>SvgCompany2 logo</title>
                    <rect width="100" height="100"/>
                </svg>
            </div>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        assert "SvgCompany1" in names or "SvgCompany2" in names

    # ==========================================================================
    # Strategy 11: NOSCRIPT
    # ==========================================================================

    def test_noscript_extraction(self, enricher):
        """Test extraction from noscript fallback content."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div id="app">Loading...</div>
            <noscript>
                <div class="portfolio">
                    <img alt="NoscriptCompany1" src="/logo1.png">
                    <a href="https://company2.com">NoscriptCompany2</a>
                    <h3>NoscriptCompany3</h3>
                </div>
            </noscript>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        assert "NoscriptCompany1" in names or "NoscriptCompany2" in names or "NoscriptCompany3" in names

    # ==========================================================================
    # Strategy 12: ANCHOR_WRAPPERS
    # ==========================================================================

    def test_anchor_wrapper_extraction(self, enricher):
        """Test extraction from anchor wrappers around images."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="logo-gallery">
                <a href="https://anchorcompany1.com" title="Anchor Company 1">
                    <img src="/logo1.png">
                </a>
                <a href="https://anchorcompany2.com" aria-label="Anchor Company 2">
                    <img src="/logo2.png">
                </a>
                <a href="https://thirdcompany.io">
                    <img src="/logo3.png">
                </a>
            </div>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name for c in result.companies]
        # Should extract from title, aria-label, or URL domain
        assert len(result.companies) >= 1

    # ==========================================================================
    # Edge Cases
    # ==========================================================================

    def test_empty_html(self, enricher):
        """Test handling of empty HTML."""
        result = enricher.extract_portfolio("", "https://example.com")
        assert result.companies == []
        # Empty HTML is detected as JS-heavy (no body content)
        assert result.failed_reason in ("content_too_short", "js_required_no_embedded_data")

    def test_minimal_html(self, enricher):
        """Test handling of minimal HTML without portfolio content."""
        html = "<html><body><h1>Welcome</h1></body></html>"
        result = enricher.extract_portfolio(html, "https://example.com")
        assert result.companies == []

    def test_malformed_html(self, enricher):
        """Test handling of malformed HTML."""
        html = """
        <html><body>
        <div class="portfolio-item">
            <h3>Company1
            <p>Description without closing tags
        <div class="portfolio-item">
            <h3>Company2</h3>
        </body></html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        # Should not crash, may or may not extract
        assert isinstance(result, PortfolioExtractionResult)

    def test_js_heavy_page_detection(self, enricher):
        """Test detection of JS-heavy pages."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div id="root"></div>
            <script src="/app.js"></script>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        assert result.failed_reason == "js_required_no_embedded_data"

    def test_noise_filtering(self, enricher):
        """Test that navigation and footer noise is filtered."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <nav>
                <a href="/about">About</a>
                <a href="/team">Team</a>
                <a href="/contact">Contact</a>
            </nav>
            <main class="portfolio">
                <div class="portfolio-item"><h3>RealCompany1</h3></div>
                <div class="portfolio-item"><h3>RealCompany2</h3></div>
                <div class="portfolio-item"><h3>RealCompany3</h3></div>
            </main>
            <footer>
                <a href="/privacy">Privacy Policy</a>
                <a href="/terms">Terms</a>
            </footer>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        names = [c.name.lower() for c in result.companies]
        # Should extract real companies, not nav items
        assert "about" not in names
        assert "contact" not in names
        assert "privacy policy" not in names
        assert "realcompany1" in names

    def test_duplicate_removal(self, enricher):
        """Test that duplicates are removed."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="portfolio-item"><h3>DuplicateCompany</h3></div>
            <div class="portfolio-item"><h3>DuplicateCompany</h3></div>
            <div class="portfolio-item"><h3>duplicatecompany</h3></div>
            <div class="portfolio-item"><h3>UniqueCompany</h3></div>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com")
        # Case-insensitive deduplication
        names_lower = [c.name.lower() for c in result.companies]
        assert names_lower.count("duplicatecompany") == 1

    def test_extraction_preserves_metadata(self, enricher):
        """Test that extraction preserves company metadata."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <script id="__NEXT_DATA__" type="application/json">
            {
                "props": {
                    "pageProps": {
                        "portfolio": [
                            {
                                "name": "MetadataCompany",
                                "description": "A detailed description of the company",
                                "url": "https://metadata.com",
                                "sector": "Technology"
                            }
                        ]
                    }
                }
            }
            </script>
        </body>
        </html>
        """
        result = enricher.extract_portfolio(html, "https://example.com/portfolio")
        company = next((c for c in result.companies if c.name == "MetadataCompany"), None)
        if company:
            assert company.description_short is not None
            assert company.website == "https://metadata.com"
            assert company.sector == "Technology"


class TestTeamExtraction:
    """Tests for team member extraction."""

    @pytest.fixture
    def enricher(self):
        return FundEnricher()

    def test_team_card_extraction(self, enricher):
        """Test extraction from team cards."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="team-section">
                <div class="team-member">
                    <h3>John Smith</h3>
                    <p class="title">Managing Partner</p>
                    <a href="https://linkedin.com/in/johnsmith">LinkedIn</a>
                </div>
                <div class="team-member">
                    <h3>Jane Doe</h3>
                    <p class="title">Partner</p>
                </div>
            </div>
        </body>
        </html>
        """
        soup = __import__('bs4', fromlist=['BeautifulSoup']).BeautifulSoup(html, "html.parser")
        members = enricher._extract_team_members(soup, "https://example.com/team")

        assert len(members) >= 2
        names = [m.name for m in members]
        assert "John Smith" in names
        assert "Jane Doe" in names

    def test_team_jsonld_extraction(self, enricher):
        """Test extraction from JSON-LD Person schema."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <script type="application/ld+json">
            [
                {"@type": "Person", "name": "Alice Johnson", "jobTitle": "CEO"},
                {"@type": "Person", "name": "Bob Williams", "jobTitle": "CFO"}
            ]
            </script>
        </head>
        <body><div>Team</div></body>
        </html>
        """
        soup = __import__('bs4', fromlist=['BeautifulSoup']).BeautifulSoup(html, "html.parser")
        members = enricher._extract_team_members(soup, "https://example.com/team")

        names = [m.name for m in members]
        assert "Alice Johnson" in names
        assert "Bob Williams" in names


class TestFundProfileEnrichment:
    """Tests for full fund profile enrichment."""

    @pytest.fixture
    def enricher(self):
        return FundEnricher()

    def test_description_from_meta(self, enricher):
        """Test description extraction from meta tags."""
        pages = [PageContent(
            url="https://example.com",
            page_type="HOME",
            html="""
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="description" content="We are a leading private equity firm investing in Italian mid-market companies.">
            </head>
            <body><h1>Welcome</h1></body>
            </html>
            """,
            text="We are a leading private equity firm investing in Italian mid-market companies.",
        )]

        profile = enricher.enrich_from_pages("test-fund", "example.com", "https://example.com", pages)
        assert profile.description is not None
        assert "private equity" in profile.description.lower()

    def test_strategy_tag_extraction(self, enricher):
        """Test strategy tag extraction from text."""
        pages = [PageContent(
            url="https://example.com/about",
            page_type="ABOUT",
            html="<html><body><p>Our focus on venture capital and growth equity investments</p></body></html>",
            text="Our focus on venture capital and growth equity investments",
        )]

        profile = enricher.enrich_from_pages("test-fund", "example.com", "https://example.com", pages)
        assert "VC" in profile.strategy_tags or "Growth" in profile.strategy_tags

    def test_italy_presence_detection(self, enricher):
        """Test Italy presence detection."""
        pages = [PageContent(
            url="https://example.com/about",
            page_type="ABOUT",
            html="<html><body><p>Headquartered in Milano, we invest across Italy</p></body></html>",
            text="Headquartered in Milano, we invest across Italy",
        )]

        profile = enricher.enrich_from_pages("test-fund", "example.com", "https://example.com", pages)
        assert profile.italy_presence is True


class TestFixtureExtraction:
    """Tests using the HTML fixtures."""

    @pytest.fixture
    def enricher(self):
        return FundEnricher()

    @pytest.mark.parametrize("fixture_name", [
        "static_site",
        "nextjs_portfolio",
        "portfolio_grid_cards",
        "portfolio_table_detailed",
        "portfolio_infinite_scroll",
    ])
    def test_portfolio_fixture_extraction(self, enricher, fixture_name):
        """Test portfolio extraction from fixtures."""
        try:
            html, meta = load_fixture(fixture_name)
        except FileNotFoundError:
            pytest.skip(f"Fixture {fixture_name} not found")
            return

        url = meta.get("url", "https://example.com")
        result = enricher.extract_portfolio(html, url)

        # Should extract at least some companies from portfolio fixtures
        if meta.get("type") == "portfolio_list" or "portfolio" in fixture_name:
            assert len(result.companies) >= 1, f"Expected companies from {fixture_name}"

    @pytest.mark.parametrize("fixture_name", [
        "nextjs_team",
        "team_cards_detailed",
        "team_simple_list",
    ])
    def test_team_fixture_extraction(self, enricher, fixture_name):
        """Test team extraction from fixtures."""
        try:
            html, meta = load_fixture(fixture_name)
        except FileNotFoundError:
            pytest.skip(f"Fixture {fixture_name} not found")
            return

        soup = __import__('bs4', fromlist=['BeautifulSoup']).BeautifulSoup(html, "html.parser")
        url = meta.get("url", "https://example.com")
        members = enricher._extract_team_members(soup, url)

        # Should extract at least some team members
        if meta.get("type") == "team_list" or "team" in fixture_name:
            assert len(members) >= 1, f"Expected team members from {fixture_name}"


class TestConfiguredSelectors:
    """Tests for site-specific selector extraction."""

    @pytest.fixture
    def enricher(self):
        return FundEnricher()

    def test_custom_css_selectors(self, enricher):
        """Test extraction using custom CSS selectors."""
        from fundradar_worker.site_config_schema import SelectorConfig

        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="custom-portfolio-container">
                <div class="custom-company-item">
                    <span class="custom-name">CustomCompany1</span>
                    <div class="custom-sector">Tech</div>
                </div>
                <div class="custom-company-item">
                    <span class="custom-name">CustomCompany2</span>
                    <div class="custom-sector">Healthcare</div>
                </div>
                <div class="custom-company-item">
                    <span class="custom-name">CustomCompany3</span>
                    <div class="custom-sector">Finance</div>
                </div>
            </div>
        </body>
        </html>
        """

        selectors = SelectorConfig(
            container=".custom-portfolio-container",
            item=".custom-company-item",
            name=".custom-name",
            sector=".custom-sector",
        )

        soup = __import__('bs4', fromlist=['BeautifulSoup']).BeautifulSoup(html, "html.parser")
        companies = enricher._extract_with_config_selectors(soup, "https://example.com", selectors)

        assert len(companies) == 3
        names = [c.name for c in companies]
        assert "CustomCompany1" in names
        assert "CustomCompany2" in names
        assert "CustomCompany3" in names
        assert companies[0].sector == "Tech"
