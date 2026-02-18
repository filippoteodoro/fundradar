"""
Extraction strategy for Next.js __NEXT_DATA__ JSON.

Many modern fund websites use Next.js, which embeds page data
in a script tag with id="__NEXT_DATA__". This data often contains
structured portfolio and team information.
"""

import json
import logging
import re
from typing import Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _find_next_data(html: str) -> dict | None:
    """
    Extract __NEXT_DATA__ JSON from HTML.

    Args:
        html: Raw HTML content

    Returns:
        Parsed JSON data or None if not found
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find the __NEXT_DATA__ script tag
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        return None

    try:
        return json.loads(script.string)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse __NEXT_DATA__: {e}")
        return None


def _navigate_path(data: dict, path: list[str]) -> Any:
    """
    Navigate a dot-separated path in a nested dictionary.

    Args:
        data: The dictionary to navigate
        path: List of keys to traverse

    Returns:
        Value at path, or None if not found
    """
    current = data
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and key.isdigit():
            idx = int(key)
            current = current[idx] if idx < len(current) else None
        else:
            return None

        if current is None:
            return None

    return current


def _find_array_in_data(data: dict, keywords: list[str]) -> list[dict] | None:
    """
    Recursively search for arrays in data matching keywords.

    Args:
        data: Data to search
        keywords: Keywords to match in key names

    Returns:
        First matching array found, or None
    """
    if not isinstance(data, dict):
        return None

    # Check direct keys
    for key, value in data.items():
        key_lower = key.lower()
        if any(kw in key_lower for kw in keywords):
            if isinstance(value, list) and len(value) > 0:
                return value

    # Recurse into nested dicts
    for key, value in data.items():
        if isinstance(value, dict):
            result = _find_array_in_data(value, keywords)
            if result:
                return result

    return None


def extract_from_next_data(html: str, data_type: str = "portfolio") -> list[dict]:
    """
    Extract data from __NEXT_DATA__ JSON.

    Args:
        html: Raw HTML content
        data_type: Type of data to extract ("portfolio" or "team")

    Returns:
        List of extracted items
    """
    if data_type == "portfolio":
        return extract_portfolio_from_next_data(html)
    elif data_type == "team":
        return extract_team_from_next_data(html)
    else:
        logger.warning(f"Unknown data type: {data_type}")
        return []


def extract_portfolio_from_next_data(html: str) -> list[dict]:
    """
    Extract portfolio companies from __NEXT_DATA__.

    Searches for arrays containing company/portfolio data in the
    Next.js page props.

    Args:
        html: Raw HTML content

    Returns:
        List of extracted company dictionaries
    """
    data = _find_next_data(html)
    if not data:
        return []

    # Navigate to pageProps
    page_props = _navigate_path(data, ["props", "pageProps"])
    if not page_props:
        return []

    # Search for portfolio/company arrays
    keywords = ["portfolio", "companies", "investments", "investments", "deals"]
    items = _find_array_in_data(page_props, keywords)

    if not items:
        return []

    # Normalize items
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue

        # Map common field names
        company = {
            "name": _extract_name(item),
            "sector": _extract_sector(item),
            "website": _extract_website(item),
            "description": _extract_description(item),
            "logo_url": _extract_logo(item),
            "status": _extract_status(item),
            "entry_year": _extract_year(item, "entry"),
            "exit_year": _extract_year(item, "exit"),
            "source": "next_data",
            "raw": item,
        }

        if company["name"]:
            results.append(company)

    logger.info(f"Extracted {len(results)} companies from __NEXT_DATA__")
    return results


def extract_team_from_next_data(html: str) -> list[dict]:
    """
    Extract team members from __NEXT_DATA__.

    Args:
        html: Raw HTML content

    Returns:
        List of extracted team member dictionaries
    """
    data = _find_next_data(html)
    if not data:
        return []

    # Navigate to pageProps
    page_props = _navigate_path(data, ["props", "pageProps"])
    if not page_props:
        return []

    # Search for team arrays
    keywords = ["team", "members", "people", "staff", "employees", "partners"]
    items = _find_array_in_data(page_props, keywords)

    if not items:
        return []

    # Normalize items
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue

        member = {
            "name": _extract_name(item),
            "title": _extract_title(item),
            "role": _extract_role(item),
            "linkedin": _extract_linkedin(item),
            "email": _extract_email(item),
            "photo_url": _extract_photo(item),
            "bio": _extract_bio(item),
            "source": "next_data",
            "raw": item,
        }

        if member["name"]:
            results.append(member)

    logger.info(f"Extracted {len(results)} team members from __NEXT_DATA__")
    return results


def _extract_name(item: dict) -> str | None:
    """Extract name from various field names."""
    name_fields = ["name", "title", "companyName", "company_name", "Name", "company"]
    for field in name_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str) and len(value) > 1:
                return value.strip()
    return None


def _extract_sector(item: dict) -> str | None:
    """Extract sector/industry from various field names."""
    sector_fields = ["sector", "industry", "category", "type", "segment", "vertical"]
    for field in sector_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str):
                return value.strip()
            elif isinstance(value, list) and value:
                return ", ".join(str(v) for v in value[:3])
    return None


def _extract_website(item: dict) -> str | None:
    """Extract website URL."""
    url_fields = ["website", "url", "link", "site", "websiteUrl", "website_url"]
    for field in url_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str) and ("http" in value or "www" in value):
                return value.strip()
    return None


def _extract_description(item: dict) -> str | None:
    """Extract description."""
    desc_fields = ["description", "summary", "about", "excerpt", "overview", "desc"]
    for field in desc_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str) and len(value) > 10:
                return value.strip()[:500]
    return None


def _extract_logo(item: dict) -> str | None:
    """Extract logo/image URL."""
    logo_fields = ["logo", "image", "thumbnail", "logoUrl", "logo_url", "imageUrl", "img"]
    for field in logo_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str):
                return value.strip()
            elif isinstance(value, dict):
                # Nested image object
                for subfield in ["url", "src", "path"]:
                    if subfield in value:
                        return value[subfield]
    return None


def _extract_status(item: dict) -> str:
    """Extract investment status (current/exited)."""
    status_fields = ["status", "state", "type", "investmentStatus"]
    for field in status_fields:
        if field in item and item[field]:
            value = str(item[field]).lower()
            if "exit" in value or "past" in value or "former" in value:
                return "exited"
            elif "current" in value or "active" in value:
                return "current"

    # Check for exit_year or exit date
    exit_fields = ["exitYear", "exit_year", "exitDate", "exit_date", "divestment"]
    for field in exit_fields:
        if field in item and item[field]:
            return "exited"

    return "current"  # Default


def _extract_year(item: dict, year_type: str) -> int | None:
    """Extract entry or exit year."""
    if year_type == "entry":
        fields = ["entryYear", "entry_year", "investmentYear", "year", "date", "investmentDate"]
    else:
        fields = ["exitYear", "exit_year", "exitDate", "divestmentYear"]

    for field in fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, int) and 1900 < value < 2100:
                return value
            elif isinstance(value, str):
                # Try to extract year from string
                match = re.search(r'(19|20)\d{2}', value)
                if match:
                    return int(match.group())
    return None


def _extract_title(item: dict) -> str | None:
    """Extract job title."""
    title_fields = ["title", "position", "jobTitle", "job_title", "role", "designation"]
    for field in title_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str):
                return value.strip()
    return None


def _extract_role(item: dict) -> str | None:
    """Extract role/department."""
    role_fields = ["role", "department", "team", "group", "division"]
    for field in role_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str):
                return value.strip()
    return None


def _extract_linkedin(item: dict) -> str | None:
    """Extract LinkedIn URL."""
    linkedin_fields = ["linkedin", "linkedIn", "linkedinUrl", "linkedin_url", "social"]
    for field in linkedin_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str) and "linkedin" in value.lower():
                return value.strip()
            elif isinstance(value, dict):
                for subfield in ["linkedin", "linkedIn", "url"]:
                    if subfield in value and "linkedin" in str(value[subfield]).lower():
                        return value[subfield]
    return None


def _extract_email(item: dict) -> str | None:
    """Extract email address."""
    email_fields = ["email", "mail", "emailAddress", "email_address"]
    for field in email_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str) and "@" in value:
                return value.strip()
    return None


def _extract_photo(item: dict) -> str | None:
    """Extract photo/avatar URL."""
    photo_fields = ["photo", "avatar", "image", "picture", "photoUrl", "photo_url", "img"]
    for field in photo_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str):
                return value.strip()
            elif isinstance(value, dict):
                for subfield in ["url", "src", "path"]:
                    if subfield in value:
                        return value[subfield]
    return None


def _extract_bio(item: dict) -> str | None:
    """Extract biography."""
    bio_fields = ["bio", "biography", "about", "description", "summary"]
    for field in bio_fields:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str) and len(value) > 20:
                return value.strip()[:1000]
    return None
