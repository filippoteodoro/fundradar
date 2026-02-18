"""
Scraping health report generator for Fundradar.

Generates metrics and reports on scraping success across all funds.
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DomainStats:
    """Statistics for a single domain."""

    domain: str
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    avg_confidence: float = 0.0
    avg_extraction_count: float = 0.0
    last_check_at: str | None = None
    last_error: str | None = None
    error_types: dict[str, int] = field(default_factory=dict)
    extraction_methods: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return self.successful_checks / self.total_checks


@dataclass
class HealthReport:
    """Overall health report for scraping system."""

    generated_at: str
    total_funds: int = 0
    funds_with_website: int = 0
    funds_checked: int = 0
    overall_success_rate: float = 0.0
    avg_confidence: float = 0.0
    total_companies_extracted: int = 0
    total_signals_generated: int = 0
    domain_stats: list[DomainStats] = field(default_factory=list)
    error_summary: dict[str, int] = field(default_factory=dict)
    extraction_method_summary: dict[str, int] = field(default_factory=dict)
    coverage_gaps: list[str] = field(default_factory=list)  # Funds with no data


@dataclass
class FundHealthRecord:
    """Health record for a single fund."""

    slug: str
    name: str
    domain: str | None
    has_website: bool
    last_checked: str | None
    last_success: str | None
    portfolio_count: int | None
    team_count: int | None
    signals_count: int
    extraction_method: str | None
    failed_reason: str | None
    confidence: float | None


def generate_health_report(
    data_dir: Path,
    db_path: Path | None = None,
    signals_path: Path | None = None,
) -> HealthReport:
    """
    Generate a health report for all funds.

    Args:
        data_dir: Directory containing derived data
        db_path: Path to db.json
        signals_path: Path to detected_signals.json

    Returns:
        HealthReport with aggregated metrics
    """
    # Load data
    db_path = db_path or data_dir.parent / "db.json"
    signals_path = signals_path or data_dir / "detected_signals.json"
    portfolios_path = data_dir / "portfolio_items.json"
    enriched_path = data_dir / "enriched_funds.json"

    report = HealthReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # Load funds
    funds = []
    if db_path.exists():
        with open(db_path) as f:
            db = json.load(f)
        funds = db.get("funds", [])
    report.total_funds = len(funds)

    # Load signals
    signals = []
    if signals_path.exists():
        try:
            with open(signals_path) as f:
                signals_data = json.load(f)
            signals = signals_data.get("signals", [])
        except (json.JSONDecodeError, KeyError):
            pass
    report.total_signals_generated = len(signals)

    # Load portfolios
    portfolios = {}
    if portfolios_path.exists():
        try:
            with open(portfolios_path) as f:
                port_data = json.load(f)
            portfolios = port_data.get("fund_portfolios", {})
        except (json.JSONDecodeError, KeyError):
            pass

    # Load enriched fund data
    enriched = {}
    if enriched_path.exists():
        try:
            with open(enriched_path) as f:
                enriched_data = json.load(f)
            for item in enriched_data.get("funds", []):
                enriched[item.get("fund_slug")] = item
        except (json.JSONDecodeError, KeyError):
            pass

    # Aggregate stats
    domain_stats_map: dict[str, DomainStats] = {}
    error_counts: dict[str, int] = defaultdict(int)
    method_counts: dict[str, int] = defaultdict(int)
    coverage_gaps = []
    total_confidence = 0.0
    confidence_count = 0
    total_companies = 0

    for fund in funds:
        slug = fund.get("slug", "")
        name = fund.get("name", slug)
        website = fund.get("website", "")

        if website:
            report.funds_with_website += 1

        # Get domain
        domain = None
        if website:
            from urllib.parse import urlparse
            try:
                parsed = urlparse(website)
                domain = parsed.netloc.replace("www.", "")
            except Exception:
                pass

        # Get portfolio data
        portfolio = portfolios.get(slug, [])
        portfolio_count = len(portfolio)
        total_companies += portfolio_count

        # Get enriched data
        fund_enriched = enriched.get(slug, {})
        team_count = fund_enriched.get("team_count")
        last_enriched = fund_enriched.get("last_enriched_at")
        failed_reason = fund_enriched.get("portfolio_extraction_failed_reason")

        # Count signals for this fund
        fund_signals = [s for s in signals if s.get("fund_slug") == slug]

        # Determine success/failure
        has_data = portfolio_count > 0 or team_count or len(fund_signals) > 0

        if website and not has_data:
            coverage_gaps.append(slug)

        # Update domain stats
        if domain:
            if domain not in domain_stats_map:
                domain_stats_map[domain] = DomainStats(domain=domain)
            stats = domain_stats_map[domain]
            stats.total_checks += 1

            if has_data:
                stats.successful_checks += 1
            else:
                stats.failed_checks += 1
                if failed_reason:
                    if failed_reason not in stats.error_types:
                        stats.error_types[failed_reason] = 0
                    stats.error_types[failed_reason] += 1
                    error_counts[failed_reason] += 1

            if last_enriched:
                stats.last_check_at = last_enriched

            if failed_reason:
                stats.last_error = failed_reason

    # Calculate aggregates
    report.funds_checked = len(domain_stats_map)
    report.total_companies_extracted = total_companies
    report.coverage_gaps = coverage_gaps

    if report.funds_checked > 0:
        total_success = sum(s.successful_checks for s in domain_stats_map.values())
        total_checks = sum(s.total_checks for s in domain_stats_map.values())
        report.overall_success_rate = total_success / total_checks if total_checks > 0 else 0.0

    report.domain_stats = sorted(
        domain_stats_map.values(),
        key=lambda x: x.success_rate,
    )
    report.error_summary = dict(error_counts)

    return report


def format_health_report(report: HealthReport, verbose: bool = False) -> str:
    """
    Format a health report as human-readable text.

    Args:
        report: The health report to format
        verbose: Include detailed domain breakdown

    Returns:
        Formatted report string
    """
    lines = [
        "=" * 70,
        "FUNDRADAR SCRAPING HEALTH REPORT",
        f"Generated: {report.generated_at}",
        "=" * 70,
        "",
        "SUMMARY",
        "-" * 40,
        f"Total funds:           {report.total_funds}",
        f"Funds with website:    {report.funds_with_website}",
        f"Funds checked:         {report.funds_checked}",
        f"Overall success rate:  {report.overall_success_rate:.1%}",
        f"Total companies:       {report.total_companies_extracted}",
        f"Total signals:         {report.total_signals_generated}",
        "",
    ]

    if report.coverage_gaps:
        lines.extend([
            "COVERAGE GAPS",
            "-" * 40,
            f"Funds with website but no data: {len(report.coverage_gaps)}",
        ])
        for gap in report.coverage_gaps[:10]:
            lines.append(f"  - {gap}")
        if len(report.coverage_gaps) > 10:
            lines.append(f"  ... and {len(report.coverage_gaps) - 10} more")
        lines.append("")

    if report.error_summary:
        lines.extend([
            "ERROR BREAKDOWN",
            "-" * 40,
        ])
        for error, count in sorted(report.error_summary.items(), key=lambda x: -x[1]):
            lines.append(f"  {error}: {count}")
        lines.append("")

    if verbose and report.domain_stats:
        lines.extend([
            "DOMAIN BREAKDOWN",
            "-" * 40,
        ])
        for stats in report.domain_stats[:20]:
            status = "OK" if stats.success_rate >= 0.5 else "FAIL"
            lines.append(f"  [{status}] {stats.domain}: {stats.success_rate:.0%}")
        if len(report.domain_stats) > 20:
            lines.append(f"  ... and {len(report.domain_stats) - 20} more")
        lines.append("")

    lines.append("=" * 70)

    return "\n".join(lines)


def save_health_report(report: HealthReport, output_path: Path):
    """
    Save health report to JSON file.

    Args:
        report: The report to save
        output_path: Path to save to
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict
    data = {
        "generated_at": report.generated_at,
        "total_funds": report.total_funds,
        "funds_with_website": report.funds_with_website,
        "funds_checked": report.funds_checked,
        "overall_success_rate": report.overall_success_rate,
        "avg_confidence": report.avg_confidence,
        "total_companies_extracted": report.total_companies_extracted,
        "total_signals_generated": report.total_signals_generated,
        "error_summary": report.error_summary,
        "extraction_method_summary": report.extraction_method_summary,
        "coverage_gaps": report.coverage_gaps,
        "domain_stats": [asdict(s) for s in report.domain_stats],
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved health report to {output_path}")


def compare_reports(
    current: HealthReport,
    previous: HealthReport,
) -> dict[str, Any]:
    """
    Compare two health reports for trend analysis.

    Args:
        current: Current report
        previous: Previous report to compare against

    Returns:
        Dict with comparison metrics
    """
    return {
        "success_rate_change": current.overall_success_rate - previous.overall_success_rate,
        "companies_change": current.total_companies_extracted - previous.total_companies_extracted,
        "signals_change": current.total_signals_generated - previous.total_signals_generated,
        "coverage_gaps_change": len(current.coverage_gaps) - len(previous.coverage_gaps),
        "new_gaps": [g for g in current.coverage_gaps if g not in previous.coverage_gaps],
        "resolved_gaps": [g for g in previous.coverage_gaps if g not in current.coverage_gaps],
    }
