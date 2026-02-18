"""
Pytest configuration and fixtures for Fundradar worker tests.
"""

import gzip
import json
from pathlib import Path
from typing import NamedTuple

import pytest

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FixtureData(NamedTuple):
    """Loaded fixture data with HTML and metadata."""

    html: str
    metadata: dict
    name: str


def load_fixture(name: str) -> FixtureData:
    """
    Load a test fixture by name.

    Args:
        name: The fixture name (without extension)

    Returns:
        FixtureData with html content and metadata dict

    Raises:
        FileNotFoundError: If fixture doesn't exist
    """
    # Try compressed first, then uncompressed
    html_gz_path = FIXTURES_DIR / f"{name}.html.gz"
    html_path = FIXTURES_DIR / f"{name}.html"
    meta_path = FIXTURES_DIR / f"{name}.meta.json"

    if html_gz_path.exists():
        with gzip.open(html_gz_path, "rt", encoding="utf-8") as f:
            html = f.read()
    elif html_path.exists():
        html = html_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"Fixture HTML not found: {name}")

    if meta_path.exists():
        metadata = json.loads(meta_path.read_text())
    else:
        metadata = {}

    return FixtureData(html=html, metadata=metadata, name=name)


def save_fixture(name: str, html: str, metadata: dict, compress: bool = True):
    """
    Save a test fixture.

    Args:
        name: The fixture name
        html: The HTML content
        metadata: Metadata dict (url, date, expected extractions, etc.)
        compress: Whether to gzip compress the HTML
    """
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    if compress:
        html_path = FIXTURES_DIR / f"{name}.html.gz"
        with gzip.open(html_path, "wt", encoding="utf-8") as f:
            f.write(html)
    else:
        html_path = FIXTURES_DIR / f"{name}.html"
        html_path.write_text(html, encoding="utf-8")

    meta_path = FIXTURES_DIR / f"{name}.meta.json"
    meta_path.write_text(json.dumps(metadata, indent=2))


def list_fixtures() -> list[str]:
    """List all available fixtures by name."""
    fixtures = set()

    for path in FIXTURES_DIR.glob("*.html"):
        fixtures.add(path.stem)

    for path in FIXTURES_DIR.glob("*.html.gz"):
        fixtures.add(path.stem.replace(".html", ""))

    return sorted(fixtures)


def list_fixtures_by_type(fixture_type: str) -> list[str]:
    """
    List fixtures filtered by type.

    Args:
        fixture_type: One of 'news_list', 'portfolio_list', 'team_list', 'mixed'

    Returns:
        List of fixture names matching the type
    """
    matching = []
    for name in list_fixtures():
        try:
            data = load_fixture(name)
            if data.metadata.get("type") == fixture_type:
                matching.append(name)
        except FileNotFoundError:
            continue
    return matching


def get_fixture_types() -> dict[str, list[str]]:
    """
    Get all fixtures grouped by type.

    Returns:
        Dict mapping fixture type to list of fixture names
    """
    by_type: dict[str, list[str]] = {}
    for name in list_fixtures():
        try:
            data = load_fixture(name)
            ftype = data.metadata.get("type", "unknown")
            if ftype not in by_type:
                by_type[ftype] = []
            by_type[ftype].append(name)
        except FileNotFoundError:
            continue
    return by_type


# Pytest fixtures

@pytest.fixture
def fixture_loader():
    """Fixture that provides the load_fixture function."""
    return load_fixture


@pytest.fixture
def static_site_fixture():
    """Load the static site fixture."""
    return load_fixture("static_site")


@pytest.fixture
def nextjs_portfolio_fixture():
    """Load the Next.js portfolio fixture."""
    return load_fixture("nextjs_portfolio")


@pytest.fixture
def nextjs_team_fixture():
    """Load the Next.js team fixture."""
    return load_fixture("nextjs_team")


@pytest.fixture
def wordpress_fixture():
    """Load the WordPress fixture."""
    return load_fixture("wordpress_news")


@pytest.fixture
def spa_fixture():
    """Load the custom SPA fixture."""
    return load_fixture("custom_spa")


@pytest.fixture
def all_fixtures():
    """Load all available fixtures."""
    return {name: load_fixture(name) for name in list_fixtures()}
