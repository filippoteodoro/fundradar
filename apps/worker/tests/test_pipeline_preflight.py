from collections import namedtuple
from pathlib import Path

from fundradar_worker import pipeline


DiskUsage = namedtuple("DiskUsage", ["total", "used", "free"])


def test_preflight_blocks_low_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", Path("/tmp/fundradar"))
    monkeypatch.setattr(pipeline, "WORKER_DIR", tmp_path / "apps" / "worker")
    monkeypatch.setattr(pipeline.shutil, "disk_usage", lambda _: DiskUsage(10, 9, 64 * 1024 * 1024))

    errors, warnings = pipeline._preflight_checks([
        {"outputs": [tmp_path / "detected_signals.json"]},
    ])

    assert warnings == []
    assert len(errors) == 1
    assert "Low disk space" in errors[0]


def test_preflight_blocks_missing_canonical_when_conflict_copy_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", Path("/tmp/fundradar"))
    monkeypatch.setattr(pipeline, "WORKER_DIR", tmp_path / "apps" / "worker")
    monkeypatch.setattr(pipeline.shutil, "disk_usage", lambda _: DiskUsage(10, 2, 8 * 1024 * 1024 * 1024))

    target = tmp_path / "detected_signals.json"
    placeholder = tmp_path / ".detected_signals.json.icloud"
    duplicate = tmp_path / "detected_signals 2.json"
    placeholder.write_text("stub", encoding="utf-8")
    duplicate.write_text("{}", encoding="utf-8")

    errors, warnings = pipeline._preflight_checks([
        {"outputs": [target]},
    ])

    assert warnings == []
    assert len(errors) == 1
    assert "canonical file is missing while iCloud artifacts exist" in errors[0]


def test_preflight_warns_when_checkout_is_in_icloud(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        pipeline,
        "PROJECT_ROOT",
        Path("/Users/test/Library/Mobile Documents/com~apple~CloudDocs/Code/Fundradar"),
    )
    monkeypatch.setattr(pipeline, "WORKER_DIR", tmp_path / "apps" / "worker")
    monkeypatch.setattr(pipeline.shutil, "disk_usage", lambda _: DiskUsage(10, 2, 8 * 1024 * 1024 * 1024))
    (pipeline.WORKER_DIR / ".venv").mkdir(parents=True)

    errors, warnings = pipeline._preflight_checks([
        {"outputs": [tmp_path / "detected_signals.json"]},
    ])

    assert errors == []
    assert len(warnings) == 1
    assert "Project lives inside iCloud Drive" in warnings[0]
