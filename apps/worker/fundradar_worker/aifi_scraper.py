"""
AIFI Members Scraper

Scrapes Italian PE/VC fund data from https://www.aifi.it/en/full-members
Two-phase approach:
1. Use Playwright to render AJAX-loaded list and extract member URLs
2. Use requests/BeautifulSoup to scrape individual member detail pages

Output: data/derived/aifi_members.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import requests
from bs4 import BeautifulSoup

from .io_utils import safe_json_write
from .paths import PROJECT_ROOT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
AIFI_BASE_URL = "https://www.aifi.it"
AIFI_MEMBERS_URL = "https://www.aifi.it/en/full-members"
USER_AGENT = "Fundradar/1.0 (https://fundradar.io; research purposes)"
REQUEST_DELAY_SECONDS = 1.0


class AifiMember(TypedDict):
    """Structured data for an AIFI member."""

    name: str
    slug: str
    aifi_url: str
    city: str | None
    address: str | None
    country: str | None
    phone: str | None
    email: str | None
    website: str | None
    contact_name: str | None
    aum_eur: float | None
    num_funds: int | None
    num_portfolio_companies: int | None
    num_executives: int | None
    num_sfdr_article_8: int | None
    investment_min_eur: float | None
    investment_max_eur: float | None
    strategies: list[str]
    sectors: list[str]
    geographies: list[str]
    asset_classes: list[str]
    description: str | None
    scraped_at: str


class AifiMembersOutput(TypedDict):
    """Output file structure."""

    scraped_at: str
    source_url: str
    member_count: int
    members: list[AifiMember]


# Patterns to clean from AIFI member names before generating slugs.
# AIFI registers legal entity names (e.g. "PAI SAS - Italian Branch") but
# we want brand names (e.g. "PAI Partners") for display and slug generation.
_BRANCH_SUFFIX_RE = re.compile(
    r"\s*[-–]\s*(?:Italian\s+Branch|Succursale\s+Italiana|Italian\s+Office|"
    r"Milan\s+Branch|Rome\s+Branch)\s*$",
    re.IGNORECASE,
)
# Parenthesized legal entity info: "(Luxembourg) S.A.", "(Ireland) Limited"
_PAREN_LEGAL_RE = re.compile(
    r"\s*\([^)]*\)\s*(?:S\.?A\.?|Limited|Ltd\.?|GmbH|B\.?V\.?)?\s*$",
    re.IGNORECASE,
)
# Legal entity suffixes that aren't part of the brand name.
# SAS (French), SA (Swiss/French), GmbH (German), LLP/LP (Anglo-Saxon)
_LEGAL_SUFFIX_RE = re.compile(
    r"\s+(?:SAS|SA|GmbH|LLP|LP)\s*$",
    re.IGNORECASE,
)
# Trailing "Italy"/"Italia" that indicates a branch, not brand name
_ITALY_SUFFIX_RE = re.compile(
    r"\s+(?:Italy|Italia)\s*$",
    re.IGNORECASE,
)
# Map of known AIFI names to their correct brand names.
# Add entries here when AIFI uses a legal entity name instead of the brand.
# Key = name AFTER regex cleaning; value = correct brand name.
AIFI_NAME_OVERRIDES: dict[str, str] = {
    "PAI SAS": "PAI Partners",
    "PAI": "PAI Partners",
    "DIF Capital Partners": "CVC DIF",
    "HLD Conseils": "HLD",
    "BU": "BU",  # Not "BU Italy"; brand is just "BU"
    "ARDIAN": "Ardian",
    "Itago SGR": "Itago",  # Brand is "Itago", not "Itago SGR"
    # Fix AIFI legal entity names → brand names (Sprint 2026-02-11)
    "CVC Advisers": "CVC",  # AIFI: "CVC Advisers (Italia)" → paren stripped → "CVC Advisers"
    "Amber Capital Italia SGR": "Amber Capital",  # SGR not stripped by regex, so full string needs override
    "EnTrust Global": "EnTrust Global",  # Already cleaned by _ITALY_SUFFIX_RE; explicit for safety
    "Oxy Capital": "Oxy Capital",  # Already cleaned by _ITALY_SUFFIX_RE; explicit for safety
    "Unigrains": "Unigrains",  # Already cleaned by _ITALY_SUFFIX_RE; explicit for safety
    "Argos Wityu": "Argos Wityu",  # Already cleaned by _ITALY_SUFFIX_RE; explicit for safety
    # Brand name shortening (Sprint 2026-02-12)
    "Apollo Global Management": "Apollo",
    "TowerBrook Capital Partners": "TowerBrook",
    "Three Hills Capital Partners": "Three Hills",
    "BlueGem Capital Partners": "BlueGem",
    "Mindful Capital Partners": "Mindful Capital",
    "Charme Capital Partners SGR": "Charme Capital",
    "EOS Investment Management Group": "EOS IM",
    "Eiffel Investment Group": "Eiffel",
    "Sosteneo Infrastructure Partners": "Sosteneo",
    "Montefiore Investment": "Montefiore",
    "Scientifica Venture Capital": "Scientifica VC",
    "Sienna Private Equity": "Sienna PE",
    # Slug-friendly brand names (Sprint 2026-02-12 slug rename)
    "H.I.G. European Capital Partners Italy": "H.I.G. Capital",
    "AVM SGR Gestore EuVECA Societa Benefit": "AVM",
    "Real Estate Asset Management SGR REAM SGR": "REAM SGR",
    "Real Estate Asset Management SGR": "REAM SGR",
    "Equiter Investimenti per il Territorio": "Equiter",
    "Macquarie MAM": "Macquarie",
    "Eurizon Capital Real Asset SGR": "Eurizon Real Asset",
    "Eurizon Capital Real Asset": "Eurizon Real Asset",
    "Polis SGR": "Polis SGR",
    "Clessidra Private Equity SGR": "Clessidra SGR",
    "Clessidra Private Equity": "Clessidra SGR",
    "CDP Venture Capital SGR": "Cdp Venture Capital",
    "Cdp Venture Capital SGR": "Cdp Venture Capital",
}


def clean_fund_name(raw_name: str) -> tuple[str, str]:
    """Clean an AIFI member name for display and slug generation.

    Returns (display_name, legal_name) where legal_name is the original.

    Cleaning pipeline:
    1. Strip branch suffixes ("- Italian Branch", "- Milan Branch")
    2. Strip parenthesized legal info ("(Luxembourg) S.A.")
    3. Strip foreign legal suffixes (SAS, GmbH, etc.)
    4. Strip trailing "Italy"/"Italia" (branch indicator)
    5. Apply explicit overrides for known brand mismatches
    """
    legal_name = raw_name.strip()
    name = _BRANCH_SUFFIX_RE.sub("", legal_name).strip()
    name = _PAREN_LEGAL_RE.sub("", name).strip()
    name = _LEGAL_SUFFIX_RE.sub("", name).strip()
    name = _ITALY_SUFFIX_RE.sub("", name).strip()
    # Check explicit overrides last (takes priority)
    if name in AIFI_NAME_OVERRIDES:
        name = AIFI_NAME_OVERRIDES[name]
    return name, legal_name


def parse_aum(text: str | None) -> float | None:
    """
    Parse AUM text like "1.5 Bln Euro" or "500 Mln Euro" to float in EUR.

    Examples:
        "1.5 Bln Euro" -> 1_500_000_000
        "500 Mln Euro" -> 500_000_000
        "1,5 Bln Euro" -> 1_500_000_000 (comma decimal)
    """
    if not text:
        return None

    text = text.strip().lower()

    # Extract number and unit
    match = re.search(r"([\d.,]+)\s*(bln|mln|billion|million)", text, re.IGNORECASE)
    if not match:
        return None

    number_str = match.group(1)
    unit = match.group(2).lower()

    # Handle both comma and dot as decimal separator
    # Italian format uses dot as thousands separator and comma as decimal
    # But some entries use dot as decimal
    if "," in number_str and "." in number_str:
        # Format like "1.500,5" - dot is thousands, comma is decimal
        number_str = number_str.replace(".", "").replace(",", ".")
    elif "," in number_str:
        # Format like "1,5" - comma is decimal
        number_str = number_str.replace(",", ".")

    try:
        value = float(number_str)
    except ValueError:
        return None

    multiplier = 1_000_000_000 if unit in ("bln", "billion") else 1_000_000
    return value * multiplier


def parse_investment_amount(text: str | None) -> float | None:
    """
    Parse investment amount like "20.000.000 EUR" or "5,000,000 EUR" to float.

    Handles Italian number format (dots as thousands separators).

    Examples:
        "20.000.000 EUR" -> 20_000_000
        "5.000.000" -> 5_000_000
        "500.000 EUR" -> 500_000
    """
    if not text:
        return None

    text = text.strip()

    # Extract number part
    match = re.search(r"([\d.,]+)", text)
    if not match:
        return None

    number_str = match.group(1)

    # Italian format: dots as thousands separators, comma as decimal
    # Count dots and commas to determine format
    dots = number_str.count(".")
    commas = number_str.count(",")

    if dots > 1 or (dots == 1 and commas == 0 and len(number_str.split(".")[-1]) == 3):
        # Italian format: 20.000.000 or 20.000
        number_str = number_str.replace(".", "")
    elif commas > 1:
        # US format with commas as thousands: 20,000,000
        number_str = number_str.replace(",", "")
    elif commas == 1 and dots == 1:
        # Could be 1.000,50 (Italian) or 1,000.50 (US)
        # Check position of comma vs dot
        dot_pos = number_str.index(".")
        comma_pos = number_str.index(",")
        if dot_pos < comma_pos:
            # Italian: 1.000,50
            number_str = number_str.replace(".", "").replace(",", ".")
        else:
            # US: 1,000.50
            number_str = number_str.replace(",", "")
    elif commas == 1:
        # Single comma - likely decimal separator in Italian
        number_str = number_str.replace(",", ".")

    try:
        return float(number_str)
    except ValueError:
        return None


def parse_int_safely(text: str | None) -> int | None:
    """Parse integer from text, handling Italian number format."""
    if not text:
        return None

    # Remove non-digit characters except for potential decimal separators
    text = text.strip()
    match = re.search(r"(\d+)", text.replace(".", "").replace(",", ""))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return None


def discover_member_urls(debug: bool = False) -> list[str]:
    """
    Use Playwright to render the AJAX-loaded member list and extract profile URLs.

    Args:
        debug: If True, save screenshot and HTML for debugging

    Returns list of full URLs like "https://www.aifi.it/en/associates/21-invest"
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        raise

    logger.info("Starting Playwright to discover member URLs...")
    member_urls: list[str] = []

    # Debug output directory
    debug_dir = PROJECT_ROOT / "data" / "derived"

    with sync_playwright() as p:
        # Use non-headless mode to avoid bot detection
        # Some sites block headless browsers
        browser = p.chromium.launch(
            headless=False,  # Use headed mode to avoid detection
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = context.new_page()

        try:
            logger.info(f"Navigating to {AIFI_MEMBERS_URL}")
            # Use domcontentloaded instead of networkidle (less strict)
            page.goto(AIFI_MEMBERS_URL, wait_until="domcontentloaded", timeout=60000)

            # Wait for page to stabilize and AJAX to load
            logger.info("Waiting for page content to load...")
            page.wait_for_timeout(5000)

            # Save debug info
            if debug:
                screenshot_path = debug_dir / "aifi_debug_screenshot.png"
                html_path = debug_dir / "aifi_debug_page.html"
                page.screenshot(path=str(screenshot_path), full_page=True)
                html_content = page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info(f"Saved debug screenshot to {screenshot_path}")
                logger.info(f"Saved debug HTML to {html_path}")

            # The AIFI page loads members directly in the HTML (no separate URLs)
            # Members are in div.associato elements within #elencoassaderenti
            # Detail pages use JavaScript postbacks, not direct URLs

            # Wait for the member list container to appear
            try:
                page.wait_for_selector("#elencoassaderenti .associato", timeout=10000)
                logger.info("Found member list container")
            except Exception:
                logger.warning("Member list container not found, checking page content...")

            # Get all member cards
            member_cards = page.query_selector_all(".associato")
            logger.info(f"Found {len(member_cards)} member cards on page")

            # Since there are no URLs, we'll return the page content for parsing
            # Store the HTML content path as a special marker
            if member_cards:
                member_urls = ["__PARSE_FROM_HTML__"]  # Special marker

            # Always save the HTML for parsing
            html_content = page.content()
            html_path = debug_dir / "aifi_members_page.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"Saved page HTML to {html_path}")

            # Save debug info if requested
            if debug:
                page.screenshot(path=str(debug_dir / "aifi_debug_screenshot.png"), full_page=True)
                logger.info(f"Saved debug screenshot")

        finally:
            context.close()
            browser.close()

    return sorted(member_urls)


def scrape_members_with_details(limit: int | None = None, debug: bool = False) -> list[AifiMember]:
    """
    Scrape all members by clicking through each detail page.

    This extracts rich data like AUM, number of funds, portfolio companies, etc.
    that is only available on detail pages.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        raise

    members: list[AifiMember] = []
    debug_dir = PROJECT_ROOT / "data" / "derived"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = context.new_page()

        try:
            logger.info(f"Navigating to {AIFI_MEMBERS_URL}")
            page.goto(AIFI_MEMBERS_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            # Wait for member list
            page.wait_for_selector("#elencoassaderenti .associato", timeout=15000)

            # Count members
            member_cards = page.query_selector_all(".associato")
            total_members = len(member_cards)
            logger.info(f"Found {total_members} members to scrape")

            if limit:
                total_members = min(total_members, limit)
                logger.info(f"Limited to {total_members} members")

            # Scrape each member
            for i in range(total_members):
                try:
                    # Re-query the cards (DOM may have changed)
                    member_cards = page.query_selector_all(".associato")
                    if i >= len(member_cards):
                        logger.warning(f"Member card {i} not found, skipping")
                        continue

                    card = member_cards[i]

                    # Get basic info from list card
                    name_elem = card.query_selector("h4")
                    name = name_elem.inner_text() if name_elem else f"Member {i+1}"
                    logger.info(f"[{i+1}/{total_members}] Scraping: {name}")

                    # Click "Go to details"
                    detail_btn = card.query_selector("a.btn")
                    if not detail_btn:
                        logger.warning(f"No detail button for {name}")
                        continue

                    detail_btn.click()

                    # Wait for detail content to load (UpdatePanel)
                    page.wait_for_timeout(2000)

                    # Try to find the detail panel
                    try:
                        page.wait_for_selector(".detail-section, .scheda-dettaglio, #dettaglio", timeout=5000)
                    except Exception:
                        # Detail might be in different structure, continue anyway
                        pass

                    # Extract data from detail page
                    html_content = page.content()
                    member = parse_detail_page(html_content, name, i)

                    if member:
                        members.append(member)

                        # Save debug HTML for first member
                        if debug and i == 0:
                            with open(debug_dir / "aifi_detail_debug.html", "w") as f:
                                f.write(html_content)
                            logger.info("Saved first detail page HTML for debugging")

                    # Go back to list
                    page.go_back()
                    page.wait_for_timeout(2000)

                    # Re-wait for member list
                    try:
                        page.wait_for_selector("#elencoassaderenti .associato", timeout=10000)
                    except Exception:
                        # If back doesn't work, reload the page
                        logger.warning("Back navigation failed, reloading page...")
                        page.goto(AIFI_MEMBERS_URL, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(3000)
                        page.wait_for_selector("#elencoassaderenti .associato", timeout=15000)

                except Exception as e:
                    logger.error(f"Error scraping member {i}: {e}")
                    # Try to recover by reloading the page
                    try:
                        page.goto(AIFI_MEMBERS_URL, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(3000)
                    except Exception:
                        pass
                    continue

        finally:
            context.close()
            browser.close()

    logger.info(f"Successfully scraped {len(members)} members with details")
    return members


def parse_detail_page(html_content: str, name: str, index: int) -> AifiMember | None:
    """Parse a member detail page HTML to extract rich data."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Clean AIFI legal name → brand name, preserve original as legal_name
    display_name, legal_name = clean_fund_name(name)
    slug = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")

    def find_value(labels: list[str]) -> str | None:
        """
        Find value for a labeled field.

        The detail page structure is:
        <strong class="l-green">Label:</strong> Value<br>
        """
        for label in labels:
            # Find strong elements with l-green class
            for strong in soup.find_all("strong", class_="l-green"):
                strong_text = strong.get_text(strip=True).lower()
                if label.lower() in strong_text:
                    # Get the text after this strong element
                    # The value is the next sibling text or next element
                    next_sibling = strong.next_sibling
                    if next_sibling:
                        if isinstance(next_sibling, str):
                            value = next_sibling.strip()
                        else:
                            value = next_sibling.get_text(strip=True)

                        # Clean up the value
                        value = value.lstrip(":").strip()
                        # Handle &nbsp; and other whitespace
                        value = re.sub(r"\s+", " ", value).strip()

                        if value and value != "-":
                            return value
        return None

    def find_list_value(labels: list[str]) -> list[str]:
        """Find comma-separated values for a labeled field."""
        text = find_value(labels)
        if text:
            # Split by comma and clean up
            items = [item.strip() for item in text.split(",")]
            return [item for item in items if item and item != "-"]
        return []

    # Extract basic contact info
    city = find_value(["City"])
    address = find_value(["Address", "Indirizzo"])
    country = find_value(["Nation", "Country", "Paese"])
    phone = find_value(["Telephone", "Telefono"])
    contact_name = find_value(["Contact"])

    # Extract email from mailto link within the detail section
    email = None
    # Look for email in the Information section specifically
    info_section = soup.find("div", id=re.compile("pnlInfo|pnlInformazioni", re.IGNORECASE))
    if info_section:
        email_link = info_section.find("a", href=re.compile(r"^mailto:"))
        if email_link:
            email = email_link.get_text(strip=True)
    # Fallback: find any mailto that's not the footer
    if not email:
        for link in soup.find_all("a", href=re.compile(r"^mailto:")):
            # Skip footer emails
            if link.find_parent("footer"):
                continue
            email = link.get_text(strip=True)
            if email and email != "-" and "aifi.it" not in email:
                break

    # Extract website
    website = None
    for strong in soup.find_all("strong", class_="l-green"):
        if "website" in strong.get_text(strip=True).lower():
            next_elem = strong.find_next("a")
            if next_elem and next_elem.get("href"):
                website = next_elem.get("href")
                break

    # Extract rich metrics
    aum_text = find_value(["Total capital under management", "Total capital", "Capitale totale"])
    num_funds_text = find_value(["Number of funds managed", "Number of funds", "Fondi gestiti"])
    num_portfolio_text = find_value(["Number of portfolio companies", "Portfolio companies"])
    num_executives_text = find_value(["Number of executives", "Executives"])
    num_sfdr_text = find_value(["funds art. 8 sfdr", "SFDR Article 8", "art. 8"])
    min_investment_text = find_value(["Minimum investment", "Investimento minimo"])
    max_investment_text = find_value(["Maximum investment", "Investimento massimo"])

    # Extract list fields (comma-separated in detail page)
    strategies = find_list_value(["Investment focus", "Focus investimento"])
    sectors = find_list_value(["Sectoral preferences", "Preferenze settoriali"])
    geographies = find_list_value(["Geographical preferences", "Preferenze geografiche"])
    asset_classes = find_list_value(["Asset class"])

    # Extract description from Remarks section
    description = None
    remarks_section = soup.find("h2", string=re.compile("Remarks|Note", re.IGNORECASE))
    if remarks_section:
        parent = remarks_section.find_parent("div")
        if parent:
            p = parent.find("p")
            if p:
                description = p.get_text(strip=True)[:2000]

    member: AifiMember = {
        "name": display_name,
        "slug": slug,
        "aifi_url": AIFI_MEMBERS_URL,
        "city": city,
        "address": address,
        "country": country or "Italy",  # Default to Italy if not specified
        "phone": phone,
        "email": email,
        "website": website,
        "contact_name": contact_name,
        "aum_eur": parse_aum(aum_text),
        "num_funds": parse_int_safely(num_funds_text),
        "num_portfolio_companies": parse_int_safely(num_portfolio_text),
        "num_executives": parse_int_safely(num_executives_text),
        "num_sfdr_article_8": parse_int_safely(num_sfdr_text),
        "investment_min_eur": parse_investment_amount(min_investment_text),
        "investment_max_eur": parse_investment_amount(max_investment_text),
        "strategies": strategies,
        "sectors": sectors,
        "geographies": geographies,
        "asset_classes": asset_classes,
        "description": description,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    return member


def parse_members_from_html(html_path: Path) -> list[AifiMember]:
    """
    Parse member data directly from the AIFI members list page HTML.

    NOTE: This only extracts basic info. Use scrape_members_with_details() for full data.

    The list page contains all member info in div.associato elements.
    """
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")
    members: list[AifiMember] = []

    # Find all member cards
    member_cards = soup.select("#elencoassaderenti .associato")
    logger.info(f"Parsing {len(member_cards)} member cards from HTML")

    for card in member_cards:
        try:
            # Extract name from h4 and clean legal entity suffixes
            name_elem = card.find("h4")
            raw_name = name_elem.get_text(strip=True) if name_elem else "Unknown"
            name, _legal = clean_fund_name(raw_name)

            # Generate slug from cleaned name
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

            # Extract fields from p elements with l-green spans
            def get_field(label: str) -> str | None:
                for p in card.find_all("p"):
                    span = p.find("span", class_="l-green")
                    if span and label.lower() in span.get_text(strip=True).lower():
                        # Get the text after the span
                        text = p.get_text(strip=True)
                        # Remove the label part
                        value = text.replace(span.get_text(strip=True), "").strip()
                        if value and value != "-":
                            return value
                return None

            city = get_field("City")
            address = get_field("Address")
            phone = get_field("Telephone")
            contact_name = get_field("Contact")

            # Extract email from mailto link
            email = None
            email_link = card.find("a", href=re.compile(r"^mailto:"))
            if email_link:
                email = email_link.get_text(strip=True)
                if email == "-":
                    email = None

            # Extract website from external link
            website = None
            for link in card.find_all("a", href=True):
                href = link.get("href", "")
                if href.startswith("http") and "aifi.it" not in href:
                    website = href
                    break

            member: AifiMember = {
                "name": name,
                "slug": slug,
                "aifi_url": AIFI_MEMBERS_URL,  # List page URL
                "city": city,
                "address": address,
                "country": "Italy",  # Default for AIFI members
                "phone": phone,
                "email": email,
                "website": website,
                "contact_name": contact_name,
                "aum_eur": None,  # Not available on list page
                "num_funds": None,
                "num_portfolio_companies": None,
                "num_executives": None,
                "num_sfdr_article_8": None,
                "investment_min_eur": None,
                "investment_max_eur": None,
                "strategies": [],
                "sectors": [],
                "geographies": [],
                "asset_classes": [],
                "description": None,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            members.append(member)

        except Exception as e:
            logger.error(f"Failed to parse member card: {e}")
            continue

    logger.info(f"Successfully parsed {len(members)} members")
    return members


def scrape_member_detail(url: str) -> AifiMember | None:
    """
    Scrape a single member detail page using requests/BeautifulSoup.

    Args:
        url: Full URL to member detail page

    Returns:
        AifiMember dict or None if scraping failed
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Extract slug from URL
    slug = url.rstrip("/").split("/")[-1]

    # Extract name from page title or heading
    name = None
    title_tag = soup.find("h1")
    if title_tag:
        name = title_tag.get_text(strip=True)

    if not name:
        # Try meta title
        meta_title = soup.find("title")
        if meta_title:
            name = meta_title.get_text(strip=True).split("|")[0].strip()

    if not name:
        name = slug.replace("-", " ").title()

    # Clean legal entity names (e.g. "PAI SAS - Italian Branch" → "PAI Partners")
    name, _legal = clean_fund_name(name)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    # Helper to find text by label
    def find_field(label_patterns: list[str]) -> str | None:
        for pattern in label_patterns:
            # Look for label in various structures
            for elem in soup.find_all(string=re.compile(pattern, re.IGNORECASE)):
                parent = elem.find_parent()
                if parent:
                    # Get sibling or next text
                    sibling = parent.find_next_sibling()
                    if sibling:
                        text = sibling.get_text(strip=True)
                        if text:
                            return text
                    # Or text after label in same element
                    full_text = parent.get_text(strip=True)
                    match = re.search(rf"{pattern}[:\s]*(.+)", full_text, re.IGNORECASE)
                    if match:
                        return match.group(1).strip()
        return None

    # Extract contact info
    city = find_field(["City", "Citta"])
    address = find_field(["Address", "Indirizzo"])
    country = find_field(["Country", "Paese"])
    phone = find_field(["Phone", "Telefono", "Tel"])
    email = find_field(["Email", "E-mail"])
    website = find_field(["Website", "Sito web", "Web"])
    contact_name = find_field(["Contact", "Contatto", "Reference"])

    # Extract metrics
    aum_text = find_field(["Total capital", "AUM", "Assets under management", "Capitale"])
    num_funds_text = find_field(["Number of funds", "Fondi gestiti", "Funds managed"])
    num_portfolio_text = find_field(["Portfolio companies", "Societa in portafoglio"])
    num_executives_text = find_field(["Executives", "Dirigenti", "Team"])
    num_sfdr_text = find_field(["SFDR Article 8", "Article 8"])

    # Extract investment policy
    min_investment_text = find_field(["Minimum investment", "Investimento minimo"])
    max_investment_text = find_field(["Maximum investment", "Investimento massimo"])

    # Extract list fields
    def extract_list_field(label_patterns: list[str]) -> list[str]:
        for pattern in label_patterns:
            for elem in soup.find_all(string=re.compile(pattern, re.IGNORECASE)):
                parent = elem.find_parent()
                if parent:
                    # Look for list items
                    container = parent.find_parent()
                    if container:
                        items = container.find_all("li")
                        if items:
                            return [item.get_text(strip=True) for item in items if item.get_text(strip=True)]
                        # Or comma-separated text
                        sibling = parent.find_next_sibling()
                        if sibling:
                            text = sibling.get_text(strip=True)
                            if "," in text:
                                return [s.strip() for s in text.split(",") if s.strip()]
        return []

    strategies = extract_list_field(["Strategy", "Strategia", "Investment strategy"])
    sectors = extract_list_field(["Sector", "Settore", "Industry"])
    geographies = extract_list_field(["Geography", "Geografia", "Geographic focus", "Area geografica"])
    asset_classes = extract_list_field(["Asset class", "Classe di attivo"])

    # Extract description
    description = None
    desc_elem = soup.find("div", class_=re.compile("description|about|profile", re.IGNORECASE))
    if desc_elem:
        description = desc_elem.get_text(strip=True)[:2000]  # Limit length

    # Build result
    member: AifiMember = {
        "name": name,
        "slug": slug,
        "aifi_url": url,
        "city": city,
        "address": address,
        "country": country,
        "phone": phone,
        "email": email,
        "website": website,
        "contact_name": contact_name,
        "aum_eur": parse_aum(aum_text),
        "num_funds": parse_int_safely(num_funds_text),
        "num_portfolio_companies": parse_int_safely(num_portfolio_text),
        "num_executives": parse_int_safely(num_executives_text),
        "num_sfdr_article_8": parse_int_safely(num_sfdr_text),
        "investment_min_eur": parse_investment_amount(min_investment_text),
        "investment_max_eur": parse_investment_amount(max_investment_text),
        "strategies": strategies,
        "sectors": sectors,
        "geographies": geographies,
        "asset_classes": asset_classes,
        "description": description,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    return member


def scrape_all_members(
    dry_run: bool = False,
    limit: int | None = None,
    debug: bool = False,
) -> list[AifiMember]:
    """
    Full scrape: discover member URLs, then scrape each detail page.

    Args:
        dry_run: If True, only discover URLs without scraping details
        limit: Maximum number of members to scrape (for testing)
        debug: If True, save debug screenshot and HTML

    Returns:
        List of scraped AifiMember records
    """
    # Phase 1: Load the page and check for members
    member_urls = discover_member_urls(debug=debug)

    # Determine paths
    html_path = PROJECT_ROOT / "data" / "derived" / "aifi_members_page.html"

    # Check if we should parse from HTML (no direct URLs available)
    if member_urls == ["__PARSE_FROM_HTML__"]:
        logger.info("Parsing members directly from list page HTML...")

        if not html_path.exists():
            logger.error(f"HTML file not found: {html_path}")
            return []

        members = parse_members_from_html(html_path)

        if dry_run:
            logger.info(f"Dry run - Found {len(members)} members:")
            for m in members[:20]:
                print(f"  {m['name']} ({m['city']})")
            if len(members) > 20:
                print(f"  ... and {len(members) - 20} more")
            return []

        if limit:
            members = members[:limit]
            logger.info(f"Limited to {limit} members")

        return members

    # Legacy path: if we have actual URLs, scrape each one
    if dry_run:
        logger.info("Dry run - URLs discovered:")
        for url in member_urls[:20]:
            print(f"  {url}")
        if len(member_urls) > 20:
            print(f"  ... and {len(member_urls) - 20} more")
        return []

    if limit:
        member_urls = member_urls[:limit]
        logger.info(f"Limited to {limit} members")

    members: list[AifiMember] = []
    failed_urls: list[str] = []

    for i, url in enumerate(member_urls):
        logger.info(f"Scraping [{i + 1}/{len(member_urls)}]: {url}")

        member = scrape_member_detail(url)
        if member:
            members.append(member)
        else:
            failed_urls.append(url)

        # Rate limiting
        if i < len(member_urls) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    logger.info(f"Scraped {len(members)} members successfully")
    if failed_urls:
        logger.warning(f"Failed to scrape {len(failed_urls)} URLs: {failed_urls[:5]}...")

    return members


def save_results(members: list[AifiMember], output_path: Path) -> None:
    """Save scraped members to JSON file."""
    output: AifiMembersOutput = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source_url": AIFI_MEMBERS_URL,
        "member_count": len(members),
        "members": members,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_json_write(output_path, output)

    logger.info(f"Saved {len(members)} members to {output_path}")


def main(dry_run: bool = False, limit: int | None = None, debug: bool = False, quick: bool = False) -> None:
    """Main entry point."""
    # Determine output path (relative to project root)
    output_path = PROJECT_ROOT / "data" / "derived" / "aifi_members.json"

    logger.info("Starting AIFI members scrape")
    logger.info(f"Output will be saved to: {output_path}")

    if quick:
        # Quick mode: only basic info from list page
        logger.info("Quick mode: extracting basic info only (no AUM, funds, etc.)")
        members = scrape_all_members(dry_run=dry_run, limit=limit, debug=debug)
    else:
        # Full mode: click through detail pages for rich data
        logger.info("Full mode: scraping detail pages for AUM, funds, portfolio companies, etc.")
        if dry_run:
            # For dry run, just show what would be scraped
            members = scrape_all_members(dry_run=True, limit=limit, debug=debug)
        else:
            members = scrape_members_with_details(limit=limit, debug=debug)

    if not dry_run and members:
        save_results(members, output_path)

    logger.info("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape AIFI member directory for Italian PE/VC fund data"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be scraped without actually scraping",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of members to scrape (for testing)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save debug screenshot and HTML to data/derived/",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: only extract basic info from list page (no AUM, funds, etc.)",
    )
    args = parser.parse_args()

    main(dry_run=args.dry_run, limit=args.limit, debug=args.debug, quick=args.quick)
