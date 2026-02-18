"""
Structured enrichment for fund profiles and portfolio companies.

Extracts fund metadata, team information, and portfolio company data
from monitored pages.
"""

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse, urljoin, parse_qs, urlencode

from bs4 import BeautifulSoup

from .normalizer import ContentNormalizer
from .relevance import ItalyRelevanceScorer
from .site_config_schema import SiteConfig, ExtractionStrategy


@dataclass
class TeamMember:
    """A team member extracted from a fund website."""
    name: str
    role: str | None = None
    title: str | None = None
    email: str | None = None
    linkedin: str | None = None
    source_url: str | None = None


@dataclass
class PortfolioCompany:
    """A portfolio company extracted from a fund website."""
    name: str
    description_short: str | None = None
    country: str | None = None
    website: str | None = None
    sector: str | None = None
    tags: list[str] = field(default_factory=list)
    source_url: str | None = None
    investment_date: str | None = None
    status: str | None = None  # 'current', 'exited', 'unknown'


@dataclass
class PortfolioExtractionResult:
    """Result of portfolio extraction with failure tracking."""
    companies: list[PortfolioCompany]
    extraction_method: str | None = None  # 'jsonld', 'embedded_data', 'html_cards', 'logo_grid', etc.
    failed_reason: str | None = None  # 'js_required_no_embedded_data', 'blocked', 'parse_error', etc.
    pages_fetched: int = 1


@dataclass
class FundProfile:
    """Enriched fund profile data."""
    fund_slug: str
    domain: str
    website: str
    description: str | None = None
    description_source: str | None = None
    strategy_tags: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    hq_city: str | None = None
    hq_country: str | None = None
    italy_presence: bool = False
    italy_presence_evidence: str | None = None
    team_count: int | None = None
    team_summary: list[TeamMember] = field(default_factory=list)
    portfolio_count: int | None = None
    portfolio_extraction_failed_reason: str | None = None
    last_enriched_at: str = ""

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        # Convert TeamMember list to dicts
        d["team_summary"] = [asdict(m) for m in self.team_summary]
        return d


PageType = Literal["HOME", "TEAM", "PORTFOLIO", "ABOUT", "NEWS", "CAREERS", "OTHER"]


@dataclass
class PageContent:
    """Content from a fetched page for enrichment."""
    url: str
    page_type: PageType
    html: str
    text: str
    title: str | None = None


class FundEnricher:
    """
    Extracts structured data from fund websites.

    Combines information from multiple page types (home, team, portfolio, about)
    to build a comprehensive fund profile.
    """

    # Strategy keywords for classification
    STRATEGY_KEYWORDS = {
        "PE": ["private equity", "buyout", "leveraged", "lbo"],
        "VC": ["venture capital", "venture", "seed", "startup", "early stage", "early-stage"],
        "Growth": ["growth equity", "growth capital", "expansion"],
        "Infra": ["infrastructure", "infra"],
        "Real Estate": ["real estate", "property", "reit"],
        "Credit": ["credit", "debt", "lending", "mezzanine"],
        "Secondaries": ["secondary", "secondaries"],
        "Fund of Funds": ["fund of funds", "fof"],
    }

    # Sector keywords
    SECTOR_KEYWORDS = {
        "Technology": ["technology", "tech", "software", "digital", "saas", "fintech"],
        "Healthcare": ["healthcare", "health", "pharma", "biotech", "medical", "life sciences"],
        "Consumer": ["consumer", "retail", "food", "beverage", "fmcg"],
        "Industrial": ["industrial", "manufacturing", "engineering"],
        "Energy": ["energy", "renewable", "clean energy", "power"],
        "Financial Services": ["financial services", "banking", "insurance", "finserv"],
        "TMT": ["media", "telecom", "telecommunications"],
        "Business Services": ["business services", "services"],
    }

    # Italy-specific indicators
    ITALY_INDICATORS = [
        "italy", "italia", "italian", "italiano", "italiana",
        "milano", "milan", "roma", "rome", "torino", "turin",
        "bologna", "firenze", "florence", "napoli", "naples",
        "venezia", "venice", "genova", "genoa", "padova", "verona",
        "headquartered in italy", "based in italy",
        "italian market", "italian companies", "italian portfolio",
        "lombardia", "lombardy", "veneto", "piemonte", "piedmont",
        "toscana", "tuscany", "lazio", "emilia-romagna",
        "s.p.a.", "spa", "s.r.l.", "srl", "s.a.s.",
    ]

    # Description stop phrases (content to skip)
    DESCRIPTION_STOP_PHRASES = [
        "cookie", "cookies", "privacy policy", "terms of service",
        "accept all", "reject all", "manage preferences",
        "subscribe to", "newsletter", "sign up for",
        "copyright", "all rights reserved",
        "login", "sign in", "register",
        "contact us", "get in touch",
    ]

    def __init__(self, site_config_loader=None):
        self.normalizer = ContentNormalizer()
        self.relevance_scorer = ItalyRelevanceScorer()
        self._site_config_loader = site_config_loader

    def enrich_from_pages(
        self,
        fund_slug: str,
        domain: str,
        website: str,
        pages: list[PageContent],
    ) -> FundProfile:
        """
        Extract a fund profile from multiple page types.
        """
        profile = FundProfile(
            fund_slug=fund_slug,
            domain=domain,
            website=website,
            last_enriched_at=datetime.now(timezone.utc).isoformat(),
        )

        # Process pages in priority order for description
        home_page = None
        about_page = None

        for page in pages:
            if page.page_type == "HOME":
                home_page = page
            elif page.page_type == "ABOUT":
                about_page = page
            elif page.page_type == "TEAM":
                self._enrich_from_team(profile, page)

        # Try to extract description in priority order
        # 1. First try meta tags from any page
        for page in pages:
            if not profile.description:
                self._extract_description_from_meta(profile, page)

        # 2. Try JSON-LD from any page
        for page in pages:
            if not profile.description:
                self._extract_description_from_jsonld(profile, page)

        # 3. Try ABOUT page content
        if not profile.description and about_page:
            self._extract_description_from_content(profile, about_page, "about_page")

        # 4. Try HOME page hero/intro
        if not profile.description and home_page:
            self._extract_description_from_content(profile, home_page, "home_page")

        # Extract strategy/sectors from all pages
        for page in pages:
            self._extract_strategy_sectors(profile, page.text)

        # Determine Italy presence from all available text
        combined_text = " ".join(p.text for p in pages if p.text)
        self._determine_italy_presence(profile, combined_text)

        return profile

    def _extract_description_from_meta(self, profile: FundProfile, page: PageContent):
        """Extract description from HTML meta tags."""
        soup = BeautifulSoup(page.html, "html.parser")

        # Priority order of meta tags
        meta_selectors = [
            ("meta", {"name": "description"}),
            ("meta", {"property": "og:description"}),
            ("meta", {"name": "twitter:description"}),
            ("meta", {"property": "description"}),
        ]

        for tag, attrs in meta_selectors:
            meta = soup.find(tag, attrs=attrs)
            if meta and meta.get("content"):
                desc = meta.get("content", "").strip()
                if self._is_valid_description(desc):
                    profile.description = self._clean_description(desc)
                    profile.description_source = f"meta_{attrs.get('name') or attrs.get('property')}"
                    return

    def _extract_description_from_jsonld(self, profile: FundProfile, page: PageContent):
        """Extract description from JSON-LD structured data."""
        soup = BeautifulSoup(page.html, "html.parser")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string) if script.string else None
                if not data:
                    continue

                # Handle @graph structure
                if isinstance(data, dict) and "@graph" in data:
                    data = data["@graph"]

                # Normalize to list
                items = data if isinstance(data, list) else [data]

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    item_type = item.get("@type", "")
                    if item_type in ["Organization", "Corporation", "FinancialService", "LocalBusiness", "WebSite"]:
                        desc = item.get("description", "")
                        if desc and self._is_valid_description(desc):
                            profile.description = self._clean_description(desc)
                            profile.description_source = f"jsonld_{item_type}"
                            return

            except (json.JSONDecodeError, TypeError):
                continue

    def _extract_description_from_content(self, profile: FundProfile, page: PageContent, source: str):
        """Extract description from page content (paragraphs)."""
        soup = BeautifulSoup(page.html, "html.parser")

        # Remove noise elements first
        for selector in ["nav", "footer", "header", "aside", "[class*='cookie']", "[class*='banner']"]:
            for el in soup.select(selector):
                el.decompose()

        # Find main content area
        main = soup.find("main") or soup.find("article") or soup.find("[role='main']")
        if not main:
            # Try to find by common class names
            for selector in [".content", ".main-content", "#content", "#main"]:
                main = soup.select_one(selector)
                if main:
                    break
        if not main:
            main = soup.find("body") or soup

        # Look for hero/intro section first
        hero_selectors = [
            "[class*='hero']", "[class*='intro']", "[class*='banner']",
            "[class*='headline']", "[class*='tagline']", "[class*='about-us']",
        ]
        for selector in hero_selectors:
            for el in main.select(selector):
                text = el.get_text(separator=" ", strip=True)
                if self._is_valid_description(text, min_length=80):
                    profile.description = self._clean_description(text)
                    profile.description_source = f"{source}_hero"
                    return

        # Fall back to first substantial paragraphs
        paragraphs = []
        for p in main.find_all("p"):
            text = p.get_text(strip=True)
            if self._is_valid_description(text, min_length=80):
                paragraphs.append(text)
                if len(" ".join(paragraphs)) > 200:
                    break

        if paragraphs:
            combined = " ".join(paragraphs)
            profile.description = self._clean_description(combined)
            profile.description_source = f"{source}_paragraph"

    def _is_valid_description(self, text: str, min_length: int = 50) -> bool:
        """Check if text is a valid description (not boilerplate)."""
        if not text or len(text) < min_length:
            return False

        text_lower = text.lower()

        # Skip if contains stop phrases
        for phrase in self.DESCRIPTION_STOP_PHRASES:
            if phrase in text_lower:
                return False

        # Skip if too short after cleaning
        words = text.split()
        if len(words) < 8:
            return False

        return True

    def _clean_description(self, text: str, max_length: int = 500) -> str:
        """Clean and truncate description."""
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Truncate at sentence boundary if possible
        if len(text) > max_length:
            # Try to cut at sentence end
            truncated = text[:max_length]
            last_period = truncated.rfind(".")
            last_exclaim = truncated.rfind("!")
            last_question = truncated.rfind("?")
            cut_point = max(last_period, last_exclaim, last_question)

            if cut_point > max_length * 0.6:
                text = truncated[:cut_point + 1]
            else:
                text = truncated.rsplit(" ", 1)[0] + "..."

        return text

    def _enrich_from_team(self, profile: FundProfile, page: PageContent):
        """Extract team information from team page."""
        soup = BeautifulSoup(page.html, "html.parser")

        team_members = self._extract_team_members(soup, page.url)
        if team_members:
            profile.team_summary = team_members[:20]
            profile.team_count = len(team_members)

    def _extract_strategy_sectors(self, profile: FundProfile, text: str):
        """Extract strategy tags and sectors from text."""
        text_lower = text.lower()

        for strategy, keywords in self.STRATEGY_KEYWORDS.items():
            if strategy not in profile.strategy_tags:
                for kw in keywords:
                    if kw in text_lower:
                        profile.strategy_tags.append(strategy)
                        break

        for sector, keywords in self.SECTOR_KEYWORDS.items():
            if sector not in profile.sectors:
                for kw in keywords:
                    if kw in text_lower:
                        profile.sectors.append(sector)
                        break

    def _determine_italy_presence(self, profile: FundProfile, text: str):
        """Determine Italy presence from text."""
        # Use relevance scorer
        italy_result = self.relevance_scorer.score(text, "OTHER")

        if italy_result.italy_relevant:
            profile.italy_presence = True
            profile.italy_presence_evidence = ", ".join(italy_result.relevance_reasons[:3])
        else:
            # Check for explicit Italy mentions with lower threshold
            text_lower = text.lower()
            for indicator in self.ITALY_INDICATORS:
                if indicator in text_lower:
                    profile.italy_presence = True
                    profile.italy_presence_evidence = f"Contains '{indicator}'"
                    break

    def _extract_team_members(self, soup: BeautifulSoup, source_url: str) -> list[TeamMember]:
        """Extract team members from a team page."""
        members = []
        seen_names = set()

        # Strategy 1: JSON-LD Person data
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string) if script.string else None
                if not data:
                    continue

                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "Person":
                        name = item.get("name", "")
                        if name and name not in seen_names:
                            seen_names.add(name)
                            members.append(TeamMember(
                                name=name,
                                role=item.get("jobTitle"),
                                source_url=source_url,
                            ))
            except (json.JSONDecodeError, TypeError):
                pass

        # Strategy 2: Team card patterns
        card_selectors = [
            "[class*='team-member']", "[class*='person-card']",
            "[class*='member-card']", "[class*='staff-card']",
            "[class*='profile-card']", ".team-item", ".member", ".person",
        ]

        for selector in card_selectors:
            try:
                for card in soup.select(selector):
                    member = self._extract_member_from_card(card, source_url)
                    if member and member.name not in seen_names:
                        seen_names.add(member.name)
                        members.append(member)
            except Exception:
                pass

        # Strategy 3: h3/h4 with names
        if len(members) < 5:
            for heading in soup.find_all(["h3", "h4"]):
                text = heading.get_text(strip=True)
                if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$", text):
                    if text not in seen_names:
                        role = None
                        next_el = heading.find_next_sibling()
                        if next_el:
                            role_text = next_el.get_text(strip=True)
                            if len(role_text) < 100:
                                role = role_text

                        seen_names.add(text)
                        members.append(TeamMember(name=text, role=role, source_url=source_url))

        return members

    def _extract_member_from_card(self, card, source_url: str) -> TeamMember | None:
        """Extract a team member from a card-like element."""
        name = None
        role = None
        linkedin = None

        name_el = card.find(["h2", "h3", "h4", "h5", "strong", "[class*='name']"])
        if name_el:
            name = name_el.get_text(strip=True)
        else:
            link = card.find("a")
            if link:
                name = link.get_text(strip=True)

        if not name or len(name) < 3:
            return None

        name = re.sub(r"^(Dr\.?|Mr\.?|Ms\.?|Mrs\.?|Prof\.?)\s*", "", name)
        name = re.sub(r",?\s*(MBA|PhD|CFA|CPA|MD|JD|Esq\.?).*$", "", name)

        role_el = card.find(["[class*='title']", "[class*='role']", "[class*='position']", "p", "span"])
        if role_el and role_el != name_el:
            role = role_el.get_text(strip=True)
            if len(role) > 100:
                role = None

        for link in card.find_all("a", href=True):
            href = link.get("href", "")
            if "linkedin.com" in href:
                linkedin = href
                break

        return TeamMember(name=name, role=role, linkedin=linkedin, source_url=source_url)

    def extract_portfolio(
        self,
        html: str,
        url: str,
        fund_slug: str | None = None,
        site_config: SiteConfig | None = None,
    ) -> PortfolioExtractionResult:
        """
        Extract portfolio companies from a portfolio page.

        Enhanced with embedded data extraction for JS-heavy sites.
        If a site_config is provided, uses configured selectors and strategy order.

        Args:
            html: The HTML content to extract from
            url: The source URL
            fund_slug: Optional fund identifier
            site_config: Optional site-specific extraction configuration
        """
        soup = BeautifulSoup(html, "html.parser")
        companies = []
        seen_names = set()
        extraction_method = None

        # Try to get site config if not provided
        if not site_config and self._site_config_loader:
            site_config = self._site_config_loader.get_config(url)

        # If we have a site config with portfolio selectors, try them first
        if site_config and site_config.portfolio.selectors.container:
            config_companies = self._extract_with_config_selectors(
                soup, url, site_config.portfolio.selectors
            )
            if config_companies:
                for c in config_companies:
                    if c.name.lower() not in seen_names:
                        seen_names.add(c.name.lower())
                        companies.append(c)
                extraction_method = "site_config_selectors"

        # Use configured strategy order if available, otherwise use defaults
        strategies_to_try = []
        if site_config and site_config.portfolio.strategies:
            strategies_to_try = site_config.portfolio.strategies
        else:
            # Default strategy order
            strategies_to_try = [
                ExtractionStrategy.NEXT_DATA,
                ExtractionStrategy.NUXT_DATA,
                ExtractionStrategy.JSON_LD,
                ExtractionStrategy.HTML_CARDS,
                ExtractionStrategy.LOGO_GRID,
                ExtractionStrategy.LINK_LIST,
                ExtractionStrategy.HEADINGS_IN_CONTEXT,
                ExtractionStrategy.TABLE_ROWS,
                ExtractionStrategy.ATTRIBUTES,
                ExtractionStrategy.SVG_TITLES,
                ExtractionStrategy.NOSCRIPT,
                ExtractionStrategy.ANCHOR_WRAPPERS,
            ]

        # Run strategies in order until we have enough companies
        for strategy in strategies_to_try:
            if len(companies) >= 3:
                break

            strategy_companies = self._run_strategy(strategy, soup, url)
            for c in strategy_companies:
                if c.name.lower() not in seen_names:
                    seen_names.add(c.name.lower())
                    companies.append(c)
            if strategy_companies and not extraction_method:
                extraction_method = strategy.value

        # Filter and dedupe
        companies = self._filter_valid_companies(companies)

        # Determine failure reason if not enough companies
        failed_reason = None
        if len(companies) < 3:
            if self._is_js_heavy_page(soup):
                failed_reason = "js_required_no_embedded_data"
            elif len(html) < 1000:
                failed_reason = "content_too_short"
            else:
                failed_reason = "parse_error_insufficient_data"

        return PortfolioExtractionResult(
            companies=companies,
            extraction_method=extraction_method,
            failed_reason=failed_reason if len(companies) < 3 else None,
        )

    def _run_strategy(
        self,
        strategy: ExtractionStrategy,
        soup: BeautifulSoup,
        url: str,
    ) -> list[PortfolioCompany]:
        """Run a single extraction strategy and return results."""
        try:
            if strategy == ExtractionStrategy.NEXT_DATA:
                return self._extract_from_embedded_data(soup, url)
            elif strategy == ExtractionStrategy.NUXT_DATA:
                return self._extract_from_embedded_data(soup, url)  # Same method handles both
            elif strategy == ExtractionStrategy.JSON_LD:
                return self._extract_from_jsonld(soup, url)
            elif strategy == ExtractionStrategy.HTML_CARDS:
                return self._extract_from_cards(soup, url)
            elif strategy == ExtractionStrategy.LOGO_GRID:
                return self._extract_from_logo_grid(soup, url)
            elif strategy == ExtractionStrategy.LINK_LIST:
                return self._extract_from_links(soup, url)
            elif strategy == ExtractionStrategy.HEADINGS_IN_CONTEXT:
                return self._extract_from_headings(soup, url)
            elif strategy == ExtractionStrategy.TABLE_ROWS:
                return self._extract_from_tables(soup, url)
            elif strategy == ExtractionStrategy.ATTRIBUTES:
                return self._extract_from_attributes(soup, url)
            elif strategy == ExtractionStrategy.SVG_TITLES:
                return self._extract_from_svg_titles(soup, url)
            elif strategy == ExtractionStrategy.NOSCRIPT:
                return self._extract_from_noscript(soup, url)
            elif strategy == ExtractionStrategy.ANCHOR_WRAPPERS:
                return self._extract_from_anchor_wrappers(soup, url)
            else:
                return []
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"Strategy {strategy} failed: {e}")
            return []

    def _extract_with_config_selectors(
        self,
        soup: BeautifulSoup,
        url: str,
        selectors,  # SelectorConfig
    ) -> list[PortfolioCompany]:
        """Extract companies using site-specific CSS selectors."""
        companies = []

        if not selectors.container or not selectors.item:
            return companies

        try:
            # Find the container
            container = soup.select_one(selectors.container)
            if not container:
                return companies

            # Find items within container
            items = container.select(selectors.item)

            for item in items:
                name = None
                description = None
                sector = None
                website = None
                status = None

                # Extract name
                if selectors.name:
                    name_el = item.select_one(selectors.name)
                    if name_el:
                        name = name_el.get_text(strip=True)

                if not name:
                    # Fallback: try common name patterns
                    for fallback in ["h3", "h2", "h4", ".name", ".title"]:
                        el = item.select_one(fallback)
                        if el:
                            name = el.get_text(strip=True)
                            break

                if not name or len(name) < 2:
                    continue

                # Extract other fields
                if selectors.description:
                    desc_el = item.select_one(selectors.description)
                    if desc_el:
                        description = desc_el.get_text(strip=True)[:500]

                if selectors.sector:
                    sector_el = item.select_one(selectors.sector)
                    if sector_el:
                        sector = sector_el.get_text(strip=True)

                if selectors.website:
                    website_el = item.select_one(selectors.website)
                    if website_el:
                        website = website_el.get("href")

                if selectors.status:
                    status_el = item.select_one(selectors.status)
                    if status_el:
                        status = status_el.get_text(strip=True).lower()
                        if "exit" in status:
                            status = "exited"
                        elif "current" in status or "active" in status:
                            status = "current"
                        else:
                            status = "unknown"

                companies.append(PortfolioCompany(
                    name=name,
                    description_short=description,
                    sector=sector,
                    website=website,
                    status=status,
                    source_url=url,
                ))

        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"Config selector extraction failed: {e}")

        return companies

    def _extract_from_embedded_data(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract portfolio from embedded JS data structures."""
        companies = []

        for script in soup.find_all("script"):
            script_text = script.string or ""
            if not script_text:
                continue

            # Try __NEXT_DATA__ (Next.js)
            if script.get("id") == "__NEXT_DATA__":
                try:
                    data = json.loads(script_text)
                    companies.extend(self._extract_companies_from_nextjs(data, url))
                except (json.JSONDecodeError, TypeError):
                    pass
                continue

            # Try __NUXT__ (Nuxt.js)
            nuxt_match = re.search(r"window\.__NUXT__\s*=\s*(\{.+?\});?\s*(?:</script>|$)", script_text, re.DOTALL)
            if nuxt_match:
                try:
                    # Nuxt often uses JS object syntax, try to parse
                    data = self._parse_js_object(nuxt_match.group(1))
                    if data:
                        companies.extend(self._extract_companies_from_generic_data(data, url))
                except Exception:
                    pass
                continue

            # Try __INITIAL_STATE__ or similar
            state_patterns = [
                r"window\.__INITIAL_STATE__\s*=\s*(\{.+?\});",
                r"window\.__PRELOADED_STATE__\s*=\s*(\{.+?\});",
                r"window\.initialData\s*=\s*(\{.+?\});",
                r"var\s+initialData\s*=\s*(\{.+?\});",
            ]
            for pattern in state_patterns:
                match = re.search(pattern, script_text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        companies.extend(self._extract_companies_from_generic_data(data, url))
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Try inline JSON arrays that look like portfolio data
            json_array_pattern = r'\[\s*\{\s*"(?:name|title|company)"[^]]+\}\s*\]'
            for match in re.finditer(json_array_pattern, script_text):
                try:
                    data = json.loads(match.group())
                    companies.extend(self._extract_companies_from_generic_data(data, url))
                except (json.JSONDecodeError, TypeError):
                    pass

        return companies

    def _extract_companies_from_nextjs(self, data: dict, url: str) -> list[PortfolioCompany]:
        """Extract companies from Next.js __NEXT_DATA__ structure."""
        companies = []

        def search_props(obj, depth=0):
            if depth > 10:
                return
            if isinstance(obj, dict):
                # Look for portfolio-like keys
                for key in ["portfolio", "companies", "investments", "cases", "caseStudies", "projects"]:
                    if key in obj:
                        items = obj[key]
                        if isinstance(items, list):
                            for item in items:
                                company = self._item_to_company(item, url)
                                if company:
                                    companies.append(company)

                # Recurse into nested objects
                for v in obj.values():
                    search_props(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    search_props(item, depth + 1)

        search_props(data.get("props", {}))
        return companies

    def _extract_companies_from_generic_data(self, data, url: str) -> list[PortfolioCompany]:
        """Extract companies from generic JSON data structures."""
        companies = []

        def search(obj, depth=0):
            if depth > 10:
                return
            if isinstance(obj, dict):
                # Check if this looks like a company
                company = self._item_to_company(obj, url)
                if company:
                    companies.append(company)
                    return

                # Look for portfolio-like keys
                for key in ["portfolio", "companies", "investments", "items", "data", "results", "nodes"]:
                    if key in obj and isinstance(obj[key], list):
                        for item in obj[key]:
                            c = self._item_to_company(item, url)
                            if c:
                                companies.append(c)

                for v in obj.values():
                    search(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    search(item, depth + 1)

        search(data)
        return companies

    def _item_to_company(self, item, url: str) -> PortfolioCompany | None:
        """Convert a dict item to a PortfolioCompany if it looks like one."""
        if not isinstance(item, dict):
            return None

        # Try common name fields
        name = None
        for key in ["name", "title", "companyName", "company_name", "company", "label"]:
            if key in item and isinstance(item[key], str):
                name = item[key].strip()
                break

        if not name or len(name) < 2 or len(name) > 100:
            return None

        # Skip obvious non-companies
        skip_patterns = ["page", "menu", "nav", "footer", "header", "button", "link"]
        if any(p in name.lower() for p in skip_patterns):
            return None

        description = None
        for key in ["description", "summary", "excerpt", "shortDescription", "short_description"]:
            if key in item and isinstance(item[key], str):
                description = item[key][:500]
                break

        website = None
        for key in ["url", "website", "link", "href", "externalUrl"]:
            if key in item and isinstance(item[key], str):
                if item[key].startswith("http"):
                    website = item[key]
                    break

        sector = None
        for key in ["sector", "industry", "category", "type"]:
            if key in item and isinstance(item[key], str):
                sector = item[key]
                break

        return PortfolioCompany(
            name=name,
            description_short=description,
            website=website,
            sector=sector,
            source_url=url,
        )

    def _parse_js_object(self, js_text: str) -> dict | None:
        """Attempt to parse a JS object literal as JSON."""
        try:
            # Simple cleanup: add quotes to unquoted keys
            # This is a simplified approach and won't work for all cases
            cleaned = re.sub(r"(\w+):", r'"\1":', js_text)
            cleaned = re.sub(r"'", '"', cleaned)
            return json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            return None

    def _extract_from_jsonld(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract companies from JSON-LD structured data."""
        companies = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string) if script.string else None
                if not data:
                    continue

                # Handle @graph
                if isinstance(data, dict) and "@graph" in data:
                    data = data["@graph"]

                items = data if isinstance(data, list) else [data]

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    item_type = item.get("@type", "")
                    if item_type in ["Organization", "Corporation", "LocalBusiness", "Product"]:
                        name = item.get("name", "")
                        if name and len(name) >= 2:
                            companies.append(PortfolioCompany(
                                name=name,
                                description_short=item.get("description", "")[:500] if item.get("description") else None,
                                website=item.get("url"),
                                source_url=url,
                            ))

                    # Check for ItemList
                    if item_type == "ItemList" and "itemListElement" in item:
                        for el in item["itemListElement"]:
                            if isinstance(el, dict):
                                name = el.get("name") or el.get("item", {}).get("name")
                                if name:
                                    companies.append(PortfolioCompany(
                                        name=name,
                                        website=el.get("url") or el.get("item", {}).get("url"),
                                        source_url=url,
                                    ))

            except (json.JSONDecodeError, TypeError):
                pass

        return companies

    def _extract_from_cards(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract companies from HTML card patterns."""
        companies = []

        card_selectors = [
            # Portfolio-specific
            "[class*='portfolio-item']", "[class*='portfolio-card']", "[class*='portfolio_item']",
            "[class*='company-card']", "[class*='company-item']", "[class*='company_card']",
            "[class*='investment-card']", "[class*='investment-item']", "[class*='investment_item']",
            "[class*='case-study']", "[class*='casestudy']", "[class*='case_study']",
            "[class*='fund-item']", "[class*='brand-item']", "[class*='brand-card']",
            # Generic item patterns
            ".portfolio-item", ".company", ".investment", ".brand",
            "[class*='grid-item']", "[class*='card-item']",
            # Article patterns (common in Next.js/React)
            "article", "article[class*='portfolio']", "article[class*='company']", "article[class*='card']",
            # Common frameworks
            "[class*='swiper-slide']", "[class*='slick-slide']",
            # List items in portfolio context
            "li[class*='portfolio']", "li[class*='company']", "li[class*='investment']",
            # Data attributes
            "[data-company]", "[data-portfolio]", "[data-investment]",
            # Hashed class names (React/Vue/Angular)
            "[class*='Card_']", "[class*='_card']", "[class*='Item_']", "[class*='_item']",
        ]

        for selector in card_selectors:
            try:
                for card in soup.select(selector):
                    company = self._extract_company_from_card(card, url)
                    if company:
                        companies.append(company)
            except Exception:
                pass

        # Also try generic article/div patterns within portfolio sections
        portfolio_sections = soup.select(
            "section[class*='portfolio'], div[class*='portfolio'], "
            "section[class*='companies'], div[class*='companies'], "
            "section[class*='investments'], div[class*='investments'], "
            "main[class*='portfolio'], #portfolio, #companies, #investments"
        )
        for section in portfolio_sections:
            # Look for uniform children (cards in a grid)
            for tag in ["article", "div", "li"]:
                children = section.find_all(tag, recursive=False)
                if 3 <= len(children) <= 200:
                    for child in children:
                        company = self._extract_company_from_card(child, url)
                        if company:
                            companies.append(company)

        return companies

    def _extract_company_from_card(self, card, source_url: str) -> PortfolioCompany | None:
        """Extract company from a card-like element."""
        name = None
        description = None
        website = None
        sector = None

        # Find name - prioritize headings, then elements with name-like classes
        name_selectors = ["h2", "h3", "h4", "h5", "strong"]
        for sel in name_selectors:
            name_el = card.find(sel)
            if name_el:
                name = name_el.get_text(strip=True)
                if name and len(name) >= 2:
                    break

        # Try class-based selectors (handle hashed class names like 'CompanyName__abc123')
        if not name or len(name) < 2:
            for el in card.find_all(class_=True):
                class_str = " ".join(el.get("class", []))
                if re.search(r"(name|title|heading)", class_str, re.I):
                    text = el.get_text(strip=True)
                    if text and 2 <= len(text) <= 100:
                        name = text
                        break

        # Try link text
        if not name or len(name) < 2:
            link = card.find("a")
            if link:
                name = link.get_text(strip=True)

        if not name or len(name) < 2:
            return None

        # Skip if name is too generic
        if name.lower() in ["read more", "learn more", "view", "details", "more"]:
            return None

        # Find description - look for p or description-like classes
        desc_selectors = ["p"]
        for sel in desc_selectors:
            desc_el = card.find(sel)
            if desc_el and desc_el != (card.find("h2") or card.find("h3") or card.find("h4")):
                text = desc_el.get_text(strip=True)
                if text and len(text) > 10:
                    description = text[:500]
                    break

        if not description:
            for el in card.find_all(class_=True):
                class_str = " ".join(el.get("class", []))
                if re.search(r"(desc|summary|excerpt|content)", class_str, re.I):
                    text = el.get_text(strip=True)
                    if text and 10 < len(text) <= 500:
                        description = text[:500]
                        break

        # Find website
        for link in card.find_all("a", href=True):
            href = link.get("href", "")
            if href.startswith("http"):
                if urlparse(source_url).netloc not in href:
                    website = href
                    break

        # Find sector - look for tag/sector elements
        for el in card.find_all(class_=True):
            class_str = " ".join(el.get("class", []))
            if re.search(r"(sector|industry|tag|category)", class_str, re.I):
                text = el.get_text(strip=True)
                if text and len(text) < 50:
                    sector = text
                    break

        return PortfolioCompany(
            name=name,
            description_short=description,
            website=website,
            sector=sector,
            source_url=source_url,
        )

    def _extract_from_logo_grid(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract companies from logo grids."""
        companies = []

        # Look for logo containers
        logo_containers = soup.select(
            "[class*='logo'], [class*='partner'], [class*='client'], "
            "[class*='brand'], [class*='gallery'], [class*='grid']"
        )

        for container in logo_containers:
            for img in container.find_all("img", alt=True):
                alt = img.get("alt", "").strip()
                if alt and len(alt) > 2 and len(alt) < 100:
                    if not re.match(r"^(logo|image|icon|picture|photo|placeholder|banner|bg|background)$", alt, re.I):
                        name = re.sub(r"\s*(logo|icon|image)\s*$", "", alt, flags=re.I).strip()
                        if name and len(name) > 2:
                            parent = img.parent
                            website = None
                            if parent and parent.name == "a":
                                href = parent.get("href", "")
                                if href.startswith("http") and urlparse(url).netloc not in href:
                                    website = href

                            companies.append(PortfolioCompany(
                                name=name,
                                website=website,
                                source_url=url,
                            ))

        # Look for figure elements with figcaption
        for figure in soup.find_all("figure"):
            caption = figure.find("figcaption")
            if caption:
                name = caption.get_text(strip=True)
                if name and 2 < len(name) < 100:
                    link = figure.find("a", href=True)
                    website = link.get("href") if link and link.get("href", "").startswith("http") else None
                    companies.append(PortfolioCompany(name=name, website=website, source_url=url))

        # Also check standalone img tags
        for img in soup.find_all("img", alt=True):
            alt = img.get("alt", "").strip()
            if alt and len(alt) > 2 and len(alt) < 100:
                if not re.match(r"^(logo|image|icon|picture|photo|placeholder|banner|bg|background)$", alt, re.I):
                    # Check if in portfolio context
                    parent = img.find_parent(class_=re.compile(r"portfolio|company|investment|brand", re.I))
                    if parent:
                        name = re.sub(r"\s*(logo|icon|image)\s*$", "", alt, flags=re.I).strip()
                        if name:
                            companies.append(PortfolioCompany(name=name, source_url=url))

        # Look for title attributes on images
        for img in soup.find_all("img", title=True):
            title = img.get("title", "").strip()
            if title and 2 < len(title) < 100:
                parent = img.find_parent(class_=re.compile(r"portfolio|company|investment|brand", re.I))
                if parent:
                    name = re.sub(r"\s*(logo|icon|image)\s*$", "", title, flags=re.I).strip()
                    if name:
                        companies.append(PortfolioCompany(name=name, source_url=url))

        return companies

    def _extract_from_links(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract companies from link lists."""
        companies = []

        # Find portfolio sections
        portfolio_sections = soup.select(
            "[class*='portfolio'], [class*='companies'], [class*='investments'], "
            "[class*='brand'], [id*='portfolio'], [id*='companies'], [id*='investments'], "
            "section:has(h1:contains('portfolio')), section:has(h2:contains('portfolio')), "
            "main, article"
        )

        for section in portfolio_sections:
            for link in section.find_all("a", href=True):
                name = link.get_text(strip=True)
                if name and len(name) > 2 and len(name) < 100:
                    href = link.get("href", "")
                    website = href if href.startswith("http") else None

                    # Skip navigation-like links
                    if any(x in name.lower() for x in ["read more", "learn more", "view", "contact", "email", "linkedin", "twitter"]):
                        continue

                    companies.append(PortfolioCompany(
                        name=name,
                        website=website,
                        source_url=url,
                    ))

        # Also look for heading + list patterns
        for heading in soup.find_all(["h2", "h3", "h4"]):
            heading_text = heading.get_text(strip=True).lower()
            if any(x in heading_text for x in ["portfolio", "investment", "companies", "brand", "case stud"]):
                # Look for adjacent list or div with items
                next_el = heading.find_next_sibling()
                if next_el:
                    for item in next_el.find_all(["li", "a"]):
                        name = item.get_text(strip=True)
                        if name and 2 < len(name) < 100:
                            href = item.get("href", "") if item.name == "a" else None
                            website = href if href and href.startswith("http") else None
                            companies.append(PortfolioCompany(name=name, website=website, source_url=url))

        return companies

    def _extract_from_headings(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract companies from heading patterns (h2/h3/h4 that look like company names)."""
        companies = []

        # Look for headings that look like company names
        # Pattern: multiple consecutive headings at same level in portfolio context
        portfolio_context = soup.select_one(
            "[class*='portfolio'], [class*='companies'], [class*='investments'], "
            "[class*='brand'], main, article, body"
        )
        if not portfolio_context:
            portfolio_context = soup

        # Find repeated heading patterns
        for level in ["h3", "h4", "h5"]:
            headings = portfolio_context.find_all(level)
            if len(headings) >= 3:
                # Check if these look like company names
                potential_companies = []
                for h in headings:
                    name = h.get_text(strip=True)
                    if name and 2 < len(name) < 100:
                        # Skip section headings
                        lower = name.lower()
                        if any(x in lower for x in ["about", "team", "contact", "portfolio", "investment", "our "]):
                            continue
                        # Check for capitalized name pattern
                        if re.match(r'^[A-Z]', name):
                            website = None
                            link = h.find("a", href=True)
                            if link:
                                href = link.get("href", "")
                                if href.startswith("http"):
                                    website = href
                            potential_companies.append(PortfolioCompany(name=name, website=website, source_url=url))

                # If we found enough, add them
                if len(potential_companies) >= 3:
                    companies.extend(potential_companies)
                    break

        return companies

    def _extract_from_tables(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract companies from HTML tables."""
        companies = []

        for table in soup.find_all("table"):
            # Look for tables with company-like headers
            headers = []
            thead = table.find("thead")
            if thead:
                for th in thead.find_all("th"):
                    headers.append(th.get_text(strip=True).lower())

            # Also try first row
            if not headers:
                first_row = table.find("tr")
                if first_row:
                    for cell in first_row.find_all(["th", "td"]):
                        headers.append(cell.get_text(strip=True).lower())

            # Find name column index
            name_idx = -1
            for i, h in enumerate(headers):
                if any(x in h for x in ["name", "company", "investment", "portfolio"]):
                    name_idx = i
                    break

            if name_idx < 0 and headers:
                name_idx = 0  # Default to first column

            # Extract from rows
            for row in table.find_all("tr")[1:]:  # Skip header row
                cells = row.find_all(["td", "th"])
                if cells and name_idx < len(cells):
                    name = cells[name_idx].get_text(strip=True)
                    if name and 2 < len(name) < 100:
                        link = cells[name_idx].find("a", href=True)
                        website = None
                        if link:
                            href = link.get("href", "")
                            if href.startswith("http"):
                                website = href
                        companies.append(PortfolioCompany(name=name, website=website, source_url=url))

        return companies

    def _extract_from_attributes(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract companies from aria-label, title, and data-* attributes in portfolio contexts."""
        companies = []

        # Find portfolio-like sections
        portfolio_sections = soup.select(
            "[class*='portfolio'], [class*='companies'], [class*='investments'], "
            "[class*='brand'], [class*='partner'], [class*='client'], "
            "[id*='portfolio'], [id*='companies'], main, article"
        )

        if not portfolio_sections:
            portfolio_sections = [soup.find("body") or soup]

        for section in portfolio_sections:
            # Extract from aria-label attributes
            for el in section.find_all(attrs={"aria-label": True}):
                label = el.get("aria-label", "").strip()
                if label and 2 < len(label) < 100:
                    # Skip common UI patterns
                    label_lower = label.lower()
                    if any(x in label_lower for x in ["menu", "navigation", "button", "close", "open", "toggle", "expand", "collapse"]):
                        continue
                    companies.append(PortfolioCompany(name=label, source_url=url))

            # Extract from title attributes on links/images in portfolio context
            for el in section.find_all(attrs={"title": True}):
                title = el.get("title", "").strip()
                if title and 2 < len(title) < 100:
                    # Clean company name suffix
                    name = re.sub(r"\s*(logo|icon|image|website|link)\s*$", "", title, flags=re.I).strip()
                    if name and len(name) > 2:
                        companies.append(PortfolioCompany(name=name, source_url=url))

            # Extract from data-* attributes that look like company names
            for el in section.find_all(True):
                for attr, value in el.attrs.items():
                    if not attr.startswith("data-"):
                        continue
                    if not isinstance(value, str):
                        continue
                    if not (2 < len(value) < 100):
                        continue
                    # Skip numeric/json/path values
                    if re.match(r"^[\d\s\-_/]+$", value):
                        continue
                    if value.startswith(("{", "[", "/")):
                        continue
                    # Check if attribute name suggests company data
                    attr_lower = attr.lower()
                    if any(x in attr_lower for x in ["name", "company", "title", "label", "brand"]):
                        companies.append(PortfolioCompany(name=value, source_url=url))

        return companies

    def _extract_from_svg_titles(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract companies from SVG title elements."""
        companies = []

        for svg in soup.find_all("svg"):
            title = svg.find("title")
            if title:
                name = title.get_text(strip=True)
                if name and 2 < len(name) < 100:
                    # Clean company name suffix
                    name = re.sub(r"\s*(logo|icon|svg)\s*$", "", name, flags=re.I).strip()
                    if name and len(name) > 2:
                        # Check if in portfolio context
                        parent = svg.find_parent(class_=re.compile(r"portfolio|company|investment|brand|partner|client", re.I))
                        if parent or len(name) > 5:  # Allow if long enough even without context
                            companies.append(PortfolioCompany(name=name, source_url=url))

        return companies

    def _extract_from_noscript(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract companies from noscript content (fallback content for JS-disabled)."""
        companies = []

        for noscript in soup.find_all("noscript"):
            # Parse the noscript content as HTML
            noscript_html = noscript.decode_contents()
            if not noscript_html or len(noscript_html) < 50:
                continue

            noscript_soup = BeautifulSoup(noscript_html, "html.parser")

            # Look for company patterns in noscript
            # Images with alt
            for img in noscript_soup.find_all("img", alt=True):
                alt = img.get("alt", "").strip()
                if alt and 2 < len(alt) < 100:
                    name = re.sub(r"\s*(logo|icon|image)\s*$", "", alt, flags=re.I).strip()
                    if name:
                        companies.append(PortfolioCompany(name=name, source_url=url))

            # Links with text
            for link in noscript_soup.find_all("a"):
                text = link.get_text(strip=True)
                if text and 2 < len(text) < 100:
                    companies.append(PortfolioCompany(name=text, source_url=url))

            # Headings
            for h in noscript_soup.find_all(["h2", "h3", "h4", "h5"]):
                text = h.get_text(strip=True)
                if text and 2 < len(text) < 100:
                    companies.append(PortfolioCompany(name=text, source_url=url))

        return companies

    def _extract_from_anchor_wrappers(self, soup: BeautifulSoup, url: str) -> list[PortfolioCompany]:
        """Extract companies from anchor wrappers around images (even when images lack alt)."""
        companies = []

        # Find portfolio-like sections with logo grids
        portfolio_sections = soup.select(
            "[class*='logo'], [class*='partner'], [class*='client'], "
            "[class*='brand'], [class*='portfolio'], [class*='companies'], "
            "[class*='grid'], [class*='Gallery']"
        )

        for section in portfolio_sections:
            for link in section.find_all("a", href=True):
                href = link.get("href", "")

                # Check if this is an external company link
                if not href.startswith("http"):
                    continue
                if urlparse(url).netloc in href:
                    continue  # Skip internal links

                # Try to get company name from various sources
                name = None

                # 1. Check link text
                text = link.get_text(strip=True)
                if text and 2 < len(text) < 100:
                    name = text

                # 2. Check title attribute
                if not name:
                    title = link.get("title", "").strip()
                    if title and 2 < len(title) < 100:
                        name = title

                # 3. Check aria-label
                if not name:
                    aria = link.get("aria-label", "").strip()
                    if aria and 2 < len(aria) < 100:
                        name = aria

                # 4. Try to extract from URL
                if not name:
                    try:
                        parsed = urlparse(href)
                        domain = parsed.netloc.replace("www.", "")
                        # Extract company name from domain
                        parts = domain.split(".")
                        if parts and len(parts[0]) > 2:
                            name = parts[0].replace("-", " ").replace("_", " ").title()
                    except Exception:
                        pass

                if name:
                    # Clean name
                    name = re.sub(r"\s*(logo|icon|website|link|visit)\s*$", "", name, flags=re.I).strip()
                    if name and len(name) > 2:
                        companies.append(PortfolioCompany(name=name, website=href, source_url=url))

        return companies

    def _filter_valid_companies(self, companies: list[PortfolioCompany]) -> list[PortfolioCompany]:
        """Filter out invalid or noisy company entries."""
        valid = []
        seen = set()

        # Extended stop words for navigation/footer junk
        stop_words = {
            "about", "about us", "team", "contact", "contact us", "careers",
            "news", "blog", "press", "media", "events",
            "read more", "learn more", "view all", "see all", "load more",
            "next", "previous", "back", "forward", "close", "open",
            "privacy", "privacy policy", "cookie", "cookies", "terms",
            "login", "sign in", "register", "sign up",
            "home", "menu", "nav", "navigation", "footer", "header",
            "linkedin", "twitter", "facebook", "instagram", "youtube",
            "email", "phone", "address", "location",
            "subscribe", "newsletter", "follow us",
            "copyright", "all rights reserved",
            "portfolio", "investments", "companies", "our investments",
            "current investments", "past investments", "exited",
        }

        # Common noise patterns
        noise_patterns = [
            r"^(home|about|contact|team|portfolio|investments|news|careers|login|menu|nav)$",
            r"^(read more|learn more|view all|see all|load more|next|previous)$",
            r"^(our |the |a |an )",  # Starts with article
            r"^\d+$",  # Just numbers
            r"^[^a-zA-Z]+$",  # No letters
            r"^(https?://|www\.)",  # URLs
            r"^\s*$",  # Empty/whitespace
        ]

        for company in companies:
            name = company.name.strip()
            name_lower = name.lower()

            # Skip if too short or too long
            if len(name) < 3 or len(name) > 100:
                continue

            # Skip if in stop words
            if name_lower in stop_words:
                continue

            # Skip if matches noise pattern
            skip = False
            for pattern in noise_patterns:
                if re.match(pattern, name_lower, re.I):
                    skip = True
                    break
            if skip:
                continue

            # Skip duplicates (case-insensitive)
            if name_lower in seen:
                continue
            seen.add(name_lower)

            valid.append(company)

        return valid

    def _is_js_heavy_page(self, soup: BeautifulSoup) -> bool:
        """Check if page appears to be JS-heavy with minimal server-rendered content."""
        body = soup.find("body")
        if not body:
            return True

        # Check text content
        text = body.get_text(strip=True)
        if len(text) < 500:
            return True

        # Check for React/Vue/Angular root elements with no content
        root_selectors = ["#root", "#app", "#__next", "[data-reactroot]", "[ng-app]"]
        for sel in root_selectors:
            root = soup.select_one(sel)
            if root and len(root.get_text(strip=True)) < 100:
                return True

        return False
