"""
Priority ranking for LinkedIn scraping.

Ranks funds by importance for Italy PE/VC coverage to ensure
the most valuable funds are scraped first if budget runs out.
"""

import json
from datetime import date
from pathlib import Path
from dataclasses import dataclass


@dataclass
class FundPriority:
    """Fund with priority score for scraping order."""
    slug: str
    name: str
    linkedin_url: str
    priority_score: float
    priority_reasons: list[str]


def calculate_priority(fund_data: dict, aifi_data: dict | None, deals_count: int, in_db: bool = True) -> tuple[float, list[str]]:
    """
    Calculate priority score for a fund.

    Higher score = higher priority = scrape first.
    Tuned for Italian PE audience: mid-market Italian SGRs rank above
    global mega-fund satellite offices.

    Factors:
    - Italian HQ: +25 (biggest differentiator for audience value)
    - AUM: +0-40 (capped — mega-AUM doesn't dominate)
    - Category (PE/VC): +15
    - Active dealmaker (5+ PEM deals): +10
    - AIFI membership: +10 (confirms genuine Italy presence)
    - Deal count: +0-25
    - db.json match: +5 (ensures data can be displayed)
    - Not in db.json: score capped at 0
    """
    score = 0.0
    reasons = []

    # Funds not in db.json get score capped at 0 (no page to display data)
    if not in_db:
        return 0.0, ["Not in db.json (no fund page)"]

    # db.json match bonus
    score += 5
    reasons.append("In db.json")

    # Italian HQ (from AIFI or fund data) — biggest differentiator
    city = ""
    if aifi_data:
        city = (aifi_data.get("city") or "").lower()
    if not city:
        city = (fund_data.get("hq_city") or "").lower()

    italian_cities = ["milano", "milan", "roma", "rome", "torino", "turin",
                     "treviso", "bologna", "firenze", "florence", "napoli",
                     "verona", "padova", "brescia", "bergamo", "genova",
                     "vicenza", "modena", "parma", "udine", "trieste",
                     "bari", "catania", "palermo", "cagliari"]
    if city and any(c in city for c in italian_cities):
        score += 25
        reasons.append(f"Italy HQ ({city.title()})")

    # Get AUM from either aifi_data or fund_data
    aum = 0
    if aifi_data and aifi_data.get("aum_eur"):
        aum = aifi_data.get("aum_eur")
    elif fund_data.get("aum_eur"):
        aum = fund_data.get("aum_eur")

    # AUM scoring (up to 40 points) — capped so mega-AUM doesn't dominate
    if aum and aum > 0:
        if aum >= 50_000_000_000:  # €50B+
            score += 40
            reasons.append("Mega AUM (€50B+)")
        elif aum >= 10_000_000_000:  # €10B+
            score += 38
            reasons.append("Large AUM (€10B+)")
        elif aum >= 5_000_000_000:  # €5B+
            score += 35
            reasons.append("AUM €5-10B")
        elif aum >= 1_000_000_000:  # €1B+
            score += 30
            reasons.append("AUM €1-5B")
        elif aum >= 500_000_000:  # €500M+
            score += 20
            reasons.append("AUM €500M-1B")
        elif aum >= 100_000_000:  # €100M+
            score += 10
            reasons.append("AUM €100-500M")

    # Category bonus — PE/VC are core employer pool for Italian PE audience
    category = fund_data.get("category", "").lower()
    if category == "pe":
        score += 15
        reasons.append("PE fund")
    elif category == "vc":
        score += 15
        reasons.append("VC fund")
    elif category == "growth":
        score += 10
        reasons.append("Growth fund")
    elif category in ["debt", "infra"]:
        score += 8
        reasons.append(f"{category.title()} fund")
    elif category in ["bank", "asset_manager"]:
        score += 3

    # Active dealmaker bonus — proves Italy activity
    if deals_count >= 5:
        score += 10
        reasons.append(f"Active dealmaker ({deals_count} deals)")

    # Deal count scoring (up to 25 points)
    if deals_count > 0:
        deal_score = min(deals_count * 3, 25)
        score += deal_score
        reasons.append(f"{deals_count} Italy deals")

    # AIFI membership — confirms genuine Italy presence
    if aifi_data:
        score += 10
        reasons.append("AIFI member")

    return score, reasons


def load_fund_deals_count(project_root: Path) -> dict[str, int]:
    """Load deal counts per fund from PEM deals."""
    deals_path = project_root / "data" / "derived" / "pem_deals.json"
    if not deals_path.exists():
        return {}

    with open(deals_path) as f:
        data = json.load(f)

    counts: dict[str, int] = {}
    for deal in data.get("deals", []):
        slug = deal.get("lead_investor_slug")
        if slug:
            counts[slug] = counts.get(slug, 0) + 1

    return counts


def rank_funds_by_priority(project_root: Path) -> list[FundPriority]:
    """
    Load all funds and rank them by scraping priority.

    Returns list of FundPriority sorted by priority_score descending.
    """
    # Load LinkedIn URLs
    linkedin_path = project_root / "data" / "derived" / "linkedin" / "fund_linkedin_urls.json"
    with open(linkedin_path) as f:
        linkedin_data = json.load(f)
    companies = linkedin_data["companies"]

    # Load AIFI enriched data
    aifi_path = project_root / "data" / "derived" / "aifi_members_enriched.json"
    aifi_by_slug: dict[str, dict] = {}
    if aifi_path.exists():
        with open(aifi_path) as f:
            aifi_data = json.load(f)
        for member in aifi_data.get("members", []):
            aifi_by_slug[member["slug"]] = member

    # Load db.json for fund categories
    db_path = project_root / "data" / "db.json"
    fund_by_slug: dict[str, dict] = {}
    if db_path.exists():
        with open(db_path) as f:
            db_data = json.load(f)
        for fund in db_data.get("funds", []):
            fund_by_slug[fund["slug"]] = fund

    # Load deal counts
    deal_counts = load_fund_deals_count(project_root)

    # Calculate priority for each fund
    priorities: list[FundPriority] = []

    for company in companies:
        slug = company["slug"]
        name = company["name"]
        linkedin_url = company["linkedin_url"]

        # Skip entries with notes (search URLs)
        if company.get("note"):
            continue

        # Get fund data
        fund_data = fund_by_slug.get(slug, {"category": "unknown"})
        aifi_data = aifi_by_slug.get(slug)
        deals_count = deal_counts.get(slug, 0)

        in_db = slug in fund_by_slug
        score, reasons = calculate_priority(fund_data, aifi_data, deals_count, in_db=in_db)

        priorities.append(FundPriority(
            slug=slug,
            name=name,
            linkedin_url=linkedin_url,
            priority_score=score,
            priority_reasons=reasons,
        ))

    # Sort by priority (highest first)
    priorities.sort(key=lambda x: x.priority_score, reverse=True)

    return priorities


def create_prioritized_linkedin_urls(project_root: Path) -> None:
    """
    Create a prioritized version of fund_linkedin_urls.json.

    Saves to fund_linkedin_urls_prioritized.json
    """
    priorities = rank_funds_by_priority(project_root)

    output = {
        "generated_at": date.today().isoformat(),
        "note": "Funds sorted by Italy PE/VC importance. Scrape in this order.",
        "matched_count": len(priorities),
        "companies": [
            {
                "slug": p.slug,
                "name": p.name,
                "linkedin_url": p.linkedin_url,
                "priority_score": round(p.priority_score, 1),
                "priority_reasons": p.priority_reasons,
            }
            for p in priorities
        ]
    }

    output_path = project_root / "data" / "derived" / "linkedin" / "fund_linkedin_urls_prioritized.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Created prioritized LinkedIn URLs: {output_path}")
    print(f"Total funds: {len(priorities)}")
    print()
    print("Top 20 priority funds:")
    for i, p in enumerate(priorities[:20], 1):
        print(f"  {i:2}. [{p.priority_score:5.1f}] {p.name}")
        print(f"      Reasons: {', '.join(p.priority_reasons)}")
    print()
    print("Bottom 10 priority funds:")
    for p in priorities[-10:]:
        print(f"      [{p.priority_score:5.1f}] {p.name}")


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent.parent.parent
    create_prioritized_linkedin_urls(project_root)
