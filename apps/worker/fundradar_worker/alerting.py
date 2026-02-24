"""
Alerting system for Fundradar — Telegram + webhook notifications.

Supports:
- Quality degradation alerts (via QualityMonitor)
- URL failure alerts (404s, timeouts, DNS errors)
- Consecutive-failure gating to prevent noise from transient issues
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)


@dataclass
class AlertConfig:
    """Configuration for alert delivery channels."""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    webhook_url: str = ""
    consecutive_failure_threshold: int = 3  # Failures before alerting

    @classmethod
    def from_env(cls) -> "AlertConfig":
        return cls(
            telegram_bot_token=os.environ.get("FUNDRADAR_TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("FUNDRADAR_TELEGRAM_CHAT_ID", ""),
            webhook_url=os.environ.get("FUNDRADAR_ALERT_WEBHOOK", ""),
            consecutive_failure_threshold=int(
                os.environ.get("FUNDRADAR_FAILURE_THRESHOLD", "3")
            ),
        )

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def webhook_enabled(self) -> bool:
        return bool(self.webhook_url)


@dataclass
class Alert:
    """A single alert to send."""

    title: str
    message: str
    level: str = "warning"  # info, warning, error, critical
    source: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class AlertManager:
    """
    Manages alert delivery with consecutive-failure gating.

    Tracks failures per source key. Only sends alerts after N consecutive
    failures to avoid noise from transient issues.
    """

    def __init__(self, config: AlertConfig):
        self.config = config
        self._failure_counts: dict[str, int] = {}
        self._pending_alerts: list[Alert] = []

    def record_failure(
        self, source_key: str, reason: str, metadata: dict | None = None
    ):
        """
        Record a failure for a source. Queues alert after threshold reached.
        """
        self._failure_counts[source_key] = (
            self._failure_counts.get(source_key, 0) + 1
        )
        count = self._failure_counts[source_key]

        if count >= self.config.consecutive_failure_threshold:
            self._pending_alerts.append(
                Alert(
                    title=f"[{count}x FAILURE] {source_key}",
                    message=reason,
                    level="error" if count >= 5 else "warning",
                    source=source_key,
                    metadata=metadata or {},
                )
            )

    def record_success(self, source_key: str):
        """Reset failure counter on success."""
        self._failure_counts.pop(source_key, None)

    def add_alert(self, alert: Alert):
        """Add an alert directly (bypasses failure counting)."""
        self._pending_alerts.append(alert)

    def send_pending_alerts(self):
        """Send all queued alerts via configured channels."""
        if not self._pending_alerts:
            return

        for alert in self._pending_alerts:
            if self.config.telegram_enabled:
                self._send_telegram(alert)
            if self.config.webhook_enabled:
                self._send_webhook(alert)

        sent = len(self._pending_alerts)
        self._pending_alerts.clear()
        logger.info(f"Sent {sent} alert(s)")

    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Escape Markdown special characters for Telegram."""
        for char in ('_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'):
            text = text.replace(char, f'\\{char}')
        # Escape unbalanced asterisks (but preserve *bold* pairs)
        text = text.replace('*', '\\*')
        return text

    def _send_telegram(self, alert: Alert):
        """Send alert via Telegram Bot API."""
        try:
            icon = {"info": "ℹ️", "warning": "⚠️", "error": "🔴", "critical": "🚨"}.get(
                alert.level, "📢"
            )
            # Use plain text (no parse_mode) to avoid Markdown escaping issues
            text = f"{icon} {alert.title}\n\n{alert.message}"

            # Truncate to Telegram's 4096 char limit
            if len(text) > 4000:
                text = text[:3997] + "..."

            url = (
                f"https://api.telegram.org/bot{self.config.telegram_bot_token}"
                f"/sendMessage"
            )
            payload = json.dumps(
                {
                    "chat_id": self.config.telegram_chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                }
            ).encode("utf-8")

            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info(f"Telegram alert sent: {alert.title}")
                else:
                    logger.warning(f"Telegram returned status {resp.status}")

        except (URLError, OSError) as e:
            logger.error(f"Failed to send Telegram alert: {e}")

    def _send_webhook(self, alert: Alert):
        """Send alert via generic webhook (POST JSON)."""
        try:
            payload = json.dumps(asdict(alert)).encode("utf-8")
            req = Request(
                self.config.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urlopen(req, timeout=10) as resp:
                logger.info(f"Webhook alert sent: {resp.status}")
        except (URLError, OSError) as e:
            logger.error(f"Failed to send webhook alert: {e}")


def _get_active_monitored_urls() -> set[str]:
    """Get the set of URLs currently monitored by active extractors."""
    try:
        from .url_generator import generate_all_monitored_urls
        all_urls = set()
        for domain, types in generate_all_monitored_urls().items():
            for page_type, url_list in types.items():
                if isinstance(url_list, list):
                    all_urls.update(url_list)
                elif isinstance(url_list, str):
                    all_urls.add(url_list)
        return all_urls
    except Exception as e:
        logger.warning(f"Could not load active URLs from extractors: {e}")
        return set()  # Empty = don't filter (fall back to old behavior)


def send_url_failure_alerts(data_dir: Path, failure_threshold: int = 3):
    """
    Scan url_status.json for URLs with persistent failures and send alerts.

    Only counts failures for URLs that are currently monitored by active
    extractors — stale/orphan entries from old configurations are ignored.

    Called at the end of a monitor run. Groups failures by fund/domain
    to avoid spamming individual URL alerts.

    Args:
        data_dir: Path to data/derived/
        failure_threshold: Minimum consecutive failures to trigger alert
    """
    config = AlertConfig.from_env()
    if not config.telegram_enabled and not config.webhook_enabled:
        logger.info("No alert channels configured, skipping URL failure alerts")
        return

    status_path = data_dir / "url_status.json"
    if not status_path.exists():
        return

    with open(status_path) as f:
        data = json.load(f)

    statuses = data.get("statuses", {})

    # Only alert on URLs from active extractors (ignore stale entries)
    active_urls = _get_active_monitored_urls()

    # Collect URLs with persistent failures
    failing: list[dict] = []
    for url, record in statuses.items():
        # Skip stale URLs not in any active extractor
        if active_urls and url not in active_urls:
            continue
        failures = record.get("consecutive_failures", 0)
        if failures >= failure_threshold:
            failing.append({
                "url": url,
                "status": record.get("status", "unknown"),
                "failures": failures,
                "last_checked": record.get("last_checked_at", ""),
                "error": record.get("error_message", ""),
            })

    if not failing:
        return

    # Sort by failure count descending
    failing.sort(key=lambda x: x["failures"], reverse=True)

    # Build a single summary message
    lines = [f"*{len(failing)} URLs with persistent failures:*\n"]
    for entry in failing[:20]:  # Cap at 20 to stay within Telegram limits
        status = entry["status"]
        count = entry["failures"]
        url = entry["url"]
        # Shorten URL for readability
        short_url = url.replace("https://", "").replace("http://", "")
        if len(short_url) > 60:
            short_url = short_url[:57] + "..."
        lines.append(f"• `{short_url}` — {status} ({count}x)")

    if len(failing) > 20:
        lines.append(f"\n...and {len(failing) - 20} more")

    manager = AlertManager(config)
    manager.add_alert(
        Alert(
            title=f"URL Failures: {len(failing)} broken URLs",
            message="\n".join(lines),
            level="error" if len(failing) > 5 else "warning",
            source="url_failures",
        )
    )
    manager.send_pending_alerts()


def prune_stale_url_statuses(data_dir: Path) -> int:
    """
    Remove entries from url_status.json that are not in any active extractor.

    Returns the number of stale entries removed.
    """
    status_path = data_dir / "url_status.json"
    if not status_path.exists():
        return 0

    active_urls = _get_active_monitored_urls()
    if not active_urls:
        logger.info("No active URLs loaded — skipping url_status.json pruning")
        return 0

    with open(status_path) as f:
        data = json.load(f)

    statuses = data.get("statuses", {})
    original_count = len(statuses)

    # Keep only entries for active URLs
    pruned = {url: record for url, record in statuses.items() if url in active_urls}
    removed = original_count - len(pruned)

    if removed > 0:
        data["statuses"] = pruned
        from .io_utils import safe_json_write
        safe_json_write(status_path, data)
        logger.info(f"Pruned {removed} stale entries from url_status.json ({len(pruned)} remaining)")

    return removed
