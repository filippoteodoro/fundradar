#!/usr/bin/env python3
"""
One-off cleanup for already displayed signals.

Syncs detected_signals_filtered.json to only include signals that survived
the enrichment hard filter (detected_signals_enriched.json).

Safe-guards:
- Requires a completed enrichment run (enriched_at present)
- Creates a timestamped backup of detected_signals_filtered.json
"""

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DERIVED = REPO_ROOT / "data" / "derived"
FILTERED = DERIVED / "detected_signals_filtered.json"
ENRICHED = DERIVED / "detected_signals_enriched.json"

READ_TIME_PATTERNS = [
    r"\b\d+\s*min(?:ute)?s?\s*read\b",
    r"\b\d+\s*min\.?\s*read\b",
    r"\b\d+\s*min(?:uto|uti)\s*di\s*lettura\b",
    r"\btempo\s+di\s+lettura\b",
    r"\bread\s+time\b",
]

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]

MONTHS_PATTERN = "(?:" + "|".join(MONTHS) + ")"
DATE_PREFIX_NUMERIC_RE = re.compile(r"^\s*\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{2,4}\s*", re.IGNORECASE)
DATE_PREFIX_WORD_RE = re.compile(r"^\s*\d{1,2}\s+" + MONTHS_PATTERN + r"\s+\d{4}\s*", re.IGNORECASE)
DATE_PREFIX_WORD_RE2 = re.compile(r"^\s*" + MONTHS_PATTERN + r"\s+\d{1,2},?\s*\d{4}\s*", re.IGNORECASE)
PRESS_RELEASE_PREFIX_RE = re.compile(r"^(?:press\s*release|comunicato\s*stampa)\s*[-:]?\s*", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
LEADING_LABEL_RE = re.compile(
    r"^\s*(?:news|update|announcement|new announcement|new portfolio investment|new portfolio exit|new portfolio|new investment|new exit|new team members|team update|fundraising update|fund close|press release|comunicato stampa|news release)\s*[:\-–]\s*",
    re.IGNORECASE,
)

FRAGMENTED_PHRASES = [
    "continua a leggere",
    "read more",
    "leggi di piu",
    "leggi di più",
    "approfondisci",
]


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def clean_text(text: str | None) -> str | None:
    if not text:
        return text
    cleaned = text
    for pattern in READ_TIME_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = URL_RE.sub("", cleaned)
    cleaned = DATE_PREFIX_NUMERIC_RE.sub("", cleaned)
    cleaned = DATE_PREFIX_WORD_RE.sub("", cleaned)
    cleaned = DATE_PREFIX_WORD_RE2.sub("", cleaned)
    cleaned = PRESS_RELEASE_PREFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"(?<=\d)(?=[A-Za-zÀ-ÖØ-öø-ÿ])", " ", cleaned)
    cleaned = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])(?=\d)", " ", cleaned)
    cleaned = re.sub(r"(?<=[A-ZÀ-ÖØ-Þ]{2})(?=[a-zà-öø-ÿ])", " ", cleaned)
    cleaned = re.sub(r"(?<=[a-zà-öø-ÿ]{3})(?=[A-ZÀ-ÖØ-Þ]{2,})", " ", cleaned)
    cleaned = re.sub(r"([,;:])(?=[A-Za-zÀ-ÖØ-öø-ÿ])", r"\1 ", cleaned)
    cleaned = re.sub(r"(?<=\d),\s+(?=\d)", ",", cleaned)
    cleaned = re.sub(
        r"\b(?i:di|da|del|dello|della|dei|degli|delle|de|e|ed|la|il|lo|gli|le|al|allo|alla|ai|agli|alle|nel|nello|nella|nei|negli|nelle|sul|sullo|sulla|sui|sugli|sulle|per|con|su|in)(?=[A-ZÀ-ÖØ-Þ])",
        r"\g<0> ",
        cleaned,
    )
    cleaned = re.sub(r"(?<=[a-zà-öø-ÿ]{3})(?=[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ])", " ", cleaned)
    cleaned = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])(?=[\"“])", " ", cleaned)
    for phrase in FRAGMENTED_PHRASES:
        pattern = r"".join(re.escape(ch) + r"\s*" for ch in phrase)
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = LEADING_LABEL_RE.sub("", cleaned)
    cleaned = re.sub(r"\bde\s+l\b", "del", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdi\s+l\b", "del", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bi\s+l\b", "il", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bsu\s+l\b", "sul", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdel\s+la\b", "della", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdel\s+le\b", "delle", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdel\s+lo\b", "dello", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdel\s+i\b", "dei", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdel\s+gli\b", "degli", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bal\s+la\b", "alla", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bal\s+lo\b", "allo", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bal\s+le\b", "alle", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bal\s+gli\b", "agli", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b([A-Za-zÀ-ÖØ-öø-ÿ]{2,})\s([ECIPSV])\s+([a-zà-öø-ÿ]{2,})",
        r"\1 \2\3",
        cleaned,
    )
    cleaned = re.sub(
        r"\b([Ii])\s+nvest",
        lambda m: ("I" if m.group(1).isupper() else "i") + "nvest",
        cleaned,
    )
    cleaned = re.sub(r"(?i)\b(?:press\s*release|comunicato\s*stampa)\b\s*[-:]?\s*", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" -|").strip()


def clean_signal_fields(signal: dict) -> dict:
    if not signal:
        return signal
    for key in ("title", "what_changed", "diff_summary", "enriched_summary"):
        val = signal.get(key)
        if isinstance(val, str) and val:
            signal[key] = clean_text(val)
    return signal


def signal_key(signal: dict) -> str:
    source_url = (signal.get("source_url") or "").strip()
    title = (signal.get("title") or "").strip()
    published_at = (signal.get("published_at") or "").strip()
    what_changed = (signal.get("what_changed") or "").strip()
    return f"{source_url}::{title}::{published_at}::{what_changed}"


def ensure_unique_ids(signals: list[dict]) -> tuple[dict[str, str], int]:
    seen_ids: set[str] = set()
    key_to_id: dict[str, str] = {}
    changed = 0

    for s in signals:
        key = signal_key(s)
        base_id = (s.get("id") or "").strip()
        if key in key_to_id:
            new_id = key_to_id[key]
        else:
            if not base_id or base_id in seen_ids:
                suffix = hashlib.blake2s(key.encode(), digest_size=4).hexdigest()
                base = base_id or "signal"
                new_id = f"{base}-{suffix}"
            else:
                new_id = base_id
            if new_id in seen_ids:
                counter = 2
                while f"{new_id}-{counter}" in seen_ids:
                    counter += 1
                new_id = f"{new_id}-{counter}"
            key_to_id[key] = new_id
        seen_ids.add(new_id)
        if s.get("id") != new_id:
            s["id"] = new_id
            changed += 1

    return key_to_id, changed


def main() -> int:
    if not FILTERED.exists():
        print(f"Missing filtered file: {FILTERED}")
        return 1
    if not ENRICHED.exists():
        print(f"Missing enriched file: {ENRICHED}")
        return 1

    enriched = load_json(ENRICHED)
    enriched_at = enriched.get("enriched_at")
    if not enriched_at:
        print("Enriched file is missing enriched_at; run enrichment to completion first.")
        return 1

    enriched_signals = enriched.get("signals", [])
    cleaned_enriched = []
    cleaned_enriched_count = 0
    for s in enriched_signals:
        before = json.dumps({k: s.get(k) for k in ("title", "what_changed", "diff_summary", "enriched_summary")}, sort_keys=True)
        clean_signal_fields(s)
        after = json.dumps({k: s.get(k) for k in ("title", "what_changed", "diff_summary", "enriched_summary")}, sort_keys=True)
        if before != after:
            cleaned_enriched_count += 1
        cleaned_enriched.append(s)

    key_to_id, reassigned_enriched = ensure_unique_ids(cleaned_enriched)

    keep_ids = {s.get("id") for s in cleaned_enriched if s.get("id")}
    # If soft mode was used, still drop llm_keep=false if present
    drop_ids = {s.get("id") for s in cleaned_enriched if s.get("llm_keep") is False and s.get("id")}

    data = load_json(FILTERED)
    filtered_signals = data.get("signals", [])
    before = len(filtered_signals)

    cleaned = []
    reassigned_filtered = 0
    for s in filtered_signals:
        key = signal_key(s)
        sid = s.get("id")
        mapped_id = key_to_id.get(key)
        if mapped_id and sid != mapped_id:
            s["id"] = mapped_id
            sid = mapped_id
            reassigned_filtered += 1
        if sid and sid in drop_ids:
            continue
        if sid and sid in keep_ids:
            clean_signal_fields(s)
            cleaned.append(s)

    removed = before - len(cleaned)

    # Backup original
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = FILTERED.with_suffix(f".json.bak.{ts}")
    shutil.copy2(FILTERED, backup_path)
    backup_enriched = ENRICHED.with_suffix(f".json.bak.{ts}")
    shutil.copy2(ENRICHED, backup_enriched)

    data["signals"] = cleaned
    if "signal_count" in data:
        data["signal_count"] = len(cleaned)
    data["cleanup_at"] = datetime.now(timezone.utc).isoformat()
    data["cleanup_stats"] = {
        "original_count": before,
        "cleaned_count": len(cleaned),
        "removed_count": removed,
        "enriched_at": enriched_at,
        "text_fields_cleaned": cleaned_enriched_count,
        "ids_reassigned_enriched": reassigned_enriched,
        "ids_reassigned_filtered": reassigned_filtered,
    }

    save_json(FILTERED, data)
    enriched["signals"] = cleaned_enriched
    enriched["cleanup_at"] = datetime.now(timezone.utc).isoformat()
    enriched["cleanup_stats"] = {
        "text_fields_cleaned": cleaned_enriched_count,
        "filtered_synced_at": data["cleanup_at"],
    }
    save_json(ENRICHED, enriched)

    print(f"Cleaned signals: {len(cleaned)} (removed {removed})")
    print(f"Backup created: {backup_path}")
    print(f"Backup created: {backup_enriched}")
    print(f"Updated: {FILTERED}")
    print(f"Updated: {ENRICHED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
