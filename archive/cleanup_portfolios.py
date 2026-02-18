#!/usr/bin/env python3
"""
One-time cleanup of portfolio_items.json.
Applies the same quality rules as isValidPortfolioEntry() in data.ts.
Creates a backup before overwriting.
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parent.parent
PORTFOLIOS_PATH = REPO_ROOT / "data" / "derived" / "portfolio_items.json"

NAV_PATTERNS = [
    re.compile(r"^page not found", re.IGNORECASE),
    re.compile(r"^click here", re.IGNORECASE),
    re.compile(r"^powered by", re.IGNORECASE),
    re.compile(r"vai alla", re.IGNORECASE),
    re.compile(r"^stay tuned", re.IGNORECASE),
    re.compile(r"^logout$", re.IGNORECASE),
    re.compile(r"^portfolio stories", re.IGNORECASE),
    re.compile(r"^what we do$", re.IGNORECASE),
    re.compile(r"^about us$", re.IGNORECASE),
    re.compile(r"^contact us$", re.IGNORECASE),
    re.compile(r"^home$", re.IGNORECASE),
    re.compile(r"^menu$", re.IGNORECASE),
    re.compile(r"^search$", re.IGNORECASE),
    re.compile(r"^privacy policy", re.IGNORECASE),
    re.compile(r"^cookie policy", re.IGNORECASE),
    re.compile(r"^infrastrutture:$", re.IGNORECASE),
    re.compile(r"notizie\s*leggi", re.IGNORECASE),
    re.compile(r"publications.*report", re.IGNORECASE),
    re.compile(r"combined\s*shape", re.IGNORECASE),
    re.compile(r"\.pdf$", re.IGNORECASE),
    re.compile(r"^work with us$", re.IGNORECASE),
    re.compile(r"^case stud(?:y|ies)$", re.IGNORECASE),
    re.compile(r"^awards$", re.IGNORECASE),
    re.compile(r"^governance$", re.IGNORECASE),
    re.compile(r"^sustainability$", re.IGNORECASE),
    re.compile(r"^compliance$", re.IGNORECASE),
    re.compile(r"^ombudsman$", re.IGNORECASE),
    re.compile(r"^people$", re.IGNORECASE),
    re.compile(r"^error page", re.IGNORECASE),
    re.compile(r"^cross.border\s+merger", re.IGNORECASE),
    re.compile(r"with\s+clouds?$", re.IGNORECASE),
    re.compile(r"\bmerger\s+on\s+\d", re.IGNORECASE),
]


def is_valid(name: str, fund_slug: str) -> bool:
    trimmed = name.strip()
    if not trimmed or len(trimmed) <= 2:
        return False
    if len(trimmed) > 60:
        return False
    if re.match(r"^Logo\s", trimmed, re.IGNORECASE):
        return False
    # Colon-subtitle: reject if text after colon is longer than 10 chars
    colon_match = re.search(r":\s*(.+)", trimmed)
    if colon_match and len(colon_match.group(1)) > 10:
        return False
    # Reject article-title patterns: gerund + lowercase preposition/article
    if re.match(r"^[A-Z][a-z]+ing\s+(?:on|in|into|with|for|new|big|the|a|an)\s", trimmed, re.IGNORECASE):
        return False
    # Reject Italian investment-category headings
    if re.match(r"^Investimenti\s+in\s", trimmed, re.IGNORECASE):
        return False
    for pattern in NAV_PATTERNS:
        if pattern.search(trimmed):
            return False
    # Reject fund name matches
    fund_name = fund_slug.replace("-", " ").lower()
    name_norm = re.sub(r"[^a-z0-9\s]", "", trimmed.lower()).strip()
    if name_norm == fund_name:
        return False
    fund_core = re.sub(
        r"\b(sgr|capital|partners|investimenti|advisory|management)\b",
        "",
        fund_name,
    ).strip()
    if fund_core and len(fund_core) > 3 and name_norm == fund_core:
        return False
    # Reject partial fund name + generic suffix
    fund_words = fund_name.split()
    if fund_words and len(fund_words[0]) > 3:
        first_word = fund_words[0]
        if name_norm.startswith(first_word) and len(name_norm) > len(first_word):
            rest = name_norm[len(first_word):].strip()
            if re.match(r"^(investment|capital|partners|management|im |group|advisory|sgr|holding|fund)", rest, re.IGNORECASE):
                return False
    return True


def main():
    if not PORTFOLIOS_PATH.exists():
        print(f"File not found: {PORTFOLIOS_PATH}")
        return

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = PORTFOLIOS_PATH.with_suffix(f".backup_{ts}.json")
    shutil.copy2(PORTFOLIOS_PATH, backup_path)
    print(f"Backup saved to: {backup_path}")

    with open(PORTFOLIOS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    portfolios = data.get("fund_portfolios", {})
    total_removed = 0
    total_kept = 0

    for fund_slug, companies in portfolios.items():
        original_count = len(companies)
        filtered = []
        for c in companies:
            name = c.get("name", "")
            if is_valid(name, fund_slug):
                filtered.append(c)
            else:
                total_removed += 1
                print(f"  REMOVED [{fund_slug}]: {name!r}")
        portfolios[fund_slug] = filtered
        total_kept += len(filtered)

    data["fund_portfolios"] = portfolios

    with open(PORTFOLIOS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nDone: removed {total_removed} entries, kept {total_kept}")


if __name__ == "__main__":
    main()
