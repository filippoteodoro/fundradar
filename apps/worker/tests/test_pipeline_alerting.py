from fundradar_worker import pipeline


def test_remaining_work_ignores_known_portfolio_backlog_without_step_issue(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "_portfolio_enrichment_status",
        lambda: {"remaining_entries": 2220, "remaining_calls": 89, "top_funds": []},
    )
    monkeypatch.setattr(pipeline, "_signal_to_portfolio_status", lambda: {"remaining": 0, "processed": 0, "total_signals": 0})

    remaining = pipeline._remaining_work_items(
        results={"enrich_portfolio": True, "enrich_portfolio_final": True},
        retry_log={},
        step_details={},
        report={"filtered": {"count": 17}, "enriched": {"count": 17}},
    )

    assert remaining == []


def test_remaining_work_includes_portfolio_backlog_when_enrichment_step_failed(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "_portfolio_enrichment_status",
        lambda: {"remaining_entries": 2220, "remaining_calls": 89, "top_funds": []},
    )
    monkeypatch.setattr(pipeline, "_signal_to_portfolio_status", lambda: {"remaining": 0, "processed": 0, "total_signals": 0})

    remaining = pipeline._remaining_work_items(
        results={"enrich_portfolio": True, "enrich_portfolio_final": True},
        retry_log={},
        step_details={"enrich_portfolio": {"skipped": True, "reason": "exit code 1", "exit_code": 1}},
        report={"filtered": {"count": 17}, "enriched": {"count": 17}},
    )

    assert remaining == ["Portfolio enrichment: 2220 entries remaining"]


def test_suggest_reruns_includes_signal_to_portfolio(monkeypatch):
    monkeypatch.setattr(pipeline, "_portfolio_enrichment_status", lambda: None)
    monkeypatch.setattr(pipeline, "_signal_to_portfolio_status", lambda: {"remaining": 7, "processed": 0, "total_signals": 7})

    suggestions = pipeline._suggest_reruns(report=None)

    assert suggestions == [(
        "Signal→Portfolio incomplete (7 signals remaining)",
        "python apps/worker/scripts/signal_to_portfolio.py --pipeline",
    )]
