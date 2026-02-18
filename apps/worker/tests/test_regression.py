"""
Regression tests for Fundradar extraction.

Compares current extraction results against stored baselines.
Run with: pytest tests/test_regression.py -v

To update baselines:
  python -m fundradar_worker.cli generate-baselines --overwrite
"""

import json
import pytest
from pathlib import Path

from fundradar_worker.enrichment import FundEnricher
from fundradar_worker.baseline import (
    load_baseline,
    compare_to_baseline,
    RegressionDiff,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"
BASELINES_DIR = Path(__file__).parent / "baselines"


def get_fixture_names() -> list[str]:
    """Get names of fixtures that have baselines."""
    baselines = []
    if BASELINES_DIR.exists():
        for path in BASELINES_DIR.glob("*.baseline.json"):
            fixture_name = path.stem.replace(".baseline", "")
            # Verify the fixture HTML exists
            if (FIXTURES_DIR / f"{fixture_name}.html").exists():
                baselines.append(fixture_name)
    return sorted(baselines)


@pytest.fixture
def enricher():
    return FundEnricher()


class TestRegression:
    """Regression tests comparing extraction to baselines."""

    @pytest.mark.parametrize("fixture_name", get_fixture_names())
    def test_extraction_matches_baseline(self, enricher, fixture_name):
        """Test that extraction matches the stored baseline."""
        # Load fixture
        html_path = FIXTURES_DIR / f"{fixture_name}.html"
        html = html_path.read_text(encoding="utf-8")

        # Get URL from metadata
        meta_path = FIXTURES_DIR / f"{fixture_name}.meta.json"
        url = "https://example.com"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                url = meta.get("url", url)
            except json.JSONDecodeError:
                pass

        # Extract
        result = enricher.extract_portfolio(html, url)

        # Compare to baseline
        diff = compare_to_baseline(fixture_name, result, BASELINES_DIR)

        # Assert no regression
        assert diff.passed, (
            f"Regression in {fixture_name}: {diff.message}\n"
            f"  Lost companies: {diff.removed_companies}\n"
            f"  Method changed: {diff.baseline_method} -> {diff.current_method}"
        )


class TestBaselineIntegrity:
    """Tests for baseline file integrity."""

    def test_all_baselines_have_fixtures(self):
        """Verify all baselines have corresponding fixtures."""
        if not BASELINES_DIR.exists():
            pytest.skip("No baselines directory")

        missing = []
        for baseline_path in BASELINES_DIR.glob("*.baseline.json"):
            fixture_name = baseline_path.stem.replace(".baseline", "")
            if not (FIXTURES_DIR / f"{fixture_name}.html").exists():
                missing.append(fixture_name)

        assert not missing, f"Baselines without fixtures: {missing}"

    def test_baselines_are_valid_json(self):
        """Verify all baseline files are valid JSON."""
        if not BASELINES_DIR.exists():
            pytest.skip("No baselines directory")

        invalid = []
        for baseline_path in BASELINES_DIR.glob("*.baseline.json"):
            try:
                with open(baseline_path) as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                invalid.append(f"{baseline_path.name}: {e}")

        assert not invalid, f"Invalid baseline files: {invalid}"


def test_no_baselines_is_ok():
    """Test that running without baselines doesn't fail."""
    # This test just ensures the baseline system handles missing baselines gracefully
    result = load_baseline("nonexistent_fixture")
    assert result is None
