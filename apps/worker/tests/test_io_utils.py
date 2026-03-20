import json

from fundradar_worker.io_utils import (
    icloud_artifact_state,
    recover_icloud_conflict_copy,
    safe_json_write,
)
from fundradar_worker.pipeline import _validate_output


def test_recover_icloud_conflict_copy_restores_canonical_name(tmp_path):
    target = tmp_path / "detected_signals.json"
    placeholder = tmp_path / ".detected_signals.json.icloud"
    duplicate = tmp_path / "detected_signals 2.json"

    placeholder.write_text("stub", encoding="utf-8")
    duplicate.write_text('{"signals":[{"id":"sig-1"}],"signal_count":1}', encoding="utf-8")

    recovered = recover_icloud_conflict_copy(target)

    assert recovered == target
    assert target.exists()
    assert not placeholder.exists()
    assert not duplicate.exists()
    assert json.loads(target.read_text(encoding="utf-8"))["signal_count"] == 1


def test_safe_json_write_removes_icloud_placeholder(tmp_path):
    target = tmp_path / "portfolio_items.json"
    placeholder = tmp_path / ".portfolio_items.json.icloud"
    placeholder.write_text("stub", encoding="utf-8")

    safe_json_write(target, {"fund_portfolios": {"test-fund": []}})

    assert target.exists()
    assert not placeholder.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "fund_portfolios": {"test-fund": []}
    }


def test_validate_output_recovers_icloud_conflict_copy(tmp_path):
    target = tmp_path / "portfolio_items.json"
    placeholder = tmp_path / ".portfolio_items.json.icloud"
    duplicate = tmp_path / "portfolio_items 2.json"

    placeholder.write_text("stub", encoding="utf-8")
    duplicate.write_text(
        '{"fund_portfolios":{"test-fund":[{"name":"Acme"}]}}',
        encoding="utf-8",
    )

    ok, message = _validate_output(target)

    assert ok is True
    assert message.startswith("OK: portfolio_items.json")
    assert target.exists()
    assert not placeholder.exists()
    assert not duplicate.exists()


def test_icloud_artifact_state_reports_placeholder_and_conflict_copy(tmp_path):
    target = tmp_path / "detected_signals.json"
    placeholder = tmp_path / ".detected_signals.json.icloud"
    duplicate = tmp_path / "detected_signals 2.json"

    placeholder.write_text("stub", encoding="utf-8")
    duplicate.write_text("{}", encoding="utf-8")

    state = icloud_artifact_state(target)

    assert state["canonical"] == target
    assert state["placeholder"] == placeholder
    assert state["conflict_copies"] == [duplicate]
