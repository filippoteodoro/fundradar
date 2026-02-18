"""
Website monitoring and signal generation for Fundradar.

Monitors fund websites, detects changes via content hashing and normalized diffs.
Generates signals with Italy relevance scoring, supports graceful shutdown,
and enriches portfolio/team/news data through specialized extractors.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import signal
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TypedDict, Literal, Callable

from .date_utils import normalize_news_date
from .differ import DiffResult, NewsItem, NewsPageResult, compute_diff, compute_high_value_diff, compute_normalized_diff, generate_what_changed, extract_news_items, compare_news_items, classify_news_signal, compare_team_members
from .io_utils import safe_json_write, backup_before_write
from .slug_normalizer import get_slug_normalizer
from .url_utils import canonical_url, extract_domain
import logging
import re

logger = logging.getLogger(__name__)


def _normalize_signal_title(title: str, max_len: int = 200) -> str:
    """Normalize whitespace and truncate at word boundary."""
    # Collapse multiple spaces (from get_text artifacts, etc.)
    title = re.sub(r'\s+', ' ', title).strip()
    if len(title) <= max_len:
        return title
    # Truncate at last space before max_len
    truncated = title[:max_len].rsplit(' ', 1)[0]
    return truncated


# ---------------------------------------------------------------------------
# Parallel fetching configuration
# ---------------------------------------------------------------------------
MAX_WORKERS = int(os.environ.get("FUNDRADAR_MAX_WORKERS", "8"))
PER_URL_TIMEOUT = 120  # seconds - per-URL safety net for stuck fetches
MAX_TOTAL_TIMEOUT = 300  # seconds (5 min) - hard ceiling for entire batch

# ---------------------------------------------------------------------------
# Support-staff filter: titles irrelevant for PE/VC investment signals
# ---------------------------------------------------------------------------
# Patterns that indicate non-investment support/admin roles.
# Kept as compiled regexes for performance.
_SUPPORT_ROLE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\bassistant\b(?!.*\b(?:invest|portfolio|fund manager|vice president|vp)\b)',
        r'\bexecutive\s+assistant\b',
        r'\bteam\s+assistant\b',
        r'\bpersonal\s+assistant\b',
        r'\boffice\s+manager\b',
        r'\boffice\s+coordinator\b',
        r'\breceptionist\b',
        r'\bfront\s+desk\b',
        r'\bsecretar(?:y|ial)\b',
        r'\badministrat(?:ive|ion)\b(?!.*\b(?:partner|director|board|fund)\b)',
        r'\baccountant\b',
        r'\bbookkeeper\b',
        r'\b(?:it|system)\s+(?:support|admin|helpdesk|technician)\b',
        r'\bhuman\s+resources?\b(?!.*\bdirector\b)',
        r'\bhr\s+(?:coordinator|assistant|officer|specialist|admin)\b',
        r'\bfacilities\b',
        r'\bdriver\b',
        r'\bcleaning\b',
        r'\bmailroom\b',
        r'\bjunior\s+(?:financial\s+)?controller\b',
        r'\bsupport\s+staff\b',
        r'\boffice\s+&\s+events\b',
    ]
]


def is_support_role(title: str | None) -> bool:
    """Return True if the title indicates non-investment support staff."""
    if not title:
        return False
    return any(pat.search(title) for pat in _SUPPORT_ROLE_PATTERNS)

# Import site-specific extractor for richer extraction
try:
    from .site_extractor import extract_news_items as site_extract_news_items, ExtractedNewsItem, compute_fingerprint
    SITE_EXTRACTOR_AVAILABLE = True
except ImportError:
    SITE_EXTRACTOR_AVAILABLE = False
    ExtractedNewsItem = dict
    compute_fingerprint = None

# Import strategy orchestrator for fund-specific news extractors
try:
    from .strategy_orchestrator import StrategyOrchestrator as _StrategyOrchestrator, get_orchestrator as _get_orchestrator
    STRATEGY_ORCHESTRATOR_AVAILABLE = True
except ImportError:
    STRATEGY_ORCHESTRATOR_AVAILABLE = False
    _get_orchestrator = None

# Import specialized extractors (Phase 3)
try:
    from .extractors import PortfolioExtractor, TeamExtractor, NewsExtractor
    from .extractors import ExtractedCompany, ExtractedTeamMember
    SPECIALIZED_EXTRACTORS_AVAILABLE = True
except ImportError:
    SPECIALIZED_EXTRACTORS_AVAILABLE = False
    PortfolioExtractor = None
    TeamExtractor = None
    NewsExtractor = None

# Import detail page fetcher (Phase 6)
try:
    from .detail_page_fetcher import DetailPageFetcher, enrich_portfolio_sync
    from .strategies.site_specific import get_site_extractor
    DETAIL_FETCHER_AVAILABLE = True
except ImportError:
    DETAIL_FETCHER_AVAILABLE = False
    DetailPageFetcher = None
    enrich_portfolio_sync = None

# Import quality monitor (Phase 6)
try:
    from .quality_monitor import QualityMonitor, check_and_alert
    QUALITY_MONITOR_AVAILABLE = True
except ImportError:
    QUALITY_MONITOR_AVAILABLE = False
    QualityMonitor = None
    check_and_alert = None
from .domain_policies import DomainPolicyRegistry, FetchPolicy, detect_requires_headless, update_domain_policy_headless
from .fetcher import SnapshotStore, fetch_url, FetchResult
from .relevance import ItalyRelevanceScorer, RelevanceResult, PageCategory

# Playwright imports - may not be available
PLAYWRIGHT_AVAILABLE = False
try:
    from .playwright_fetcher import PlaywrightFetcher, FetchOptions, PLAYWRIGHT_AVAILABLE as PW_AVAIL
    PLAYWRIGHT_AVAILABLE = PW_AVAIL
except ImportError:
    PlaywrightFetcher = None
    FetchOptions = None


@dataclass
class ShutdownState:
    """Tracks the state of a graceful shutdown."""

    requested: bool = False
    request_time: float | None = None
    completed: bool = False
    current_url: str | None = None
    urls_processed: int = 0
    urls_total: int = 0
    signals_generated: int = 0


class GracefulShutdown:
    """
    Handles graceful shutdown for long-running monitor processes.

    Usage:
        shutdown = GracefulShutdown(timeout=30)
        shutdown.install_handlers()

        while not shutdown.should_stop():
            # do work
            pass

        shutdown.cleanup()

    Features:
    - Captures SIGTERM and SIGINT
    - Allows configurable timeout before forced exit
    - Logs shutdown progress
    - Can checkpoint work in progress
    """

    # Default timeout before forced exit (from env or 30s)
    DEFAULT_TIMEOUT = float(os.environ.get("FUNDRADAR_SHUTDOWN_TIMEOUT", "30"))

    def __init__(self, timeout: float | None = None, on_shutdown: Callable[[], None] | None = None):
        self.timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        self.on_shutdown = on_shutdown
        self.state = ShutdownState()
        self._lock = threading.RLock()
        self._original_sigterm = None
        self._original_sigint = None
        self._timer: threading.Timer | None = None

    def install_handlers(self):
        """Install signal handlers for graceful shutdown."""
        def handler(signum, frame):
            signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
            self._handle_shutdown_signal(signal_name)

        self._original_sigterm = signal.signal(signal.SIGTERM, handler)
        self._original_sigint = signal.signal(signal.SIGINT, handler)

        print(f"Graceful shutdown handlers installed (timeout: {self.timeout}s)")

    def _handle_shutdown_signal(self, signal_name: str):
        """Handle a shutdown signal."""
        with self._lock:
            if self.state.requested:
                # Second signal - force exit
                print(f"\n{signal_name} received again - forcing immediate exit")
                import sys
                sys.exit(130)

            self.state.requested = True
            self.state.request_time = datetime.now(timezone.utc).timestamp()

            print(f"\n{signal_name} received - initiating graceful shutdown...")
            print(f"  Completing current work (timeout: {self.timeout}s)")
            print(f"  Send signal again to force immediate exit")

            if self.state.current_url:
                print(f"  Currently processing: {self.state.current_url}")

            # Start timeout timer
            self._timer = threading.Timer(self.timeout, self._force_exit)
            self._timer.daemon = True
            self._timer.start()

            # Call shutdown callback if provided
            if self.on_shutdown:
                try:
                    self.on_shutdown()
                except Exception as e:
                    print(f"  Warning: shutdown callback failed: {e}")

    def _force_exit(self):
        """Force exit after timeout."""
        print(f"\nShutdown timeout ({self.timeout}s) exceeded - forcing exit")
        self._log_final_state()
        import sys
        sys.exit(1)

    def should_stop(self) -> bool:
        """Check if shutdown has been requested."""
        with self._lock:
            return self.state.requested

    def set_current_url(self, url: str | None):
        """Set the URL currently being processed."""
        with self._lock:
            self.state.current_url = url

    def set_progress(self, processed: int, total: int, signals: int = 0):
        """Update progress for logging."""
        with self._lock:
            self.state.urls_processed = processed
            self.state.urls_total = total
            self.state.signals_generated = signals

    def _log_final_state(self):
        """Log the final state before exit."""
        with self._lock:
            print(f"\nShutdown Summary:")
            print(f"  URLs processed: {self.state.urls_processed}/{self.state.urls_total}")
            print(f"  Signals generated: {self.state.signals_generated}")
            if self.state.current_url:
                print(f"  Last URL: {self.state.current_url}")

    def cleanup(self):
        """Clean up handlers and log final state."""
        with self._lock:
            self.state.completed = True

            # Cancel timer if running
            if self._timer:
                self._timer.cancel()
                self._timer = None

            # Restore original signal handlers
            if self._original_sigterm:
                signal.signal(signal.SIGTERM, self._original_sigterm)
            if self._original_sigint:
                signal.signal(signal.SIGINT, self._original_sigint)

            if self.state.requested:
                self._log_final_state()
                print("Graceful shutdown completed")

    def checkpoint(self, checkpoint_path: Path, data: dict):
        """Save a checkpoint file for recovery."""
        checkpoint = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "state": {
                "urls_processed": self.state.urls_processed,
                "urls_total": self.state.urls_total,
                "signals_generated": self.state.signals_generated,
                "current_url": self.state.current_url,
            },
            "data": data,
        }

        safe_json_write(checkpoint_path, checkpoint)

        print(f"  Checkpoint saved: {checkpoint_path}")


UrlStatusType = Literal["ok", "404", "403", "dns_error", "ssl_error", "timeout", "other_error", "unknown"]


class UrlStatusRecord(TypedDict):
    """Tracking status for a monitored URL."""
    url: str
    status: UrlStatusType
    status_code: int | None
    error_message: str | None
    last_checked_at: str
    consecutive_failures: int
    next_check_after: str | None  # Backoff: don't check until this time


class UrlStatusStore:
    """
    Tracks the health status of monitored URLs.

    Implements retry/backoff policy:
    - URLs with consecutive failures get deprioritized
    - Backoff increases exponentially with failures
    """

    BACKOFF_MINUTES = [0, 5, 15, 60, 240, 1440]  # 0, 5min, 15min, 1h, 4h, 24h

    def __init__(self, store_path: Path):
        self.store_path = store_path
        self._dirty = False
        self._load()

    def _load(self):
        """Load status records from disk."""
        if self.store_path.exists():
            with open(self.store_path) as f:
                data = json.load(f)
                self.statuses: dict[str, UrlStatusRecord] = data.get("statuses", {})
        else:
            self.statuses = {}

    def _save(self):
        """Save status records to disk."""
        safe_json_write(self.store_path, {"statuses": self.statuses})

    def flush(self):
        """Flush to disk if any changes occurred."""
        if self._dirty:
            self._save()
            self._dirty = False

    def should_check(self, url: str) -> bool:
        """Check if a URL should be checked now (respecting backoff)."""
        if url not in self.statuses:
            return True

        status = self.statuses[url]
        next_check = status.get("next_check_after")
        if not next_check:
            return True

        return datetime.now(timezone.utc) >= datetime.fromisoformat(next_check)

    def update_status(self, url: str, status_code: int | None, error: str | None):
        """Update the status of a URL after a check."""
        now = datetime.now(timezone.utc)

        # Determine status type
        if error:
            error_lower = error.lower()
            if "timeout" in error_lower:
                status_type: UrlStatusType = "timeout"
            elif "ssl" in error_lower or "certificate" in error_lower:
                status_type = "ssl_error"
            elif "dns" in error_lower or "name or service" in error_lower or "getaddrinfo" in error_lower:
                status_type = "dns_error"
            else:
                status_type = "other_error"
        elif status_code == 200:
            status_type = "ok"
        elif status_code == 404:
            status_type = "404"
        elif status_code == 403:
            status_type = "403"
        elif status_code:
            status_type = "other_error"
        else:
            status_type = "unknown"

        # Get previous record for consecutive failure tracking
        prev = self.statuses.get(url)
        if status_type == "ok":
            consecutive_failures = 0
            next_check_after = None
        else:
            consecutive_failures = (prev.get("consecutive_failures", 0) if prev else 0) + 1
            # Calculate backoff
            backoff_idx = min(consecutive_failures, len(self.BACKOFF_MINUTES) - 1)
            backoff_minutes = self.BACKOFF_MINUTES[backoff_idx]
            next_check_after = (now + timedelta(minutes=backoff_minutes)).isoformat() if backoff_minutes > 0 else None

        self.statuses[url] = {
            "url": url,
            "status": status_type,
            "status_code": status_code,
            "error_message": error,
            "last_checked_at": now.isoformat(),
            "consecutive_failures": consecutive_failures,
            "next_check_after": next_check_after,
        }
        self._dirty = True

    def get_status(self, url: str) -> UrlStatusRecord | None:
        """Get the current status of a URL."""
        return self.statuses.get(url)

    def generate_report(self) -> dict:
        """Generate a report of URL statuses for maintenance."""
        by_status: dict[str, list[str]] = {}
        by_domain: dict[str, dict[str, int]] = {}

        for url, record in self.statuses.items():
            status = record["status"]
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(url)

            # Group by domain
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                if domain not in by_domain:
                    by_domain[domain] = {}
                by_domain[domain][status] = by_domain[domain].get(status, 0) + 1
            except:
                pass

        # Find problematic domains (high failure rate)
        problem_domains = []
        for domain, counts in by_domain.items():
            total = sum(counts.values())
            failures = total - counts.get("ok", 0)
            if total > 0 and failures / total > 0.5:
                problem_domains.append({
                    "domain": domain,
                    "total": total,
                    "failures": failures,
                    "counts": counts,
                })

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_urls": len(self.statuses),
            "by_status": {k: len(v) for k, v in by_status.items()},
            "failing_urls": {
                status: urls[:20]  # Limit to 20 per status
                for status, urls in by_status.items()
                if status != "ok"
            },
            "problem_domains": sorted(problem_domains, key=lambda d: d["failures"], reverse=True)[:20],
        }


class SignalRecord(TypedDict):
    """A generated signal from website changes."""

    id: str
    fund_id: str
    fund_slug: str
    signal_type: str
    title: str
    what_changed: str
    source_url: str
    source_name: str
    published_at: str | None
    observed_at: str
    created_at: str
    snapshot_id: str
    diff_summary: str
    page_category: str  # Canonical: HOME, NEWS, TEAM, PORTFOLIO, CAREERS, ABOUT, OTHER
    page_type: str  # Detailed subtype: NEWS_LIST, TEAM_LIST, PORTFOLIO_LIST, etc.
    # Sprint 2: Italy relevance scoring
    relevance_score: float  # 0.0 to 1.0
    relevance_reasons: list[str]
    italy_relevant: bool
    extracted_entities: dict  # {companies: [], people: [], locations: []}


@dataclass
class MonitoredUrl:
    """A URL being monitored for a fund."""

    url: str
    fund_slug: str
    fund_name: str
    page_type: str  # detailed subtype: 'team_list', 'portfolio_list', 'news_item', etc.
    category: str = ""  # canonical category from config: 'NEWS', 'TEAM', 'PORTFOLIO', 'CAREERS', etc.


# Signal quality filtering: only generate signals from these page categories
# HOME pages are too noisy (timestamps, carousels, dynamic content)
SIGNAL_PAGE_CATEGORIES = {'NEWS', 'TEAM', 'PORTFOLIO', 'CAREERS', 'ABOUT'}


class SignalStore:
    """File-based storage for generated signals."""

    def __init__(self, store_path: Path):
        self.store_path = store_path
        self._dirty = False
        self._load()
        self._index_keys()

    def _load(self):
        """Load signals from disk."""
        if self.store_path.exists():
            with open(self.store_path) as f:
                data = json.load(f)
                self.signals: list[SignalRecord] = data.get("signals", [])
                self.signal_count = data.get("signal_count", 0)
        else:
            self.signals = []
            self.signal_count = 0

    def _index_keys(self):
        """Build a fast lookup to avoid duplicate signals."""
        self._seen_keys: set[str] = set()
        for signal in self.signals:
            key = self._signal_key(signal)
            if key:
                self._seen_keys.add(key)

    def _signal_key(self, signal: SignalRecord) -> str:
        """Composite key for deduplication."""
        source_url = (signal.get("source_url") or "").strip()
        title = (signal.get("title") or "").strip()
        published_at = (signal.get("published_at") or "").strip()
        what_changed = (signal.get("what_changed") or "").strip()
        return f"{source_url}::{title}::{published_at}::{what_changed}"

    def _save(self):
        """Save signals to disk."""
        backup_before_write(self.store_path)
        safe_json_write(
            self.store_path,
            {"signals": self.signals, "signal_count": self.signal_count},
        )

    def flush(self):
        """Flush to disk if any changes occurred."""
        if self._dirty:
            self._save()
            self._dirty = False

    def add(self, signal: SignalRecord):
        """Add a new signal, sanitizing scraped text fields."""
        from .io_utils import sanitize_text, sanitize_url

        signal["title"] = sanitize_text(signal.get("title"), max_length=200) or ""
        signal["what_changed"] = sanitize_text(signal.get("what_changed"), max_length=2000) or ""
        signal["diff_summary"] = sanitize_text(signal.get("diff_summary"), max_length=500) or ""
        signal["source_url"] = sanitize_url(signal.get("source_url")) or ""
        signal["source_name"] = sanitize_text(signal.get("source_name"), max_length=200) or ""

        # Sanitize extracted entities
        entities = signal.get("extracted_entities", {})
        if entities:
            entities["companies"] = [
                sanitize_text(c, max_length=200) for c in entities.get("companies", [])
                if sanitize_text(c, max_length=200)
            ]
            entities["people"] = [
                sanitize_text(p, max_length=200) for p in entities.get("people", [])
                if sanitize_text(p, max_length=200)
            ]
            entities["locations"] = [
                sanitize_text(loc, max_length=200) for loc in entities.get("locations", [])
                if sanitize_text(loc, max_length=200)
            ]

        # Deduplicate by composite key to avoid duplicates on force-extract runs
        key = self._signal_key(signal)
        if key and key in self._seen_keys:
            return

        self.signals.append(signal)
        self.signal_count += 1
        if key:
            self._seen_keys.add(key)
        self._dirty = True

    def get_latest_for_fund(self, fund_slug: str, limit: int = 10) -> list[SignalRecord]:
        """Get the most recent signals for a fund."""
        fund_signals = [s for s in self.signals if s["fund_slug"] == fund_slug]
        return sorted(fund_signals, key=lambda s: s["observed_at"], reverse=True)[:limit]


class NewsItemsStore:
    """
    Stores news items per URL for tracking new items.

    Each URL has a list of item fingerprints that we've seen.
    """

    def __init__(self, store_path: Path):
        self.store_path = store_path
        self._dirty = False
        self._load()

    def _load(self):
        """Load from disk."""
        if self.store_path.exists():
            with open(self.store_path) as f:
                data = json.load(f)
                self.url_items: dict[str, list[NewsItem]] = data.get("url_items", {})
        else:
            self.url_items = {}

    def _save(self):
        """Save to disk."""
        safe_json_write(self.store_path, {"url_items": self.url_items})

    def flush(self):
        """Flush to disk if any changes occurred."""
        if self._dirty:
            self._save()
            self._dirty = False

    def get_items(self, url: str) -> list[NewsItem]:
        """Get previously seen items for a URL."""
        return self.url_items.get(url, [])

    def update_items(self, url: str, items: list[NewsItem]):
        """Update the items for a URL, sanitizing scraped text fields."""
        from .io_utils import sanitize_text, sanitize_url

        sanitized = []
        for item in items:
            sanitized.append({
                **item,
                "title": sanitize_text(item.get("title"), max_length=300) or "",
                "url": sanitize_url(item.get("url")),
            })
        self.url_items[url] = sanitized
        self._dirty = True


class PortfolioStore:
    """
    Stores extracted portfolio companies per fund for tracking changes.

    Phase 3: Used by new specialized extractors.
    """

    def __init__(self, store_path: Path):
        self.store_path = store_path
        self._dirty = False
        self._backed_up = False  # Only backup once per session
        self._load()

    def _load(self):
        """Load from disk."""
        if self.store_path.exists():
            with open(self.store_path) as f:
                data = json.load(f)
                self.fund_portfolios: dict[str, list[dict]] = data.get("fund_portfolios", {})
                self.fund_source_urls: dict[str, str] = data.get("fund_source_urls", {})
                self.geo_scopes: dict[str, str] = data.get("geo_scopes", {})
                self.fund_portfolio_notes: dict[str, str] = data.get("fund_portfolio_notes", {})
        else:
            self.fund_portfolios = {}
            self.fund_source_urls = {}
            self.geo_scopes = {}
            self.fund_portfolio_notes = {}

    def _save(self):
        """Save to disk."""
        if not self._backed_up:
            backup_before_write(self.store_path)
            self._backed_up = True
        out: dict = {
            "fund_portfolios": self.fund_portfolios,
            "fund_source_urls": self.fund_source_urls,
            "geo_scopes": self.geo_scopes,
        }
        if self.fund_portfolio_notes:
            out["fund_portfolio_notes"] = self.fund_portfolio_notes
        safe_json_write(self.store_path, out)

    def flush(self):
        """Flush to disk if any changes occurred."""
        if self._dirty:
            self._save()
            self._dirty = False

    def get_portfolio(self, fund_slug: str) -> list[dict]:
        """Get previously extracted portfolio for a fund."""
        return self.fund_portfolios.get(fund_slug, [])

    def update_portfolio(self, fund_slug: str, companies: list[dict], source_url: str | None = None):
        """Update the portfolio for a fund with pre-write validation and sanitization."""
        from .io_utils import sanitize_text, sanitize_url
        from .portfolio_validation import validate_and_clean_portfolio

        # Clean names and filter garbage entries before counting
        companies = validate_and_clean_portfolio(companies, fund_slug)

        existing = self.fund_portfolios.get(fund_slug, [])
        existing_count = len(existing)
        new_count = len(companies)

        # Guard 1: Never overwrite existing data with empty results
        if existing_count > 0 and new_count == 0:
            logger.warning(
                f"Skipping portfolio update for {fund_slug}: "
                f"empty results would overwrite {existing_count} existing entries. "
                f"Website may be down or extractor needs updating."
            )
            return

        # Guard 2: if new count is less than 50% of existing, skip update
        if existing_count >= 4 and new_count < existing_count * 0.5:
            logger.warning(
                f"Skipping portfolio update for {fund_slug}: "
                f"new count ({new_count}) < 50% of existing ({existing_count}). "
                f"Possible extraction failure."
            )
            return

        # Sanitize scraped text fields and add source tracking
        for company in companies:
            company["name"] = sanitize_text(company.get("name"), max_length=200) or ""
            company["sector"] = sanitize_text(company.get("sector"), max_length=200)
            company["description"] = sanitize_text(company.get("description"), max_length=1000)
            company["headquarters"] = sanitize_text(company.get("headquarters"), max_length=200)
            company["website"] = sanitize_url(company.get("website"))
            company["detail_page_url"] = sanitize_url(company.get("detail_page_url"))

            # Add source tracking to each entry (if not already present)
            if source_url and not company.get("source_url"):
                company["source_url"] = source_url
            if not company.get("data_source"):
                company["data_source"] = "fund_website"

        # Merge: preserve enriched fields (sector, hq, description) from existing entries
        # that match by normalized name — prevents Gemini enrichment from being lost on re-extract
        if existing:
            existing_by_name: dict[str, dict] = {}
            for e in existing:
                name_key = (e.get("name") or "").lower().strip()
                if name_key:
                    existing_by_name[name_key] = e

            new_name_keys: set[str] = set()
            for company in companies:
                name_key = (company.get("name") or "").lower().strip()
                new_name_keys.add(name_key)
                old = existing_by_name.get(name_key)
                if old:
                    # Keep curated entries stable across re-extractions.
                    if old.get("curation_locked"):
                        for field in (
                            "status",
                            "sector",
                            "headquarters",
                            "description",
                            "website",
                            "investment_date",
                            "source_url",
                            "data_source",
                            "detail_page_url",
                            "curation_locked",
                            "curation_source",
                            "curation_applied_at",
                            "curation_note",
                            "gemini_confidence",
                            "gemini_reason",
                            "gemini_evidence_urls",
                        ):
                            if old.get(field) is not None:
                                company[field] = old.get(field)

                    # Carry over enriched fields if new extraction doesn't have them
                    for field in ("sector", "headquarters", "description"):
                        if not company.get(field) and old.get(field):
                            company[field] = old[field]

            # Preserve enriched entries that the extractor no longer returns
            # (e.g. website redesign removed a company, but we have curated data)
            for name_key, old_entry in existing_by_name.items():
                if name_key not in new_name_keys:
                    if old_entry.get("curation_locked"):
                        companies.append(old_entry)
                        logger.info(
                            f"Preserved curation-locked entry '{old_entry.get('name')}' for {fund_slug} "
                            f"(not returned by extractor)"
                        )
                        continue
                    has_enrichment = any(
                        old_entry.get(f) for f in ("sector", "headquarters", "description")
                    )
                    if has_enrichment:
                        companies.append(old_entry)
                        logger.info(
                            f"Preserved enriched entry '{old_entry.get('name')}' for {fund_slug} "
                            f"(no longer returned by extractor)"
                        )

        self.fund_portfolios[fund_slug] = companies
        if source_url:
            self.fund_source_urls[fund_slug] = source_url
        self._dirty = True


class TeamStore:
    """
    Stores extracted team members per fund for tracking changes.

    Phase 3: Used by new specialized extractors.
    """

    def __init__(self, store_path: Path):
        self.store_path = store_path
        self._dirty = False
        self._load()

    def _load(self):
        """Load from disk."""
        if self.store_path.exists():
            with open(self.store_path) as f:
                data = json.load(f)
                self.fund_teams: dict[str, list[dict]] = data.get("fund_teams", {})
        else:
            self.fund_teams = {}

    def _save(self):
        """Save to disk."""
        safe_json_write(self.store_path, {"fund_teams": self.fund_teams})

    def flush(self):
        """Flush to disk if any changes occurred."""
        if self._dirty:
            self._save()
            self._dirty = False

    def get_team(self, fund_slug: str) -> list[dict]:
        """Get previously extracted team for a fund."""
        return self.fund_teams.get(fund_slug, [])

    def update_team(self, fund_slug: str, members: list[dict]):
        """Update the team for a fund, sanitizing scraped text fields."""
        from .io_utils import sanitize_text

        for member in members:
            member["name"] = sanitize_text(member.get("name"), max_length=200) or ""
            member["title"] = sanitize_text(member.get("title"), max_length=200)
            member["role"] = sanitize_text(member.get("role"), max_length=200)

        self.fund_teams[fund_slug] = members
        self._dirty = True


class WebsiteMonitor:
    """
    Monitors fund websites and generates signals on changes.

    Usage:
        monitor = WebsiteMonitor(data_dir)
        signals = monitor.check_urls(urls_to_monitor)

    Sprint 3 enhancements:
    - Playwright fallback for JS-heavy sites
    - Auto-detection of sites requiring headless browser
    - Async support for Playwright operations
    """

    # Minimum content length to consider a page as properly rendered
    MIN_CONTENT_LENGTH = 500

    def __init__(self, data_dir: Path, use_playwright: bool = True, enable_graceful_shutdown: bool = False, force_extract: bool = False):
        self.data_dir = data_dir
        self.snapshot_store = SnapshotStore(data_dir / "snapshots.json")
        self.signal_store = SignalStore(data_dir / "detected_signals.json")
        self.url_status_store = UrlStatusStore(data_dir / "url_status.json")
        self.news_items_store = NewsItemsStore(data_dir / "news_items.json")
        self.domain_policies = DomainPolicyRegistry(data_dir / "domain_policies.json")
        # Phase 3: Portfolio and team stores
        self.portfolio_store = PortfolioStore(data_dir / "portfolio_items.json")
        self.team_store = TeamStore(data_dir / "team_items.json")
        # Phase 3: Specialized extractors
        self._portfolio_extractor = PortfolioExtractor() if SPECIALIZED_EXTRACTORS_AVAILABLE else None
        self._team_extractor = TeamExtractor() if SPECIALIZED_EXTRACTORS_AVAILABLE else None
        # Sprint 2: Italy relevance scorer
        self.relevance_scorer = ItalyRelevanceScorer()
        # Sprint 3: Playwright support
        self._use_playwright = use_playwright and PLAYWRIGHT_AVAILABLE
        self._playwright_fetcher: "PlaywrightFetcher" | None = None
        self._playwright_thread_local = threading.local()
        self._playwright_loops: list["asyncio.AbstractEventLoop"] = []
        self._playwright_fetchers: list["PlaywrightFetcher"] = []
        self._playwright_lock = threading.Lock()
        # Force extraction even if content unchanged (use after updating extractors)
        self._force_extract = force_extract
        # Sprint 5: Graceful shutdown
        self._shutdown: GracefulShutdown | None = None
        if enable_graceful_shutdown:
            self._shutdown = GracefulShutdown(on_shutdown=self._on_shutdown)
            self._shutdown.install_handlers()

        if use_playwright and not PLAYWRIGHT_AVAILABLE:
            print("  Note: Playwright not available, headless fetching disabled")
        if not SPECIALIZED_EXTRACTORS_AVAILABLE:
            print("  Note: Specialized extractors not available")

    def _on_shutdown(self):
        """Called when shutdown signal received — flush all stores to prevent data loss."""
        # Flush all stores so in-progress data is persisted
        for store_name in ('snapshot_store', 'signal_store', 'url_status_store',
                           'news_items_store', 'portfolio_store', 'team_store'):
            try:
                store = getattr(self, store_name, None)
                if store and hasattr(store, 'flush'):
                    store.flush()
            except Exception:
                pass
        # Save checkpoint with current progress
        checkpoint_path = self.data_dir / "monitor_checkpoint.json"
        if self._shutdown:
            checkpoint_data = {
                "last_url": self._shutdown.state.current_url,
            }
            self._shutdown.checkpoint(checkpoint_path, checkpoint_data)

    def is_shutting_down(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown is not None and self._shutdown.should_stop()

    async def _get_playwright_fetcher(self) -> "PlaywrightFetcher":
        """Get or create the Playwright fetcher."""
        if self._playwright_fetcher is None:
            self._playwright_fetcher = PlaywrightFetcher()
            await self._playwright_fetcher.start()
        return self._playwright_fetcher

    async def _shutdown_playwright(self):
        """Shut down the Playwright fetcher if running."""
        if self._playwright_fetcher:
            await self._playwright_fetcher.stop()
            self._playwright_fetcher = None

    async def _fetch_with_playwright(
        self,
        url: str,
        page_type: str,
        fetcher: "PlaywrightFetcher" | None = None,
    ) -> FetchResult:
        """
        Fetch a URL using Playwright headless browser.

        Configures fetch options based on page type.
        Uses site config pagination settings when available (e.g., click-to-load).
        Enforces PER_URL_TIMEOUT to prevent stalls from scrolling/network-idle waits.
        """
        import asyncio as _asyncio

        fetcher = fetcher or await self._get_playwright_fetcher()

        # Configure options based on page type
        options = FetchOptions(
            wait_for_network_idle=True,
            dismiss_consent=True,
        )

        if page_type in ("portfolio", "investments"):
            options.scroll_to_bottom = True
            options.max_scrolls = 5
            options.scroll_pause_ms = 800
        elif page_type == "team":
            options.scroll_to_bottom = True
            options.max_scrolls = 3
            options.scroll_pause_ms = 500
        elif page_type in ("news", "press"):
            options.scroll_to_bottom = True
            options.max_scrolls = 2

        try:
            return await _asyncio.wait_for(
                fetcher.fetch(url, options),
                timeout=PER_URL_TIMEOUT,
            )
        except _asyncio.TimeoutError:
            print(f"    Playwright timeout after {PER_URL_TIMEOUT}s: {url}")
            return FetchResult(
                url=url, status_code=0, html="", text="", title=None,
                content_hash="", error=f"Playwright timeout ({PER_URL_TIMEOUT}s)",
            )

    def _get_thread_playwright(self) -> tuple["asyncio.AbstractEventLoop", "PlaywrightFetcher"]:
        """Create or reuse a thread-local Playwright loop and fetcher."""
        import asyncio

        state = self._playwright_thread_local
        loop = getattr(state, "loop", None)
        fetcher = getattr(state, "fetcher", None)

        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            state.loop = loop

        if fetcher is None:
            fetcher = PlaywrightFetcher()
            loop.run_until_complete(fetcher.start())
            state.fetcher = fetcher
            with self._playwright_lock:
                self._playwright_loops.append(loop)
                self._playwright_fetchers.append(fetcher)

        return loop, fetcher

    def _run_playwright_fetch(self, url: str, page_type: str) -> FetchResult:
        """Run Playwright fetch on a persistent thread-local event loop."""
        loop, fetcher = self._get_thread_playwright()
        return loop.run_until_complete(self._fetch_with_playwright(url, page_type, fetcher=fetcher))

    def _should_use_playwright(self, url: str, http_result: FetchResult | None = None) -> tuple[bool, str]:
        """
        Determine if Playwright should be used for a URL.

        Returns (should_use, reason).
        """
        if not self._use_playwright:
            return False, "Playwright disabled"

        # Check domain policy first
        policy = self.domain_policies.get_policy(url)
        if policy.requires_headless:
            return True, f"Domain policy: {policy.reason or 'requires headless'}"

        # Check if HTTP result suggests JS-heavy page
        if http_result and http_result.html:
            detection = detect_requires_headless(http_result.html)
            if detection.requires_headless:
                # Update domain policy for future requests
                update_domain_policy_headless(self.domain_policies, url, detection)
                reason = detection.framework_detected or "JS-heavy content"
                return True, f"Auto-detected: {reason}"

            # Check for minimal content
            if len(http_result.text) < self.MIN_CONTENT_LENGTH:
                return True, f"Minimal content ({len(http_result.text)} chars)"

        return False, ""

    def _generate_signal_id(self) -> str:
        """Generate a unique signal ID."""
        return f"web-signal-{self.signal_store.signal_count + 1:05d}"

    def _determine_signal_type(self, page_type: str, diff: DiffResult) -> str:
        """Determine the signal type based on page and changes."""
        # Check content for hints
        added_text = " ".join(diff.added_lines).lower()

        if any(kw in added_text for kw in ["hiring", "job", "career", "position", "vacancy"]):
            return "job_posting"
        elif any(kw in added_text for kw in ["invest", "portfolio", "acquisition"]):
            return "deal_announced"
        elif any(kw in added_text for kw in ["fund", "raise", "commit", "close"]):
            return "fundraise_announced"
        elif any(kw in added_text for kw in ["join", "appoint", "hire", "welcome"]):
            return "people_move"
        elif any(kw in added_text for kw in ["exit", "sale", "ipo", "divest"]):
            return "exit_announced"

        # Default based on page type
        if page_type == "team":
            return "people_move"
        elif page_type == "portfolio":
            return "deal_announced"
        elif page_type == "news":
            return "other"
        else:
            return "website_change"

    def check_url(self, monitored: MonitoredUrl, skip_backoff: bool = False) -> list[SignalRecord]:
        """
        Check a single URL for changes and generate signals if meaningful.

        Phase 1 improvements:
        - Uses conditional requests (ETag/Last-Modified) to reduce bandwidth
        - Stores lightweight check records for 304/unchanged responses
        - Deduplicates HTML storage via content-addressed blobs

        Phase 2 improvements:
        - Uses domain policies for SSL, timeout, and retry settings
        - Skips domains that require headless browser (until implemented)

        Phase 3 improvements:
        - Falls back to Playwright for JS-heavy sites
        - Auto-detects sites requiring headless browser
        - Logs which fetch method was used

        For news/press pages, uses item-based detection to avoid false positives
        from layout changes.

        Args:
            monitored: The MonitoredUrl to check
            skip_backoff: If True, ignore backoff and check anyway

        Returns:
            List of SignalRecords (may be empty or contain multiple for news pages)
        """
        # Check if domain policy says skip entirely (not just requires_headless)
        policy = self.domain_policies.get_policy(monitored.url)
        if policy.skip_monitoring:
            print(f"  Skipping {monitored.url} (policy: {policy.reason})")
            return []

        # Filter out HOME page and other noisy page types
        # Only generate signals from NEWS, TEAM, PORTFOLIO, CAREERS, ABOUT pages
        page_category = monitored.category.upper() if monitored.category else monitored.page_type.upper()
        if page_category not in SIGNAL_PAGE_CATEGORIES:
            print(f"  Skipping {monitored.url} (page category {page_category} not in signal categories)")
            return []

        # Check backoff policy
        if not skip_backoff and not self.url_status_store.should_check(monitored.url):
            status = self.url_status_store.get_status(monitored.url)
            print(f"  Skipping {monitored.url} (backoff until {status.get('next_check_after') if status else 'unknown'})")
            return []

        print(f"  Fetching {monitored.url}...")

        # Get cached metadata for conditional request
        cached_meta = self.snapshot_store.get_url_metadata(monitored.url)
        etag = cached_meta.get("etag") if cached_meta else None
        last_modified = cached_meta.get("last_modified") if cached_meta else None

        # Track fetch method for logging
        fetch_method = "HTTP"

        # Check if we should use Playwright directly (from domain policy)
        use_playwright, pw_reason = self._should_use_playwright(monitored.url)
        if use_playwright:
            print(f"    Using Playwright: {pw_reason}")
            fetch_method = "Playwright"
            result = self._run_playwright_fetch(monitored.url, monitored.page_type)
        else:
            # Try HTTP first
            result = fetch_url(
                monitored.url,
                etag=etag,
                last_modified=last_modified,
                timeout=policy.timeout,
                ssl_verify=policy.ssl_verify,
                retry_count=policy.retry_count,
            )

            # Check if we should fallback to Playwright
            if result.status_code == 200 and not result.error:
                use_playwright, pw_reason = self._should_use_playwright(monitored.url, result)
                if use_playwright:
                    print(f"    Falling back to Playwright: {pw_reason}")
                    fetch_method = "Playwright (fallback)"
                    result = self._run_playwright_fetch(monitored.url, monitored.page_type)

        print(f"    Fetch method: {fetch_method}")

        # Update URL status
        self.url_status_store.update_status(monitored.url, result.status_code, result.error)

        if result.error:
            print(f"    Error: {result.error}")
            # Store check record for audit
            self.snapshot_store.store_check_record(
                monitored.url, monitored.fund_slug, result.status_code, "error", result.error
            )
            return []

        # Handle 304 Not Modified - page unchanged since last check
        if result.was_not_modified:
            if self._force_extract:
                # Load previous snapshot HTML for re-extraction
                previous = self.snapshot_store.get_latest_for_url(monitored.url)
                if previous and previous.get("blob_hash"):
                    print(f"    304 Not Modified but force-extracting from cached HTML")
                    blob_path = self.snapshot_store.blobs_dir / f"{previous['blob_hash']}.html"
                    if blob_path.exists():
                        result.html = blob_path.read_text(encoding="utf-8")
                        result.content_hash = previous.get("content_hash", "")
                        result.status_code = 200
                        result.was_not_modified = False
                    else:
                        print(f"    Cached HTML blob not found, skipping")
                        return []
                else:
                    print(f"    304 Not Modified, no cached HTML for force-extract")
                    return []
            else:
                print(f"    304 Not Modified (cached)")
                self.snapshot_store.store_check_record(
                    monitored.url, monitored.fund_slug, 304, "not_modified"
                )
                return []

        if result.status_code != 200:
            print(f"    HTTP {result.status_code}")
            self.snapshot_store.store_check_record(
                monitored.url, monitored.fund_slug, result.status_code, "http_error"
            )
            return []

        # Check if content actually changed (by content_hash)
        previous = self.snapshot_store.get_latest_for_url(monitored.url)
        content_changed = not previous or previous.get("content_hash") != result.content_hash

        # Store the new snapshot (persist HTML when force-extracting to keep comparisons stable)
        snapshot = self.snapshot_store.store(
            result,
            monitored.fund_slug,
            store_html=content_changed or self._force_extract,
        )

        # Check if this extractor fetches its own data (API-based) — always extract
        always_extract = False
        try:
            from urllib.parse import urlparse
            url_domain = urlparse(monitored.url).netloc.lower()
            from .strategies.extractors import ALWAYS_EXTRACT as _AE_DOMAINS
            always_extract = url_domain in _AE_DOMAINS
        except Exception:
            pass

        # Skip if content unchanged (unless force_extract or always_extract)
        if not content_changed and not self._force_extract and not always_extract:
            print(f"    Content unchanged (hash match)")
            self.snapshot_store.store_check_record(
                monitored.url, monitored.fund_slug, 200, "unchanged"
            )
            return []

        if content_changed:
            print(f"    Stored snapshot {snapshot['id']}")
        elif always_extract:
            print(f"    HTML unchanged but extractor fetches own data — extracting")
        else:
            print(f"    Content unchanged but force-extracting")

        # For news/press pages, use item-based detection
        if monitored.page_type in ("news", "press"):
            return self._check_news_page(monitored, result, snapshot)

        # Phase 3: For portfolio pages, use specialized extraction
        if monitored.page_type in ("portfolio", "investments", "portfolio_list") and self._portfolio_extractor:
            return self._check_portfolio_page(monitored, result, snapshot)

        # Phase 3: For team pages, use specialized extraction
        if monitored.page_type in ("team", "team_list", "people") and self._team_extractor:
            return self._check_team_page(monitored, result, snapshot)

        # For other pages, use standard diff-based detection
        return self._check_standard_page(monitored, result, snapshot)

    def _check_news_page(self, monitored: MonitoredUrl, result, snapshot) -> list[SignalRecord]:
        """
        Check a news/press page for new items.

        Uses item extraction to detect new announcements without triggering
        on layout/boilerplate changes.

        Phase 2 enhancements:
        - Uses site-specific extraction for better article URLs
        - Generates more meaningful titles from extracted data
        - Sets published_at from extracted date
        - Creates better what_changed descriptions
        """
        # Try fund-specific extractor first (strategies/extractors/)
        extracted_items = []
        if STRATEGY_ORCHESTRATOR_AVAILABLE and compute_fingerprint:
            try:
                orchestrator = _get_orchestrator()
                orch_items = orchestrator.extract_news(result.html, monitored.url)
                if orch_items:
                    for item in orch_items:
                        fp = compute_fingerprint(item.title, item.date, item.url)
                        extracted_items.append({
                            "title": item.title,
                            "url": item.url,
                            "date": item.date,
                            "date_raw": None,
                            "description": item.description,
                            "company_name": getattr(item, "company_mentioned", None),
                            "deal_type": getattr(item, "deal_type", None),
                            "fingerprint": fp,
                        })
                    print(f"    Found {len(extracted_items)} news items (fund-specific extractor)")
            except Exception as e:
                print(f"    Fund-specific extraction failed: {e}")

        # Try site-specific config extraction (Phase 2)
        if not extracted_items and SITE_EXTRACTOR_AVAILABLE:
            try:
                extracted_items = site_extract_news_items(result.html, monitored.url)
                print(f"    Found {len(extracted_items)} news items (site-config extraction)")
            except Exception as e:
                print(f"    Site-config extraction failed: {e}")

        # Fall back to generic extraction if needed
        if not extracted_items:
            current_items = extract_news_items(result.html, monitored.url)
            print(f"    Found {len(current_items)} news items (generic extraction)")
            # Convert to extended format for consistency
            extracted_items = [
                {
                    "title": item["title"],
                    "url": item.get("url"),
                    "date": item.get("date"),
                    "date_raw": None,
                    "description": None,
                    "company_name": None,
                    "deal_type": None,
                    "fingerprint": item["fingerprint"],
                }
                for item in current_items
            ]

        if not extracted_items:
            print("    No news items found on page")
            return []

        # Get previously seen items (convert to standard format for comparison)
        previous_items = self.news_items_store.get_items(monitored.url)
        current_items_standard = [
            NewsItem(
                title=item["title"],
                date=item.get("date"),
                url=item.get("url"),
                fingerprint=item["fingerprint"],
            )
            for item in extracted_items
        ]

        # Compare with previous
        news_result = compare_news_items(previous_items, current_items_standard)

        # Update stored items
        self.news_items_store.update_items(monitored.url, current_items_standard)

        if not news_result.new_items:
            print("    No new news items detected")
            return []

        # Create a lookup for extended item info
        item_lookup = {item["fingerprint"]: item for item in extracted_items}

        # Generate signals for new items
        signals = []
        skipped_noise = 0
        now = datetime.now(timezone.utc).isoformat()

        for basic_item in news_result.new_items[:15]:  # Limit to 15 new items per check
            # Get extended info if available
            item = item_lookup.get(basic_item["fingerprint"], basic_item)

            # Classify the news item to filter noise and determine signal type
            should_keep, signal_type = classify_news_signal(item["title"])

            if not should_keep:
                skipped_noise += 1
                print(f"    Skipping noise: {item['title'][:50]}...")
                continue

            # Override signal_type if we detected deal_type
            if item.get("deal_type"):
                deal_type_map = {
                    "acquisition": "deal_announced",
                    "investment": "deal_announced",
                    "exit": "exit_announced",
                    "fundraise": "fundraise_announced",
                }
                signal_type = deal_type_map.get(item["deal_type"], signal_type)

            print(f"    New item ({signal_type}): {item['title'][:50]}...")

            # Use canonical category from config (should be NEWS for news pages)
            category = monitored.category.upper() if monitored.category else "NEWS"

            # Generate meaningful title
            title = _normalize_signal_title(item["title"])
            if item.get("company_name") and len(title) < 80:
                # Title already contains company info
                pass
            elif item.get("deal_type") and item.get("company_name"):
                # Enhance title with extracted info
                title = f"{monitored.fund_name}: {item['deal_type'].title()} - {item['company_name']}"

            # Generate better what_changed description
            what_changed_parts = []
            if item.get("description"):
                what_changed_parts.append(item["description"][:500])
            elif item.get("company_name"):
                what_changed_parts.append(f"New {item.get('deal_type', 'announcement')} involving {item['company_name']}")
            else:
                what_changed_parts.append(f"New announcement: {item['title'][:300]}")

            what_changed = " ".join(what_changed_parts)
            # Safety: ensure what_changed is never empty
            if not what_changed or not what_changed.strip():
                what_changed = item.get("title") or "New announcement"

            # Use actual article URL (not list page) - Phase 2 improvement
            source_url = item.get("url") or monitored.url
            if source_url == monitored.url:
                print(f"    Warning: No article URL found, using list page URL")

            # Score Italy relevance for this news item
            relevance_text = item["title"]
            if item.get("description"):
                relevance_text += " " + item["description"]
            relevance = self.relevance_scorer.score(
                relevance_text,
                page_category=category,
            )

            # Extract companies from title if not already extracted
            companies = relevance.extracted_entities.companies.copy()
            if item.get("company_name") and item["company_name"] not in companies:
                companies.append(item["company_name"])

            signal: SignalRecord = {
                "id": self._generate_signal_id(),
                "fund_id": "",
                "fund_slug": monitored.fund_slug,
                "signal_type": signal_type,
                "title": title,
                "what_changed": what_changed,
                "source_url": source_url,
                "source_name": monitored.fund_name,
                "published_at": normalize_news_date(item.get("date")),
                "observed_at": now,
                "created_at": now,
                "snapshot_id": snapshot["id"],
                "diff_summary": f"New news item detected" + (f" (dated {item.get('date')})" if item.get("date") else ""),
                "page_category": category,
                "page_type": monitored.page_type.upper(),
                "relevance_score": relevance.relevance_score,
                "relevance_reasons": relevance.relevance_reasons,
                "italy_relevant": relevance.italy_relevant,
                "extracted_entities": {
                    "companies": companies,
                    "people": relevance.extracted_entities.people,
                    "locations": relevance.extracted_entities.locations,
                },
            }

            self.signal_store.add(signal)
            signals.append(signal)

        if skipped_noise:
            print(f"    Skipped {skipped_noise} noise items (cookie/privacy notices)")
        print(f"    Generated {len(signals)} signals from news items")
        return signals

    def _check_portfolio_page(self, monitored: MonitoredUrl, result, snapshot) -> list[SignalRecord]:
        """
        Check a portfolio page for new companies using specialized extraction.

        Phase 3: Uses the PortfolioExtractor for structured extraction.
        Phase 6: Enriches with detail page data for priority sites.
        """
        # Extract current companies
        current_companies = self._portfolio_extractor.extract(result.html, monitored.url)
        print(f"    Found {len(current_companies)} portfolio companies")

        # Phase 6: Enrich with detail pages for priority sites
        if DETAIL_FETCHER_AVAILABLE and current_companies:
            from urllib.parse import urlparse
            domain = urlparse(monitored.url).netloc.lower()
            # Priority sites for detail page enrichment
            priority_domains = ["www.21invest.com", "www.fondoitaliano.it"]
            if domain in priority_domains:
                # Check if we have a site-specific detail extractor
                detail_extractor = get_site_extractor(domain, "company_detail")
                if detail_extractor:
                    companies_with_details = [c for c in current_companies if c.detail_page_url]
                    if companies_with_details:
                        print(f"    Enriching {len(companies_with_details)} companies with detail pages...")
                        try:
                            current_companies = enrich_portfolio_sync(
                                current_companies,
                                monitored.url,
                                max_concurrent=3,
                                use_playwright=False,
                            )
                            print(f"    Detail page enrichment complete")
                        except Exception as e:
                            print(f"    Warning: Detail page enrichment failed: {e}")

        if not current_companies:
            print("    No companies found on page")
            return []

        # Get previous companies
        previous = self.portfolio_store.get_portfolio(monitored.fund_slug)
        previous_names = {c.get("name", "").lower().strip() for c in previous if c.get("name")}
        is_baseline = len(previous) == 0  # First scrape — no previous data

        # Find new companies
        new_companies = []
        if not is_baseline:
            for company in current_companies:
                if company.confidence < 0.5:  # Skip low-confidence extractions
                    continue
                name_lower = company.name.lower().strip()
                if name_lower not in previous_names:
                    new_companies.append(company)
        else:
            print(f"    Baseline load: {len(current_companies)} companies (no signals generated)")

        # Update stored portfolio (Phase 6: include new detail fields)
        self.portfolio_store.update_portfolio(
            monitored.fund_slug,
            [{
                "name": c.name,
                "sector": c.sector,
                "status": c.status,
                "confidence": c.confidence,
                "website": c.website,
                "description": c.description,
                "detail_page_url": c.detail_page_url,
                "headquarters": c.headquarters,
                "investment_date": c.investment_date,
            } for c in current_companies],
            source_url=monitored.url,
        )

        # Phase 6: Quality monitoring
        if QUALITY_MONITOR_AVAILABLE:
            avg_confidence = sum(c.confidence for c in current_companies) / len(current_companies) if current_companies else 0
            alerts = check_and_alert(
                self.data_dir,
                monitored.fund_slug,
                "portfolio",
                len(current_companies),
                avg_confidence,
            )
            if alerts:
                print(f"    Quality alerts triggered: {len(alerts)}")

        if not new_companies:
            print("    No new portfolio companies detected")
            return []

        # If most companies are "new", this is likely a page restructure or
        # extractor change, not individual deal announcements. Only generate
        # signals when a small number of genuinely new companies appear.
        if len(previous) > 0 and len(new_companies) > max(5, len(current_companies) * 0.5):
            print(f"    Bulk change detected: {len(new_companies)} new out of {len(current_companies)} total — suppressing signals (likely page restructure)")
            return []

        # Generate signals for new companies
        signals = []
        now = datetime.now(timezone.utc).isoformat()
        category = monitored.category.upper() if monitored.category else "PORTFOLIO"

        for company in new_companies[:5]:  # Limit to 5 per check
            signal_type = "exit_announced" if company.status == "exited" else "deal_announced"
            action = "exit" if company.status == "exited" else "investment"

            print(f"    New {action}: {company.name} (confidence: {company.confidence:.2f})")

            # Score Italy relevance
            relevance_text = f"{company.name} {company.sector or ''} {company.description or ''}"
            relevance = self.relevance_scorer.score(relevance_text, page_category=category)

            if company.status == "exited":
                title = f"{company.name} exited from {monitored.fund_name} portfolio"
            else:
                title = f"{company.name} added to {monitored.fund_name} portfolio"
            if company.sector:
                title += f" ({company.sector})"
            what_changed = title

            signal: SignalRecord = {
                "id": self._generate_signal_id(),
                "fund_id": "",
                "fund_slug": monitored.fund_slug,
                "signal_type": signal_type,
                "title": _normalize_signal_title(title),
                "what_changed": what_changed,
                "source_url": monitored.url,
                "source_name": monitored.fund_name,
                "published_at": None,
                "observed_at": now,
                "created_at": now,
                "snapshot_id": snapshot["id"],
                "diff_summary": f"New portfolio company detected via extraction",
                "page_category": category,
                "page_type": monitored.page_type.upper(),
                "relevance_score": relevance.relevance_score,
                "relevance_reasons": relevance.relevance_reasons,
                "italy_relevant": relevance.italy_relevant,
                "extracted_entities": {
                    "companies": [company.name],
                    "people": relevance.extracted_entities.people,
                    "locations": relevance.extracted_entities.locations,
                },
            }

            self.signal_store.add(signal)
            signals.append(signal)

        print(f"    Generated {len(signals)} signals from portfolio extraction")
        return signals

    def _check_team_page(self, monitored: MonitoredUrl, result, snapshot) -> list[SignalRecord]:
        """
        Check a team page for new members using specialized extraction.

        Phase 3: Uses the TeamExtractor for structured extraction.
        """
        # Extract current team members
        current_members = self._team_extractor.extract(result.html, monitored.url)
        print(f"    Found {len(current_members)} team members")

        if not current_members:
            print("    No team members found on page")
            # Fall back to standard diff-based detection
            return self._check_standard_page(monitored, result, snapshot)

        # Get previous team
        previous = self.team_store.get_team(monitored.fund_slug)
        previous_names = {m.get("name", "").lower().strip() for m in previous if m.get("name")}
        is_baseline = len(previous) == 0  # First scrape — no previous data

        # Find new members (exclude support/admin roles)
        new_members = []
        if not is_baseline:
            for member in current_members:
                if member.confidence < 0.5:  # Skip low-confidence extractions
                    continue
                name_lower = member.name.lower().strip()
                if name_lower not in previous_names:
                    if is_support_role(member.title):
                        print(f"    Skipping support role: {member.name} ({member.title})")
                        continue
                    new_members.append(member)
        else:
            print(f"    Baseline load: {len(current_members)} team members (no signals generated)")

        # Bulk change guard: if most members appear "new", likely a page restructure
        if not is_baseline and len(previous) > 0 and len(new_members) > max(3, len(current_members) * 0.5):
            print(f"    Bulk change detected: {len(new_members)} new out of {len(current_members)} total — suppressing signals (likely page restructure)")
            new_members = []

        # Update stored team
        self.team_store.update_team(
            monitored.fund_slug,
            [{"name": m.name, "title": m.title, "role": m.role, "confidence": m.confidence}
             for m in current_members]
        )

        if not new_members:
            print("    No new team members detected")
            return []

        # Generate signal for new members
        signals = []
        now = datetime.now(timezone.utc).isoformat()
        category = monitored.category.upper() if monitored.category else "TEAM"

        # Create one signal for all new members (to avoid noise)
        member_details = []
        for member in new_members[:5]:
            detail = member.name
            if member.title:
                detail += f" ({member.title})"
            member_details.append(detail)
            print(f"    New member: {detail} (confidence: {member.confidence:.2f})")

        names_text = ", ".join(member_details)
        if len(new_members) > 5:
            names_text += f" (+{len(new_members) - 5} more)"

        # Score Italy relevance
        relevance = self.relevance_scorer.score(names_text, page_category=category)

        title = f"New team member{'s' if len(new_members) > 1 else ''}: {new_members[0].name}"
        if len(new_members) > 1:
            title += f" (+{len(new_members) - 1} more)"

        signal: SignalRecord = {
            "id": self._generate_signal_id(),
            "fund_id": "",
            "fund_slug": monitored.fund_slug,
            "signal_type": "people_move",
            "title": _normalize_signal_title(title),
            "what_changed": f"New team member{'s' if len(new_members) > 1 else ''}: {names_text}",
            "source_url": monitored.url,
            "source_name": monitored.fund_name,
            "published_at": None,
            "observed_at": now,
            "created_at": now,
            "snapshot_id": snapshot["id"],
            "diff_summary": f"{len(new_members)} new team member{'s' if len(new_members) > 1 else ''} via extraction",
            "page_category": category,
            "page_type": monitored.page_type.upper(),
            "relevance_score": relevance.relevance_score,
            "relevance_reasons": relevance.relevance_reasons,
            "italy_relevant": relevance.italy_relevant,
            "extracted_entities": {
                "companies": relevance.extracted_entities.companies,
                "people": [m.name for m in new_members],
                "locations": relevance.extracted_entities.locations,
            },
        }

        self.signal_store.add(signal)
        signals.append(signal)

        print(f"    Generated 1 signal for {len(new_members)} new team member(s)")
        return signals

    def _try_content_extraction(
        self,
        monitored: MonitoredUrl,
        result,
        snapshot,
        previous,
    ) -> list[SignalRecord] | None:
        """
        Try to extract meaningful content from page changes.

        Phase 7: Attempts news-style extraction before falling back to diff.
        Returns signals if extraction found new items, None to fall back to diff.
        """
        # Skip noisy page types like HOME
        if monitored.page_type in ("home",):
            return None

        if not SITE_EXTRACTOR_AVAILABLE and not STRATEGY_ORCHESTRATOR_AVAILABLE:
            return None

        try:
            current_items = []

            # Try fund-specific extraction first
            if STRATEGY_ORCHESTRATOR_AVAILABLE and compute_fingerprint:
                try:
                    orchestrator = _get_orchestrator()
                    orch_items = orchestrator.extract_news(result.html, monitored.url)
                    if orch_items:
                        for item in orch_items:
                            fp = compute_fingerprint(item.title, item.date, item.url)
                            current_items.append({
                                "title": item.title,
                                "url": item.url,
                                "date": normalize_news_date(item.date),
                                "date_raw": None,
                                "description": item.description,
                                "company_name": getattr(item, "company_mentioned", None),
                                "deal_type": getattr(item, "deal_type", None),
                                "fingerprint": fp,
                            })
                except Exception:
                    pass

            # Fall back to site config extraction
            if not current_items and SITE_EXTRACTOR_AVAILABLE:
                current_items = site_extract_news_items(result.html, monitored.url)

            if not current_items:
                return None

            # Get previous HTML for comparison
            prev_html = self.snapshot_store.get_html(previous["id"]) if previous else ""
            prev_items = []
            if prev_html:
                # Use same extraction method for consistency
                if STRATEGY_ORCHESTRATOR_AVAILABLE and compute_fingerprint:
                    try:
                        orch_items = _get_orchestrator().extract_news(prev_html, monitored.url)
                        if orch_items:
                            for item in orch_items:
                                fp = compute_fingerprint(item.title, item.date, item.url)
                                prev_items.append({
                                    "title": item.title, "url": item.url,
                                    "date": item.date, "fingerprint": fp,
                                })
                    except Exception:
                        pass
                if not prev_items and SITE_EXTRACTOR_AVAILABLE:
                    prev_items = site_extract_news_items(prev_html, monitored.url) if prev_html else []

            # Find new items by fingerprint
            prev_fingerprints = {item["fingerprint"] for item in prev_items}
            new_items = [
                item for item in current_items
                if item["fingerprint"] not in prev_fingerprints
            ]

            if not new_items:
                return None

            # Generate signals for new extracted items
            return self._signals_from_extracted_items(new_items, monitored, result, snapshot)

        except Exception as e:
            print(f"    Content extraction failed: {e}")
            return None

    def _signals_from_extracted_items(
        self,
        items: list,
        monitored: MonitoredUrl,
        result,
        snapshot,
    ) -> list[SignalRecord]:
        """
        Convert extracted items into signals.

        Phase 7: Creates rich signals from extracted content.
        """
        signals = []
        now = datetime.now(timezone.utc).isoformat()
        category = monitored.category.upper() if monitored.category else monitored.page_type.upper()
        skipped_noise = 0

        for item in items[:10]:  # Limit to 10 items per check
            title = item.get("title", "")

            # Filter noise
            should_keep, signal_type = classify_news_signal(title)
            if not should_keep:
                skipped_noise += 1
                continue

            print(f"    Extracted item: {title[:50]}...")

            # Score Italy relevance
            relevance_text = title
            if item.get("description"):
                relevance_text += " " + item["description"]
            relevance = self.relevance_scorer.score(relevance_text, page_category=category)

            # Build what_changed from extracted content
            what_changed = item.get("description") or title
            if len(what_changed) > 500:
                what_changed = what_changed[:497] + "..."

            source_url = item.get("url") or monitored.url

            signal: SignalRecord = {
                "id": self._generate_signal_id(),
                "fund_id": "",
                "fund_slug": monitored.fund_slug,
                "signal_type": signal_type,
                "title": _normalize_signal_title(title),
                "what_changed": what_changed,
                "source_url": source_url,
                "source_name": monitored.fund_name,
                "published_at": normalize_news_date(item.get("date")),
                "observed_at": now,
                "created_at": now,
                "snapshot_id": snapshot["id"],
                "diff_summary": f"New content extracted from {monitored.page_type} page",
                "page_category": category,
                "page_type": monitored.page_type.upper(),
                "relevance_score": relevance.relevance_score,
                "relevance_reasons": relevance.relevance_reasons,
                "italy_relevant": relevance.italy_relevant,
                "extracted_entities": {
                    "companies": relevance.extracted_entities.companies + ([item.get("company_name")] if item.get("company_name") else []),
                    "people": relevance.extracted_entities.people,
                    "locations": relevance.extracted_entities.locations,
                },
            }

            self.signal_store.add(signal)
            signals.append(signal)

        if skipped_noise:
            print(f"    Skipped {skipped_noise} noise items")

        return signals

    def _check_standard_page(self, monitored: MonitoredUrl, result, snapshot) -> list[SignalRecord]:
        """
        Check a standard page (team/portfolio/etc) for changes using diff.

        Phase 7: Tries content extraction before falling back to diff.

        For high-value pages (team, portfolio, investments), uses enhanced
        noise reduction to avoid false positives from cookie banners, etc.

        For team pages, uses name extraction to detect actual new members
        rather than relying on HTML diffs.
        """
        # Get previous snapshot for comparison
        previous = self.snapshot_store.get_previous_for_url(monitored.url)

        # If no previous snapshot, this is the first fetch
        if not previous:
            print("    First snapshot, no comparison possible")
            return []

        # Phase 7: Try content extraction before diff fallback
        # Skip HOME pages as they're too noisy
        if monitored.page_type not in ("home",):
            extraction_signals = self._try_content_extraction(
                monitored, result, snapshot, previous
            )
            if extraction_signals:
                print(f"    Generated {len(extraction_signals)} signals from content extraction")
                return extraction_signals

        # For team pages, use specialized name-based comparison
        if monitored.page_type in ("team", "team_list"):
            return self._check_team_page_names(monitored, result, snapshot, previous)

        # Use normalized diff for high-value pages (Sprint 2 enhancement)
        high_value_types = ("team", "portfolio", "investments", "about")
        if monitored.page_type in high_value_types:
            # Need to get the raw HTML for both - use snapshot store
            prev_html = self.snapshot_store.get_html(previous["id"]) or ""
            # Sprint 2: Use the enhanced normalized diff
            normalized_result = compute_normalized_diff(prev_html, result.html)
            diff = DiffResult(
                has_changes=normalized_result.has_changes,
                is_meaningful=normalized_result.is_meaningful,
                change_ratio=normalized_result.change_ratio,
                added_lines=normalized_result.added_lines,
                removed_lines=normalized_result.removed_lines,
                summary=normalized_result.summary,
            )
            print(f"    Using normalized diff (removed {normalized_result.new_noise_removed} noise elements)")
        else:
            # Standard text diff
            diff = compute_diff(previous["text_content"], result.text)

        if not diff.has_changes:
            print("    No changes")
            return []

        if not diff.is_meaningful:
            print(f"    Changes not meaningful: {diff.summary}")
            return []

        # Generate signal
        print(f"    Meaningful changes: {diff.summary}")

        signal_type = self._determine_signal_type(monitored.page_type, diff)
        what_changed = generate_what_changed(diff, result.title)
        # Safety: ensure what_changed is never empty
        if not what_changed or not what_changed.strip():
            what_changed = result.title or diff.summary or "Page content updated"
        now = datetime.now(timezone.utc).isoformat()

        # Use canonical category from config, fallback to deriving from page_type
        category = monitored.category.upper() if monitored.category else monitored.page_type.upper().split("_")[0]

        # Sprint 2: Score Italy relevance based on the changed content
        change_text = " ".join(diff.added_lines) if diff.added_lines else result.text[:1000]
        relevance = self.relevance_scorer.score(
            change_text,
            page_category=category,
        )

        # Phase 2: Generate more meaningful title based on content
        page_type_name = monitored.page_type.replace('_', ' ').title()
        title = f"{monitored.fund_name}: {page_type_name} page update"

        # Try to make title more specific based on detected content
        if diff.added_lines:
            added_text = " ".join(diff.added_lines[:3]).lower()
            if relevance.extracted_entities.companies:
                company = relevance.extracted_entities.companies[0]
                if signal_type == "deal_announced":
                    title = f"{monitored.fund_name}: New investment - {company}"
                elif signal_type == "exit_announced":
                    title = f"{monitored.fund_name}: Exit - {company}"
                else:
                    title = f"{monitored.fund_name}: {company} added to {page_type_name.lower()}"
            elif "hiring" in added_text or "career" in added_text or "job" in added_text:
                title = f"{monitored.fund_name}: New career opportunity posted"
            elif relevance.extracted_entities.people:
                person = relevance.extracted_entities.people[0]
                title = f"{monitored.fund_name}: {person} - {page_type_name.lower()} update"

        signal: SignalRecord = {
            "id": self._generate_signal_id(),
            "fund_id": "",
            "fund_slug": monitored.fund_slug,
            "signal_type": signal_type,
            "title": _normalize_signal_title(title),
            "what_changed": what_changed,
            "source_url": monitored.url,
            "source_name": monitored.fund_name,
            "published_at": None,
            "observed_at": now,
            "created_at": now,
            "snapshot_id": snapshot["id"],
            "diff_summary": diff.summary,
            "page_category": category,
            "page_type": monitored.page_type.upper(),
            # Sprint 2: Italy relevance fields
            "relevance_score": relevance.relevance_score,
            "relevance_reasons": relevance.relevance_reasons,
            "italy_relevant": relevance.italy_relevant,
            "extracted_entities": {
                "companies": relevance.extracted_entities.companies,
                "people": relevance.extracted_entities.people,
                "locations": relevance.extracted_entities.locations,
            },
        }

        self.signal_store.add(signal)
        return [signal]

    def _check_team_page_names(self, monitored: MonitoredUrl, result, snapshot, previous) -> list[SignalRecord]:
        """
        Check a team page for new members using name extraction.

        Instead of relying on HTML diffs (which trigger on layout changes),
        this extracts actual names and compares them between snapshots.
        """
        # Get previous HTML
        prev_html = self.snapshot_store.get_html(previous["id"]) or ""

        # Compare team members
        team_result = compare_team_members(prev_html, result.html)

        print(f"    Team members: {team_result.total_previous} -> {team_result.total_current}")

        if not team_result.has_new_members:
            print("    No new team members detected")
            return []

        # Generate signals for new members
        signals = []
        now = datetime.now(timezone.utc).isoformat()
        category = monitored.category.upper() if monitored.category else "TEAM"

        # Create one signal for all new members (to avoid noise)
        new_names = team_result.new_members[:5]  # Limit to 5 names
        names_text = ", ".join(new_names)
        if len(team_result.new_members) > 5:
            names_text += f" (+{len(team_result.new_members) - 5} more)"

        print(f"    New members: {names_text}")

        # Score Italy relevance based on the new member names
        relevance = self.relevance_scorer.score(
            names_text,
            page_category=category,
        )

        signal: SignalRecord = {
            "id": self._generate_signal_id(),
            "fund_id": "",
            "fund_slug": monitored.fund_slug,
            "signal_type": "people_move",
            "title": f"New team member{'s' if len(team_result.new_members) > 1 else ''}: {new_names[0]}" + (f" (+{len(team_result.new_members) - 1} more)" if len(team_result.new_members) > 1 else ""),
            "what_changed": f"New team member{'s' if len(team_result.new_members) > 1 else ''} added: {names_text}",
            "source_url": monitored.url,
            "source_name": "Website Monitor",
            "published_at": None,
            "observed_at": now,
            "created_at": now,
            "snapshot_id": snapshot["id"],
            "diff_summary": f"{len(team_result.new_members)} new team member{'s' if len(team_result.new_members) > 1 else ''} detected",
            "page_category": category,
            "page_type": monitored.page_type.upper(),
            "relevance_score": relevance.relevance_score,
            "relevance_reasons": relevance.relevance_reasons,
            "italy_relevant": relevance.italy_relevant,
            "extracted_entities": {
                "companies": relevance.extracted_entities.companies,
                "people": team_result.new_members,  # Use extracted names
                "locations": relevance.extracted_entities.locations,
            },
        }

        self.signal_store.add(signal)
        signals.append(signal)

        print(f"    Generated 1 signal for {len(team_result.new_members)} new team member(s)")
        return signals

    def check_urls(self, urls: list[MonitoredUrl], skip_backoff: bool = False) -> list[SignalRecord]:
        """
        Check multiple URLs for changes, fetching from different domains in parallel.

        URLs are deduplicated by canonical form, grouped by domain, then processed
        with a ThreadPoolExecutor. Same-domain requests run sequentially (respecting
        rate limits); different domains run in parallel across worker threads.

        Args:
            urls: List of MonitoredUrl objects to check
            skip_backoff: If True, ignore backoff and check all URLs

        Returns:
            List of SignalRecords for detected changes
        """
        print(f"Checking {len(urls)} URLs for changes...")

        # --- Step 1: Deduplicate URLs by canonical form ---
        seen_canonical: dict[str, MonitoredUrl] = {}
        unique_urls: list[MonitoredUrl] = []
        dupes = 0
        for url in urls:
            canon = canonical_url(url.url)
            if canon not in seen_canonical:
                seen_canonical[canon] = url
                unique_urls.append(url)
            else:
                dupes += 1
        if dupes:
            print(f"  Deduplicated: {len(urls)} -> {len(unique_urls)} URLs ({dupes} duplicates removed)")
        urls = unique_urls

        # --- Step 2: Group URLs by domain ---
        domain_groups: dict[str, list[MonitoredUrl]] = defaultdict(list)
        for url in urls:
            domain = extract_domain(url.url)
            domain_groups[domain].append(url)
        print(f"  Grouped into {len(domain_groups)} domains (max {MAX_WORKERS} parallel workers)")

        # --- Step 3: Thread-safe accumulators ---
        signals: list[SignalRecord] = []
        signals_lock = threading.Lock()
        checked = 0
        skipped = 0
        counter_lock = threading.Lock()

        # Track active domains for stall diagnosis
        active_domains: dict[str, str] = {}  # domain -> current URL
        active_lock = threading.Lock()
        domains_done = 0

        def _process_domain_group(domain: str, domain_urls: list[MonitoredUrl]) -> None:
            """Process all URLs for a single domain sequentially."""
            nonlocal checked, skipped, domains_done

            for url_obj in domain_urls:
                if self.is_shutting_down():
                    return

                with active_lock:
                    active_domains[domain] = url_obj.url

                print(f"\n[{url_obj.fund_name}]")
                url_signals = self.check_url(url_obj, skip_backoff=skip_backoff)

                with signals_lock:
                    signals.extend(url_signals)

                with counter_lock:
                    if not self.url_status_store.should_check(url_obj.url) and not skip_backoff:
                        skipped += 1
                    else:
                        checked += 1

                    # Update progress for shutdown logging
                    if self._shutdown:
                        self._shutdown.set_current_url(url_obj.url)
                        self._shutdown.set_progress(checked + skipped, len(urls), len(signals))

            with active_lock:
                active_domains.pop(domain, None)
                domains_done += 1
                remaining = len(domain_groups) - domains_done
                if remaining > 0 and remaining <= 5:
                    print(f"\n  [{remaining} domains still running: {list(active_domains.keys())}]")

        # --- Step 4: Run domain groups in parallel ---
        total_timeout = min(PER_URL_TIMEOUT * len(urls), MAX_TOTAL_TIMEOUT)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
        futures: dict[concurrent.futures.Future, str] = {}
        for domain, domain_urls in domain_groups.items():
            if self.is_shutting_down():
                break
            future = executor.submit(_process_domain_group, domain, domain_urls)
            futures[future] = domain

        # Wait for completion — poll every 30s so we can log stuck domains
        import time
        deadline = time.monotonic() + total_timeout
        done_futures = set()

        while len(done_futures) < len(futures):
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                with active_lock:
                    stuck = list(active_domains.items())
                print(f"\n  WARNING: Global timeout ({total_timeout}s) reached.")
                for domain, url in stuck:
                    print(f"    STUCK: {domain} -> {url}")
                break

            # Wait up to 30s for any future to complete
            wait_time = min(30, remaining_time)
            newly_done, _ = concurrent.futures.wait(
                [f for f in futures if f not in done_futures],
                timeout=wait_time,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )

            for future in newly_done:
                done_futures.add(future)
                domain = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"\n  ERROR processing domain '{domain}': {e}")

            # If nothing completed in 30s, log what's still running
            if not newly_done and len(done_futures) < len(futures):
                with active_lock:
                    still_active = list(active_domains.items())
                if still_active:
                    print(f"\n  Waiting on {len(still_active)} domain(s): {[d for d, _ in still_active]}")
                    for domain, url in still_active:
                        print(f"    -> {domain}: {url}")

        executor.shutdown(wait=False, cancel_futures=True)

        # Flush all accumulated state to disk after all requests complete
        for store_name in ('snapshot_store', 'signal_store', 'url_status_store',
                           'news_items_store', 'portfolio_store', 'team_store'):
            try:
                store = getattr(self, store_name, None)
                if store and hasattr(store, 'flush'):
                    store.flush()
            except Exception:
                pass
        try:
            from .circuit_breaker import get_circuit_registry
            get_circuit_registry().save_if_dirty()
        except Exception:
            pass

        # Clear current URL
        if self._shutdown:
            self._shutdown.set_current_url(None)
            self._shutdown.set_progress(checked, len(urls), len(signals))

        print(f"\nChecked {checked} URLs, skipped {skipped} (backoff)")
        print(f"Generated {len(signals)} new signals")

        if self.is_shutting_down():
            print(f"Remaining: {len(urls) - checked - skipped} URLs not processed due to shutdown")

        return signals

    def cleanup(self):
        """Clean up resources and handlers."""
        # Shutdown Playwright loops/fetchers (thread-local)
        if self._playwright_fetchers:
            for idx, fetcher in enumerate(self._playwright_fetchers):
                loop = self._playwright_loops[idx] if idx < len(self._playwright_loops) else None
                if not loop or loop.is_closed():
                    continue
                try:
                    loop.run_until_complete(fetcher.stop())
                except Exception:
                    pass
                try:
                    loop.close()
                except Exception:
                    pass
            self._playwright_fetchers = []
            self._playwright_loops = []

        # Shutdown legacy Playwright fetcher if running
        if self._playwright_fetcher:
            try:
                import asyncio
                asyncio.run(self._playwright_fetcher.stop())
            except Exception:
                pass
            self._playwright_fetcher = None

        # Flush all stores (batched writes accumulated during monitoring)
        for store_name in ('snapshot_store', 'signal_store', 'url_status_store',
                           'news_items_store', 'portfolio_store', 'team_store'):
            try:
                store = getattr(self, store_name, None)
                if store and hasattr(store, 'flush'):
                    store.flush()
            except Exception:
                pass

        # Save circuit breaker state (batched — may have deferred writes)
        try:
            from .circuit_breaker import get_circuit_registry
            get_circuit_registry().save_if_dirty()
        except Exception:
            pass

        # Close connection-pooled HTTP session
        try:
            from .fetcher import close_session
            close_session()
        except Exception:
            pass

        # Cleanup shutdown handlers
        if self._shutdown:
            self._shutdown.cleanup()

    def generate_status_report(self, output_path: Path | None = None) -> dict:
        """
        Generate a report of URL statuses for maintenance.

        Args:
            output_path: Optional path to write the report JSON

        Returns:
            The report dictionary
        """
        report = self.url_status_store.generate_report()

        if output_path:
            safe_json_write(output_path, report)
            print(f"Status report written to: {output_path}")

        return report


def load_urls_from_config(config_file: Path, limit: int | None = None) -> list[MonitoredUrl]:
    """
    Load monitored URLs from monitor_urls.json config.

    Only loads explicitly validated URLs - does NOT auto-generate subpage URLs.
    Each entity should specify its validated_urls with page_type tags.

    Args:
        config_file: Path to monitor_urls.json
        limit: Optional limit on number of URLs to load

    Returns:
        List of MonitoredUrl objects
    """
    with open(config_file) as f:
        config = json.load(f)

    urls = []
    entities = config.get("entities", [])
    normalizer = get_slug_normalizer()
    skipped_entities = 0

    # Optionally limit to matched entities or specific count
    if limit:
        entities = entities[:limit]

    for entity in entities:
        if not entity.get("active", True):
            continue

        base_url = entity["url"].rstrip("/")
        raw_slug = entity.get("slug") or entity["name"].lower().replace(" ", "-")
        normalization = normalizer.normalize(
            slug=raw_slug,
            name=entity.get("name"),
            source_url=entity.get("url"),
        )
        if not normalization.slug:
            skipped_entities += 1
            continue
        slug = normalization.slug
        name = normalizer.funds_by_slug.get(slug, {}).get("name") or entity["name"]

        # If entity has validated_urls, use those exclusively
        if "validated_urls" in entity:
            for validated in entity["validated_urls"]:
                # Get canonical category from config
                category = validated.get("category", "").upper()
                # page_type can be detailed subtype or fallback to category
                page_type = validated.get("page_type") or category.lower() or "other"

                urls.append(
                    MonitoredUrl(
                        url=validated["url"],
                        fund_slug=slug,
                        fund_name=name,
                        page_type=page_type,
                        category=category,
                    )
                )
        else:
            # Fallback: only add the base URL as 'home' page type
            # Do NOT auto-append /news, /portfolio, /team anymore
            urls.append(
                MonitoredUrl(
                    url=base_url,
                    fund_slug=slug,
                    fund_name=name,
                    page_type="home",
                    category="HOME",
                )
            )

    if skipped_entities:
        logger.info(f"Skipped {skipped_entities} monitor entities without canonical slugs")

    return urls


def load_urls_from_fund_urls(fund_urls_file: Path, limit: int | None = None) -> list[MonitoredUrl]:
    """
    Load monitored URLs from fund_urls.json config.

    This file contains verified news, portfolio, and team URLs for each fund,
    discovered through URL discovery or manual verification.

    Args:
        fund_urls_file: Path to fund_urls.json (in data/site_configs/)
        limit: Optional limit on number of funds to load

    Returns:
        List of MonitoredUrl objects with proper page_type and category
    """
    with open(fund_urls_file) as f:
        fund_urls = json.load(f)

    urls = []
    funds = list(fund_urls.items())
    normalizer = get_slug_normalizer()

    if limit:
        funds = funds[:limit]

    for fund_slug, data in funds:
        normalization = normalizer.normalize(slug=fund_slug, name=data.get("fund_name"))
        if not normalization.slug:
            continue
        canonical_slug = normalization.slug
        fund_name = normalizer.funds_by_slug.get(canonical_slug, {}).get("name") or data.get("fund_name", canonical_slug)

        # Add news URL if present
        if data.get("news"):
            urls.append(
                MonitoredUrl(
                    url=data["news"],
                    fund_slug=canonical_slug,
                    fund_name=fund_name,
                    page_type="news",
                    category="NEWS",
                )
            )

        # Add portfolio URL if present
        if data.get("portfolio"):
            urls.append(
                MonitoredUrl(
                    url=data["portfolio"],
                    fund_slug=canonical_slug,
                    fund_name=fund_name,
                    page_type="portfolio",
                    category="PORTFOLIO",
                )
            )

        # Add team URL if present
        if data.get("team"):
            urls.append(
                MonitoredUrl(
                    url=data["team"],
                    fund_slug=canonical_slug,
                    fund_name=fund_name,
                    page_type="team",
                    category="TEAM",
                )
            )

    return urls


def _filter_fresh_funds(urls: list[MonitoredUrl], data_dir: Path) -> tuple[list[MonitoredUrl], int]:
    """
    Filter out URLs for funds already scraped today whose extractor hasn't changed.

    Checks snapshots.json for the latest fetch timestamp per fund, and compares
    extractor file mtime to detect if the extractor was modified since last scrape.

    Skips a fund if: (a) scraped today AND (b) extractor not modified since.
    Use --force-extract or --slugs to bypass this check.

    Returns:
        (filtered_urls, skipped_fund_count)
    """
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Load snapshots → find latest fetch per fund
    snapshots_path = data_dir / "snapshots.json"
    latest_fetch: dict[str, str] = {}  # fund_slug → latest fetched_at ISO string
    if snapshots_path.exists():
        try:
            with open(snapshots_path) as f:
                snap_data = json.load(f)
            for snap in snap_data.get("snapshots", []):
                slug = snap.get("fund_slug", "")
                fetched = snap.get("fetched_at", "")
                if slug and fetched and (slug not in latest_fetch or fetched > latest_fetch[slug]):
                    latest_fetch[slug] = fetched
        except Exception:
            return urls, 0  # Can't read snapshots, don't skip anything

    # 2. Build domain → extractor file mtime from already-loaded extractors
    extractor_mtime: dict[str, float] = {}  # domain → file mtime epoch
    extractors_dir = Path(__file__).parent / "strategies" / "extractors"
    try:
        from .strategies.extractors import ALL_EXTRACTORS
        import importlib
        for domain in ALL_EXTRACTORS:
            # Find the module that declared this domain
            for py_file in extractors_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                # Quick text scan for DOMAIN = "domain" without importing
                try:
                    text = py_file.read_text(encoding="utf-8")
                    if f'DOMAIN = "{domain}"' in text or f"DOMAIN = '{domain}'" in text:
                        extractor_mtime[domain] = py_file.stat().st_mtime
                        break
                except Exception:
                    continue
    except Exception:
        pass  # Fall back to no mtime checking

    # 3. Map fund_slug → domain from the URL list
    slug_to_domain: dict[str, str] = {}
    for u in urls:
        if u.fund_slug and u.url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(u.url)
                if parsed.hostname:
                    slug_to_domain[u.fund_slug] = parsed.hostname
            except Exception:
                continue

    # 4. Load ALWAYS_EXTRACT domains (API-based extractors whose data changes independently)
    always_extract_domains: set[str] = set()
    try:
        from .strategies.extractors import ALWAYS_EXTRACT as _AE_DOMAINS
        always_extract_domains = _AE_DOMAINS
    except Exception:
        pass

    # 5. Decide which funds to skip
    skip_slugs: set[str] = set()
    for slug, fetched_at in latest_fetch.items():
        if not fetched_at.startswith(today):
            continue

        domain = slug_to_domain.get(slug)

        # Never skip API-based extractors — their data can change without HTML changing
        if domain and domain in always_extract_domains:
            continue

        # Check if extractor was modified after the last fetch
        if domain and domain in extractor_mtime:
            try:
                fetch_epoch = datetime.fromisoformat(fetched_at).timestamp()
                if extractor_mtime[domain] > fetch_epoch:
                    continue  # Extractor modified since last scrape — re-scrape
            except Exception:
                continue

        skip_slugs.add(slug)

    if not skip_slugs:
        return urls, 0

    filtered = [u for u in urls if u.fund_slug not in skip_slugs]
    remaining = len(set(u.fund_slug for u in filtered))
    print(f"Freshness filter: {len(set(u.fund_slug for u in urls))} funds → {remaining} to scrape")
    return filtered, len(skip_slugs)


def load_urls_from_extractors(data_dir: Path, limit: int | None = None) -> list[MonitoredUrl]:
    """
    Load monitored URLs from extractor URLS declarations.

    This reads URLS dicts from extractors and maps them to fund slugs using db.json.
    Extractors declare both what to extract (EXTRACTORS) and where to fetch (URLS).

    Args:
        data_dir: Data directory (for finding db.json)
        limit: Optional limit on number of funds

    Returns:
        List of MonitoredUrl objects
    """
    from .url_generator import generate_all_monitored_urls, normalize_domain

    normalizer = get_slug_normalizer()

    # Generate URLs from extractors
    all_urls = generate_all_monitored_urls()

    urls = []
    funds_processed = 0

    for domain, page_urls in all_urls.items():
        if limit and funds_processed >= limit:
            break

        norm_domain = normalize_domain(domain)
        normalization = normalizer.normalize(source_domain=norm_domain)
        if not normalization.slug:
            continue
        fund_slug = normalization.slug
        fund_name = normalizer.funds_by_slug.get(fund_slug, {}).get("name") or domain

        has_urls = False

        # Add portfolio URLs
        for url in page_urls.get("portfolio", []):
            urls.append(MonitoredUrl(
                url=url,
                fund_slug=fund_slug,
                fund_name=fund_name,
                page_type="portfolio",
                category="PORTFOLIO",
            ))
            has_urls = True

        # Add team URLs
        for url in page_urls.get("team", []):
            urls.append(MonitoredUrl(
                url=url,
                fund_slug=fund_slug,
                fund_name=fund_name,
                page_type="team",
                category="TEAM",
            ))
            has_urls = True

        # Add news URLs
        for url in page_urls.get("news", []):
            urls.append(MonitoredUrl(
                url=url,
                fund_slug=fund_slug,
                fund_name=fund_name,
                page_type="news",
                category="NEWS",
            ))
            has_urls = True

        if has_urls:
            funds_processed += 1

    return urls


def run_monitor(
    data_dir: Path,
    urls_file: Path | None = None,
    config_file: Path | None = None,
    limit: int | None = None,
    skip_backoff: bool = False,
    generate_report: bool = True,
    enable_graceful_shutdown: bool = True,
    use_fund_urls: bool = True,
    use_extractor_urls: bool = True,
    force_extract: bool = False,
    slugs_filter: list[str] | None = None,
):
    """
    Run the website monitor.

    Args:
        data_dir: Directory for storing snapshots and signals
        urls_file: Optional JSON file with URLs to monitor (legacy format)
        config_file: Optional path to monitor_urls config file
        limit: Optional limit on number of entities to monitor
        skip_backoff: If True, ignore backoff and check all URLs
        generate_report: If True, generate a status report after monitoring
        enable_graceful_shutdown: If True, install signal handlers for graceful shutdown
        use_fund_urls: If True, use fund_urls.json as primary URL source (default True)
        use_extractor_urls: If True, use extractor URLS declarations instead of fund_urls.json
        force_extract: If True, re-extract even if content unchanged (use after updating extractors)
        slugs_filter: If provided, only process URLs for these fund slugs
    """
    monitor = WebsiteMonitor(data_dir, enable_graceful_shutdown=enable_graceful_shutdown, force_extract=force_extract)

    urls = []

    # Option 1: Load from extractor URLS declarations (new preferred method)
    if use_extractor_urls:
        print("Loading URLs from extractor URLS declarations...")
        urls = load_urls_from_extractors(data_dir, limit=limit)
        entity_count = len(set(u.fund_slug for u in urls))
        print(f"Loaded {len(urls)} URLs from {entity_count} funds (extractors)")

    # Fallback to monitor_urls.json if no extractor URLs found
    if not urls:
        if config_file is None:
            config_file = data_dir / "monitor_urls.json"

        if config_file.exists():
            print(f"Loading URLs from {config_file}")
            urls = load_urls_from_config(config_file, limit=limit)
            entity_count = len(set(u.fund_slug for u in urls))
            print(f"Loaded {len(urls)} URLs from {entity_count} entities (monitor_urls.json)")
        elif urls_file and urls_file.exists():
            with open(urls_file) as f:
                urls_data = json.load(f)
                urls = [MonitoredUrl(**u) for u in urls_data["urls"]]

    # Final fallback: default sample URLs for testing
    if not urls:
        urls = [
            MonitoredUrl(
                url="https://www.investindustrial.com/about-us/team.html",
                fund_slug="investindustrial",
                fund_name="Investindustrial",
                page_type="team",
            ),
            MonitoredUrl(
                url="https://www.investindustrial.com/our-portfolio.html",
                fund_slug="investindustrial",
                fund_name="Investindustrial",
                page_type="portfolio",
            ),
        ]

    # Skip funds already scraped today (unless --force-extract or --slugs)
    if urls and not force_extract and not slugs_filter:
        urls, skipped = _filter_fresh_funds(urls, data_dir)
        if skipped:
            print(f"Skipped {skipped} fund(s) already scraped today (use --force-extract to override)")

    # Filter URLs to specific fund slugs if requested
    if slugs_filter and urls:
        normalizer = get_slug_normalizer()
        normalized_slugs = []
        for slug in slugs_filter:
            result = normalizer.normalize(slug=slug)
            if result.slug:
                normalized_slugs.append(result.slug)
        slugs_set = set(normalized_slugs)
        before_count = len(urls)
        urls = [u for u in urls if u.fund_slug in slugs_set]
        print(f"Slug filter: {before_count} URLs → {len(urls)} URLs for {len(slugs_set)} fund(s)")

    # Run the check
    try:
        signals = monitor.check_urls(urls, skip_backoff=skip_backoff)

        # Generate status report
        if generate_report and not monitor.is_shutting_down():
            report_path = data_dir / "url_status_report.json"
            report = monitor.generate_status_report(report_path)
            print(f"\nURL Status Summary:")
            print(f"  Total tracked: {report['total_urls']}")
            for status, count in report.get("by_status", {}).items():
                print(f"  {status}: {count}")

        # Prune old snapshots to prevent unbounded blob/snapshot growth
        if not monitor.is_shutting_down():
            try:
                prune_stats = monitor.snapshot_store.prune_old_snapshots(max_age_days=30)
                if prune_stats["snapshots_pruned"] > 0:
                    print(f"\nSnapshot pruning: removed {prune_stats['snapshots_pruned']} snapshots, "
                          f"{prune_stats['blobs_removed']} blobs, "
                          f"{prune_stats['legacy_html_removed']} legacy HTML files")
            except Exception as e:
                print(f"\nWarning: snapshot pruning failed: {e}")

        # Send Telegram alerts for URLs with persistent failures
        if not monitor.is_shutting_down():
            try:
                from .alerting import send_url_failure_alerts
                send_url_failure_alerts(data_dir)
            except Exception as e:
                print(f"\nWarning: URL failure alerting failed: {e}")

        return signals
    finally:
        # Always cleanup
        monitor.cleanup()


if __name__ == "__main__":
    import sys

    # Get project root
    project_root = Path(__file__).parent.parent.parent.parent
    data_dir = project_root / "data" / "derived"

    # Parse command line arguments
    limit = None
    skip_backoff = False
    report_only = False
    config_file = None
    use_fund_urls = True  # Default to using fund_urls.json
    use_extractor_urls = True  # Use extractor URLS declarations (preferred)
    force_extract = False  # Force re-extraction even if content unchanged
    slugs_filter = None  # Only process these specific fund slugs

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
        elif arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
        elif arg == "--slugs" and i + 1 < len(args):
            slugs_filter = [s.strip() for s in args[i + 1].split(",") if s.strip()]
        elif arg.startswith("--slugs="):
            slugs_filter = [s.strip() for s in arg.split("=", 1)[1].split(",") if s.strip()]
        elif arg == "--config" and i + 1 < len(args):
            config_file = Path(args[i + 1])
        elif arg.startswith("--config="):
            config_file = Path(arg.split("=")[1])
        elif arg == "--skip-backoff":
            skip_backoff = True
        elif arg == "--report-only":
            report_only = True
        elif arg == "--no-fund-urls":
            use_fund_urls = False
        elif arg == "--extractor-urls":
            use_extractor_urls = True
        elif arg == "--force-extract":
            force_extract = True
        elif arg == "--help" or arg == "-h":
            print("Usage: python -m fundradar_worker.monitor [OPTIONS]")
            print("\nOptions:")
            print("  --limit N          Limit to N entities")
            print("  --slugs s1,s2,...  Only process these fund slugs (comma-separated)")
            print("  --config FILE      Use custom config file")
            print("  --skip-backoff     Ignore backoff, check all URLs")
            print("  --report-only      Only generate status report")
            print("  --no-fund-urls     Use monitor_urls.json instead of fund_urls.json")
            print("  --extractor-urls   Use extractor URLS declarations (new, preferred)")
            print("  --force-extract    Re-extract all funds (bypasses daily freshness skip + content hash)")
            print("  --help, -h         Show this help message")
            sys.exit(0)

    print("Fundradar Website Monitor")
    print("=========================\n")

    if report_only:
        # Just generate the status report
        monitor = WebsiteMonitor(data_dir)
        report = monitor.generate_status_report(data_dir / "url_status_report.json")
        print(f"\nURL Status Summary:")
        print(f"  Total tracked: {report['total_urls']}")
        for status, count in report.get("by_status", {}).items():
            print(f"  {status}: {count}")
        if report.get("problem_domains"):
            print(f"\nProblem domains (>50% failure rate):")
            for domain in report["problem_domains"][:10]:
                print(f"  - {domain['domain']}: {domain['failures']}/{domain['total']} failures")
    else:
        if config_file:
            print(f"Using config: {config_file}")
        if limit:
            print(f"Limiting to {limit} entities")
        if slugs_filter:
            print(f"Filtering to {len(slugs_filter)} fund(s): {', '.join(slugs_filter)}")
        if skip_backoff:
            print("Skipping backoff (checking all URLs)")
        if use_extractor_urls:
            print("Using extractor URLS declarations as primary URL source")
        elif use_fund_urls:
            print("Using fund_urls.json as primary URL source")
        if force_extract:
            print("Force extraction enabled (will re-extract even if content unchanged)")
        print()

        signals = run_monitor(data_dir, config_file=config_file, limit=limit, skip_backoff=skip_backoff, use_fund_urls=use_fund_urls, use_extractor_urls=use_extractor_urls, force_extract=force_extract, slugs_filter=slugs_filter)

        if signals:
            print("\nGenerated Signals:")
            for signal in signals:
                print(f"  - [{signal['signal_type']}] {signal['fund_slug']}: {signal['title']}")
