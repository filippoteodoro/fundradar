"""
Quality monitoring system for Fundradar scrapers.

Tracks extraction baselines, detects quality degradation, and triggers alerts.
Integrates with the existing alerting.py webhook system.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .alerting import Alert, AlertManager, AlertConfig

logger = logging.getLogger(__name__)


AlertSeverity = Literal["info", "warning", "error", "critical"]


@dataclass
class QualityBaseline:
    """Baseline metrics for a scraper."""

    fund_slug: str
    data_type: str  # "portfolio", "team", "news"
    baseline_count: int
    baseline_confidence: float
    last_successful: str  # ISO timestamp
    extraction_methods: list[str] = field(default_factory=list)


@dataclass
class QualityAlert:
    """An alert triggered by quality degradation."""

    fund_slug: str
    data_type: str
    severity: AlertSeverity
    reason: str
    current_count: int
    baseline_count: int
    current_confidence: float
    baseline_confidence: float
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class MaintenanceStatus:
    """Current maintenance status of all scrapers."""

    generated_at: str
    total_scrapers: int
    healthy_scrapers: int
    degraded_scrapers: int
    broken_scrapers: int
    scrapers_needing_attention: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


class QualityMonitor:
    """
    Monitors extraction quality and triggers maintenance alerts.

    Compares current extraction results against historical baselines
    and triggers alerts when quality drops significantly.
    """

    # Thresholds (configurable via environment)
    COUNT_DROP_WARNING_THRESHOLD = float(os.environ.get("FUNDRADAR_COUNT_DROP_WARNING", "0.3"))  # 30%
    COUNT_DROP_ERROR_THRESHOLD = float(os.environ.get("FUNDRADAR_COUNT_DROP_ERROR", "0.5"))  # 50%
    CONFIDENCE_DROP_THRESHOLD = float(os.environ.get("FUNDRADAR_CONFIDENCE_DROP", "0.2"))  # 20%

    def __init__(
        self,
        baselines_path: Path,
        status_path: Path,
        alert_manager: AlertManager | None = None,
    ):
        """
        Initialize quality monitor.

        Args:
            baselines_path: Path to quality_baselines.json
            status_path: Path to maintenance_status.json
            alert_manager: Optional AlertManager instance (creates one if not provided)
        """
        self.baselines_path = baselines_path
        self.status_path = status_path
        self.alert_manager = alert_manager or AlertManager(AlertConfig.from_env())
        self.baselines: dict[str, QualityBaseline] = {}
        self._load_baselines()

    def _load_baselines(self):
        """Load baselines from disk."""
        if self.baselines_path.exists():
            try:
                with open(self.baselines_path) as f:
                    data = json.load(f)
                    for key, baseline_data in data.get("baselines", {}).items():
                        self.baselines[key] = QualityBaseline(**baseline_data)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to load baselines: {e}")

    def _save_baselines(self):
        """Save baselines to disk."""
        self.baselines_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "baselines": {key: asdict(baseline) for key, baseline in self.baselines.items()},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.baselines_path, "w") as f:
            json.dump(data, f, indent=2)

    def _baseline_key(self, fund_slug: str, data_type: str) -> str:
        """Generate a unique key for fund/data_type combination."""
        return f"{fund_slug}:{data_type}"

    def update_baseline(
        self,
        fund_slug: str,
        data_type: str,
        count: int,
        confidence: float,
        extraction_methods: list[str] | None = None,
    ):
        """
        Update the baseline for a fund/data_type.

        Only updates if the new results are better or comparable to existing baseline.
        This prevents bad extractions from poisoning the baseline.

        Args:
            fund_slug: The fund identifier
            data_type: Type of data ("portfolio", "team", "news")
            count: Number of items extracted
            confidence: Average confidence score
            extraction_methods: Methods used for extraction
        """
        key = self._baseline_key(fund_slug, data_type)
        existing = self.baselines.get(key)

        # Only update baseline if:
        # 1. No existing baseline, OR
        # 2. Count is within 10% of baseline (not a massive drop), OR
        # 3. New count is higher (improvement)
        should_update = (
            existing is None
            or count >= existing.baseline_count * 0.9
            or count > existing.baseline_count
        )

        if should_update:
            self.baselines[key] = QualityBaseline(
                fund_slug=fund_slug,
                data_type=data_type,
                baseline_count=count,
                baseline_confidence=confidence,
                last_successful=datetime.now(timezone.utc).isoformat(),
                extraction_methods=extraction_methods or [],
            )
            self._save_baselines()
            logger.info(f"Updated baseline for {key}: count={count}, confidence={confidence:.2f}")
        else:
            logger.debug(f"Skipped baseline update for {key}: count {count} < baseline {existing.baseline_count}")

    def check_extraction_quality(
        self,
        fund_slug: str,
        data_type: str,
        count: int,
        confidence: float,
    ) -> list[QualityAlert]:
        """
        Compare current extraction results against baseline.

        Args:
            fund_slug: The fund identifier
            data_type: Type of data
            count: Current extraction count
            confidence: Current average confidence

        Returns:
            List of QualityAlert objects (empty if no issues)
        """
        key = self._baseline_key(fund_slug, data_type)
        baseline = self.baselines.get(key)

        alerts = []

        # If no baseline, this is first extraction - set it
        if baseline is None:
            logger.info(f"No baseline for {key}, setting initial baseline")
            self.update_baseline(fund_slug, data_type, count, confidence)
            return alerts

        # Check for zero results (critical)
        if count == 0 and baseline.baseline_count > 0:
            alerts.append(QualityAlert(
                fund_slug=fund_slug,
                data_type=data_type,
                severity="critical",
                reason=f"Zero results (was {baseline.baseline_count})",
                current_count=count,
                baseline_count=baseline.baseline_count,
                current_confidence=confidence,
                baseline_confidence=baseline.baseline_confidence,
            ))
            return alerts  # Critical - don't check other thresholds

        # Check for significant count drop
        if baseline.baseline_count > 0:
            count_drop = (baseline.baseline_count - count) / baseline.baseline_count

            if count_drop > self.COUNT_DROP_ERROR_THRESHOLD:
                alerts.append(QualityAlert(
                    fund_slug=fund_slug,
                    data_type=data_type,
                    severity="error",
                    reason=f"Count dropped {count_drop:.0%} (from {baseline.baseline_count} to {count})",
                    current_count=count,
                    baseline_count=baseline.baseline_count,
                    current_confidence=confidence,
                    baseline_confidence=baseline.baseline_confidence,
                ))
            elif count_drop > self.COUNT_DROP_WARNING_THRESHOLD:
                alerts.append(QualityAlert(
                    fund_slug=fund_slug,
                    data_type=data_type,
                    severity="warning",
                    reason=f"Count dropped {count_drop:.0%} (from {baseline.baseline_count} to {count})",
                    current_count=count,
                    baseline_count=baseline.baseline_count,
                    current_confidence=confidence,
                    baseline_confidence=baseline.baseline_confidence,
                ))

        # Check for confidence drop
        if baseline.baseline_confidence > 0:
            confidence_drop = baseline.baseline_confidence - confidence

            if confidence_drop > self.CONFIDENCE_DROP_THRESHOLD:
                alerts.append(QualityAlert(
                    fund_slug=fund_slug,
                    data_type=data_type,
                    severity="warning",
                    reason=f"Confidence dropped {confidence_drop:.0%} (from {baseline.baseline_confidence:.2f} to {confidence:.2f})",
                    current_count=count,
                    baseline_count=baseline.baseline_count,
                    current_confidence=confidence,
                    baseline_confidence=baseline.baseline_confidence,
                ))

        return alerts

    def trigger_alerts(self, alerts: list[QualityAlert]) -> int:
        """
        Send alerts via configured channels.

        Quality alerts are sent immediately (not gated behind consecutive-failure
        thresholds) because a single large drop is already actionable.

        Args:
            alerts: List of QualityAlert objects

        Returns:
            Number of alerts sent
        """
        sent = 0

        for qa in alerts:
            # Convert to Alert format for AlertManager
            alert = Alert(
                title=f"[{qa.severity.upper()}] {qa.fund_slug}/{qa.data_type}: {qa.reason}",
                message=(
                    f"Fund: {qa.fund_slug}\n"
                    f"Data type: {qa.data_type}\n"
                    f"Issue: {qa.reason}\n"
                    f"Current: {qa.current_count} items (confidence: {qa.current_confidence:.2f})\n"
                    f"Baseline: {qa.baseline_count} items (confidence: {qa.baseline_confidence:.2f})"
                ),
                level=qa.severity,
                source=f"quality:{qa.fund_slug}:{qa.data_type}",
                metadata={
                    "fund_slug": qa.fund_slug,
                    "data_type": qa.data_type,
                    "current_count": qa.current_count,
                    "baseline_count": qa.baseline_count,
                    "current_confidence": qa.current_confidence,
                    "baseline_confidence": qa.baseline_confidence,
                },
            )

            # Log based on severity
            if qa.severity == "critical":
                logger.error(f"CRITICAL: {qa.fund_slug}/{qa.data_type} - {qa.reason}")
            elif qa.severity == "error":
                logger.warning(f"ERROR: {qa.fund_slug}/{qa.data_type} - {qa.reason}")
            else:
                logger.info(f"WARNING: {qa.fund_slug}/{qa.data_type} - {qa.reason}")

            # Route through record_failure() so Telegram fires after 2
            # consecutive failures (not on every transient glitch).
            self.alert_manager.record_failure(
                f"quality:{qa.fund_slug}:{qa.data_type}",
                qa.reason,
                asdict(qa),
            )
            sent += 1

        # Send all queued alerts via webhook + Telegram
        self.alert_manager.send_pending_alerts()

        return sent

    def generate_maintenance_status(
        self,
        extraction_results: dict[str, dict],
    ) -> MaintenanceStatus:
        """
        Generate current maintenance status for all scrapers.

        Args:
            extraction_results: Dict mapping "fund_slug:data_type" to results
                               with keys: count, confidence, status ("ok" | "error")

        Returns:
            MaintenanceStatus object
        """
        healthy = []
        degraded = []
        broken = []
        needing_attention = []

        for key, baseline in self.baselines.items():
            result = extraction_results.get(key, {})

            if not result:
                # No recent extraction - needs attention
                broken.append(key)
                needing_attention.append({
                    "fund_slug": baseline.fund_slug,
                    "data_type": baseline.data_type,
                    "status": "missing",
                    "reason": "No recent extraction results",
                    "baseline_count": baseline.baseline_count,
                    "last_successful": baseline.last_successful,
                })
                continue

            if result.get("status") == "error":
                broken.append(key)
                needing_attention.append({
                    "fund_slug": baseline.fund_slug,
                    "data_type": baseline.data_type,
                    "status": "error",
                    "reason": result.get("error", "Unknown error"),
                    "baseline_count": baseline.baseline_count,
                    "current_count": result.get("count", 0),
                })
                continue

            count = result.get("count", 0)
            confidence = result.get("confidence", 0)

            # Check quality
            if count == 0 and baseline.baseline_count > 0:
                broken.append(key)
                needing_attention.append({
                    "fund_slug": baseline.fund_slug,
                    "data_type": baseline.data_type,
                    "status": "broken",
                    "reason": f"Zero results (was {baseline.baseline_count})",
                    "baseline_count": baseline.baseline_count,
                    "current_count": count,
                })
            elif baseline.baseline_count > 0:
                drop = (baseline.baseline_count - count) / baseline.baseline_count
                if drop > self.COUNT_DROP_ERROR_THRESHOLD:
                    broken.append(key)
                    needing_attention.append({
                        "fund_slug": baseline.fund_slug,
                        "data_type": baseline.data_type,
                        "status": "broken",
                        "reason": f"Count dropped {drop:.0%}",
                        "baseline_count": baseline.baseline_count,
                        "current_count": count,
                    })
                elif drop > self.COUNT_DROP_WARNING_THRESHOLD:
                    degraded.append(key)
                    needing_attention.append({
                        "fund_slug": baseline.fund_slug,
                        "data_type": baseline.data_type,
                        "status": "degraded",
                        "reason": f"Count dropped {drop:.0%}",
                        "baseline_count": baseline.baseline_count,
                        "current_count": count,
                    })
                else:
                    healthy.append(key)
            else:
                healthy.append(key)

        status = MaintenanceStatus(
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_scrapers=len(self.baselines),
            healthy_scrapers=len(healthy),
            degraded_scrapers=len(degraded),
            broken_scrapers=len(broken),
            scrapers_needing_attention=needing_attention,
        )

        # Save to disk
        self._save_maintenance_status(status)

        return status

    def _save_maintenance_status(self, status: MaintenanceStatus):
        """Save maintenance status to disk."""
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.status_path, "w") as f:
            json.dump(status.to_dict(), f, indent=2)
        logger.info(f"Maintenance status saved to {self.status_path}")

    def initialize_baselines_from_results(self, results_path: Path):
        """
        Initialize baselines from existing extraction test results.

        Args:
            results_path: Path to extraction_test_results.json
        """
        if not results_path.exists():
            logger.warning(f"Results file not found: {results_path}")
            return

        with open(results_path) as f:
            data = json.load(f)

        # Process portfolio results
        for result in data.get("portfolio", []):
            fund_slug = result.get("fund")
            if not fund_slug:
                continue

            count = result.get("total_companies", 0)
            # Calculate average confidence from companies
            companies = result.get("companies", [])
            if companies:
                confidence = sum(c.get("confidence", 0.5) for c in companies) / len(companies)
            else:
                confidence = 0.0

            self.update_baseline(fund_slug, "portfolio", count, confidence)

        # Process team results (if present)
        for result in data.get("team", []):
            fund_slug = result.get("fund")
            if not fund_slug:
                continue

            count = result.get("total_members", 0)
            members = result.get("members", [])
            if members:
                confidence = sum(m.get("confidence", 0.5) for m in members) / len(members)
            else:
                confidence = 0.0

            self.update_baseline(fund_slug, "team", count, confidence)

        # Process news results (if present)
        for result in data.get("news", []):
            fund_slug = result.get("fund")
            if not fund_slug:
                continue

            count = result.get("total_items", 0)
            items = result.get("items", [])
            if items:
                confidence = sum(i.get("confidence", 0.5) for i in items) / len(items)
            else:
                confidence = 0.0

            self.update_baseline(fund_slug, "news", count, confidence)

        logger.info(f"Initialized {len(self.baselines)} baselines from results")


# Module-level helper functions
def get_quality_monitor(data_dir: Path) -> QualityMonitor:
    """Get a QualityMonitor instance for the given data directory."""
    return QualityMonitor(
        baselines_path=data_dir / "quality_baselines.json",
        status_path=data_dir / "maintenance_status.json",
    )


def check_and_alert(
    data_dir: Path,
    fund_slug: str,
    data_type: str,
    count: int,
    confidence: float,
) -> list[QualityAlert]:
    """
    Convenience function to check quality and trigger alerts.

    Args:
        data_dir: Data directory containing baselines
        fund_slug: The fund identifier
        data_type: Type of data
        count: Current extraction count
        confidence: Current average confidence

    Returns:
        List of alerts triggered
    """
    monitor = get_quality_monitor(data_dir)
    alerts = monitor.check_extraction_quality(fund_slug, data_type, count, confidence)

    if alerts:
        monitor.trigger_alerts(alerts)
    else:
        # Update baseline on successful extraction
        monitor.update_baseline(fund_slug, data_type, count, confidence)

    return alerts
