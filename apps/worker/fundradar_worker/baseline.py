"""
Regression test baseline management for Fundradar.

Stores and compares extraction results against known baselines.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .enrichment import FundEnricher, PortfolioExtractionResult, PortfolioCompany

logger = logging.getLogger(__name__)

# Default baselines directory
BASELINES_DIR = Path(__file__).parent.parent / "tests" / "baselines"


@dataclass
class BaselineResult:
    """Stored baseline for regression comparison."""

    fixture_name: str
    extraction_method: str | None
    company_count: int
    company_names: list[str]
    failed_reason: str | None
    created_at: str
    version: str = "1.0"


@dataclass
class RegressionDiff:
    """Difference between current and baseline extraction."""

    fixture_name: str
    passed: bool
    company_count_diff: int  # positive = more companies now
    added_companies: list[str]  # in current, not in baseline
    removed_companies: list[str]  # in baseline, not in current
    extraction_method_changed: bool
    failed_reason_changed: bool
    current_method: str | None
    baseline_method: str | None
    message: str


def load_baseline(fixture_name: str, baselines_dir: Path | None = None) -> BaselineResult | None:
    """
    Load a baseline for a fixture.

    Args:
        fixture_name: Name of the fixture
        baselines_dir: Optional directory for baselines

    Returns:
        BaselineResult if found, None otherwise
    """
    baselines_dir = baselines_dir or BASELINES_DIR
    baseline_path = baselines_dir / f"{fixture_name}.baseline.json"

    if not baseline_path.exists():
        return None

    try:
        with open(baseline_path) as f:
            data = json.load(f)
        return BaselineResult(**data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to load baseline for {fixture_name}: {e}")
        return None


def save_baseline(
    fixture_name: str,
    result: PortfolioExtractionResult,
    baselines_dir: Path | None = None,
) -> BaselineResult:
    """
    Save a baseline for a fixture.

    Args:
        fixture_name: Name of the fixture
        result: Extraction result to save
        baselines_dir: Optional directory for baselines

    Returns:
        The saved BaselineResult
    """
    baselines_dir = baselines_dir or BASELINES_DIR
    baselines_dir.mkdir(parents=True, exist_ok=True)

    baseline = BaselineResult(
        fixture_name=fixture_name,
        extraction_method=result.extraction_method,
        company_count=len(result.companies),
        company_names=sorted([c.name for c in result.companies]),
        failed_reason=result.failed_reason,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    baseline_path = baselines_dir / f"{fixture_name}.baseline.json"
    with open(baseline_path, "w") as f:
        json.dump(asdict(baseline), f, indent=2)

    logger.info(f"Saved baseline for {fixture_name}: {baseline.company_count} companies")
    return baseline


def compare_to_baseline(
    fixture_name: str,
    result: PortfolioExtractionResult,
    baselines_dir: Path | None = None,
) -> RegressionDiff:
    """
    Compare extraction result to baseline.

    Args:
        fixture_name: Name of the fixture
        result: Current extraction result
        baselines_dir: Optional directory for baselines

    Returns:
        RegressionDiff with comparison details
    """
    baseline = load_baseline(fixture_name, baselines_dir)

    current_names = set(c.name for c in result.companies)

    if baseline is None:
        return RegressionDiff(
            fixture_name=fixture_name,
            passed=True,  # No baseline to compare
            company_count_diff=len(result.companies),
            added_companies=sorted(current_names),
            removed_companies=[],
            extraction_method_changed=False,
            failed_reason_changed=False,
            current_method=result.extraction_method,
            baseline_method=None,
            message="No baseline found (first run)",
        )

    baseline_names = set(baseline.company_names)

    added = sorted(current_names - baseline_names)
    removed = sorted(baseline_names - current_names)

    count_diff = len(result.companies) - baseline.company_count
    method_changed = result.extraction_method != baseline.extraction_method
    failed_changed = result.failed_reason != baseline.failed_reason

    # Determine if this is a regression
    # Regression = lost companies, or changed from success to failure
    is_regression = (
        len(removed) > 0 and len(removed) > len(added)  # Lost more than gained
    ) or (
        baseline.failed_reason is None and result.failed_reason is not None
    )

    if is_regression:
        message = f"REGRESSION: Lost {len(removed)} companies: {', '.join(removed[:5])}"
        if len(removed) > 5:
            message += f" (+{len(removed) - 5} more)"
    elif added or removed:
        message = f"Changed: +{len(added)} -{len(removed)} companies"
    else:
        message = "Matches baseline"

    return RegressionDiff(
        fixture_name=fixture_name,
        passed=not is_regression,
        company_count_diff=count_diff,
        added_companies=added,
        removed_companies=removed,
        extraction_method_changed=method_changed,
        failed_reason_changed=failed_changed,
        current_method=result.extraction_method,
        baseline_method=baseline.extraction_method,
        message=message,
    )


def generate_baselines_for_fixtures(
    fixtures_dir: Path,
    baselines_dir: Path | None = None,
    overwrite: bool = False,
) -> list[BaselineResult]:
    """
    Generate baselines for all fixtures in a directory.

    Args:
        fixtures_dir: Directory containing HTML fixtures
        baselines_dir: Directory to save baselines
        overwrite: Whether to overwrite existing baselines

    Returns:
        List of generated baselines
    """
    baselines_dir = baselines_dir or BASELINES_DIR
    enricher = FundEnricher()
    baselines = []

    for html_path in sorted(fixtures_dir.glob("*.html")):
        fixture_name = html_path.stem

        # Skip if baseline exists and not overwriting
        baseline_path = baselines_dir / f"{fixture_name}.baseline.json"
        if baseline_path.exists() and not overwrite:
            logger.debug(f"Skipping {fixture_name}: baseline exists")
            continue

        # Load fixture
        html = html_path.read_text(encoding="utf-8")
        meta_path = html_path.with_suffix(".meta.json")

        url = "https://example.com"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                url = meta.get("url", url)
            except json.JSONDecodeError:
                pass

        # Extract and save baseline
        result = enricher.extract_portfolio(html, url)
        baseline = save_baseline(fixture_name, result, baselines_dir)
        baselines.append(baseline)

    return baselines


def run_regression_tests(
    fixtures_dir: Path,
    baselines_dir: Path | None = None,
) -> tuple[list[RegressionDiff], bool]:
    """
    Run regression tests against all fixtures with baselines.

    Args:
        fixtures_dir: Directory containing HTML fixtures
        baselines_dir: Directory with baselines

    Returns:
        Tuple of (list of diffs, all_passed)
    """
    baselines_dir = baselines_dir or BASELINES_DIR
    enricher = FundEnricher()
    diffs = []
    all_passed = True

    for baseline_path in sorted(baselines_dir.glob("*.baseline.json")):
        fixture_name = baseline_path.stem.replace(".baseline", "")
        html_path = fixtures_dir / f"{fixture_name}.html"

        if not html_path.exists():
            logger.warning(f"Fixture not found for baseline: {fixture_name}")
            continue

        # Load fixture
        html = html_path.read_text(encoding="utf-8")
        meta_path = fixtures_dir / f"{fixture_name}.meta.json"

        url = "https://example.com"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                url = meta.get("url", url)
            except json.JSONDecodeError:
                pass

        # Extract and compare
        result = enricher.extract_portfolio(html, url)
        diff = compare_to_baseline(fixture_name, result, baselines_dir)
        diffs.append(diff)

        if not diff.passed:
            all_passed = False
            logger.error(f"Regression in {fixture_name}: {diff.message}")
        else:
            logger.info(f"Passed: {fixture_name} ({diff.message})")

    return diffs, all_passed


def format_regression_report(diffs: list[RegressionDiff]) -> str:
    """
    Format regression test results as a report.

    Args:
        diffs: List of regression diffs

    Returns:
        Formatted report string
    """
    lines = [
        "=" * 60,
        "REGRESSION TEST REPORT",
        "=" * 60,
        "",
    ]

    passed = [d for d in diffs if d.passed]
    failed = [d for d in diffs if not d.passed]

    lines.append(f"Total: {len(diffs)} | Passed: {len(passed)} | Failed: {len(failed)}")
    lines.append("")

    if failed:
        lines.append("-" * 40)
        lines.append("FAILURES")
        lines.append("-" * 40)
        for diff in failed:
            lines.append(f"\n{diff.fixture_name}:")
            lines.append(f"  {diff.message}")
            if diff.removed_companies:
                lines.append(f"  Lost: {', '.join(diff.removed_companies[:10])}")
            if diff.added_companies:
                lines.append(f"  Added: {', '.join(diff.added_companies[:10])}")
            if diff.extraction_method_changed:
                lines.append(f"  Method: {diff.baseline_method} -> {diff.current_method}")
        lines.append("")

    if passed:
        lines.append("-" * 40)
        lines.append("PASSED")
        lines.append("-" * 40)
        for diff in passed:
            status = "✓" if diff.company_count_diff == 0 else f"±{diff.company_count_diff}"
            lines.append(f"  {status} {diff.fixture_name}")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)
