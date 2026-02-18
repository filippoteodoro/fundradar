"""
Safe I/O utilities for Fundradar.

Provides atomic writes, backup rotation, and data sanitization
to prevent data corruption and prompt injection.
"""

import json
import logging
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default backup directory relative to data/derived/
_BACKUP_DIR_NAME = "backups"


def safe_json_write(path: Path | str, data: dict | list, indent: int = 2) -> None:
    """
    Atomic write: serialize to temp file, then rename.

    If the process crashes mid-write, the original file remains intact
    because os.replace is atomic on POSIX filesystems.

    Args:
        path: Target file path.
        data: JSON-serializable data.
        indent: JSON indentation level.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file in the same directory (same filesystem = atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".tmp",
        prefix=f".{path.stem}_",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)

        # Atomic replace
        os.replace(tmp_path, str(path))
        logger.debug(f"Wrote {path.name} ({path.stat().st_size:,} bytes)")
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def backup_before_write(path: Path | str, max_backups: int = 7) -> Path | None:
    """
    Copy current file to backups/{name}.{ISO_DATE}.json before overwriting.

    Rotates old backups, keeping at most `max_backups` per file.

    Args:
        path: The file to back up.
        max_backups: Maximum number of backup copies to retain.

    Returns:
        Path to the backup file, or None if the source doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        return None

    backup_dir = path.parent / _BACKUP_DIR_NAME
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    backup_name = f"{path.stem}.{timestamp}{path.suffix}"
    backup_path = backup_dir / backup_name

    shutil.copy2(str(path), str(backup_path))
    logger.info(f"Backed up {path.name} -> backups/{backup_name}")

    # Rotate: remove oldest backups beyond max_backups
    pattern = f"{path.stem}.*{path.suffix}"
    existing = sorted(backup_dir.glob(pattern))
    if len(existing) > max_backups:
        for old in existing[: len(existing) - max_backups]:
            old.unlink()
            logger.debug(f"Rotated old backup: {old.name}")

    return backup_path


# ---------------------------------------------------------------------------
# Data sanitization
# ---------------------------------------------------------------------------

# Control character categories to strip (preserves letters, numbers, punctuation, symbols, spaces)
_ALLOWED_CATEGORIES = frozenset({
    "Lu", "Ll", "Lt", "Lm", "Lo",  # Letters (includes accented: à, è, ì, ò, ù, é)
    "Nd", "Nl", "No",               # Numbers
    "Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po",  # Punctuation
    "Sm", "Sc", "Sk", "So",         # Symbols
    "Zs",                            # Space separators
})


def sanitize_text(text: str | None, max_length: int = 1000) -> str | None:
    """
    Sanitize text from scraped web content.

    - Strips HTML tags via BeautifulSoup
    - Removes control characters (preserves Italian accents and symbols)
    - Normalizes whitespace
    - Truncates to max_length

    Returns None for empty/None input.
    """
    if text is None:
        return None

    if not isinstance(text, str):
        text = str(text)

    # Strip HTML tags
    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    except Exception:
        # Fallback: basic tag stripping if BeautifulSoup fails
        text = re.sub(r"<[^>]+>", " ", text)

    # Remove control characters (preserve accented letters, punctuation, symbols)
    cleaned = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in _ALLOWED_CATEGORIES or ch in ("\n", "\t"):
            cleaned.append(ch)
    text = "".join(cleaned)

    # Normalize whitespace: collapse runs of whitespace to single space
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate
    if len(text) > max_length:
        text = text[:max_length]

    return text if text else None


def sanitize_url(url: str | None) -> str | None:
    """
    Sanitize a URL from scraped web content.

    - Validates http/https scheme
    - Prefixes bare domains with https://
    - Rejects javascript:, data:, vbscript:, etc.

    Returns None for invalid/None input.
    """
    if url is None:
        return None

    if not isinstance(url, str):
        return None

    url = url.strip()
    if not url:
        return None

    # Prefix bare domains (e.g., "example.com/path")
    if not url.startswith(("http://", "https://", "//")):
        # Check if it looks like a domain (has a dot, no spaces, no colon prefix)
        if "." in url and " " not in url and ":" not in url.split("/")[0]:
            url = "https://" + url
        elif url.startswith("//"):
            url = "https:" + url
        else:
            # Not a recognizable URL pattern
            return None

    # Handle protocol-relative URLs
    if url.startswith("//"):
        url = "https:" + url

    parsed = urlparse(url)

    # Only allow http and https schemes
    if parsed.scheme not in ("http", "https"):
        return None

    return url
