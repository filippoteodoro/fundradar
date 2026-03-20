"""
Data writer for Fundradar.

Handles writing signals, deals, and portfolio updates to storage.
Supports both file-based JSON and Supabase backends.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .enrichment import PortfolioCompany
from .entity_resolver import CompanyEntity
from .io_utils import safe_json_write, recover_icloud_conflict_copy
from .portfolio_diff import CompanyChange

logger = logging.getLogger(__name__)


@dataclass
class SignalRecord:
    """A signal to be written."""

    id: str
    fund_slug: str
    signal_type: str
    title: str
    what_changed: str
    source_url: str | None
    source_name: str | None
    observed_at: str
    snapshot_id: str | None = None
    company_name: str | None = None
    confidence: float = 1.0
    metadata: dict | None = None


@dataclass
class DealRecord:
    """A deal record to be written."""

    id: str
    fund_slug: str
    company_id: str | None
    company_name: str
    deal_type: str
    source_signal_id: str | None
    source_url: str | None
    observed_at: str
    confidence: float = 1.0


@dataclass
class PortfolioRecord:
    """A fund-company portfolio relationship."""

    fund_slug: str
    company_name: str
    status: str  # 'current', 'exited'
    source_signal_id: str | None = None
    entry_date: str | None = None
    exit_date: str | None = None
    confidence: float = 1.0


class DataStore(Protocol):
    """Protocol for data storage backends."""

    def write_signal(self, signal: SignalRecord) -> bool: ...
    def write_deal(self, deal: DealRecord) -> bool: ...
    def write_portfolio_record(self, record: PortfolioRecord) -> bool: ...
    def get_portfolio_for_fund(self, fund_slug: str) -> list[PortfolioRecord]: ...


class JsonFileStore:
    """
    JSON file-based storage backend.

    Stores data in separate JSON files for signals, deals, and portfolio.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.signals_path = data_dir / "detected_signals.json"
        self.deals_path = data_dir / "deal_updates.json"
        self.portfolio_path = data_dir / "portfolio_items.json"

        # Ensure directory exists
        data_dir.mkdir(parents=True, exist_ok=True)

        # Load existing data
        self._signals = self._load_json(self.signals_path, {"signals": [], "signal_count": 0})
        self._deals = self._load_json(self.deals_path, {"deals": []})
        self._portfolios = self._load_json(self.portfolio_path, {"fund_portfolios": {}})

    def _load_json(self, path: Path, default: dict) -> dict:
        """Load JSON file or return default."""
        path = recover_icloud_conflict_copy(path)
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return default

    def _save_json(self, path: Path, data: dict):
        """Save data to JSON file (atomic write)."""
        safe_json_write(path, data)

    def write_signal(self, signal: SignalRecord) -> bool:
        """Write a signal record."""
        try:
            signal_dict = asdict(signal)
            self._signals["signals"].append(signal_dict)
            self._signals["signal_count"] += 1
            self._save_json(self.signals_path, self._signals)
            logger.debug(f"Wrote signal: {signal.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to write signal: {e}")
            return False

    def write_deal(self, deal: DealRecord) -> bool:
        """Write a deal record."""
        try:
            deal_dict = asdict(deal)
            self._deals["deals"].append(deal_dict)
            self._save_json(self.deals_path, self._deals)
            logger.debug(f"Wrote deal: {deal.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to write deal: {e}")
            return False

    def write_portfolio_record(self, record: PortfolioRecord) -> bool:
        """Write or update a portfolio record in monitor format."""
        try:
            fund_slug = record.fund_slug
            if fund_slug not in self._portfolios["fund_portfolios"]:
                self._portfolios["fund_portfolios"][fund_slug] = []

            # Convert to monitor format
            record_dict = {
                "name": record.company_name,
                "sector": None,
                "status": record.status or "current",
                "confidence": record.confidence,
                "website": None,
                "description": None,
                "detail_page_url": None,
                "headquarters": None,
                "investment_date": record.entry_date,
            }

            # Check if record already exists (match by name)
            existing = None
            for i, existing_record in enumerate(self._portfolios["fund_portfolios"][fund_slug]):
                if existing_record.get("name") == record.company_name:
                    existing = i
                    break

            if existing is not None:
                # Update existing
                self._portfolios["fund_portfolios"][fund_slug][existing] = record_dict
            else:
                # Add new
                self._portfolios["fund_portfolios"][fund_slug].append(record_dict)

            self._save_json(self.portfolio_path, self._portfolios)
            logger.debug(f"Wrote portfolio record: {fund_slug}/{record.company_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to write portfolio record: {e}")
            return False

    def get_portfolio_for_fund(self, fund_slug: str) -> list[PortfolioRecord]:
        """Get all portfolio records for a fund."""
        records = self._portfolios["fund_portfolios"].get(fund_slug, [])
        return [
            PortfolioRecord(
                fund_slug=fund_slug,
                company_name=r.get("name", ""),
                status=r.get("status", "current"),
                source_signal_id=None,
                entry_date=r.get("investment_date"),
                exit_date=None,
                confidence=r.get("confidence", 1.0),
            )
            for r in records
        ]


class DataWriter:
    """
    High-level data writer that handles transactions.

    Coordinates writing signals, deals, and portfolio updates.
    """

    def __init__(self, store: DataStore | None = None, data_dir: Path | None = None):
        if store:
            self.store = store
        elif data_dir:
            self.store = JsonFileStore(data_dir)
        else:
            default_dir = Path(__file__).parent.parent.parent.parent / "data" / "derived"
            self.store = JsonFileStore(default_dir)

        self._signal_counter = 0

    def _generate_signal_id(self) -> str:
        """Generate unique signal ID."""
        self._signal_counter += 1
        return f"signal-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._signal_counter:04d}"

    def _generate_deal_id(self) -> str:
        """Generate unique deal ID."""
        return f"deal-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._signal_counter:04d}"

    def write_portfolio_change(
        self,
        fund_slug: str,
        change: CompanyChange,
        entity: CompanyEntity | None = None,
    ) -> tuple[SignalRecord | None, DealRecord | None]:
        """
        Write a portfolio change to storage.

        Creates appropriate signal and deal records.

        Args:
            fund_slug: The fund identifier
            change: The portfolio change
            entity: Resolved company entity

        Returns:
            Tuple of (signal_record, deal_record)
        """
        now = datetime.now(timezone.utc).isoformat()

        # Create signal
        signal_type = "portfolio_update"
        title = f"Portfolio update: {change.company.name}"

        if change.change_type == "added":
            signal_type = "deal_announced"
            title = f"New portfolio company: {change.company.name}"
        elif change.change_type == "removed":
            signal_type = "exit_announced"
            title = f"Portfolio exit: {change.company.name}"
        elif change.change_type == "status_changed" and change.new_status == "exited":
            signal_type = "exit_announced"
            title = f"Exit: {change.company.name}"

        signal = SignalRecord(
            id=self._generate_signal_id(),
            fund_slug=fund_slug,
            signal_type=signal_type,
            title=title,
            what_changed=f"{change.change_type}: {change.company.name}",
            source_url=change.company.source_url,
            source_name="Portfolio Monitor",
            observed_at=now,
            company_name=change.company.name,
            confidence=change.confidence,
        )

        self.store.write_signal(signal)

        # Create deal if new investment or exit
        deal = None
        if change.change_type in ("added", "removed") or (
            change.change_type == "status_changed" and change.new_status == "exited"
        ):
            deal_type = "new_investment" if change.change_type == "added" else "exit"
            deal = DealRecord(
                id=self._generate_deal_id(),
                fund_slug=fund_slug,
                company_id=entity.id if entity else None,
                company_name=change.company.name,
                deal_type=deal_type,
                source_signal_id=signal.id,
                source_url=change.company.source_url,
                observed_at=now,
                confidence=change.confidence,
            )
            self.store.write_deal(deal)

        # Update portfolio record
        portfolio_record = PortfolioRecord(
            fund_slug=fund_slug,
            company_name=change.company.name,
            status=change.new_status or "current",
            source_signal_id=signal.id,
            entry_date=now if change.change_type == "added" else None,
            exit_date=now if change.new_status == "exited" else None,
            confidence=change.confidence,
        )
        self.store.write_portfolio_record(portfolio_record)

        return signal, deal

    def get_fund_portfolio(self, fund_slug: str) -> list[PortfolioRecord]:
        """Get current portfolio for a fund."""
        return self.store.get_portfolio_for_fund(fund_slug)


# Module-level writer
_writer: DataWriter | None = None


def get_data_writer() -> DataWriter:
    """Get the global data writer."""
    global _writer
    if _writer is None:
        _writer = DataWriter()
    return _writer
