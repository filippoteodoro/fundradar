import time
from pathlib import Path

from fundradar_worker import monitor
from fundradar_worker.monitor import MonitoredUrl, WebsiteMonitor


def _url(domain: str, path: str) -> MonitoredUrl:
    return MonitoredUrl(
        url=f"https://{domain}{path}",
        fund_slug=domain.replace(".", "-"),
        fund_name=domain,
        page_type="news",
        category="NEWS",
    )


def test_compute_global_timeout_scales_with_parallel_domain_waves(monkeypatch):
    monkeypatch.setattr(monitor, "MAX_WORKERS", 4)
    monkeypatch.setattr(monitor, "PER_URL_TIMEOUT", 10)
    monkeypatch.setattr(monitor, "MIN_TOTAL_TIMEOUT", 30)
    monkeypatch.setattr(monitor, "MAX_TOTAL_TIMEOUT", 300)
    monkeypatch.setattr(monitor, "GLOBAL_TIMEOUT_GRACE", 5)

    domain_groups = {
        "a.com": [_url("a.com", "/1")],
        "b.com": [_url("b.com", "/1")],
        "c.com": [_url("c.com", "/1")],
        "d.com": [_url("d.com", "/1")],
        "e.com": [_url("e.com", "/1")],
        "f.com": [_url("f.com", "/1")],
        "g.com": [_url("g.com", "/1")],
        "h.com": [_url("h.com", "/1")],
        "i.com": [_url("i.com", "/1")],
    }

    # 9 domains on 4 workers => 3 waves => 3 * 10s + 5s grace
    assert monitor._compute_global_timeout(domain_groups) == 35


def test_check_urls_timeout_stops_after_current_domain_url(monkeypatch, tmp_path: Path):
    worker = WebsiteMonitor(tmp_path, use_playwright=False, enable_graceful_shutdown=False)

    monkeypatch.setattr(monitor, "MAX_WORKERS", 1)
    monkeypatch.setattr(monitor, "PER_URL_TIMEOUT", 1)
    monkeypatch.setattr(monitor, "TIMEOUT_DRAIN_GRACE", 1)
    monkeypatch.setattr(monitor, "_compute_global_timeout", lambda _: 1)

    processed: list[str] = []

    def fake_check_url(url_obj: MonitoredUrl, skip_backoff: bool = False):
        processed.append(url_obj.url)
        time.sleep(1.05)
        return []

    monkeypatch.setattr(worker, "check_url", fake_check_url)

    urls = [
        _url("example.com", "/news-1"),
        _url("example.com", "/news-2"),
    ]

    signals = worker.check_urls(urls)

    assert signals == []
    assert processed == ["https://example.com/news-1"]
