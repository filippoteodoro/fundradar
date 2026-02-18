#!/usr/bin/env python3
"""
Cleanup active derived artifacts so db.json is the only slug source of truth.

Default mode is dry-run. Use --apply to write changes.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "db.json"
PORTFOLIO_PATH = REPO_ROOT / "data" / "derived" / "portfolio_items.json"
LINKEDIN_PATH = REPO_ROOT / "data" / "derived" / "linkedin" / "fund_linkedin_urls.json"
LINKEDIN_PRIORITIZED_PATH = REPO_ROOT / "data" / "derived" / "linkedin" / "fund_linkedin_urls_prioritized.json"
LINKEDIN_PEOPLE_STATS_PATH = REPO_ROOT / "data" / "derived" / "linkedin" / "fund_people_stats.json"
DEDUP_JSONL_PATH = REPO_ROOT / "data" / "derived" / "gemini_fund_asset_logs" / "fund_checks_deduplicated.jsonl"
FUND_ALIASES_PATH = REPO_ROOT / "data" / "derived" / "fund_aliases.json"

EXTRACTOR_WORK_QUEUE_PATH = REPO_ROOT / "data" / "derived" / "extractor_work_queue.json"
SIGNAL_WORK_QUEUE_PATH = REPO_ROOT / "data" / "derived" / "signal_work_queue.json"
URL_DISCOVERY_QUEUE_PATH = REPO_ROOT / "data" / "derived" / "url_discovery_queue.json"
FUND_EXTRACTION_AUDIT_PATH = REPO_ROOT / "data" / "derived" / "fund_extraction_audit.json"
FUND_PAGE_AUDIT_PATH = REPO_ROOT / "data" / "derived" / "fund_page_audit.json"
FUND_QUALITY_AUDIT_PATH = REPO_ROOT / "data" / "derived" / "fund_quality_audit.json"
SIGNAL_AUDIT_REPORT_PATH = REPO_ROOT / "data" / "derived" / "signal_audit_report.json"
QUALITY_BASELINES_PATH = REPO_ROOT / "data" / "derived" / "quality_baselines.json"
POISON_URLS_PATH = REPO_ROOT / "data" / "derived" / "poison_urls.json"
ASSET_STATUS_AUDIT_PATH = REPO_ROOT / "data" / "derived" / "asset_status_audit.json"
AIFI_REFRESH_QUEUE_PATH = REPO_ROOT / "data" / "derived" / "aifi_refresh_queue.json"
BULK_EXTRACTION_AUDIT_PATH = REPO_ROOT / "data" / "derived" / "bulk_extraction_audit.json"

PROMPT_SLUG_RE = re.compile(r"(?:^|\n)\s*(?:-|\\*)?\s*slug\s*:\s*([a-z0-9][a-z0-9-]*)\b", re.IGNORECASE)
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# High-confidence one-off aliases not yet present in fund_aliases.json
MANUAL_SLUG_ALIASES: dict[str, str] = {
    "hig-capital": "h-i-g-capital",
    "21invest": "21-invest",
    "greenarrow": "green-arrow-capital-sgr",
    "fondoitaliano": "fondo-italiano-d-investimento-sgr",
    "equiter-sgr": "equiter",
}


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_repo_relative_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON: {path}")
    return data


def save_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def backup_file(path: Path) -> Path:
    stamp = now_ts()
    backup = path.with_name(f"{path.name}.slug_cleanup_{stamp}.bak")
    shutil.copy2(path, backup)
    return backup


def extract_prompt_text(request_obj: Any) -> str:
    if not isinstance(request_obj, dict):
        return ""
    contents = request_obj.get("contents")
    if not isinstance(contents, list):
        return ""
    texts: list[str] = []
    for content in contents:
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        elif isinstance(content.get("text"), str):
            texts.append(content["text"])
    return "\n".join(texts)


def infer_slug_from_jsonl_row(row: dict[str, Any]) -> str | None:
    manual_slug = row.get("manual_slug")
    if isinstance(manual_slug, str) and manual_slug.strip():
        return manual_slug.strip().lower()
    prompt = extract_prompt_text(row.get("request"))
    match = PROMPT_SLUG_RE.search(prompt)
    if match:
        return match.group(1).strip().lower()
    return None


def load_alias_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = load_json(path)
    aliases = payload.get("aliases")
    if not isinstance(aliases, dict):
        return {}
    out: dict[str, str] = {}
    for raw, canonical in aliases.items():
        if not isinstance(raw, str) or not isinstance(canonical, str):
            continue
        out[raw.strip().lower()] = canonical.strip().lower()
    return out


def slug_fingerprint(value: str) -> str:
    return NON_ALNUM_RE.sub("", value.lower().strip())


def build_slug_resolver(
    db_slugs: set[str],
    alias_map: dict[str, str],
) -> tuple[Callable[[str | None], str | None], dict[str, int]]:
    alias_to_canonical: dict[str, str] = {}

    for canonical in db_slugs:
        alias_to_canonical[canonical] = canonical

    for alias, canonical in alias_map.items():
        if canonical in db_slugs:
            alias_to_canonical[alias] = canonical

    for alias, canonical in MANUAL_SLUG_ALIASES.items():
        if canonical in db_slugs:
            alias_to_canonical[alias] = canonical

    normalized_to_canonical: dict[str, set[str]] = {}
    for alias, canonical in alias_to_canonical.items():
        fp = slug_fingerprint(alias)
        if not fp:
            continue
        normalized_to_canonical.setdefault(fp, set()).add(canonical)

    for canonical in db_slugs:
        fp = slug_fingerprint(canonical)
        if fp:
            normalized_to_canonical.setdefault(fp, set()).add(canonical)

    def resolve_slug(raw: str | None) -> str | None:
        if not isinstance(raw, str):
            return None
        slug = raw.strip().lower()
        if not slug:
            return None

        direct = alias_to_canonical.get(slug)
        if direct:
            return direct

        # Common legacy artifact: canonical slug with extra -sgr suffix
        if slug.endswith("-sgr"):
            base = slug[: -len("-sgr")]
            if base in db_slugs:
                return base

        fp = slug_fingerprint(slug)
        candidates = normalized_to_canonical.get(fp, set())
        if len(candidates) == 1:
            return next(iter(candidates))
        return None

    return resolve_slug, {
        "db_slugs": len(db_slugs),
        "aliases_loaded": len(alias_map),
        "manual_aliases": len(MANUAL_SLUG_ALIASES),
        "resolver_entries": len(alias_to_canonical),
    }


def maybe_backup_and_write(path: Path, before: dict[str, Any], after: dict[str, Any], *, apply: bool) -> bool:
    changed = before != after
    if apply and changed:
        backup_file(path)
        save_json_atomic(path, after)
    return changed


def normalize_slug_list(
    entries: list[Any],
    slug_field: str,
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
    dedupe_by_slug: bool = False,
) -> tuple[list[Any], dict[str, int]]:
    out: list[Any] = []
    seen: set[str] = set()
    stats = {
        "total": len(entries),
        "kept": 0,
        "removed_non_db": 0,
        "remapped": 0,
        "removed_duplicates": 0,
    }

    for entry in entries:
        if not isinstance(entry, dict):
            out.append(entry)
            stats["kept"] += 1
            continue

        row = dict(entry)
        raw_slug = row.get(slug_field)
        if not isinstance(raw_slug, str) or not raw_slug.strip():
            out.append(row)
            stats["kept"] += 1
            continue

        resolved = resolve_slug(raw_slug)
        if resolved is None:
            stats["removed_non_db"] += 1
            if prune_non_db:
                continue
            out.append(row)
            stats["kept"] += 1
            continue

        if resolved != raw_slug:
            row[slug_field] = resolved
            stats["remapped"] += 1

        if dedupe_by_slug:
            if resolved in seen:
                stats["removed_duplicates"] += 1
                continue
            seen.add(resolved)

        out.append(row)
        stats["kept"] += 1

    return out, stats


def normalize_slug_string_list(
    entries: list[Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[list[str], dict[str, int]]:
    out: list[str] = []
    seen: set[str] = set()
    stats = {
        "total": len(entries),
        "kept": 0,
        "removed_non_db": 0,
        "remapped": 0,
        "removed_duplicates": 0,
    }

    for entry in entries:
        if not isinstance(entry, str):
            continue
        resolved = resolve_slug(entry)
        if resolved is None:
            stats["removed_non_db"] += 1
            if prune_non_db:
                continue
            continue
        if resolved != entry:
            stats["remapped"] += 1
        if resolved in seen:
            stats["removed_duplicates"] += 1
            continue
        seen.add(resolved)
        out.append(resolved)
        stats["kept"] += 1

    return out, stats


def cleanup_linkedin_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    companies = payload.get("companies")
    if not isinstance(companies, list):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "removed_duplicates": 0, "remapped": 0}

    cleaned, stats = normalize_slug_list(
        companies,
        "slug",
        resolve_slug,
        prune_non_db=prune_non_db,
        dedupe_by_slug=True,
    )
    out = dict(payload)
    out["companies"] = cleaned
    if isinstance(payload.get("matched_count"), int):
        out["matched_count"] = len(cleaned)
    return out, stats


def cleanup_portfolio_payload(
    payload: dict[str, Any],
    db_slugs: set[str],
    *,
    prune_non_db: bool,
    ensure_all_db_keys: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    # Deep-copy because we mutate nested maps.
    out = json.loads(json.dumps(payload))

    fund_portfolios = out.get("fund_portfolios")
    if not isinstance(fund_portfolios, dict):
        fund_portfolios = {}
        out["fund_portfolios"] = fund_portfolios

    removed_from_fund_portfolios = 0
    if prune_non_db:
        extra = [k for k in list(fund_portfolios.keys()) if k not in db_slugs]
        for key in extra:
            fund_portfolios.pop(key, None)
        removed_from_fund_portfolios = len(extra)

    added_empty_fund_portfolios = 0
    if ensure_all_db_keys:
        for slug in sorted(db_slugs):
            if slug not in fund_portfolios:
                fund_portfolios[slug] = []
                added_empty_fund_portfolios += 1

    removed_from_other_maps = 0
    for key in ("fund_source_urls", "portfolio_geo_scope", "portfolio_notes"):
        mapping = out.get(key)
        if not isinstance(mapping, dict):
            continue
        if not prune_non_db:
            continue
        extra = [k for k in list(mapping.keys()) if k not in db_slugs]
        for slug in extra:
            mapping.pop(slug, None)
        removed_from_other_maps += len(extra)

    return out, {
        "fund_portfolios_total": len(fund_portfolios),
        "removed_non_db_fund_portfolios": removed_from_fund_portfolios,
        "added_missing_empty_fund_portfolios": added_empty_fund_portfolios,
        "removed_non_db_other_maps": removed_from_other_maps,
    }


def cleanup_fund_people_stats_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    funds = payload.get("funds")
    if not isinstance(funds, dict):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "merged_collisions": 0}

    out = dict(payload)
    cleaned: dict[str, Any] = {}
    stats = {"total": len(funds), "kept": 0, "removed_non_db": 0, "remapped": 0, "merged_collisions": 0}

    for key, value in funds.items():
        resolved = resolve_slug(key if isinstance(key, str) else None)
        if resolved is None and isinstance(value, dict):
            resolved = resolve_slug(value.get("fund_slug"))

        if resolved is None:
            stats["removed_non_db"] += 1
            if prune_non_db:
                continue
            continue

        row = dict(value) if isinstance(value, dict) else {"fund_slug": resolved}
        if row.get("fund_slug") != resolved:
            row["fund_slug"] = resolved
            stats["remapped"] += 1
        if resolved != key:
            stats["remapped"] += 1

        if resolved in cleaned:
            stats["merged_collisions"] += 1
            current = cleaned[resolved]
            current_profiles = current.get("total_profiles", 0) if isinstance(current, dict) else 0
            new_profiles = row.get("total_profiles", 0) if isinstance(row, dict) else 0
            if isinstance(current_profiles, int) and isinstance(new_profiles, int) and new_profiles > current_profiles:
                cleaned[resolved] = row
        else:
            cleaned[resolved] = row
            stats["kept"] += 1

    out["funds"] = cleaned
    out["fund_count"] = len(cleaned)
    return out, stats


def cleanup_fund_page_audit_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    funds = payload.get("funds")
    if not isinstance(funds, list):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "removed_duplicates": 0}

    out = dict(payload)
    cleaned, stats = normalize_slug_list(
        funds,
        "slug",
        resolve_slug,
        prune_non_db=prune_non_db,
        dedupe_by_slug=True,
    )
    out["funds"] = cleaned

    summary = out.get("summary")
    if isinstance(summary, dict):
        s = dict(summary)
        s["total_funds_audited"] = len(cleaned)
        if cleaned:
            s["tier1_count"] = sum(1 for f in cleaned if isinstance(f, dict) and f.get("tier") == 1)
            s["tier2_count"] = sum(1 for f in cleaned if isinstance(f, dict) and f.get("tier") == 2)
            s["tier3_count"] = sum(1 for f in cleaned if isinstance(f, dict) and f.get("tier") == 3)
            s["total_null_status"] = sum(
                int(f.get("null_status_count", 0)) for f in cleaned if isinstance(f, dict) and isinstance(f.get("null_status_count"), int)
            )
            s["total_pem_deals"] = sum(
                int(f.get("pem_deal_count", 0)) for f in cleaned if isinstance(f, dict) and isinstance(f.get("pem_deal_count"), int)
            )
            scores = [f.get("credibility_score") for f in cleaned if isinstance(f, dict) and isinstance(f.get("credibility_score"), (int, float))]
            if scores:
                s["avg_credibility_score"] = round(sum(scores) / len(scores))
                s["funds_below_50_credibility"] = sum(1 for score in scores if score < 50)
            s["total_null_sectors"] = sum(
                int(f.get("null_sector_count", 0)) for f in cleaned if isinstance(f, dict) and isinstance(f.get("null_sector_count"), int)
            )
            s["total_null_descriptions"] = sum(
                int(f.get("null_description_count", 0))
                for f in cleaned
                if isinstance(f, dict) and isinstance(f.get("null_description_count"), int)
            )
        out["summary"] = s

    return out, stats


def cleanup_fund_quality_audit_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    funds = payload.get("funds")
    if not isinstance(funds, list):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "removed_duplicates": 0}

    out = dict(payload)
    cleaned, stats = normalize_slug_list(
        funds,
        "slug",
        resolve_slug,
        prune_non_db=prune_non_db,
        dedupe_by_slug=True,
    )
    out["funds"] = cleaned
    out["total_funds"] = len(cleaned)

    grade_distribution: dict[str, int] = {}
    scores: list[float] = []
    for row in cleaned:
        if not isinstance(row, dict):
            continue
        grade = row.get("grade")
        if isinstance(grade, str):
            grade_distribution[grade] = grade_distribution.get(grade, 0) + 1
        score = row.get("compositeScore")
        if isinstance(score, (int, float)):
            scores.append(float(score))
    if grade_distribution:
        out["grade_distribution"] = grade_distribution
    if scores:
        out["average_score"] = round(sum(scores) / len(scores), 1)
        out["median_score"] = float(median(scores))

    return out, stats


def cleanup_fund_extraction_audit_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    funds = payload.get("funds")
    if not isinstance(funds, dict):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "merged_collisions": 0}

    out = dict(payload)
    cleaned: dict[str, Any] = {}
    stats = {"total": len(funds), "kept": 0, "removed_non_db": 0, "remapped": 0, "merged_collisions": 0}

    for key, value in funds.items():
        resolved = resolve_slug(key if isinstance(key, str) else None)
        if resolved is None and isinstance(value, dict):
            resolved = resolve_slug(value.get("fund_id"))

        if resolved is None:
            stats["removed_non_db"] += 1
            if prune_non_db:
                continue
            continue

        row = dict(value) if isinstance(value, dict) else {}
        if row.get("fund_id") != resolved:
            row["fund_id"] = resolved
            stats["remapped"] += 1
        if resolved != key:
            stats["remapped"] += 1

        if resolved in cleaned:
            stats["merged_collisions"] += 1
            existing = cleaned[resolved]
            existing_score = existing.get("overall_quality", 0) if isinstance(existing, dict) else 0
            new_score = row.get("overall_quality", 0) if isinstance(row, dict) else 0
            if isinstance(existing_score, (int, float)) and isinstance(new_score, (int, float)) and new_score > existing_score:
                cleaned[resolved] = row
        else:
            cleaned[resolved] = row
            stats["kept"] += 1

    out["funds"] = cleaned
    if isinstance(out.get("total_tested"), int):
        out["total_tested"] = len(cleaned)
    if isinstance(out.get("tested_funds"), int):
        out["tested_funds"] = len(cleaned)
    if isinstance(out.get("total_funds"), int):
        out["total_funds"] = len(cleaned)
    return out, stats


def cleanup_quality_baselines_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    baselines = payload.get("baselines")
    if not isinstance(baselines, dict):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "merged_collisions": 0}

    out = dict(payload)
    cleaned: dict[str, Any] = {}
    stats = {"total": len(baselines), "kept": 0, "removed_non_db": 0, "remapped": 0, "merged_collisions": 0}

    for key, value in baselines.items():
        if not isinstance(key, str):
            continue
        slug_part, sep, suffix = key.partition(":")
        resolved = resolve_slug(slug_part)
        if resolved is None and isinstance(value, dict):
            resolved = resolve_slug(value.get("fund_slug"))
        if resolved is None:
            stats["removed_non_db"] += 1
            if prune_non_db:
                continue
            continue

        new_key = f"{resolved}:{suffix}" if sep else resolved
        row = dict(value) if isinstance(value, dict) else {}
        if row.get("fund_slug") != resolved:
            row["fund_slug"] = resolved
            stats["remapped"] += 1
        if new_key != key:
            stats["remapped"] += 1

        if new_key in cleaned:
            stats["merged_collisions"] += 1
            existing = cleaned[new_key]
            existing_ts = existing.get("last_successful", "") if isinstance(existing, dict) else ""
            new_ts = row.get("last_successful", "") if isinstance(row, dict) else ""
            if isinstance(existing_ts, str) and isinstance(new_ts, str) and new_ts > existing_ts:
                cleaned[new_key] = row
        else:
            cleaned[new_key] = row
            stats["kept"] += 1

    out["baselines"] = cleaned
    return out, stats


def cleanup_queue_payload(
    payload: dict[str, Any],
    *,
    slug_field: str,
    resolve_slug: Callable[[str | None], str | None],
    prune_non_db: bool,
    summary_total_key: str | None = None,
    summary_count_keys: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    out = dict(payload)
    per_list: dict[str, Any] = {}

    list_keys = [
        key
        for key, value in payload.items()
        if isinstance(value, list) and any(isinstance(item, dict) and slug_field in item for item in value)
    ]

    for key in list_keys:
        cleaned, stats = normalize_slug_list(
            payload.get(key, []),
            slug_field,
            resolve_slug,
            prune_non_db=prune_non_db,
            dedupe_by_slug=True,
        )
        out[key] = cleaned
        per_list[key] = stats

    summary = out.get("summary")
    if isinstance(summary, dict):
        s = dict(summary)
        if summary_count_keys:
            for key in summary_count_keys:
                if key in out and isinstance(out[key], list):
                    s[key] = len(out[key])
        if summary_total_key and summary_count_keys:
            s[summary_total_key] = sum(int(s.get(k, 0)) for k in summary_count_keys)
        out["summary"] = s

    totals = {
        "lists_checked": len(list_keys),
        "removed_non_db": sum(int(per_list[k].get("removed_non_db", 0)) for k in per_list),
        "remapped": sum(int(per_list[k].get("remapped", 0)) for k in per_list),
        "removed_duplicates": sum(int(per_list[k].get("removed_duplicates", 0)) for k in per_list),
    }
    return out, {"totals": totals, "by_list": per_list}


def cleanup_poison_urls_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    poison_urls = payload.get("poison_urls")
    if not isinstance(poison_urls, list):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "removed_duplicates": 0}

    out = dict(payload)
    cleaned, stats = normalize_slug_list(
        poison_urls,
        "fund_slug",
        resolve_slug,
        prune_non_db=prune_non_db,
        dedupe_by_slug=True,
    )
    out["poison_urls"] = cleaned
    if isinstance(out.get("summary"), dict):
        summary = dict(out["summary"])
        summary["poison_urls_found"] = len(cleaned)
        out["summary"] = summary
    return out, stats


def cleanup_asset_status_audit_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    queue = payload.get("queue")
    if not isinstance(queue, list):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "removed_duplicates": 0}

    out = dict(payload)
    cleaned_queue, stats = normalize_slug_list(
        queue,
        "fund_slug",
        resolve_slug,
        prune_non_db=prune_non_db,
        dedupe_by_slug=False,
    )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in cleaned_queue:
        if not isinstance(row, dict):
            continue
        slug = row.get("fund_slug")
        if not isinstance(slug, str) or not slug:
            continue
        grouped.setdefault(slug, []).append(row)

    funds_map: dict[str, dict[str, Any]] = {}
    for slug, items in grouped.items():
        funds_map[slug] = {
            "asset_count": len(items),
            "queue_count": len(items),
            "queue": items,
        }

    out["queue"] = cleaned_queue
    out["funds"] = funds_map
    out["fund_count"] = len(funds_map)
    out["asset_count"] = len(cleaned_queue)
    return out, stats


def cleanup_aifi_refresh_queue_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "removed_duplicates": 0}

    out = dict(payload)
    cleaned, stats = normalize_slug_list(
        entries,
        "fund_slug",
        resolve_slug,
        prune_non_db=prune_non_db,
        dedupe_by_slug=True,
    )
    out["entries"] = cleaned
    out["entry_count"] = len(cleaned)
    out["fund_count"] = len({row.get("fund_slug") for row in cleaned if isinstance(row, dict) and isinstance(row.get("fund_slug"), str)})
    return out, stats


def cleanup_bulk_extraction_audit_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    results = payload.get("results")
    if not isinstance(results, list):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "removed_duplicates": 0}

    out = dict(payload)
    cleaned, stats = normalize_slug_list(
        results,
        "fund_id",
        resolve_slug,
        prune_non_db=prune_non_db,
        dedupe_by_slug=True,
    )
    out["results"] = cleaned
    out["tested_funds"] = len(cleaned)
    out["total_funds"] = len(cleaned)
    return out, stats


def _cleanup_signal_report_dict_list(
    payload: dict[str, Any],
    key: str,
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, int]]:
    items = payload.get(key)
    if not isinstance(items, list):
        return payload, {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "removed_duplicates": 0}
    out = dict(payload)
    cleaned, stats = normalize_slug_list(
        items,
        "slug",
        resolve_slug,
        prune_non_db=prune_non_db,
        dedupe_by_slug=True,
    )
    out[key] = cleaned
    return out, stats


def cleanup_signal_audit_report_payload(
    payload: dict[str, Any],
    resolve_slug: Callable[[str | None], str | None],
    *,
    prune_non_db: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    out = dict(payload)
    stats: dict[str, Any] = {}

    for key in ("all_funds_low_quality", "all_funds_zero_signals"):
        out, s = _cleanup_signal_report_dict_list(out, key, resolve_slug, prune_non_db=prune_non_db)
        stats[key] = s

    funds_working_well = out.get("funds_working_well")
    if isinstance(funds_working_well, list):
        cleaned_strings, s = normalize_slug_string_list(
            funds_working_well,
            resolve_slug,
            prune_non_db=prune_non_db,
        )
        out["funds_working_well"] = cleaned_strings
        stats["funds_working_well"] = s
    else:
        stats["funds_working_well"] = {"total": 0, "kept": 0, "removed_non_db": 0, "remapped": 0, "removed_duplicates": 0}

    priority_issues = out.get("priority_issues")
    if isinstance(priority_issues, dict):
        cleaned_priority = dict(priority_issues)
        for key in ("italian_funds_zero_signals", "funds_with_extractor_but_zero_signals", "high_pem_deals_zero_signals"):
            if isinstance(cleaned_priority.get(key), list):
                cleaned_list, s = normalize_slug_list(
                    cleaned_priority[key],
                    "slug",
                    resolve_slug,
                    prune_non_db=prune_non_db,
                    dedupe_by_slug=True,
                )
                cleaned_priority[key] = cleaned_list
                stats[f"priority_issues.{key}"] = s
        out["priority_issues"] = cleaned_priority

    summary = out.get("summary")
    if isinstance(summary, dict):
        s = dict(summary)
        total_funds = len(set(out.get("funds_working_well", []))) + len(out.get("all_funds_zero_signals", []))
        if total_funds > 0:
            s["total_funds"] = total_funds
            s["funds_with_zero_signals"] = len(out.get("all_funds_zero_signals", []))
            s["funds_with_low_quality_signals"] = len(out.get("all_funds_low_quality", []))
            covered = total_funds - int(s["funds_with_zero_signals"])
            s["coverage_pct"] = round((covered / total_funds) * 100, 1)
        out["summary"] = s

    return out, stats


def cleanup_dedup_jsonl(
    path: Path,
    resolve_slug: Callable[[str | None], str | None],
    *,
    apply: bool,
    prune_non_db: bool,
) -> dict[str, int]:
    total = 0
    kept = 0
    removed_non_db = 0
    parse_errors = 0
    rows_out: list[str] = []

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            total += 1
            try:
                row = json.loads(line)
            except Exception:
                parse_errors += 1
                rows_out.append(line)
                kept += 1
                continue

            if isinstance(row, dict):
                slug = infer_slug_from_jsonl_row(row)
                if slug and resolve_slug(slug) is None:
                    removed_non_db += 1
                    if prune_non_db:
                        continue

            rows_out.append(line)
            kept += 1

    if apply:
        backup_file(path)
        with open(path, "w", encoding="utf-8") as f:
            for line in rows_out:
                f.write(line)
                f.write("\n")

    return {
        "total_rows": total,
        "kept_rows": kept,
        "removed_non_db_rows": removed_non_db,
        "parse_error_rows_kept": parse_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup derived artifacts using db.json slugs as source of truth.")
    parser.add_argument("--db-path", type=str, default=str(DB_PATH.relative_to(REPO_ROOT)))
    parser.add_argument("--portfolio-path", type=str, default=str(PORTFOLIO_PATH.relative_to(REPO_ROOT)))
    parser.add_argument("--linkedin-path", type=str, default=str(LINKEDIN_PATH.relative_to(REPO_ROOT)))
    parser.add_argument(
        "--linkedin-prioritized-path",
        type=str,
        default=str(LINKEDIN_PRIORITIZED_PATH.relative_to(REPO_ROOT)),
    )
    parser.add_argument("--dedup-jsonl-path", type=str, default=str(DEDUP_JSONL_PATH.relative_to(REPO_ROOT)))
    parser.add_argument(
        "--prune-non-db",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Remove keys/rows whose slug is not in db.json",
    )
    parser.add_argument(
        "--ensure-all-db-portfolio-keys",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Ensure fund_portfolios has one key per DB slug (empty list allowed)",
    )
    parser.add_argument("--apply", action="store_true", help="Write cleaned files (default dry-run)")
    args = parser.parse_args()

    db_path = resolve_repo_relative_path(args.db_path)
    portfolio_path = resolve_repo_relative_path(args.portfolio_path)
    linkedin_path = resolve_repo_relative_path(args.linkedin_path)
    linkedin_prioritized_path = resolve_repo_relative_path(args.linkedin_prioritized_path)
    dedup_jsonl_path = resolve_repo_relative_path(args.dedup_jsonl_path)

    if not db_path.exists():
        print(f"Error: DB file not found: {db_path}")
        return 2

    db = load_json(db_path)
    funds = db.get("funds")
    if not isinstance(funds, list):
        print("Error: data/db.json missing funds[]")
        return 2
    db_slugs = {
        f.get("slug")
        for f in funds
        if isinstance(f, dict) and isinstance(f.get("slug"), str) and f.get("slug").strip()
    }

    alias_map = load_alias_map(FUND_ALIASES_PATH)
    resolve_slug, resolver_meta = build_slug_resolver(db_slugs, alias_map)

    report: dict[str, Any] = {
        "apply": bool(args.apply),
        "db_slug_count": len(db_slugs),
        "prune_non_db": args.prune_non_db,
        "ensure_all_db_portfolio_keys": args.ensure_all_db_portfolio_keys,
        "resolver": resolver_meta,
        "results": {},
    }

    def run_cleanup(
        label: str,
        path: Path,
        cleaner: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any] | dict[str, int]]],
    ) -> None:
        if not path.exists():
            report["results"][label] = {"missing_file": str(path)}
            return
        payload = load_json(path)
        cleaned, stats = cleaner(payload)
        changed = maybe_backup_and_write(path, payload, cleaned, apply=args.apply)
        report["results"][label] = {"changed": changed, **stats}

    # LinkedIn URL files
    for label, path in (
        ("linkedin.fund_linkedin_urls", linkedin_path),
        ("linkedin.fund_linkedin_urls_prioritized", linkedin_prioritized_path),
    ):
        run_cleanup(
            label,
            path,
            lambda payload, _path=path: cleanup_linkedin_payload(
                payload,
                resolve_slug,
                prune_non_db=args.prune_non_db,
            ),
        )

    run_cleanup(
        "linkedin.fund_people_stats",
        LINKEDIN_PEOPLE_STATS_PATH,
        lambda payload: cleanup_fund_people_stats_payload(
            payload,
            resolve_slug,
            prune_non_db=args.prune_non_db,
        ),
    )

    # portfolio_items
    run_cleanup(
        "portfolio_items",
        portfolio_path,
        lambda payload: cleanup_portfolio_payload(
            payload,
            db_slugs,
            prune_non_db=args.prune_non_db,
            ensure_all_db_keys=args.ensure_all_db_portfolio_keys,
        ),
    )

    # Work queues + audits
    run_cleanup(
        "extractor_work_queue",
        EXTRACTOR_WORK_QUEUE_PATH,
        lambda payload: cleanup_queue_payload(
            payload,
            slug_field="fund_id",
            resolve_slug=resolve_slug,
            prune_non_db=args.prune_non_db,
            summary_total_key="total_funds",
            summary_count_keys=["working", "needs_fix", "needs_new", "no_urls"],
        ),
    )
    run_cleanup(
        "signal_work_queue",
        SIGNAL_WORK_QUEUE_PATH,
        lambda payload: cleanup_queue_payload(
            payload,
            slug_field="slug",
            resolve_slug=resolve_slug,
            prune_non_db=args.prune_non_db,
            summary_total_key="total_funds",
            summary_count_keys=["needs_news_extractor", "has_news_no_signals", "needs_new_extractor", "has_signals", "no_website"],
        ),
    )
    run_cleanup(
        "url_discovery_queue",
        URL_DISCOVERY_QUEUE_PATH,
        lambda payload: cleanup_queue_payload(
            payload,
            slug_field="fund_id",
            resolve_slug=resolve_slug,
            prune_non_db=args.prune_non_db,
            summary_total_key="total_actionable",
            summary_count_keys=["ready_for_extraction", "needs_portfolio_discovery", "needs_headless", "bot_protected", "site_errors", "site_gone"],
        ),
    )
    run_cleanup(
        "fund_extraction_audit",
        FUND_EXTRACTION_AUDIT_PATH,
        lambda payload: cleanup_fund_extraction_audit_payload(
            payload,
            resolve_slug,
            prune_non_db=args.prune_non_db,
        ),
    )
    run_cleanup(
        "bulk_extraction_audit",
        BULK_EXTRACTION_AUDIT_PATH,
        lambda payload: cleanup_bulk_extraction_audit_payload(
            payload,
            resolve_slug,
            prune_non_db=args.prune_non_db,
        ),
    )
    run_cleanup(
        "fund_page_audit",
        FUND_PAGE_AUDIT_PATH,
        lambda payload: cleanup_fund_page_audit_payload(
            payload,
            resolve_slug,
            prune_non_db=args.prune_non_db,
        ),
    )
    run_cleanup(
        "fund_quality_audit",
        FUND_QUALITY_AUDIT_PATH,
        lambda payload: cleanup_fund_quality_audit_payload(
            payload,
            resolve_slug,
            prune_non_db=args.prune_non_db,
        ),
    )
    run_cleanup(
        "signal_audit_report",
        SIGNAL_AUDIT_REPORT_PATH,
        lambda payload: cleanup_signal_audit_report_payload(
            payload,
            resolve_slug,
            prune_non_db=args.prune_non_db,
        ),
    )
    run_cleanup(
        "quality_baselines",
        QUALITY_BASELINES_PATH,
        lambda payload: cleanup_quality_baselines_payload(
            payload,
            resolve_slug,
            prune_non_db=args.prune_non_db,
        ),
    )
    run_cleanup(
        "poison_urls",
        POISON_URLS_PATH,
        lambda payload: cleanup_poison_urls_payload(
            payload,
            resolve_slug,
            prune_non_db=args.prune_non_db,
        ),
    )
    run_cleanup(
        "asset_status_audit",
        ASSET_STATUS_AUDIT_PATH,
        lambda payload: cleanup_asset_status_audit_payload(
            payload,
            resolve_slug,
            prune_non_db=args.prune_non_db,
        ),
    )
    run_cleanup(
        "aifi_refresh_queue",
        AIFI_REFRESH_QUEUE_PATH,
        lambda payload: cleanup_aifi_refresh_queue_payload(
            payload,
            resolve_slug,
            prune_non_db=args.prune_non_db,
        ),
    )

    # canonical dedup logs
    if dedup_jsonl_path.exists():
        report["results"]["gemini.logs.dedup_jsonl"] = cleanup_dedup_jsonl(
            dedup_jsonl_path,
            resolve_slug,
            apply=args.apply and args.prune_non_db,
            prune_non_db=args.prune_non_db,
        )
    else:
        report["results"]["gemini.logs.dedup_jsonl"] = {"missing_file": str(dedup_jsonl_path)}

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
