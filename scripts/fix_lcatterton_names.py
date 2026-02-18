#!/usr/bin/env python3
"""One-time script to fix L Catterton slug-derived portfolio names.

Fetches proper company names from L Catterton detail pages and updates
portfolio_items.json. Uses atomic write (temp file + rename).
"""
import json
import re
import time
import urllib.request
import os
import tempfile

PORTFOLIO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "derived", "portfolio_items.json",
)
BASE_URL = "https://www.lcatterton.com"
DELAY = 0.2  # seconds between requests


def fetch_proper_name(slug: str) -> str | None:
    """Fetch proper company name from L Catterton detail page."""
    url = f"{BASE_URL}/Investments-{slug}.html"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="replace")

        # Extract from <title basetitle="L Catterton">PROPER NAME</title>
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
        if m:
            name = m.group(1).strip()
            # Reject generic / empty titles
            bad = {"", "investments", "l catterton", "lcatterton", "l catterton investments"}
            if name.lower() not in bad and len(name) > 0:
                return name

        # Fallback: <div class="title">PROPER NAME</div>
        m = re.search(r'<div\s+class="title"[^>]*>(.*?)</div>', html, re.DOTALL)
        if m:
            name = m.group(1).strip()
            if name and len(name) > 0:
                return name

    except Exception:
        return None
    return None


def is_slug_derived(name: str) -> bool:
    """Return True if the name looks like a raw slug (no spaces)."""
    return " " not in name and len(name) > 0


def is_better_name(new_name: str, old_name: str) -> bool:
    """Return True if new_name is an improvement over old_name."""
    if not new_name:
        return False
    # Don't overwrite with generic L Catterton titles
    if new_name.lower() in ("l catterton", "lcatterton", "investments"):
        return False
    # Don't overwrite if identical (case-insensitive)
    if new_name.lower() == old_name.lower():
        return False
    # New name should either have spaces, punctuation, or different casing
    return True


def main():
    with open(PORTFOLIO_PATH) as f:
        data = json.load(f)

    items = data.get("fund_portfolios", {}).get("l-catterton", [])
    print(f"Total L Catterton items: {len(items)}")

    # Identify slug-derived names (no spaces)
    to_fix = []
    for i, item in enumerate(items):
        name = item.get("name", "")
        if is_slug_derived(name):
            to_fix.append((i, name))

    print(f"Slug-derived names to fix: {len(to_fix)}")
    print()

    fixed = 0
    failed = 0
    unchanged = 0
    changes = []
    failures = []

    for idx, (i, old_name) in enumerate(to_fix):
        proper_name = fetch_proper_name(old_name)

        if proper_name and is_better_name(proper_name, old_name):
            items[i]["name"] = proper_name
            # Also update detail_page_url while we're at it
            items[i]["detail_page_url"] = f"{BASE_URL}/Investments-{old_name}.html"
            changes.append((old_name, proper_name))
            fixed += 1
        elif proper_name and not is_better_name(proper_name, old_name):
            unchanged += 1
        else:
            failed += 1
            failures.append(old_name)

        if (idx + 1) % 50 == 0:
            print(f"  Progress: {idx + 1}/{len(to_fix)} (fixed={fixed}, failed={failed}, unchanged={unchanged})")

        time.sleep(DELAY)

    print()
    print(f"Results:")
    print(f"  Fixed:     {fixed}")
    print(f"  Unchanged: {unchanged}")
    print(f"  Failed:    {failed}")

    if changes:
        print(f"\nChanges ({len(changes)}):")
        for old, new in sorted(changes):
            print(f"  {old:30s} -> {new}")

    if failures:
        print(f"\nFailed (no proper name found):")
        for name in sorted(failures):
            print(f"  {name}")

    # Save atomically
    if fixed > 0:
        dir_name = os.path.dirname(PORTFOLIO_PATH)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")  # trailing newline
            os.replace(tmp_path, PORTFOLIO_PATH)
            print(f"\nSaved {fixed} name corrections to portfolio_items.json")
        except Exception:
            os.unlink(tmp_path)
            raise
    else:
        print("\nNo changes to save.")


if __name__ == "__main__":
    main()
