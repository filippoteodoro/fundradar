"""
LinkedIn people scraper for employee data.

Extracts employee lists and individual profiles from LinkedIn
company pages for team analysis and hiring pattern detection.
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .apify_client import ApifyClient, ApifyConfig, ActorRunResult, save_raw_data

logger = logging.getLogger(__name__)


@dataclass
class LinkedInEmployee:
    """Basic employee info from company employee list."""

    name: str
    title: str | None
    profile_url: str | None
    company_slug: str
    scraped_at: str


@dataclass
class Education:
    """Education entry from a profile."""

    school: str
    degree: str | None
    field_of_study: str | None
    start_year: int | None
    end_year: int | None


@dataclass
class Experience:
    """Work experience entry from a profile."""

    company: str
    title: str
    location: str | None
    start_date: str | None
    end_date: str | None
    is_current: bool
    description: str | None


@dataclass
class LinkedInProfile:
    """Full LinkedIn profile data."""

    profile_id: str
    profile_url: str
    name: str
    headline: str | None
    location: str | None
    connections: int | None
    about: str | None
    education: list[Education] = field(default_factory=list)
    experience: list[Experience] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    company_slug: str | None = None
    scraped_at: str | None = None
    raw_data: dict[str, Any] | None = None


def _extract_profile_id(item: dict[str, Any]) -> str:
    """Extract profile identifier."""
    for key in ("publicIdentifier", "profileId", "id", "urn"):
        if key in item and item[key]:
            return str(item[key])

    # Extract from URL
    url = item.get("url", item.get("profileUrl", ""))
    match = re.search(r"/in/([^/]+)", url)
    if match:
        return match.group(1)

    return f"profile-{hash(item.get('name', '') + url) & 0xFFFFFFFF:08x}"


def _parse_education(items: list[dict[str, Any]] | None) -> list[Education]:
    """Parse education entries from profile data."""
    if not items:
        return []

    education = []
    for item in items:
        school = item.get("schoolName", item.get("school", item.get("institutionName", "")))
        if not school:
            continue

        # Parse years - handle multiple formats
        start_year = None
        end_year = None

        # Format 1: dateRange object
        date_range = item.get("dateRange", item.get("timePeriod", {}))
        if isinstance(date_range, dict):
            start = date_range.get("startDate", date_range.get("start", {}))
            end = date_range.get("endDate", date_range.get("end", {}))
            if isinstance(start, dict):
                start_year = start.get("year")
            if isinstance(end, dict):
                end_year = end.get("year")

        # Format 2: direct startDate/endDate objects (Apify harvestapi format)
        if not start_year:
            start_date = item.get("startDate", {})
            if isinstance(start_date, dict):
                start_year = start_date.get("year")
        if not end_year:
            end_date = item.get("endDate", {})
            if isinstance(end_date, dict):
                end_year = end_date.get("year")

        education.append(Education(
            school=school,
            degree=item.get("degreeName", item.get("degree")),
            field_of_study=item.get("fieldOfStudy", item.get("field")),
            start_year=start_year,
            end_year=end_year,
        ))

    return education


def _parse_experience(items: list[dict[str, Any]] | None) -> list[Experience]:
    """Parse work experience entries from profile data."""
    if not items:
        return []

    experience = []
    for item in items:
        company = item.get("companyName", item.get("company", ""))
        title = item.get("position", item.get("title", ""))
        if not company or not title:
            continue

        # Parse dates - handle multiple formats
        start_date = None
        end_date = None
        is_current = False

        # Format 1: dateRange object
        date_range = item.get("dateRange", item.get("timePeriod", {}))
        if isinstance(date_range, dict):
            start = date_range.get("startDate", date_range.get("start", {}))
            end = date_range.get("endDate", date_range.get("end", {}))

            if isinstance(start, dict):
                year = start.get("year")
                month = start.get("month", 1)
                if year:
                    start_date = f"{year}-{month:02d}" if isinstance(month, int) else f"{year}-01"

            if isinstance(end, dict):
                year = end.get("year")
                month = end.get("month", 1)
                if year:
                    end_date = f"{year}-{month:02d}" if isinstance(month, int) else f"{year}-01"
            elif end is None or end == "Present":
                is_current = True

        # Format 2: direct startDate/endDate objects (Apify harvestapi format)
        if not start_date:
            start_obj = item.get("startDate", {})
            if isinstance(start_obj, dict):
                year = start_obj.get("year")
                month = start_obj.get("month", "01")
                if year:
                    # Month might be string like "Sep" or int
                    if isinstance(month, str) and not month.isdigit():
                        month_map = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                                     "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                                     "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
                        month = month_map.get(month, "01")
                    start_date = f"{year}-{month}"

        if not end_date:
            end_obj = item.get("endDate", {})
            if isinstance(end_obj, dict):
                if end_obj.get("text") == "Present":
                    is_current = True
                else:
                    year = end_obj.get("year")
                    month = end_obj.get("month", "01")
                    if year:
                        if isinstance(month, str) and not month.isdigit():
                            month_map = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                                         "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                                         "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
                            month = month_map.get(month, "01")
                        end_date = f"{year}-{month}"

        # Check for current indicator
        is_current = is_current or item.get("isCurrent", False)
        if item.get("endDate", {}).get("text") == "Present":
            is_current = True

        experience.append(Experience(
            company=company,
            title=title,
            location=item.get("location", item.get("locationName")),
            start_date=start_date,
            end_date=end_date,
            is_current=is_current,
            description=item.get("description"),
        ))

    return experience


def normalize_employee(
    item: dict[str, Any],
    company_slug: str,
) -> LinkedInEmployee:
    """
    Convert raw employee list data to LinkedInEmployee.

    Args:
        item: Raw employee data from Apify
        company_slug: Fund slug for this company

    Returns:
        Normalized LinkedInEmployee object
    """
    return LinkedInEmployee(
        name=item.get("name", item.get("fullName", "Unknown")),
        title=item.get("title", item.get("headline", item.get("position"))),
        profile_url=item.get("url", item.get("profileUrl", item.get("linkedInUrl"))),
        company_slug=company_slug,
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )


def normalize_profile(
    item: dict[str, Any],
    company_slug: str | None = None,
) -> LinkedInProfile:
    """
    Convert raw profile data to LinkedInProfile.

    Args:
        item: Raw profile data from Apify
        company_slug: Optional fund slug association

    Returns:
        Normalized LinkedInProfile object
    """
    # Parse skills - handle various formats
    skills = []
    skills_data = item.get("skills", item.get("topSkills", []))
    if isinstance(skills_data, list):
        for skill in skills_data:
            if isinstance(skill, str):
                skills.append(skill)
            elif isinstance(skill, dict):
                skills.append(skill.get("name", skill.get("skill", "")))

    # Parse languages
    languages = []
    lang_data = item.get("languages", [])
    if isinstance(lang_data, list):
        for lang in lang_data:
            if isinstance(lang, str):
                languages.append(lang)
            elif isinstance(lang, dict):
                languages.append(lang.get("name", lang.get("language", "")))

    # Build name from first/last if not available as full name
    name = item.get("name", item.get("fullName"))
    if not name:
        first = item.get("firstName", "")
        last = item.get("lastName", "")
        name = f"{first} {last}".strip() or "Unknown"

    # Get location - handle nested structure
    location = item.get("location")
    if isinstance(location, dict):
        location = location.get("linkedinText", location.get("parsed", {}).get("text", ""))

    # Get connections count
    connections = item.get("connectionsCount", item.get("connections"))

    # Get education - handle profileTopEducation from harvestapi
    education_data = item.get("education", item.get("educations", []))
    if not education_data:
        # Try profileTopEducation (limited data)
        top_edu = item.get("profileTopEducation", [])
        if top_edu:
            education_data = [{"schoolName": e.get("schoolName")} for e in top_edu]

    return LinkedInProfile(
        profile_id=_extract_profile_id(item),
        profile_url=item.get("linkedinUrl", item.get("url", item.get("profileUrl", ""))),
        name=name,
        headline=item.get("headline", item.get("title")),
        location=location,
        connections=connections,
        about=item.get("about", item.get("summary")),
        education=_parse_education(education_data),
        experience=_parse_experience(item.get("experience", item.get("positions", []))),
        skills=[s for s in skills if s],
        languages=[l for l in languages if l],
        company_slug=company_slug,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        raw_data=item,
    )


class LinkedInPeopleScraper:
    """
    Scraper for LinkedIn people data.

    Handles both employee lists and full profile scraping.
    """

    def __init__(
        self,
        client: ApifyClient | None = None,
        output_dir: Path | None = None,
    ):
        self.client = client or ApifyClient()
        self.output_dir = output_dir or Path("data/derived/linkedin")

    def scrape_employees(
        self,
        company_url: str,
        company_slug: str,
        max_employees: int = 100,
        save_raw: bool = True,
    ) -> list[LinkedInEmployee]:
        """
        Scrape employee list from a company's LinkedIn page.

        Args:
            company_url: LinkedIn company URL
            company_slug: Fund slug identifier
            max_employees: Maximum employees to retrieve
            save_raw: Whether to save raw API response

        Returns:
            List of LinkedInEmployee objects
        """
        logger.info(f"Scraping employees for {company_slug} ({company_url})")

        result = self.client.scrape_company_employees(company_url, max_employees)

        if result.error:
            logger.error(f"Failed to scrape employees for {company_slug}: {result.error}")
            return []

        if save_raw and result.items:
            raw_path = self.output_dir / "raw" / f"{company_slug}_employees.json"
            save_raw_data(result.items, raw_path, "company_employees")

        employees = []
        for item in result.items:
            try:
                employee = normalize_employee(item, company_slug)
                employees.append(employee)
            except Exception as e:
                logger.warning(f"Failed to normalize employee: {e}")
                continue

        logger.info(f"Scraped {len(employees)} employees from {company_slug}")
        return employees

    def scrape_profile(
        self,
        profile_url: str,
        company_slug: str | None = None,
        save_raw: bool = True,
    ) -> LinkedInProfile | None:
        """
        Scrape a full LinkedIn profile.

        Args:
            profile_url: LinkedIn profile URL
            company_slug: Optional fund slug association
            save_raw: Whether to save raw response

        Returns:
            LinkedInProfile or None if failed
        """
        logger.info(f"Scraping profile: {profile_url}")

        result = self.client.scrape_profile(profile_url)

        if result.error:
            logger.error(f"Failed to scrape profile {profile_url}: {result.error}")
            return None

        if not result.items:
            logger.warning(f"No data returned for profile: {profile_url}")
            return None

        item = result.items[0]

        if save_raw:
            profile_id = _extract_profile_id(item)
            raw_path = self.output_dir / "raw" / "profiles" / f"{profile_id}.json"
            save_raw_data([item], raw_path, "profile")

        try:
            return normalize_profile(item, company_slug)
        except Exception as e:
            logger.error(f"Failed to normalize profile: {e}")
            return None

    def scrape_profiles_batch(
        self,
        profile_urls: list[str],
        company_slug: str | None = None,
        save_raw: bool = True,
    ) -> list[LinkedInProfile]:
        """
        Scrape multiple profiles in a single API call.

        Args:
            profile_urls: List of LinkedIn profile URLs
            company_slug: Optional fund slug association
            save_raw: Whether to save raw responses

        Returns:
            List of LinkedInProfile objects
        """
        logger.info(f"Scraping {len(profile_urls)} profiles")

        result = self.client.scrape_profiles_batch(profile_urls)

        if result.error:
            logger.error(f"Failed to scrape profiles batch: {result.error}")
            return []

        if save_raw and result.items:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_path = self.output_dir / "raw" / f"profiles_batch_{timestamp}.json"
            save_raw_data(result.items, raw_path, "profiles_batch")

        profiles = []
        for item in result.items:
            try:
                profile = normalize_profile(item, company_slug)
                profiles.append(profile)
            except Exception as e:
                logger.warning(f"Failed to normalize profile: {e}")
                continue

        logger.info(f"Scraped {len(profiles)} profiles")
        return profiles

    def scrape_top_employees(
        self,
        company_url: str,
        company_slug: str,
        company_name: str,
        num_profiles: int = 5,
        save_raw: bool = True,
    ) -> tuple[list[LinkedInEmployee], list[LinkedInProfile]]:
        """
        Scrape employee list and top N full profiles.

        Args:
            company_url: LinkedIn company URL
            company_slug: Fund slug identifier
            company_name: Company display name
            num_profiles: Number of full profiles to scrape
            save_raw: Whether to save raw responses

        Returns:
            Tuple of (all employees, top profiles)
        """
        # First get employee list
        employees = self.scrape_employees(
            company_url, company_slug, max_employees=100, save_raw=save_raw
        )

        if not employees:
            return [], []

        # Select top profiles to scrape (prioritize by title seniority)
        seniority_keywords = [
            "partner", "managing", "director", "principal",
            "vp", "vice president", "head", "chief", "ceo", "cfo"
        ]

        def title_seniority(emp: LinkedInEmployee) -> int:
            if not emp.title:
                return 0
            title_lower = emp.title.lower()
            for i, keyword in enumerate(seniority_keywords):
                if keyword in title_lower:
                    return len(seniority_keywords) - i
            return 0

        # Sort by seniority and take top N with profile URLs
        employees_with_urls = [e for e in employees if e.profile_url]
        employees_with_urls.sort(key=title_seniority, reverse=True)
        top_urls = [e.profile_url for e in employees_with_urls[:num_profiles]]

        # Scrape top profiles
        profiles = []
        if top_urls:
            profiles = self.scrape_profiles_batch(top_urls, company_slug, save_raw)

        return employees, profiles

    def save_employees(
        self,
        employees: list[LinkedInEmployee],
        filename: str = "linkedin_employees.json"
    ) -> Path:
        """Save employees to JSON file."""
        output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "employee_count": len(employees),
            "employees": [asdict(e) for e in employees],
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {len(employees)} employees to {output_path}")
        return output_path

    def save_profiles(
        self,
        profiles: list[LinkedInProfile],
        filename: str = "linkedin_profiles.json"
    ) -> Path:
        """Save profiles to JSON file."""
        output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "profile_count": len(profiles),
            "profiles": [asdict(p) for p in profiles],
        }

        # Remove raw_data from output
        for profile in data["profiles"]:
            profile.pop("raw_data", None)

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {len(profiles)} profiles to {output_path}")
        return output_path

    def load_employees(self, filename: str = "linkedin_employees.json") -> list[LinkedInEmployee]:
        """Load employees from JSON file."""
        input_path = self.output_dir / filename

        if not input_path.exists():
            logger.warning(f"Employees file not found: {input_path}")
            return []

        with open(input_path) as f:
            data = json.load(f)

        employees = []
        for item in data.get("employees", []):
            employees.append(LinkedInEmployee(**item))

        return employees

    def load_profiles(self, filename: str = "linkedin_profiles.json") -> list[LinkedInProfile]:
        """Load profiles from JSON file."""
        input_path = self.output_dir / filename

        if not input_path.exists():
            logger.warning(f"Profiles file not found: {input_path}")
            return []

        with open(input_path) as f:
            data = json.load(f)

        profiles = []
        for item in data.get("profiles", []):
            # Handle nested dataclasses
            education = [Education(**e) for e in item.get("education", [])]
            experience = [Experience(**e) for e in item.get("experience", [])]
            item["education"] = education
            item["experience"] = experience
            profiles.append(LinkedInProfile(**item))

        return profiles
