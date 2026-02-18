"""
URL fetcher and snapshot storage for Fundradar.

Fetches web pages, extracts text content, and stores snapshots for change detection.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import requests
import requests.adapters
from bs4 import BeautifulSoup

from .io_utils import safe_json_write
from .url_utils import canonical_url, canonical_url_variants

logger = logging.getLogger(__name__)

# --- Connection-pooled HTTP session ---
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Get or create a connection-pooled HTTP session."""
    global _session
    if _session is None:
        _session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,  # number of host pools
            pool_maxsize=10,      # connections per host
            max_retries=0,        # we handle retries ourselves
        )
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
        _session.headers.update({
            "User-Agent": "Fundradar/1.0 (https://fundradar.io; research purposes)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5,it;q=0.3",
        })
    return _session


def close_session():
    """Close the HTTP session. Call at end of monitoring run."""
    global _session
    if _session:
        _session.close()
        _session = None


class FetchMetadata(TypedDict, total=False):
    """HTTP metadata for conditional requests and caching."""
    etag: str | None
    last_modified: str | None
    content_type: str | None
    final_url: str  # After redirects
    fetch_time_ms: int


class SnapshotRecord(TypedDict):
    """A stored snapshot of a web page."""

    id: str
    url: str
    fund_slug: str
    fetched_at: str
    status_code: int
    content_hash: str
    text_content: str
    html_length: int
    title: str | None
    error: str | None
    # Phase 1: Add caching metadata
    etag: str | None
    last_modified: str | None
    blob_hash: str | None  # For content-addressed storage


class CheckRecord(TypedDict):
    """Lightweight record for 304 or no-change checks."""
    url: str
    fund_slug: str
    checked_at: str
    status_code: int
    result: str  # "not_modified", "unchanged", "error"
    error: str | None


@dataclass
class FetchResult:
    """Result of fetching a URL."""

    url: str
    status_code: int
    html: str
    text: str
    title: str | None
    content_hash: str
    error: str | None = None
    # Phase 1: Add HTTP metadata
    etag: str | None = None
    last_modified: str | None = None
    final_url: str | None = None
    was_not_modified: bool = False  # True if 304 response


def extract_text_from_html(html: str) -> tuple[str, str | None]:
    """
    Extract clean text content from HTML.

    Returns (text_content, title).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Get title
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Remove script, style, nav, footer, header elements (boilerplate)
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    # Get text, normalize whitespace
    text = soup.get_text(separator="\n")

    # Clean up whitespace
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    # Remove excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text, title


def compute_content_hash(text: str) -> str:
    """Compute a hash of the text content for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fetch_url(
    url: str,
    timeout: int = 30,
    etag: str | None = None,
    last_modified: str | None = None,
    ssl_verify: bool = True,
    retry_count: int = 1,
) -> FetchResult:
    """
    Fetch a URL and extract its content.

    Supports conditional requests via ETag/Last-Modified headers.
    If the server returns 304, returns a result with was_not_modified=True.

    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds
        etag: Optional ETag from previous fetch for conditional request
        last_modified: Optional Last-Modified from previous fetch
        ssl_verify: Whether to verify SSL certificates (False for problematic sites)
        retry_count: Number of times to retry on transient errors

    Returns:
        FetchResult with status, content, and extracted text
    """
    # Per-request headers (conditional request headers only;
    # common headers are set on the session via _get_session())
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    session = _get_session()
    last_error = None
    for attempt in range(retry_count):
        try:
            response = session.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
                verify=ssl_verify,
            )

            # Extract caching headers from response
            resp_etag = response.headers.get("ETag")
            resp_last_modified = response.headers.get("Last-Modified")
            final_url = response.url

            # Handle 304 Not Modified
            if response.status_code == 304:
                return FetchResult(
                    url=url,
                    status_code=304,
                    html="",
                    text="",
                    title=None,
                    content_hash="",
                    etag=resp_etag or etag,
                    last_modified=resp_last_modified or last_modified,
                    final_url=final_url,
                    was_not_modified=True,
                )

            html = response.text
            text, title = extract_text_from_html(html)
            content_hash = compute_content_hash(text)

            return FetchResult(
                url=url,
                status_code=response.status_code,
                html=html,
                text=text,
                title=title,
                content_hash=content_hash,
                etag=resp_etag,
                last_modified=resp_last_modified,
                final_url=final_url,
            )

        except requests.Timeout:
            last_error = "Timeout"
            # Retry on timeout
            continue
        except requests.RequestException as e:
            last_error = str(e)
            # Don't retry on most request exceptions
            break

    # All retries exhausted or non-retryable error
    return FetchResult(
        url=url,
        status_code=0,
        html="",
        text="",
        title=None,
        content_hash="",
        error=last_error or "Unknown error",
    )


class SnapshotStore:
    """
    File-based storage for snapshots with content-addressed deduplication.

    Phase 1 improvements:
    - Content-addressed blob storage: HTML stored under /blobs/<hash>.html
    - Deduplication: Same content = same blob, no extra storage
    - Check records: Lightweight records for 304/no-change responses
    - Caching metadata: ETag/Last-Modified stored for conditional requests

    Storage structure:
    {
        "snapshots": [...],
        "url_index": { url: [snapshot_ids] },
        "check_records": [...],
        "url_metadata": { url: {etag, last_modified, ...} }
    }
    """

    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.html_dir = store_path.parent / "snapshots_html"
        self.blobs_dir = store_path.parent / "blobs"  # Content-addressed storage
        self._dirty = False  # Track if in-memory state diverged from disk
        self._ensure_dirs()
        self._load()

    def _ensure_dirs(self):
        """Ensure storage directories exist."""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.html_dir.mkdir(parents=True, exist_ok=True)
        self.blobs_dir.mkdir(parents=True, exist_ok=True)

    def _load(self):
        """Load snapshots from disk."""
        if self.store_path.exists():
            with open(self.store_path) as f:
                data = json.load(f)
                self.snapshots: list[SnapshotRecord] = data.get("snapshots", [])
                self.url_index: dict[str, list[str]] = data.get("url_index", {})
                self.check_records: list[CheckRecord] = data.get("check_records", [])
                self.url_metadata: dict[str, FetchMetadata] = data.get("url_metadata", {})
        else:
            self.snapshots = []
            self.url_index = {}
            self.check_records = []
            self.url_metadata = {}

    def _save(self):
        """Save snapshots to disk (atomic write)."""
        safe_json_write(
            self.store_path,
            {
                "snapshots": self.snapshots,
                "url_index": self.url_index,
                "check_records": self.check_records,
                "url_metadata": self.url_metadata,
            },
        )

    def flush(self):
        """Flush in-memory state to disk if any changes occurred.

        Call at end of monitoring run to persist accumulated snapshots,
        check records, and URL metadata in a single write.
        """
        if self._dirty:
            self._save()
            self._dirty = False

    def _generate_id(self, url: str) -> str:
        """Generate a unique snapshot ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"snap-{timestamp}-{url_hash}"

    def _compute_blob_hash(self, html: str) -> str:
        """Compute content hash for blob storage."""
        return hashlib.sha256(html.encode("utf-8")).hexdigest()

    def _store_blob(self, html: str) -> str:
        """
        Store HTML in content-addressed blob storage.
        Returns the blob hash. Deduplicates automatically.
        """
        blob_hash = self._compute_blob_hash(html)
        blob_path = self.blobs_dir / f"{blob_hash}.html"

        # Only write if not already exists (dedup)
        if not blob_path.exists():
            with open(blob_path, "w", encoding="utf-8") as f:
                f.write(html)

        return blob_hash

    def get_url_metadata(self, url: str) -> FetchMetadata | None:
        """Get cached metadata for conditional requests."""
        return self.url_metadata.get(url)

    def store_check_record(self, url: str, fund_slug: str, status_code: int, result: str, error: str | None = None):
        """
        Store a lightweight check record for 304 or unchanged responses.
        These are cheap to store and provide audit trail.
        """
        record: CheckRecord = {
            "url": url,
            "fund_slug": fund_slug,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status_code": status_code,
            "result": result,
            "error": error,
        }
        self.check_records.append(record)
        # Keep only last 1000 check records to avoid bloat
        if len(self.check_records) > 1000:
            self.check_records = self.check_records[-1000:]
        self._dirty = True

    def store(self, result: FetchResult, fund_slug: str, store_html: bool = True) -> SnapshotRecord:
        """
        Store a fetch result as a snapshot.

        Args:
            result: The FetchResult to store
            fund_slug: The slug of the fund this URL belongs to
            store_html: If False, skip storing HTML blob (for unchanged content)

        Returns:
            The stored SnapshotRecord
        """
        snapshot_id = self._generate_id(result.url)
        blob_hash = None

        # Store raw HTML in content-addressed blob storage
        if store_html and result.html:
            blob_hash = self._store_blob(result.html)
            # Also store in legacy location for backward compatibility
            html_path = self.html_dir / f"{snapshot_id}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(result.html)

        snapshot: SnapshotRecord = {
            "id": snapshot_id,
            "url": result.url,
            "fund_slug": fund_slug,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status_code": result.status_code,
            "content_hash": result.content_hash,
            "text_content": result.text[:10000] if result.text else "",  # Truncate for storage
            "html_length": len(result.html),
            "title": result.title,
            "error": result.error,
            "etag": result.etag,
            "last_modified": result.last_modified,
            "blob_hash": blob_hash,
        }

        self.snapshots.append(snapshot)

        # Update URL index
        if result.url not in self.url_index:
            self.url_index[result.url] = []
        self.url_index[result.url].append(snapshot_id)

        # Update URL metadata for future conditional requests
        self.url_metadata[result.url] = {
            "etag": result.etag,
            "last_modified": result.last_modified,
            "content_type": None,  # Could be extracted from response
            "final_url": result.final_url or result.url,
        }

        self._dirty = True
        return snapshot

    def get_latest_for_url(self, url: str) -> SnapshotRecord | None:
        """Get the most recent snapshot for a URL."""
        if url not in self.url_index or not self.url_index[url]:
            return None

        latest_id = self.url_index[url][-1]
        for snap in self.snapshots:
            if snap["id"] == latest_id:
                return snap
        return None

    def get_previous_for_url(self, url: str) -> SnapshotRecord | None:
        """Get the second-most-recent snapshot for a URL (for diff comparison)."""
        if url not in self.url_index or len(self.url_index[url]) < 2:
            return None

        prev_id = self.url_index[url][-2]
        for snap in self.snapshots:
            if snap["id"] == prev_id:
                return snap
        return None

    def get_html(self, snapshot_id: str) -> str | None:
        """Load the raw HTML for a snapshot."""
        # Try legacy location first
        html_path = self.html_dir / f"{snapshot_id}.html"
        if html_path.exists():
            return html_path.read_text(encoding="utf-8")

        # Try content-addressed blob
        for snap in self.snapshots:
            if snap["id"] == snapshot_id and snap.get("blob_hash"):
                blob_path = self.blobs_dir / f"{snap['blob_hash']}.html"
                if blob_path.exists():
                    return blob_path.read_text(encoding="utf-8")

        return None

    def get_storage_stats(self) -> dict:
        """Get storage statistics for monitoring."""
        import os

        blob_count = len(list(self.blobs_dir.glob("*.html")))
        blob_size = sum(f.stat().st_size for f in self.blobs_dir.glob("*.html"))
        legacy_count = len(list(self.html_dir.glob("*.html")))
        legacy_size = sum(f.stat().st_size for f in self.html_dir.glob("*.html"))

        return {
            "snapshot_count": len(self.snapshots),
            "check_record_count": len(self.check_records),
            "unique_urls": len(self.url_index),
            "blob_count": blob_count,
            "blob_size_mb": round(blob_size / 1024 / 1024, 2),
            "legacy_html_count": legacy_count,
            "legacy_html_size_mb": round(legacy_size / 1024 / 1024, 2),
        }

    def get_latest_for_url_canonical(self, url: str) -> SnapshotRecord | None:
        """
        Get the most recent snapshot for a URL using canonical matching.

        Tries the URL's canonical form and common variants (with/without www,
        trailing slash, etc.) to find a matching snapshot.
        """
        # Build canonical URL index if not cached
        if not hasattr(self, "_canonical_index"):
            self._canonical_index = {}
            for idx_url in self.url_index:
                canonical = canonical_url(idx_url)
                if canonical not in self._canonical_index:
                    self._canonical_index[canonical] = []
                self._canonical_index[canonical].append(idx_url)

        # Try canonical variants
        for variant in canonical_url_variants(url):
            variant_canonical = canonical_url(variant)
            if variant_canonical in self._canonical_index:
                # Get the original URL(s) that match
                for original_url in self._canonical_index[variant_canonical]:
                    snapshot = self.get_latest_for_url(original_url)
                    if snapshot and snapshot.get("status_code") == 200:
                        return snapshot

        # Also try direct URL lookup
        return self.get_latest_for_url(url)

    def load_latest_html_for_url(self, url: str) -> tuple[str | None, SnapshotRecord | None]:
        """
        Load the latest HTML for a URL using canonical matching.

        This is the primary method for enrichment to look up HTML.

        Args:
            url: The URL to find HTML for

        Returns:
            Tuple of (html_content, snapshot_record). Both None if not found.
        """
        # Try canonical matching first
        snapshot = self.get_latest_for_url_canonical(url)

        if snapshot:
            # Load HTML from blob or legacy storage
            html = self.get_html(snapshot["id"])
            if html:
                return html, snapshot

        # Try final_url redirect mapping
        for idx_url, metadata in self.url_metadata.items():
            final_url = metadata.get("final_url", "")
            if final_url and canonical_url(final_url) == canonical_url(url):
                snapshot = self.get_latest_for_url(idx_url)
                if snapshot:
                    html = self.get_html(snapshot["id"])
                    if html:
                        return html, snapshot

        return None, None

    def prune_old_snapshots(self, max_age_days: int = 30, max_per_url: int = 5) -> dict:
        """
        Remove old snapshot HTML files to reclaim disk space.

        Keeps at most `max_per_url` snapshots per URL and removes any
        HTML files older than `max_age_days`.

        Returns:
            Stats dict with counts of removed blobs and legacy HTML files.
        """
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        cutoff_iso = cutoff.isoformat()

        removed_blobs = 0
        removed_legacy = 0
        kept_blob_hashes: set[str] = set()

        # Group snapshots by URL and decide which to keep
        url_snapshots: dict[str, list[dict]] = {}
        for snap in self.snapshots:
            url = snap["url"]
            url_snapshots.setdefault(url, []).append(snap)

        snapshots_to_remove: set[str] = set()  # snapshot IDs to prune

        for url, snaps in url_snapshots.items():
            # Sort newest first
            snaps.sort(key=lambda s: s.get("fetched_at", ""), reverse=True)

            for i, snap in enumerate(snaps):
                keep = i < max_per_url and snap.get("fetched_at", "") >= cutoff_iso
                if keep:
                    if snap.get("blob_hash"):
                        kept_blob_hashes.add(snap["blob_hash"])
                else:
                    snapshots_to_remove.add(snap["id"])

        # Remove legacy HTML files for pruned snapshots
        for snap_id in snapshots_to_remove:
            legacy_path = self.html_dir / f"{snap_id}.html"
            if legacy_path.exists():
                legacy_path.unlink()
                removed_legacy += 1

        # Remove orphaned blobs (not referenced by any kept snapshot)
        all_blob_hashes = {
            snap.get("blob_hash")
            for snap in self.snapshots
            if snap.get("blob_hash")
        }
        orphaned = all_blob_hashes - kept_blob_hashes
        for blob_hash in orphaned:
            blob_path = self.blobs_dir / f"{blob_hash}.html"
            if blob_path.exists():
                blob_path.unlink()
                removed_blobs += 1

        # Remove pruned snapshots from in-memory list and index
        self.snapshots = [s for s in self.snapshots if s["id"] not in snapshots_to_remove]

        # Rebuild url_index
        self.url_index = {}
        for snap in self.snapshots:
            url = snap["url"]
            self.url_index.setdefault(url, []).append(snap["id"])

        self._save()

        stats = {
            "snapshots_pruned": len(snapshots_to_remove),
            "blobs_removed": removed_blobs,
            "legacy_html_removed": removed_legacy,
            "snapshots_remaining": len(self.snapshots),
        }
        logger.info(f"Snapshot pruning: {stats}")
        return stats

    def rebuild_canonical_index(self):
        """Force rebuild of the canonical URL index."""
        if hasattr(self, "_canonical_index"):
            delattr(self, "_canonical_index")
