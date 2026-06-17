"""Regression tests for normalize_sectors.py db.json sector_tags handling.

Guards the class of bug where the normalize_sectors pipeline step rewrote curated
db.json fund sector_tags on every run:
  - normalize_aifi_tags() alphabetically sorted tags (lost curated priority order)
  - STEP 5 derived tags from portfolio frequency and OVERWROTE curated values
Both produced a broad, lossy db.json diff that had to be manually restored from git.
"""
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "normalize_sectors.py"
_spec = importlib.util.spec_from_file_location("normalize_sectors", _SCRIPT)
ns = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ns)


def test_normalize_aifi_tags_preserves_curated_order():
    """Already-canonical tags must come back in the SAME order — never alphabetized."""
    tags = ["Software", "Healthcare", "Food & Beverage", "Industrial Manufacturing"]
    assert ns.normalize_aifi_tags(tags) == tags  # not sorted()


def test_normalize_aifi_tags_dedups_first_occurrence_order():
    out = ns.normalize_aifi_tags(["Healthcare", "Healthcare", "Software", "Healthcare"])
    assert out == ["Healthcare", "Software"]


def test_normalize_aifi_tags_drops_unknown_non_canonical():
    out = ns.normalize_aifi_tags(["Healthcare", "Highly-Efficient Hydraulic Components"])
    assert out == ["Healthcare"]  # garbage/description dropped, canonical kept in order


def test_normalize_aifi_tags_idempotent():
    """Running twice must not change canonical tags — proves no per-run db.json churn."""
    tags = ["Industrial Manufacturing", "Healthcare", "Food & Beverage", "Software", "Professional Services"]
    once = ns.normalize_aifi_tags(tags)
    assert once == tags
    assert ns.normalize_aifi_tags(once) == once
