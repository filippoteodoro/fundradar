#!/usr/bin/env python3
"""Deterministic merge gate for newly added/changed funds.

This script is CI-safe (no network calls):
- discovers affected fund slugs from git diff + explicit --slugs override
- enforces freshness of tracked quality artifacts in the same diff
- runs verify_new_fund_completion.py on affected slugs
- validates tracked reports contain passing rows for affected slugs
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "scripts" / "verify_new_fund_completion.py"

DB_REL = Path("data/db.json")
ALIASES_REL = Path("data/derived/fund_aliases.json")
REPORT_REL = Path("data/derived/new_fund_completion_report.json")
ASSET_AUDIT_REL = Path("data/derived/gemini_fund_asset_audit.json")
EXTRACTOR_DIR_PREFIX = "apps/worker/fundradar_worker/strategies/extractors/"

# ALIASES_REL is intentionally NOT in TRIGGER_RELATIVE_PATHS.
# Changes to fund_aliases.json that affect active funds are detected via
# _detect_alias_target_changes() producing non-empty candidate slugs.
# Changes to the invalid_slugs list (exclusions) produce no candidates and
# should not trigger the gate — including them here caused false positives.
TRIGGER_RELATIVE_PATHS = {str(DB_REL)}
REQUIRED_REFRESH_ARTIFACTS = {str(REPORT_REL), str(ASSET_AUDIT_REL)}
EXTRACTOR_PATH_RE = re.compile(
    r"^apps/worker/fundradar_worker/strategies/extractors/(?P<module>[a-z0-9_]+)\.py$"
)
DOMAIN_RE = re.compile(r'^\s*DOMAIN\s*=\s*["\']([^"\']+)["\']\s*$', re.MULTILINE)


def _run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_json_from_git_ref(ref: str, relative_path: Path) -> dict[str, Any] | None:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{relative_path.as_posix()}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_domain(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    host = (parsed.netloc or parsed.path or "").strip().lower()
    host = host.split("/")[0]
    if host.startswith("www."):
        return host[4:]
    return host


def _parse_changed_files(base_ref: str, head_ref: str) -> list[str]:
    candidates: list[list[str]] = []
    if base_ref and head_ref:
        candidates.append(["diff", "--name-only", base_ref, head_ref])
    if head_ref:
        candidates.append(["diff", "--name-only", f"{head_ref}~1", head_ref])
    candidates.append(["diff", "--name-only"])

    for args in candidates:
        try:
            out = _run_git(args)
            return [line.strip() for line in out.splitlines() if line.strip()]
        except RuntimeError:
            continue
    return []


def _slugify_module(module_name: str) -> str:
    return module_name.replace("_", "-")


def _build_domain_to_slug_map(db_funds: list[dict[str, Any]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for fund in db_funds:
        slug = str(fund.get("slug") or "").strip()
        if not slug:
            continue
        domain = _normalize_domain(str(fund.get("website") or ""))
        if not domain:
            continue
        out.setdefault(domain, set()).add(slug)
    return out


def _extract_domain_from_file(path: Path) -> str | None:
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    match = DOMAIN_RE.search(content)
    if not match:
        return None
    return _normalize_domain(match.group(1))


def _detect_db_changed_slugs(
    base_ref: str, db_now: dict[str, Any]
) -> tuple[set[str], set[str]]:
    """Return (new_slugs, changed_slugs).

    new_slugs: funds added for the first time (no prior db entry).
    changed_slugs: funds whose db entry changed but already existed.
    Both sets together form the full candidate set for the gate.
    """
    db_before = _load_json_from_git_ref(base_ref, DB_REL) if base_ref else None
    if not db_before:
        return set(), set()

    before_funds = db_before.get("funds")
    now_funds = db_now.get("funds")
    if not isinstance(before_funds, list) or not isinstance(now_funds, list):
        return set(), set()

    before_by_slug = {
        str(f.get("slug")): f
        for f in before_funds
        if isinstance(f, dict) and f.get("slug")
    }
    now_by_slug = {
        str(f.get("slug")): f
        for f in now_funds
        if isinstance(f, dict) and f.get("slug")
    }

    new_slugs: set[str] = set()
    changed_slugs: set[str] = set()
    for slug, now_row in now_by_slug.items():
        before_row = before_by_slug.get(slug)
        if before_row is None:
            new_slugs.add(slug)
        elif json.dumps(before_row, sort_keys=True, ensure_ascii=False) != json.dumps(
            now_row, sort_keys=True, ensure_ascii=False
        ):
            changed_slugs.add(slug)
    return new_slugs, changed_slugs


def _detect_alias_target_changes(base_ref: str) -> set[str]:
    before = _load_json_from_git_ref(base_ref, ALIASES_REL) if base_ref else None
    after = _load_json(ROOT / ALIASES_REL)
    if not before:
        return set()

    before_aliases = before.get("aliases") if isinstance(before.get("aliases"), dict) else {}
    after_aliases = after.get("aliases") if isinstance(after.get("aliases"), dict) else {}
    before_reverse = before.get("reverse_lookup") if isinstance(before.get("reverse_lookup"), dict) else {}
    after_reverse = after.get("reverse_lookup") if isinstance(after.get("reverse_lookup"), dict) else {}

    changed_targets: set[str] = set()

    all_alias_keys = set(before_aliases) | set(after_aliases)
    for alias_key in all_alias_keys:
        old_target = before_aliases.get(alias_key)
        new_target = after_aliases.get(alias_key)
        if old_target != new_target:
            if isinstance(old_target, str) and old_target:
                changed_targets.add(old_target)
            if isinstance(new_target, str) and new_target:
                changed_targets.add(new_target)

    all_reverse_keys = set(before_reverse) | set(after_reverse)
    for canonical_slug in all_reverse_keys:
        old_list = before_reverse.get(canonical_slug) if isinstance(before_reverse.get(canonical_slug), list) else []
        new_list = after_reverse.get(canonical_slug) if isinstance(after_reverse.get(canonical_slug), list) else []
        if sorted(str(x) for x in old_list) != sorted(str(x) for x in new_list):
            if isinstance(canonical_slug, str) and canonical_slug:
                changed_targets.add(canonical_slug)

    return changed_targets


def _detect_extractor_slugs(changed_files: list[str], db_funds: list[dict[str, Any]]) -> set[str]:
    db_slugs = {
        str(f.get("slug"))
        for f in db_funds
        if isinstance(f, dict) and isinstance(f.get("slug"), str) and f.get("slug")
    }
    domain_map = _build_domain_to_slug_map(db_funds)

    slugs: set[str] = set()
    for relative_path in changed_files:
        match = EXTRACTOR_PATH_RE.match(relative_path)
        if not match:
            continue
        module_name = match.group("module")
        guessed_slug = _slugify_module(module_name)
        if guessed_slug in db_slugs:
            slugs.add(guessed_slug)
            continue

        full_path = ROOT / relative_path
        domain = _extract_domain_from_file(full_path)
        if not domain:
            continue
        matched = domain_map.get(domain, set())
        slugs.update(matched)
    return slugs


def _parse_slugs(raw: str) -> set[str]:
    return {token.strip() for token in raw.split(",") if token.strip()}


def _collect_candidate_slugs(
    *,
    base_ref: str,
    changed_files: list[str],
    db_now: dict[str, Any],
    explicit_slugs: set[str],
) -> tuple[set[str], set[str]]:
    """Return (candidate_slugs, established_slugs).

    established_slugs are funds already present in db.json before this change set.
    These skip data-completeness checks (portfolio enrichment, signal completeness)
    that are only required when a fund is first added. Core metadata and Gemini
    audit checks still apply to all candidates.
    """
    if explicit_slugs:
        # Explicit overrides are always treated as new (full checks apply).
        return explicit_slugs, set()

    db_funds = db_now.get("funds") if isinstance(db_now.get("funds"), list) else []
    new_db_slugs, changed_db_slugs = _detect_db_changed_slugs(base_ref, db_now)
    alias_slugs = _detect_alias_target_changes(base_ref)
    extractor_slugs = _detect_extractor_slugs(changed_files, db_funds)

    # Alias/extractor-derived slugs are existing funds being reconfigured, not newly added.
    established_slugs = changed_db_slugs | alias_slugs | extractor_slugs
    all_candidates = new_db_slugs | established_slugs
    return all_candidates, established_slugs


def _is_trigger_change(relative_path: str) -> bool:
    if relative_path in TRIGGER_RELATIVE_PATHS:
        return True
    return relative_path.startswith(EXTRACTOR_DIR_PREFIX)


def _run_verify(
    slugs: set[str],
    top_n: int,
    min_signals: int,
    established_slugs: set[str] | None = None,
) -> tuple[int, str, str, dict[str, Any]]:
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tmp:
        report_path = Path(tmp.name)

    cmd = [
        sys.executable,
        str(VERIFY_SCRIPT),
        "--slugs",
        ",".join(sorted(slugs)),
        "--top-n",
        str(top_n),
        "--min-signals",
        str(min_signals),
        "--output",
        str(report_path),
    ]
    if established_slugs:
        cmd.extend(["--established-slugs", ",".join(sorted(established_slugs))])
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        generated: dict[str, Any] = {}
        try:
            generated = _load_json(report_path)
        except Exception:
            generated = {}
        return proc.returncode, proc.stdout, proc.stderr, generated
    finally:
        report_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic gate for new/changed fund completeness")
    parser.add_argument("--slugs", type=str, default="", help="Optional comma-separated slug override")
    parser.add_argument("--base-ref", type=str, default="", help="Git base ref/SHA for diff detection")
    parser.add_argument("--head-ref", type=str, default="HEAD", help="Git head ref/SHA for diff detection")
    parser.add_argument("--top-n", type=int, default=25, help="Forwarded to verify_new_fund_completion")
    parser.add_argument("--min-signals", type=int, default=2, help="Forwarded to verify_new_fund_completion")
    parser.add_argument(
        "--skip-artifact-freshness",
        action="store_true",
        help="Skip requirement that tracked report + asset audit are updated in same diff",
    )
    args = parser.parse_args()

    changed_files = _parse_changed_files(args.base_ref.strip(), args.head_ref.strip())
    changed_set = set(changed_files)
    trigger_changed = any(_is_trigger_change(path) for path in changed_files)
    relevant_changed = trigger_changed or any(path in REQUIRED_REFRESH_ARTIFACTS for path in changed_files)

    db_now = _load_json(ROOT / DB_REL)
    explicit_slugs = _parse_slugs(args.slugs)
    candidate_slugs, established_slugs = _collect_candidate_slugs(
        base_ref=args.base_ref.strip(),
        changed_files=changed_files,
        db_now=db_now,
        explicit_slugs=explicit_slugs,
    )

    db_slugs = {
        str(f.get("slug"))
        for f in db_now.get("funds", [])
        if isinstance(f, dict) and isinstance(f.get("slug"), str) and f.get("slug")
    }
    candidate_slugs = {slug for slug in candidate_slugs if slug in db_slugs}
    established_slugs = {slug for slug in established_slugs if slug in db_slugs}

    if not candidate_slugs:
        if trigger_changed:
            print(
                "New-fund gate error: triggering files changed but no candidate slugs were detected. "
                "Pass --slugs explicitly.",
                file=sys.stderr,
            )
            return 1
        if relevant_changed:
            print("No fund-triggering changes detected; skipping new-fund gate.")
            return 0
        print("No relevant fund-quality changes detected; skipping new-fund gate.")
        return 0

    new_slugs = candidate_slugs - established_slugs
    print(f"Candidate slugs: {', '.join(sorted(candidate_slugs))}")
    if new_slugs:
        print(f"  New (strict checks): {', '.join(sorted(new_slugs))}")
    if established_slugs & candidate_slugs:
        print(f"  Established (relaxed checks): {', '.join(sorted(established_slugs & candidate_slugs))}")

    # Freshness check only applies when genuinely new funds are in the diff.
    # Established funds (routine db.json/extractor updates) don't require the
    # audit artifacts to be re-committed — those files are gitignored and can
    # never appear in the diff for non-new-fund changes.
    if not args.skip_artifact_freshness and new_slugs:
        missing_refresh = sorted(REQUIRED_REFRESH_ARTIFACTS - changed_set)
        if missing_refresh:
            print(
                "New-fund gate failed: quality artifacts are stale for this change set. "
                f"Missing updated files in diff: {', '.join(missing_refresh)}",
                file=sys.stderr,
            )
            return 1

    returncode, stdout, stderr, generated_report = _run_verify(
        candidate_slugs,
        top_n=args.top_n,
        min_signals=args.min_signals,
        established_slugs=established_slugs & candidate_slugs,
    )
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    if returncode != 0:
        print("New-fund gate failed: verify_new_fund_completion returned non-zero.", file=sys.stderr)
        return returncode

    generated_rows = generated_report.get("funds") if isinstance(generated_report.get("funds"), list) else []
    generated_by_slug = {
        str(row.get("slug")): row
        for row in generated_rows
        if isinstance(row, dict) and row.get("slug")
    }
    missing_generated = sorted(candidate_slugs - set(generated_by_slug))
    if missing_generated:
        print(
            "New-fund gate failed: generated completion report is missing rows for slugs: "
            f"{', '.join(missing_generated)}",
            file=sys.stderr,
        )
        return 1

    # Tracked report and audit file are gitignored — only check them when new
    # funds are in the diff. Established-only changesets never have these files
    # on CI; the generated (temp) report check above is sufficient for them.
    if new_slugs:
        report_now = _load_json(ROOT / REPORT_REL)
        report_rows = report_now.get("funds") if isinstance(report_now.get("funds"), list) else []
        report_by_slug = {
            str(row.get("slug")): row
            for row in report_rows
            if isinstance(row, dict) and row.get("slug")
        }
        missing_tracked_rows = sorted(candidate_slugs - set(report_by_slug))
        if missing_tracked_rows:
            print(
                "New-fund gate failed: tracked completion report missing slugs: "
                f"{', '.join(missing_tracked_rows)}",
                file=sys.stderr,
            )
            return 1

        tracked_failed = sorted(
            slug
            for slug in candidate_slugs
            if str(report_by_slug.get(slug, {}).get("status") or "").lower() != "passed"
        )
        if tracked_failed:
            print(
                "New-fund gate failed: tracked completion report has non-passing slugs: "
                f"{', '.join(tracked_failed)}",
                file=sys.stderr,
            )
            return 1

    # Audit file is gitignored — only check it when new funds are in the diff.
    if new_slugs:
        audit_now = _load_json(ROOT / ASSET_AUDIT_REL)
        audit_rows = audit_now.get("funds") if isinstance(audit_now.get("funds"), list) else []
        audit_slugs = {
            str(row.get("slug"))
            for row in audit_rows
            if isinstance(row, dict) and isinstance(row.get("slug"), str) and row.get("slug")
        }
        missing_audit = sorted(new_slugs - audit_slugs)
        if missing_audit:
            print(
                "New-fund gate failed: tracked Gemini asset audit is missing slugs: "
                f"{', '.join(missing_audit)}",
                file=sys.stderr,
            )
            return 1

    print("New-fund gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
