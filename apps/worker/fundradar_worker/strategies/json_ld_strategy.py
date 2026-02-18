"""
Extraction strategy for JSON-LD structured data.

JSON-LD (JSON for Linking Data) is a method of encoding Linked Data
using JSON. Many websites include structured data about their
organization, team members, and portfolio companies in JSON-LD
format for SEO purposes.
"""

import json
import logging
import re
from typing import Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# Schema.org types for organizations/companies
ORGANIZATION_TYPES = {
    "Organization",
    "Corporation",
    "LocalBusiness",
    "Company",
    "GovernmentOrganization",
    "NGO",
    "EducationalOrganization",
}

# Schema.org types for people
PERSON_TYPES = {
    "Person",
}


def extract_from_json_ld(
    html: str,
    data_type: str = "organization",
) -> list[dict]:
    """
    Extract data from JSON-LD structured data.

    Args:
        html: Raw HTML content
        data_type: Type to extract ("organization", "person", "article")

    Returns:
        List of extracted items
    """
    if data_type in ("organization", "portfolio"):
        return extract_organizations_from_json_ld(html)
    elif data_type in ("person", "team"):
        return extract_people_from_json_ld(html)
    else:
        return []


def _find_json_ld_scripts(html: str) -> list[dict]:
    """
    Find and parse all JSON-LD scripts in HTML.

    Args:
        html: Raw HTML content

    Returns:
        List of parsed JSON-LD objects
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Find all script tags with type application/ld+json
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue

        try:
            data = json.loads(script.string)

            # Handle @graph arrays
            if isinstance(data, dict) and "@graph" in data:
                results.extend(data["@graph"])
            elif isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                results.append(data)

        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse JSON-LD: {e}")
            continue

    return results


def _get_type(item: dict) -> str | None:
    """
    Get the @type of a JSON-LD item.

    Args:
        item: JSON-LD object

    Returns:
        Type string or None
    """
    item_type = item.get("@type")

    if isinstance(item_type, list):
        # Return first recognized type
        for t in item_type:
            if t in ORGANIZATION_TYPES or t in PERSON_TYPES:
                return t
        return item_type[0] if item_type else None

    return item_type


def extract_organizations_from_json_ld(html: str) -> list[dict]:
    """
    Extract organization/company data from JSON-LD.

    Args:
        html: Raw HTML content

    Returns:
        List of company dictionaries
    """
    json_ld_items = _find_json_ld_scripts(html)
    results = []
    seen_names = set()

    for item in json_ld_items:
        if not isinstance(item, dict):
            continue

        item_type = _get_type(item)
        if item_type not in ORGANIZATION_TYPES:
            continue

        company = _extract_organization(item)
        if company and company.get("name"):
            name = company["name"]
            if name not in seen_names:
                seen_names.add(name)
                results.append(company)

        # Check for member organizations
        if "member" in item:
            members = item["member"]
            if isinstance(members, list):
                for member in members:
                    if isinstance(member, dict):
                        company = _extract_organization(member)
                        if company and company.get("name") and company["name"] not in seen_names:
                            seen_names.add(company["name"])
                            results.append(company)

    logger.info(f"Extracted {len(results)} organizations from JSON-LD")
    return results


def extract_people_from_json_ld(html: str) -> list[dict]:
    """
    Extract person/team member data from JSON-LD.

    Args:
        html: Raw HTML content

    Returns:
        List of team member dictionaries
    """
    json_ld_items = _find_json_ld_scripts(html)
    results = []
    seen_names = set()

    for item in json_ld_items:
        if not isinstance(item, dict):
            continue

        item_type = _get_type(item)

        # Direct Person type
        if item_type in PERSON_TYPES:
            person = _extract_person(item)
            if person and person.get("name") and person["name"] not in seen_names:
                seen_names.add(person["name"])
                results.append(person)

        # Check for employee/member arrays
        for key in ["employee", "employees", "member", "members", "founder", "founders"]:
            if key in item:
                people = item[key]
                if not isinstance(people, list):
                    people = [people]

                for person_data in people:
                    if isinstance(person_data, dict):
                        person = _extract_person(person_data)
                        if person and person.get("name") and person["name"] not in seen_names:
                            seen_names.add(person["name"])
                            results.append(person)
                    elif isinstance(person_data, str):
                        # Sometimes just a name string
                        if person_data not in seen_names and _looks_like_name(person_data):
                            seen_names.add(person_data)
                            results.append({
                                "name": person_data,
                                "title": None,
                                "role": key.rstrip("s").title() if key.startswith("founder") else None,
                                "linkedin": None,
                                "email": None,
                                "photo_url": None,
                                "source": "json_ld",
                            })

    logger.info(f"Extracted {len(results)} people from JSON-LD")
    return results


def _extract_organization(item: dict) -> dict:
    """
    Extract organization data from a JSON-LD object.

    Args:
        item: JSON-LD organization object

    Returns:
        Company dictionary
    """
    company = {
        "name": None,
        "website": None,
        "description": None,
        "logo_url": None,
        "sector": None,
        "status": None,
        "source": "json_ld",
    }

    # Name
    company["name"] = item.get("name") or item.get("legalName")

    # Website
    company["website"] = item.get("url") or item.get("sameAs")
    if isinstance(company["website"], list):
        company["website"] = company["website"][0] if company["website"] else None

    # Description
    company["description"] = item.get("description")
    if company["description"] and len(company["description"]) > 500:
        company["description"] = company["description"][:500]

    # Logo
    logo = item.get("logo") or item.get("image")
    if isinstance(logo, str):
        company["logo_url"] = logo
    elif isinstance(logo, dict):
        company["logo_url"] = logo.get("url") or logo.get("contentUrl")
    elif isinstance(logo, list) and logo:
        first_logo = logo[0]
        if isinstance(first_logo, str):
            company["logo_url"] = first_logo
        elif isinstance(first_logo, dict):
            company["logo_url"] = first_logo.get("url")

    # Sector/industry
    company["sector"] = item.get("industry") or item.get("naics")
    if isinstance(company["sector"], list):
        company["sector"] = ", ".join(company["sector"][:3])

    return company


def _extract_person(item: dict) -> dict:
    """
    Extract person data from a JSON-LD object.

    Args:
        item: JSON-LD person object

    Returns:
        Team member dictionary
    """
    person = {
        "name": None,
        "title": None,
        "role": None,
        "linkedin": None,
        "email": None,
        "photo_url": None,
        "bio": None,
        "source": "json_ld",
    }

    # Name
    person["name"] = item.get("name")
    if not person["name"]:
        given = item.get("givenName", "")
        family = item.get("familyName", "")
        if given or family:
            person["name"] = f"{given} {family}".strip()

    # Title/job
    person["title"] = item.get("jobTitle") or item.get("title")

    # Role based on relationship to org
    if item.get("@type") == "Person":
        affiliation = item.get("affiliation")
        if isinstance(affiliation, dict):
            person["role"] = affiliation.get("roleName")

    # LinkedIn and other social
    same_as = item.get("sameAs")
    if same_as:
        if isinstance(same_as, str):
            same_as = [same_as]
        for url in same_as:
            if isinstance(url, str) and "linkedin" in url.lower():
                person["linkedin"] = url
                break

    # Email
    person["email"] = item.get("email")

    # Photo
    image = item.get("image")
    if isinstance(image, str):
        person["photo_url"] = image
    elif isinstance(image, dict):
        person["photo_url"] = image.get("url") or image.get("contentUrl")

    # Bio
    person["bio"] = item.get("description")
    if person["bio"] and len(person["bio"]) > 1000:
        person["bio"] = person["bio"][:1000]

    return person


def _looks_like_name(text: str) -> bool:
    """
    Check if text looks like a person's name.

    Args:
        text: Text to check

    Returns:
        True if text appears to be a name
    """
    if not text or len(text) < 3 or len(text) > 60:
        return False

    words = text.split()
    if len(words) < 2 or len(words) > 5:
        return False

    # Check if words look like name parts (capitalized)
    for word in words:
        if not word[0].isupper():
            return False
        if not re.match(r"^[A-Za-z\'-]+\.?$", word):
            return False

    return True
