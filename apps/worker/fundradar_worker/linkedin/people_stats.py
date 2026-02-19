"""
People statistics aggregator for fund team analysis.

Aggregates LinkedIn profile data into fund-level statistics including
education breakdown, background analysis, hiring patterns, and demographics.
"""

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .people_scraper import LinkedInEmployee, LinkedInProfile, Experience, Education
from .profile_classifier import (
    ProfileClassifier,
    ClassifiedProfile,
    BackgroundType,
    SeniorityLevel,
    is_investment_relevant,
)

logger = logging.getLogger(__name__)


def harvestapi_to_profile(item: dict[str, Any], slug: str) -> tuple[LinkedInEmployee, LinkedInProfile]:
    """Convert a HarvestAPI employee record to LinkedInEmployee + LinkedInProfile.

    HarvestAPI format has: experience[].position/companyName/startDate/endDate,
    education[].schoolName/degree/fieldOfStudy/startDate/endDate, etc.
    """
    now = datetime.now(timezone.utc).isoformat()
    name = f"{item.get('firstName', '')} {item.get('lastName', '')}".strip()
    headline = item.get('headline', '')
    profile_url = item.get('linkedinUrl', '')
    profile_id = item.get('publicIdentifier') or (
        profile_url.rstrip('/').split('/')[-1] if profile_url else name.lower().replace(' ', '-')
    )

    employee = LinkedInEmployee(
        name=name, title=headline, profile_url=profile_url,
        company_slug=slug, scraped_at=now,
    )

    # Parse education
    education = []
    for edu in item.get('education', []):
        school = edu.get('schoolName') or ''
        if not school:
            continue
        start_date = edu.get('startDate') or {}
        end_date = edu.get('endDate') or {}
        education.append(Education(
            school=school,
            degree=edu.get('degree'),
            field_of_study=edu.get('fieldOfStudy'),
            start_year=start_date.get('year'),
            end_year=end_date.get('year'),
        ))

    # Parse experience
    experience = []
    for exp in item.get('experience', []):
        company = exp.get('companyName') or ''
        title = exp.get('position') or ''
        start_date = exp.get('startDate') or {}
        end_date = exp.get('endDate') or {}
        def _parse_month(m: Any) -> int:
            if m is None:
                return 1
            try:
                return int(m)
            except (ValueError, TypeError):
                return 1

        start_str = f"{start_date['year']}-{_parse_month(start_date.get('month')):02d}" if start_date.get('year') else None
        end_str = f"{end_date['year']}-{_parse_month(end_date.get('month')):02d}" if end_date.get('year') else None
        experience.append(Experience(
            company=company,
            title=title,
            location=exp.get('location'),
            start_date=start_str,
            end_date=end_str,
            is_current=not end_str,
            description=exp.get('description'),
        ))

    profile = LinkedInProfile(
        profile_id=profile_id,
        profile_url=profile_url,
        name=name,
        headline=headline,
        location=(item.get('location') or {}).get('default') if isinstance(item.get('location'), dict) else item.get('location'),
        connections=item.get('connectionsCount'),
        about=item.get('about'),
        education=education,
        experience=experience,
        skills=[s.get('name', s) if isinstance(s, dict) else s for s in item.get('skills', [])],
        languages=[l.get('name', l) if isinstance(l, dict) else l for l in item.get('languages', [])],
        company_slug=slug,
        scraped_at=now,
    )

    return employee, profile


def enriched_to_profile(item: dict[str, Any], slug: str) -> tuple[LinkedInEmployee, LinkedInProfile]:
    """Convert an Apify supreme_coder enriched profile to LinkedInEmployee + LinkedInProfile.

    Enriched format uses: positions[].company/positions[].title/timePeriod,
    educations[].schoolName/degreeName/fieldOfStudy/timePeriod.
    """
    now = datetime.now(timezone.utc).isoformat()
    name = f"{item.get('firstName', '')} {item.get('lastName', '')}".strip()
    headline = item.get('headline', '')
    profile_url = item.get('inputUrl', '')
    profile_id = item.get('publicIdentifier') or name.lower().replace(' ', '-')

    employee = LinkedInEmployee(
        name=name, title=headline, profile_url=profile_url,
        company_slug=slug, scraped_at=now,
    )

    # Parse education
    education = []
    for edu in item.get('educations', []):
        school = edu.get('schoolName') or ''
        if not school:
            continue
        tp = edu.get('timePeriod') or {}
        education.append(Education(
            school=school,
            degree=edu.get('degreeName'),
            field_of_study=edu.get('fieldOfStudy'),
            start_year=tp.get('startDate', {}).get('year') if isinstance(tp.get('startDate'), dict) else None,
            end_year=tp.get('endDate', {}).get('year') if isinstance(tp.get('endDate'), dict) else None,
        ))

    # Parse experience — nested: positions[].company + positions[].positions[].title
    experience = []
    for pos_group in item.get('positions', []):
        raw_co = pos_group.get('company') or ''
        company = raw_co.get('name', '') if isinstance(raw_co, dict) else raw_co
        for pos in pos_group.get('positions', []):
            title = pos.get('title') or ''
            tp = pos.get('timePeriod') or {}
            start = tp.get('startDate') or {}
            end = tp.get('endDate') or {}
            start_str = f"{start['year']}-{start.get('month', 1):02d}" if start.get('year') else None
            end_str = f"{end['year']}-{end.get('month', 1):02d}" if end.get('year') else None
            experience.append(Experience(
                company=company,
                title=title,
                location=pos_group.get('locationName'),
                start_date=start_str,
                end_date=end_str,
                is_current=not end_str,
                description=pos.get('description'),
            ))

    profile = LinkedInProfile(
        profile_id=profile_id,
        profile_url=profile_url,
        name=name,
        headline=headline,
        location=item.get('geoLocationName'),
        connections=item.get('connectionsCount'),
        about=None,
        education=education,
        experience=experience,
        skills=[s.get('name', s) if isinstance(s, dict) else s for s in item.get('skills', [])],
        languages=[l.get('name', l) if isinstance(l, dict) else l for l in item.get('languages', [])],
        company_slug=slug,
        scraped_at=now,
    )

    return employee, profile


@dataclass
class FundPeopleStats:
    """Aggregated people statistics for a fund."""

    fund_slug: str
    fund_name: str
    scraped_at: str
    total_employees: int

    # Seniority breakdown
    partners: int = 0
    managing_directors: int = 0
    principals: int = 0
    directors: int = 0
    vice_presidents: int = 0
    associates: int = 0
    analysts: int = 0
    other_roles: int = 0

    # Background breakdown
    background_ib: int = 0
    background_pe: int = 0
    background_vc: int = 0
    background_consulting: int = 0
    background_big_four: int = 0
    background_corporate: int = 0
    background_tech: int = 0
    background_legal: int = 0
    background_other: int = 0

    # Education
    education_schools: dict[str, int] = field(default_factory=dict)
    top_degrees: dict[str, int] = field(default_factory=dict)
    top_majors: dict[str, int] = field(default_factory=dict)
    top_mba_count: int = 0
    top_undergrad_count: int = 0

    # Hiring patterns
    new_hires_last_6mo: int = 0
    new_hires_last_12mo: int = 0
    new_hires_last_24mo: int = 0
    new_hires_last_36mo: int = 0
    new_hires_last_48mo: int = 0
    avg_tenure_years: float | None = None

    # Demographics
    gender_male_pct: float | None = None
    gender_female_pct: float | None = None
    avg_years_experience: float | None = None

    # Raw data for further analysis
    employee_list: list[dict] = field(default_factory=list)
    profile_summaries: list[dict] = field(default_factory=list)


def _count_new_hires(
    employees: list[LinkedInEmployee],
    profiles: list[LinkedInProfile],
    months: int = 6,
) -> int:
    """Count employees who started within the given months."""
    cutoff_year = datetime.now().year
    cutoff_month = datetime.now().month - months
    while cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1

    count = 0
    for profile in profiles:
        for exp in profile.experience:
            if exp.is_current and exp.start_date:
                try:
                    parts = exp.start_date.split("-")
                    year = int(parts[0])
                    month = int(parts[1]) if len(parts) > 1 else 1

                    if year > cutoff_year or (year == cutoff_year and month >= cutoff_month):
                        count += 1
                        break
                except (ValueError, IndexError):
                    continue

    return count


def _extract_school_counts(profiles: list[LinkedInProfile]) -> dict[str, int]:
    """Extract school name frequency."""
    schools = Counter()
    for profile in profiles:
        for edu in profile.education:
            if edu.school:
                # Normalize school name
                school = edu.school.strip()
                school = school.replace("Università", "University")
                schools[school] += 1

    # Return top 10
    return dict(schools.most_common(10))


def _extract_degree_counts(profiles: list[LinkedInProfile]) -> dict[str, int]:
    """Extract degree type frequency."""
    degrees = Counter()
    for profile in profiles:
        for edu in profile.education:
            if edu.degree:
                degrees[edu.degree] += 1

    # Return top 10
    return dict(degrees.most_common(10))


_MAJOR_RULES: list[tuple[str, re.Pattern]] = [
    ("Finance", re.compile(
        r"financ|finanz|banking|corporate finance|quantitative finance"
        r"|private equity|venture capital|investment|capital market", re.I)),
    ("Economics", re.compile(
        r"econom|economia|political economy", re.I)),
    ("Management", re.compile(
        r"management|gestione|gestionale|business admin|managerial"
        r"|mba|general management|strategy|international business"
        r"|business and management|business economics|project management"
        r"|amministrazione", re.I)),
    ("Accounting", re.compile(r"accounting|contabilit", re.I)),
    ("Law", re.compile(r"\blaw\b|giurisprudenza|legal|diritto", re.I)),
    ("Engineering", re.compile(
        r"engineer|ingegneria|nanotechnol|materials science"
        r"|aerospace|meccanica|electrical|electronic|computer engineer"
        r"|civil engineer|chemical engineer|biomedical engineer", re.I)),
    ("STEM", re.compile(
        r"math|physics|statistics|computer science|informatica"
        r"|data science|biotechnol|biochem|chemistry|biology|science"
        r"|pharmacol|architecture|architettura", re.I)),
    ("Humanities", re.compile(
        r"philosophy|history|literature|lettere|politic|international rel"
        r"|sociology|psycholog|communication|marketing|linguist"
        r"|liceo|arts\b|humanities", re.I)),
]


def _classify_major(field_of_study: str) -> str | None:
    """Classify a field-of-study string into a canonical major bucket."""
    if not field_of_study or len(field_of_study.strip()) < 2:
        return None
    for label, pattern in _MAJOR_RULES:
        if pattern.search(field_of_study):
            return label
    return None


def _extract_major_counts(profiles: list[LinkedInProfile]) -> dict[str, int]:
    """Extract field-of-study frequency, classified into canonical major buckets."""
    majors = Counter()
    for profile in profiles:
        # Count one major per person (highest degree first, skip duplicates)
        seen = set()
        for edu in profile.education:
            if edu.field_of_study:
                label = _classify_major(edu.field_of_study)
                if label and label not in seen:
                    majors[label] += 1
                    seen.add(label)
    return dict(majors.most_common(10))


def _calculate_avg_tenure(classified_profiles: list[ClassifiedProfile]) -> float | None:
    """Calculate average tenure at current position."""
    tenures = [cp.tenure_at_current for cp in classified_profiles if cp.tenure_at_current]
    if tenures:
        return round(sum(tenures) / len(tenures), 1)
    return None


def _calculate_avg_experience(classified_profiles: list[ClassifiedProfile]) -> float | None:
    """Calculate average years of experience."""
    years = [cp.years_experience for cp in classified_profiles if cp.years_experience]
    if years:
        return round(sum(years) / len(years), 1)
    return None


def _calculate_gender_split(classified_profiles: list[ClassifiedProfile]) -> tuple[float | None, float | None]:
    """Calculate gender percentages."""
    known = [cp for cp in classified_profiles if cp.estimated_gender in ("male", "female")]
    if not known:
        return None, None

    male = sum(1 for cp in known if cp.estimated_gender == "male")
    female = len(known) - male

    total = len(known)
    return round(male / total * 100, 1), round(female / total * 100, 1)


class PeopleStatsCalculator:
    """
    Calculator for fund people statistics.

    Aggregates employee and profile data into fund-level statistics.
    """

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or Path("data/derived/linkedin")
        self.classifier = ProfileClassifier()

    def calculate_stats(
        self,
        fund_slug: str,
        fund_name: str,
        employees: list[LinkedInEmployee],
        profiles: list[LinkedInProfile],
    ) -> FundPeopleStats:
        """
        Calculate statistics for a single fund.

        Args:
            fund_slug: Fund identifier
            fund_name: Fund display name
            employees: List of employees from LinkedIn
            profiles: List of full profiles (subset of employees)

        Returns:
            FundPeopleStats with aggregated statistics
        """
        # Filter out non-investment-relevant profiles (IT, HR, admin, secretaries)
        # before classification — they skew background and seniority analytics.
        relevant_profiles = [p for p in profiles if is_investment_relevant(p)]

        # Classify profiles
        classified = self.classifier.classify_batch(relevant_profiles)

        # Count seniority levels
        seniority_counts = {level: 0 for level in SeniorityLevel}
        for cp in classified:
            seniority_counts[cp.current_seniority] += 1

        # Count backgrounds (merge STARTUP into VENTURE_CAPITAL for web display)
        background_counts = {bt: 0 for bt in BackgroundType}
        for cp in classified:
            bg = cp.primary_background
            if bg == BackgroundType.STARTUP:
                bg = BackgroundType.VENTURE_CAPITAL
            background_counts[bg] += 1

        # Education tier counts
        top_mba = sum(1 for cp in classified if cp.education_tier == "top_mba")
        top_undergrad = sum(1 for cp in classified if cp.education_tier == "top_undergrad")

        # Gender split
        male_pct, female_pct = _calculate_gender_split(classified)

        # Create employee summaries for storage
        employee_list = [asdict(e) for e in employees]
        profile_summaries = []
        for cp in classified:
            profile_summaries.append({
                "name": cp.profile.name,
                "headline": cp.profile.headline,
                "profile_url": cp.profile.profile_url,
                "primary_background": cp.primary_background.value,
                "seniority": cp.current_seniority.value,
                "years_experience": cp.years_experience,
                "tenure": cp.tenure_at_current,
                "education_tier": cp.education_tier,
                "estimated_gender": cp.estimated_gender,
            })

        return FundPeopleStats(
            fund_slug=fund_slug,
            fund_name=fund_name,
            scraped_at=datetime.now(timezone.utc).isoformat(),
            total_employees=len(employees),

            # Seniority
            partners=seniority_counts[SeniorityLevel.PARTNER],
            managing_directors=seniority_counts[SeniorityLevel.MANAGING_DIRECTOR],
            principals=seniority_counts[SeniorityLevel.PRINCIPAL],
            directors=seniority_counts[SeniorityLevel.DIRECTOR],
            vice_presidents=seniority_counts[SeniorityLevel.VICE_PRESIDENT],
            associates=seniority_counts[SeniorityLevel.ASSOCIATE],
            analysts=seniority_counts[SeniorityLevel.ANALYST],
            other_roles=seniority_counts[SeniorityLevel.OTHER],

            # Backgrounds
            background_ib=background_counts[BackgroundType.INVESTMENT_BANKING],
            background_pe=background_counts[BackgroundType.PRIVATE_EQUITY],
            background_vc=background_counts[BackgroundType.VENTURE_CAPITAL],
            background_consulting=background_counts[BackgroundType.CONSULTING],
            background_big_four=background_counts[BackgroundType.BIG_FOUR],
            background_corporate=background_counts[BackgroundType.CORPORATE],
            background_tech=background_counts[BackgroundType.TECH],
            background_legal=background_counts[BackgroundType.LEGAL],
            background_other=background_counts[BackgroundType.OTHER],

            # Education
            education_schools=_extract_school_counts(relevant_profiles),
            top_degrees=_extract_degree_counts(relevant_profiles),
            top_majors=_extract_major_counts(relevant_profiles),
            top_mba_count=top_mba,
            top_undergrad_count=top_undergrad,

            # Hiring
            new_hires_last_6mo=_count_new_hires(employees, relevant_profiles, months=6),
            new_hires_last_12mo=_count_new_hires(employees, relevant_profiles, months=12),
            new_hires_last_24mo=_count_new_hires(employees, relevant_profiles, months=24),
            new_hires_last_36mo=_count_new_hires(employees, relevant_profiles, months=36),
            new_hires_last_48mo=_count_new_hires(employees, relevant_profiles, months=48),
            avg_tenure_years=_calculate_avg_tenure(classified),

            # Demographics
            gender_male_pct=male_pct,
            gender_female_pct=female_pct,
            avg_years_experience=_calculate_avg_experience(classified),

            # Raw data
            employee_list=employee_list,
            profile_summaries=profile_summaries,
        )

    def calculate_batch(
        self,
        fund_data: list[dict[str, Any]],
    ) -> list[FundPeopleStats]:
        """
        Calculate stats for multiple funds.

        Args:
            fund_data: List of dicts with 'slug', 'name', 'employees', 'profiles'

        Returns:
            List of FundPeopleStats
        """
        all_stats = []
        for fund in fund_data:
            stats = self.calculate_stats(
                fund_slug=fund["slug"],
                fund_name=fund.get("name", fund["slug"]),
                employees=fund.get("employees", []),
                profiles=fund.get("profiles", []),
            )
            all_stats.append(stats)

        return all_stats

    def save_stats(
        self,
        stats: list[FundPeopleStats],
        filename: str = "fund_people_stats.json",
    ) -> Path:
        """
        Save fund stats to JSON file.

        Args:
            stats: List of FundPeopleStats
            filename: Output filename

        Returns:
            Path to saved file
        """
        output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to JSON-serializable format
        data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fund_count": len(stats),
            "funds": {},
        }

        for s in stats:
            fund_dict = asdict(s)
            # Remove large raw data from main output
            fund_dict.pop("employee_list", None)
            fund_dict.pop("profile_summaries", None)
            data["funds"][s.fund_slug] = fund_dict

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved stats for {len(stats)} funds to {output_path}")
        return output_path

    def save_detailed_stats(
        self,
        stats: list[FundPeopleStats],
        filename: str = "fund_people_stats_detailed.json",
    ) -> Path:
        """Save stats including employee lists and profile summaries."""
        output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fund_count": len(stats),
            "funds": {s.fund_slug: asdict(s) for s in stats},
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved detailed stats for {len(stats)} funds to {output_path}")
        return output_path

    def load_stats(self, filename: str = "fund_people_stats.json") -> dict[str, FundPeopleStats]:
        """Load stats from JSON file."""
        input_path = self.output_dir / filename

        if not input_path.exists():
            logger.warning(f"Stats file not found: {input_path}")
            return {}

        with open(input_path) as f:
            data = json.load(f)

        stats = {}
        for slug, fund_data in data.get("funds", {}).items():
            stats[slug] = FundPeopleStats(**fund_data)

        return stats

    def generate_summary_report(
        self,
        stats: list[FundPeopleStats],
    ) -> dict[str, Any]:
        """
        Generate aggregate summary across all funds.

        Args:
            stats: List of FundPeopleStats

        Returns:
            Summary statistics dict
        """
        if not stats:
            return {}

        total_employees = sum(s.total_employees for s in stats)
        total_partners = sum(s.partners for s in stats)
        total_associates = sum(s.associates for s in stats)
        total_analysts = sum(s.analysts for s in stats)

        # Aggregate backgrounds
        bg_totals = {
            "investment_banking": sum(s.background_ib for s in stats),
            "private_equity": sum(s.background_pe for s in stats),
            "venture_capital": sum(s.background_vc for s in stats),
            "consulting": sum(s.background_consulting for s in stats),
            "big_four": sum(s.background_big_four for s in stats),
            "corporate": sum(s.background_corporate for s in stats),
            "tech": sum(s.background_tech for s in stats),
        }

        # Average gender split (only from funds with data)
        male_pcts = [s.gender_male_pct for s in stats if s.gender_male_pct is not None]
        female_pcts = [s.gender_female_pct for s in stats if s.gender_female_pct is not None]

        return {
            "fund_count": len(stats),
            "total_employees_tracked": total_employees,
            "seniority_totals": {
                "partners": total_partners,
                "associates": total_associates,
                "analysts": total_analysts,
            },
            "background_totals": bg_totals,
            "education": {
                "total_top_mba": sum(s.top_mba_count for s in stats),
                "total_top_undergrad": sum(s.top_undergrad_count for s in stats),
            },
            "hiring": {
                "total_new_hires_6mo": sum(s.new_hires_last_6mo for s in stats),
                "total_new_hires_12mo": sum(s.new_hires_last_12mo for s in stats),
            },
            "demographics": {
                "avg_male_pct": round(sum(male_pcts) / len(male_pcts), 1) if male_pcts else None,
                "avg_female_pct": round(sum(female_pcts) / len(female_pcts), 1) if female_pcts else None,
            },
        }
