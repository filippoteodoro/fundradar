"""
Geocode fund addresses/cities to lat/lng coordinates.

Reads AIFI member data (with address and city fields) and geocodes
each fund using Nominatim (OpenStreetMap, free, no API key).

Rate limited to 1 request/second per Nominatim usage policy.

Output: data/derived/fund_coordinates.json
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
AIFI_MEMBERS_PATH = PROJECT_ROOT / "data" / "derived" / "aifi_members.json"
DB_PATH = PROJECT_ROOT / "data" / "db.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "derived" / "fund_coordinates.json"

# Nominatim rate limit: 1 request per second
RATE_LIMIT_SECONDS = 1.1

# Non-Italian cities that appear in the fund DB (hq_region may incorrectly say "Italy")
NON_ITALIAN_CITIES: dict[str, str] = {
    "london": "UK",
    "londra": "UK",
    "paris": "France",
    "parigi": "France",
    "luxembourg": "Luxembourg",
    "lussemburgo": "Luxembourg",
    "new york": "USA",
    "amsterdam": "Netherlands",
    "madrid": "Spain",
    "zurich": "Switzerland",
    "zurigo": "Switzerland",
    "munich": "Germany",
    "monaco di baviera": "Germany",
    "frankfurt": "Germany",
    "francoforte": "Germany",
    "brussels": "Belgium",
    "bruxelles": "Belgium",
    "barcelona": "Spain",
    "barcellona": "Spain",
}


def geocode_funds(dry_run: bool = False) -> None:
    """Geocode all funds from AIFI data and db.json."""
    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError
    except ImportError:
        logger.error("geopy not installed. Run: pip install geopy")
        raise

    geocoder = Nominatim(
        user_agent="Fundradar/1.0 (https://fundradar.io; research-geocoding)",
        timeout=10,
    )

    # Load existing coordinates to avoid re-geocoding
    existing: dict[str, dict] = {}
    if OUTPUT_PATH.exists():
        try:
            existing = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            logger.info(f"Loaded {len(existing)} existing coordinates")
        except (json.JSONDecodeError, OSError):
            pass

    # Load AIFI members for address data
    aifi_members: list[dict] = []
    if AIFI_MEMBERS_PATH.exists():
        try:
            data = json.loads(AIFI_MEMBERS_PATH.read_text(encoding="utf-8"))
            aifi_members = data.get("members", [])
            logger.info(f"Loaded {len(aifi_members)} AIFI members")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load AIFI members: {e}")

    # Load db.json for all funds (including non-AIFI)
    db_funds: list[dict] = []
    if DB_PATH.exists():
        try:
            data = json.loads(DB_PATH.read_text(encoding="utf-8"))
            db_funds = data.get("funds", [])
            logger.info(f"Loaded {len(db_funds)} funds from db.json")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load db.json: {e}")

    # Build slug → address/city lookup from AIFI data
    aifi_by_slug: dict[str, dict] = {}
    for member in aifi_members:
        slug = member.get("slug", "")
        if slug:
            aifi_by_slug[slug] = member

    # Collect all funds to geocode
    funds_to_geocode: list[dict] = []
    for fund in db_funds:
        slug = fund.get("slug", "")
        if not slug:
            continue

        # Skip if already geocoded
        if slug in existing and existing[slug].get("lat") is not None:
            continue

        city = fund.get("hq_city")
        address = None

        # Check AIFI data for address
        aifi = aifi_by_slug.get(slug)
        if aifi:
            address = aifi.get("address")
            if not city:
                city = aifi.get("city")

        if not city:
            continue  # No location data at all

        # Determine correct country — hq_region may say "Italy" for funds
        # headquartered abroad (e.g. London-based funds with AIFI membership)
        country = fund.get("hq_region", "Italy")
        city_lower = city.lower().strip()
        if city_lower in NON_ITALIAN_CITIES:
            country = NON_ITALIAN_CITIES[city_lower]

        funds_to_geocode.append({
            "slug": slug,
            "address": address,
            "city": city,
            "country": country,
        })

    logger.info(f"Funds to geocode: {len(funds_to_geocode)}")

    if dry_run:
        for f in funds_to_geocode[:20]:
            addr = f["address"] or "(no address)"
            print(f"  {f['slug']}: {addr}, {f['city']}")
        if len(funds_to_geocode) > 20:
            print(f"  ... and {len(funds_to_geocode) - 20} more")
        return

    coordinates = dict(existing)
    geocoded = 0
    failed = 0

    for i, fund in enumerate(funds_to_geocode):
        slug = fund["slug"]
        address = fund["address"]
        city = fund["city"]
        country = fund["country"] or "Italy"

        # Try street address first, then city-level
        queries = []
        if address:
            queries.append((f"{address}, {city}, {country}", "address"))
        queries.append((f"{city}, {country}", "city"))

        result = None
        source = "city"

        for query, query_source in queries:
            try:
                logger.info(f"[{i+1}/{len(funds_to_geocode)}] Geocoding {slug}: {query}")
                location = geocoder.geocode(query)
                if location:
                    result = location
                    source = query_source
                    break
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                logger.warning(f"Geocoding error for {slug} ({query}): {e}")
            except Exception as e:
                logger.warning(f"Unexpected geocoding error for {slug}: {e}")

            time.sleep(RATE_LIMIT_SECONDS)

        if result:
            coordinates[slug] = {
                "lat": round(result.latitude, 6),
                "lng": round(result.longitude, 6),
                "source": source,
                "query": queries[0][0] if source == "address" else f"{city}, {country}",
            }
            geocoded += 1
            logger.info(f"  -> {result.latitude:.6f}, {result.longitude:.6f} ({source})")
        else:
            coordinates[slug] = {
                "lat": None,
                "lng": None,
                "source": "failed",
                "query": queries[0][0],
            }
            failed += 1
            logger.warning(f"  -> FAILED to geocode {slug}")

        time.sleep(RATE_LIMIT_SECONDS)

    # Write output using safe_json_write
    from fundradar_worker.io_utils import safe_json_write
    safe_json_write(OUTPUT_PATH, coordinates)

    logger.info(f"Done! Geocoded: {geocoded}, Failed: {failed}, Total: {len(coordinates)}")
    logger.info(f"Output: {OUTPUT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Geocode fund addresses/cities to lat/lng coordinates"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be geocoded without making requests",
    )
    args = parser.parse_args()

    geocode_funds(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
