from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_gate_module():
    repo_root = Path(__file__).resolve().parents[3]
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    module_path = scripts_dir / "check_new_fund_gate.py"
    spec = importlib.util.spec_from_file_location("check_new_fund_gate", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_domain_handles_scheme_and_www():
    mod = _load_gate_module()
    assert mod._normalize_domain("https://www.example.com/path") == "example.com"
    assert mod._normalize_domain("www.example.com") == "example.com"
    assert mod._normalize_domain("example.com") == "example.com"


def test_slugify_module_uses_hyphens():
    mod = _load_gate_module()
    assert mod._slugify_module("oaktree_capital_management") == "oaktree-capital-management"


def test_is_trigger_change_detects_extractor_paths():
    mod = _load_gate_module()
    assert mod._is_trigger_change("apps/worker/fundradar_worker/strategies/extractors/icg.py")
    assert not mod._is_trigger_change("docs/ADDING_A_FUND.md")


def test_fund_aliases_not_a_trigger_change():
    """fund_aliases.json must NOT be a trigger change.
    Changes to invalid_slugs produce no candidate slugs and must not cause
    the gate to error with "triggering files changed but no candidates detected".
    Active-fund alias changes are detected via _detect_alias_target_changes() instead."""
    mod = _load_gate_module()
    assert not mod._is_trigger_change("data/derived/fund_aliases.json")
