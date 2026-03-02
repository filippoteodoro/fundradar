from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_verify_module():
    repo_root = Path(__file__).resolve().parents[3]
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    module_path = repo_root / "scripts" / "verify_new_fund_completion.py"
    spec = importlib.util.spec_from_file_location("verify_new_fund_completion", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_top_aum_italy_blocker_triggers_when_unverified():
    mod = _load_verify_module()
    blocker = mod._top_aum_italy_assets_blocker(
        slug="icg",
        top_slugs={"icg"},
        audit_entry={"italian_portfolio_count": 0},
        verified_zero_italy_slugs=set(),
    )
    assert blocker == "top_aum_no_italy_assets_unverified"


def test_top_aum_italy_blocker_skips_when_verified_zero():
    mod = _load_verify_module()
    blocker = mod._top_aum_italy_assets_blocker(
        slug="icg",
        top_slugs={"icg"},
        audit_entry={"italian_portfolio_count": 0},
        verified_zero_italy_slugs={"icg"},
    )
    assert blocker is None


def test_top_aum_italy_blocker_skips_for_non_top_slug():
    mod = _load_verify_module()
    blocker = mod._top_aum_italy_assets_blocker(
        slug="icg",
        top_slugs={"kkr"},
        audit_entry={"italian_portfolio_count": 0},
        verified_zero_italy_slugs=set(),
    )
    assert blocker is None


def test_as_non_negative_int_handles_strings_and_invalid_values():
    mod = _load_verify_module()
    assert mod._as_non_negative_int("3") == 3
    assert mod._as_non_negative_int("7.9") == 7
    assert mod._as_non_negative_int("-2") == 0
    assert mod._as_non_negative_int("not-a-number") == 0


def test_is_complete_portfolio_entry_requires_sector_desc_hq():
    mod = _load_verify_module()
    assert mod._is_complete_portfolio_entry({"sector": "Tech", "description": "Desc", "headquarters": "Milan"})
    assert not mod._is_complete_portfolio_entry({"sector": "Tech", "description": "Desc"})
    assert not mod._is_complete_portfolio_entry({"sector": "Tech", "headquarters": "Milan"})
    assert not mod._is_complete_portfolio_entry({"description": "Desc", "headquarters": "Milan"})
