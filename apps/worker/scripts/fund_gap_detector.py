"""
Fund gap detector — finds Italian-style fund/SGR names in signal text that
are not present in db.json.

Called by filter_signals.py after filtering completes. Detected gaps are
persisted to data/derived/unknown_fund_gaps.json (30-day dedup window) and
sent as Telegram alerts via alerting.py.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fundradar_worker.io_utils import safe_json_write
from fundradar_worker.paths import DATA_DIR

logger = logging.getLogger(__name__)

# Matches Italian-style fund/investment entity names:
# "[Proper Name(s)] SGR" / "[Proper Names] Venture Partners" etc.
_RE_FUND_CANDIDATE = re.compile(
    r"\b([A-Z][A-Za-z\u00C0-\u017E]+(?:\s+[A-Z][A-Za-z\u00C0-\u017E]+){0,4})"
    r"\s+(?:SGR|Venture\s+Capital|Venture\s+Partners?|Private\s+Equity\s+(?:SGR|Partners?|Fund))\b"
)

# Legal suffixes to strip when generating a slug suggestion
_RE_LEGAL_SUFFIX = re.compile(
    r"\s+(?:SGR|S\.G\.R\.?|S\.p\.A\.?|S\.r\.l\.?|Ltd\.?|Limited|LP|LLP|LLC|S\.A\.?|GmbH)\b",
    re.IGNORECASE,
)

GAP_STATE_FILE = DATA_DIR / "unknown_fund_gaps.json"
DEDUP_WINDOW_DAYS = 30


def _slugify(text: str) -> str:
    """Convert a fund name to a URL-safe slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _normalize_mention(mention: str) -> str:
    """Strip legal suffixes from a fund mention for slug generation."""
    return _RE_LEGAL_SUFFIX.sub("", mention).strip()


def _load_gap_state() -> dict:
    """Load previously alerted fund gaps for deduplication."""
    try:
        if GAP_STATE_FILE.exists():
            with open(GAP_STATE_FILE) as f:
                return json.load(f)
    except Exception as exc:
        logger.warning(f"Could not load gap state file: {exc}")
    return {"gaps": []}


def detect_unknown_fund_mentions(
    signals: list[dict],
    known_slugs: set[str],
    invalid_slugs: set[str] | None = None,
) -> list[dict]:
    """Scan signal text for Italian-style fund names not in known_slugs.

    Deduplicates against previously alerted mentions within the last 30 days.
    New gaps are persisted to GAP_STATE_FILE.

    Args:
        signals: Filtered signals to scan.
        known_slugs: Slugs of funds in db.json.
        invalid_slugs: Slugs of blocked/non-PE entities (from fund_aliases.json).
            These suppress alerts for known credit/banking/agency entities.

    Returns a list of gap dicts:
        {mention, suggested_slug, signal_id, signal_title}
    """
    suppressed = known_slugs | (invalid_slugs or set())

    # Collect the first signal mentioning each candidate slug
    candidates: dict[str, dict] = {}  # suggested_slug -> gap info

    for sig in signals:
        text = (sig.get("title") or "") + " " + (sig.get("what_changed") or "")
        for match in _RE_FUND_CANDIDATE.finditer(text):
            full_match = match.group(0).strip()
            name_part = _normalize_mention(full_match)
            slug = _slugify(name_part)

            if not slug or len(slug) < 4:
                continue
            if slug in suppressed or slug in candidates:
                continue
            # Also reject if the full-match slug (with SGR suffix) is suppressed
            if _slugify(full_match) in suppressed:
                continue
            # Reject if slug is a prefix component of a known slug
            # e.g. "Deep Ocean SGR" (→ "deep-ocean") matches "deep-ocean-capital-sgr"
            if any(ks.startswith(slug + "-") for ks in suppressed):
                continue

            candidates[slug] = {
                "mention": full_match,
                "suggested_slug": slug,
                "signal_id": sig.get("id", ""),
                "signal_title": (sig.get("title") or "")[:120],
            }

    if not candidates:
        return []

    # Load previous state and identify already-alerted slugs (within window)
    state = _load_gap_state()
    cutoff = datetime.now(timezone.utc) - timedelta(days=DEDUP_WINDOW_DAYS)

    already_alerted: set[str] = set()
    valid_previous: list[dict] = []
    for entry in state.get("gaps", []):
        try:
            alerted_at = datetime.fromisoformat(entry.get("alerted_at", ""))
            if alerted_at > cutoff:
                already_alerted.add(entry["suggested_slug"])
                valid_previous.append(entry)
        except (ValueError, KeyError):
            pass

    new_gaps = [g for slug, g in candidates.items() if slug not in already_alerted]

    if not new_gaps:
        return []

    # Persist new entries alongside still-valid previous ones
    now = datetime.now(timezone.utc).isoformat()
    new_entries = [{**g, "alerted_at": now} for g in new_gaps]
    updated_state = {"gaps": valid_previous + new_entries}
    try:
        safe_json_write(GAP_STATE_FILE, updated_state)
    except Exception as exc:
        logger.warning(f"Could not persist gap state: {exc}")

    logger.info(f"Detected {len(new_gaps)} unknown fund mention(s)")
    return new_gaps
