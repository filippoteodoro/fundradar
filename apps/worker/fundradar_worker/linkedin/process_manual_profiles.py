"""
Process manually-curated LinkedIn profiles for mega-funds.

Reads manual_profiles.json, classifies profiles using the existing pipeline,
and merges results into fund_people_stats.json.

Two modes:
  --basic   : Classify from title only (no cost, limited background data)
  --enrich  : Call Apify profile_scraper to get full profiles first (~$0.008/profile)

Usage:
  python -m fundradar_worker.linkedin.process_manual_profiles --basic
  python -m fundradar_worker.linkedin.process_manual_profiles --enrich
  python -m fundradar_worker.linkedin.process_manual_profiles --enrich --slugs blackstone,carlyle
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .people_scraper import LinkedInProfile, LinkedInEmployee, Experience, Education
from .people_stats import PeopleStatsCalculator, FundPeopleStats
from .profile_classifier import ProfileClassifier

logger = logging.getLogger(__name__)

LINKEDIN_DIR = Path("data/derived/linkedin")
MANUAL_FILE = LINKEDIN_DIR / "manual_profiles.json"
STATS_FILE = LINKEDIN_DIR / "fund_people_stats.json"


def _normalize_linkedin_url(url: str) -> str:
    """Normalize LinkedIn URL for dedup (strip trailing slash, /en/, locale prefix)."""
    url = url.rstrip("/")
    # Strip /en/ or other locale suffixes
    for suffix in ("/en", "/it", "/fr", "/de"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    # Normalize locale subdomains
    for prefix in ("https://it.", "https://uk.", "https://fr.", "https://ca.", "https://de."):
        if url.startswith(prefix):
            url = "https://www." + url[len(prefix) :]
    return url.rstrip("/")


def load_manual_profiles() -> list[dict[str, Any]]:
    """Load and validate manual_profiles.json."""
    if not MANUAL_FILE.exists():
        logger.error(f"Manual profiles file not found: {MANUAL_FILE}")
        sys.exit(1)

    with open(MANUAL_FILE) as f:
        data = json.load(f)

    funds = data.get("funds", [])
    logger.info(f"Loaded {len(funds)} funds from {MANUAL_FILE}")

    # Dedup people within each fund by LinkedIn URL
    for fund in funds:
        seen_urls = set()
        deduped = []
        for person in fund.get("people", []):
            url = _normalize_linkedin_url(person.get("linkedin", ""))
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduped.append(person)
        fund["people"] = deduped

    total = sum(len(f["people"]) for f in funds)
    logger.info(f"Total unique profiles: {total}")
    return funds


def manual_to_profiles(fund: dict[str, Any]) -> tuple[list[LinkedInEmployee], list[LinkedInProfile]]:
    """
    Convert manual profile data to LinkedInEmployee + LinkedInProfile objects.

    Creates synthetic experience entries from the title so the classifier
    can extract seniority and basic background.
    """
    firm = fund["firm"]
    slug = fund["slug"]
    now = datetime.now(timezone.utc).isoformat()

    employees = []
    profiles = []

    for person in fund.get("people", []):
        name = person["name"]
        title = person.get("title", "")
        location = person.get("location", "")
        linkedin_url = person.get("linkedin", "")

        # Create employee record
        employees.append(LinkedInEmployee(
            name=name,
            title=title,
            profile_url=linkedin_url,
            company_slug=slug,
            scraped_at=now,
        ))

        # Create profile with synthetic experience
        # Extract profile ID from URL
        profile_id = linkedin_url.rstrip("/").split("/")[-1] if linkedin_url else name.lower().replace(" ", "-")

        # Create a synthetic current experience entry
        current_exp = Experience(
            company=firm,
            title=title,
            location=location,
            start_date=None,
            end_date=None,
            is_current=True,
            description=None,
        )

        profile = LinkedInProfile(
            profile_id=profile_id,
            profile_url=linkedin_url,
            name=name,
            headline=title,
            location=location,
            connections=None,
            about=None,
            education=[],
            experience=[current_exp],
            skills=[],
            languages=[],
            company_slug=slug,
            scraped_at=now,
        )
        profiles.append(profile)

    return employees, profiles


def enrich_with_apify(
    funds: list[dict[str, Any]],
    slugs_filter: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Enrich manual profiles by calling Apify profile_scraper.

    Returns dict of slug -> list of Apify profile results.
    """
    from .apify_client import ApifyClient, ApifyConfig, save_raw_data

    config = ApifyConfig.from_env()
    client = ApifyClient(config)

    enriched = {}
    total_cost = 0.0

    for fund in funds:
        slug = fund["slug"]
        if slugs_filter and slug not in slugs_filter:
            continue

        people = fund.get("people", [])
        urls = [p["linkedin"] for p in people if p.get("linkedin")]

        if not urls:
            continue

        logger.info(f"Enriching {len(urls)} profiles for {fund['firm']}...")

        result = client.scrape_profiles_batch(urls)

        if result.status == "SUCCEEDED" and result.items:
            logger.info(
                f"  Got {len(result.items)} enriched profiles "
                f"(cost: ${result.cost_usd:.3f}, {result.duration_secs:.0f}s)"
            )
            enriched[slug] = result.items
            total_cost += result.cost_usd

            # Save raw data
            raw_path = LINKEDIN_DIR / "raw" / f"{slug}_enriched_profiles.json"
            save_raw_data(result.items, raw_path, "enriched_profiles")
        else:
            logger.warning(f"  Failed: {result.status} - {result.error}")

        # Rate limit between funds
        time.sleep(2)

    logger.info(f"Total enrichment cost: ${total_cost:.3f}")
    return enriched


def apify_to_profile(item: dict[str, Any], slug: str) -> LinkedInProfile:
    """Convert an Apify profile scraper result to LinkedInProfile.

    Handles supreme_coder/linkedin-profile-scraper format:
    - positions: [{company: {name}, positions: [{title, timePeriod: {startDate, endDate}}]}]
    - educations: [{school: {name}, degreeName, fieldOfStudy, timePeriod}]
    """
    now = datetime.now(timezone.utc).isoformat()

    # Extract education (field is "educations" in supreme_coder format)
    education = []
    for edu in item.get("educations", item.get("education", [])):
        school_obj = edu.get("school", {}) or {}
        tp = edu.get("timePeriod", {}) or {}
        education.append(Education(
            school=school_obj.get("name") or edu.get("schoolName") or edu.get("school") or "",
            degree=edu.get("degreeName") or edu.get("degree"),
            field_of_study=edu.get("fieldOfStudy") or edu.get("field"),
            start_year=_safe_int((tp.get("startDate") or {}).get("year") or edu.get("startYear")),
            end_year=_safe_int((tp.get("endDate") or {}).get("year") or edu.get("endYear")),
        ))

    # Extract experience — supreme_coder nests positions inside company groups
    experience = []
    for pos_group in item.get("positions", []):
        company_obj = pos_group.get("company", {}) or {}
        company_name = company_obj.get("name") or pos_group.get("companyName") or ""
        # Each group has sub-positions (roles at same company)
        sub_positions = pos_group.get("positions", [])
        if sub_positions:
            for pos in sub_positions:
                tp = pos.get("timePeriod", {}) or {}
                start = tp.get("startDate", {}) or {}
                end = tp.get("endDate", {}) or {}
                start_date = f"{start['year']}-{start.get('month', 1):02d}" if start.get("year") else None
                end_date = f"{end['year']}-{end.get('month', 1):02d}" if end.get("year") else None
                experience.append(Experience(
                    company=company_name,
                    title=pos.get("title") or "",
                    location=pos.get("locationName"),
                    start_date=start_date,
                    end_date=end_date,
                    is_current=not end_date,
                    description=pos.get("description") or None,
                ))
        else:
            # Flat format fallback
            experience.append(Experience(
                company=company_name,
                title=pos_group.get("title") or "",
                location=pos_group.get("locationName"),
                start_date=None,
                end_date=None,
                is_current=True,
                description=None,
            ))

    # Build profile URL from publicIdentifier if not provided
    profile_url = item.get("inputUrl") or item.get("profileUrl") or item.get("url") or ""
    if not profile_url and item.get("publicIdentifier"):
        profile_url = f"https://www.linkedin.com/in/{item['publicIdentifier']}/"

    return LinkedInProfile(
        profile_id=item.get("publicIdentifier") or item.get("profileId") or "",
        profile_url=profile_url,
        name=item.get("fullName") or f"{item.get('firstName', '')} {item.get('lastName', '')}".strip(),
        headline=item.get("headline"),
        location=item.get("geoLocationName") or item.get("locationName"),
        connections=_safe_int(item.get("connectionsCount")),
        about=item.get("summary"),
        education=education,
        experience=experience,
        skills=[s.get("name", s) if isinstance(s, dict) else s for s in item.get("skills", [])],
        languages=[l.get("name", l) if isinstance(l, dict) else l for l in item.get("languages", [])],
        company_slug=slug,
        scraped_at=now,
    )


def _safe_int(val: Any) -> int | None:
    """Safely convert to int."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _stats_to_web_format(stats: FundPeopleStats) -> dict[str, Any]:
    """Convert FundPeopleStats to the nested TeamAnalytics format the web app expects."""
    return {
        "fund_slug": stats.fund_slug,
        "total_profiles": stats.total_employees,
        "education": {
            "top_schools": stats.education_schools,
            "top_degrees": stats.top_degrees,
            "education_tier": {
                "top_mba": stats.top_mba_count,
                "top_undergrad": stats.top_undergrad_count,
                "other": stats.total_employees - stats.top_mba_count - stats.top_undergrad_count,
            },
        },
        "backgrounds": {
            "investment_banking": stats.background_ib,
            "private_equity": stats.background_pe,
            "venture_capital": stats.background_vc,
            "consulting": stats.background_consulting,
            "big_four": stats.background_big_four,
            "corporate": stats.background_corporate,
            "tech": stats.background_tech,
            "legal": stats.background_legal,
            "other": stats.background_other,
        },
        "seniority": {
            "partner": stats.partners,
            "managing_director": stats.managing_directors,
            "principal": stats.principals,
            "director": stats.directors,
            "vice_president": stats.vice_presidents,
            "associate": stats.associates,
            "analyst": stats.analysts,
            "other": stats.other_roles,
        },
        "hiring": {
            "new_hires_last_1y": stats.new_hires_last_12mo,
            "new_hires_last_2y": stats.new_hires_last_6mo + stats.new_hires_last_12mo,
            "avg_tenure_years": stats.avg_tenure_years or 0,
        },
        "demographics": {
            "gender_male_pct": stats.gender_male_pct or 0,
            "gender_female_pct": stats.gender_female_pct or 0,
            "gender_unknown_pct": 0,
            "avg_years_experience": stats.avg_years_experience or 0,
            "avg_estimated_age": 0,
        },
    }


def merge_stats(new_stats: list[FundPeopleStats]) -> None:
    """Merge new stats into existing fund_people_stats.json (web-compatible format)."""
    existing = {}
    if STATS_FILE.exists():
        with open(STATS_FILE) as f:
            data = json.load(f)
        existing = data.get("funds", {})

    # Merge: new stats overwrite existing for same slug
    for stats in new_stats:
        existing[stats.fund_slug] = _stats_to_web_format(stats)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fund_count": len(existing),
        "funds": existing,
    }

    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATS_FILE, "w") as f:
        json.dump(output, f, indent=2)

    logger.info(f"Saved stats for {len(existing)} funds to {STATS_FILE}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Process manual LinkedIn profiles")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--basic", action="store_true", help="Classify from title only (no cost)")
    mode.add_argument("--enrich", action="store_true", help="Enrich via Apify first (~$0.008/profile)")
    parser.add_argument("--slugs", help="Comma-separated fund slugs to process (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without writing")
    args = parser.parse_args()

    slugs_filter = set(args.slugs.split(",")) if args.slugs else None

    # Load manual profiles
    funds = load_manual_profiles()

    if slugs_filter:
        funds = [f for f in funds if f["slug"] in slugs_filter]
        logger.info(f"Filtered to {len(funds)} funds: {[f['slug'] for f in funds]}")

    if not funds:
        logger.error("No funds to process")
        sys.exit(1)

    # Optional Apify enrichment
    enriched_data: dict[str, list[dict[str, Any]]] = {}
    if args.enrich:
        enriched_data = enrich_with_apify(funds, slugs_filter)

    # Process each fund
    calculator = PeopleStatsCalculator(output_dir=LINKEDIN_DIR)
    all_stats = []

    for fund in funds:
        slug = fund["slug"]
        firm = fund["firm"]

        if slug in enriched_data and enriched_data[slug]:
            # Use Apify-enriched profiles
            logger.info(f"Processing {firm} with {len(enriched_data[slug])} enriched profiles")
            profiles = [apify_to_profile(item, slug) for item in enriched_data[slug]]
            employees = [
                LinkedInEmployee(
                    name=p.name,
                    title=p.headline or "",
                    profile_url=p.profile_url,
                    company_slug=slug,
                    scraped_at=p.scraped_at or "",
                )
                for p in profiles
            ]
        else:
            # Use basic manual data
            logger.info(f"Processing {firm} with {len(fund['people'])} manual profiles (basic)")
            employees, profiles = manual_to_profiles(fund)

        stats = calculator.calculate_stats(
            fund_slug=slug,
            fund_name=firm,
            employees=employees,
            profiles=profiles,
        )

        # Log summary
        logger.info(
            f"  {firm}: {stats.total_employees} people | "
            f"Partners:{stats.partners} MD:{stats.managing_directors} "
            f"Principal:{stats.principals} Dir:{stats.directors} "
            f"VP:{stats.vice_presidents} Assoc:{stats.associates} "
            f"Analyst:{stats.analysts}"
        )

        all_stats.append(stats)

    if args.dry_run:
        logger.info("Dry run — not writing to disk")
        for stats in all_stats:
            print(f"\n{stats.fund_name} ({stats.fund_slug}):")
            print(f"  Team size: {stats.total_employees}")
            print(f"  Seniority: P={stats.partners} MD={stats.managing_directors} "
                  f"Pr={stats.principals} D={stats.directors} VP={stats.vice_presidents} "
                  f"A={stats.associates} An={stats.analysts} O={stats.other_roles}")
            print(f"  Gender: M={stats.gender_male_pct}% F={stats.gender_female_pct}%")
        return

    # Merge into existing stats
    merge_stats(all_stats)
    logger.info(f"Done! Processed {len(all_stats)} funds, {sum(s.total_employees for s in all_stats)} total profiles")


if __name__ == "__main__":
    main()
