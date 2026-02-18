#!/usr/bin/env python3
"""
Atomic fund claiming for parallel signal quality improvement.

Uses a SEPARATE queue and lock from the portfolio extractor work queue
to allow signal work and portfolio work to run in parallel without conflicts.

Usage:
    python3 scripts/claim_signal_fund.py status           # Show queue status
    python3 scripts/claim_signal_fund.py claim <id>       # Claim next fund
    python3 scripts/claim_signal_fund.py complete <fund>  # Mark as complete
    python3 scripts/claim_signal_fund.py skip <fund>      # Mark as skipped
    python3 scripts/claim_signal_fund.py info <fund>      # Get fund details
"""
import fcntl
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

QUEUE_FILE = Path(__file__).parent.parent / "data/derived/signal_work_queue.json"
LOCK_FILE = Path(__file__).parent.parent / "data/derived/.signal_work_queue.lock"


def load_queue() -> dict:
    """Load signal work queue."""
    if not QUEUE_FILE.exists():
        print(f"Queue file not found: {QUEUE_FILE}", file=sys.stderr)
        print("Run: python3 scripts/generate_signal_work_queue.py", file=sys.stderr)
        sys.exit(1)
    with open(QUEUE_FILE, "r") as f:
        return json.load(f)


def save_queue(queue: dict):
    """Save signal work queue."""
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


def claim_fund(claude_id: str, priority: str = "auto") -> str | None:
    """
    Atomically claim a fund from the signal work queue.

    Priority selection:
      - "A": claim from needs_news_extractor (add extract_news to existing)
      - "B": claim from has_news_no_signals (fix broken extract_news)
      - "C": claim from needs_new_extractor (create extractor from scratch)
      - "auto": try A first, then B, then C
    """
    LOCK_FILE.touch()

    with open(LOCK_FILE, "r+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        try:
            queue = load_queue()

            # Priority lists in order
            priority_map = {
                "A": "needs_news_extractor",
                "B": "has_news_no_signals",
                "C": "needs_new_extractor",
            }

            if priority in priority_map:
                lists_to_try = [priority_map[priority]]
            else:
                # Auto: try A → B → C
                lists_to_try = [
                    "needs_news_extractor",
                    "has_news_no_signals",
                    "needs_new_extractor",
                ]

            fund = None
            source_list_name = None
            for list_name in lists_to_try:
                source = queue.get(list_name, [])
                if source:
                    fund = source.pop(0)
                    source_list_name = list_name
                    break

            if not fund:
                return None

            slug = fund["slug"]

            # Add to in_progress
            queue.setdefault("in_progress", {})[slug] = {
                **fund,
                "claude_id": claude_id,
                "source_list": source_list_name,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

            save_queue(queue)
            return slug

        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def release_fund(slug: str, status: str = "complete") -> bool:
    """Move a fund from in_progress to completed or skipped."""
    LOCK_FILE.touch()

    with open(LOCK_FILE, "r+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        try:
            queue = load_queue()

            if slug not in queue.get("in_progress", {}):
                return False

            fund = queue["in_progress"].pop(slug)
            fund["completed_at"] = datetime.now(timezone.utc).isoformat()
            fund["result"] = status

            if status == "skipped":
                queue.setdefault("skipped", []).append(fund)
            else:
                queue.setdefault("completed", []).append(fund)

            save_queue(queue)
            return True

        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def get_fund_info(slug: str) -> dict | None:
    """Get detailed info about a fund from any queue section."""
    queue = load_queue()

    # Check in_progress
    if slug in queue.get("in_progress", {}):
        info = queue["in_progress"][slug]
        info["_status"] = "in_progress"
        return info

    # Check all list sections
    for section in [
        "needs_news_extractor",
        "has_news_no_signals",
        "needs_new_extractor",
        "completed",
        "skipped",
        "has_signals",
        "no_website",
    ]:
        for item in queue.get(section, []):
            if item.get("slug") == slug:
                item["_status"] = section
                return item

    return None


def show_status():
    """Show current signal work queue status."""
    queue = load_queue()

    a_count = len(queue.get("needs_news_extractor", []))
    b_count = len(queue.get("has_news_no_signals", []))
    c_count = len(queue.get("needs_new_extractor", []))
    in_progress = queue.get("in_progress", {})
    completed = len(queue.get("completed", []))
    skipped = len(queue.get("skipped", []))
    has_signals = len(queue.get("has_signals", []))
    no_website = len(queue.get("no_website", []))

    total_remaining = a_count + b_count + c_count

    print("=" * 60)
    print("SIGNAL WORK QUEUE STATUS")
    print("=" * 60)
    print()
    print(f"Priority A (add extract_news):   {a_count}")
    print(f"Priority B (fix broken news):    {b_count}")
    print(f"Priority C (new extractor):      {c_count}")
    print(f"                                 -----")
    print(f"Total remaining:                 {total_remaining}")
    print()
    print(f"In Progress:                     {len(in_progress)}")
    print(f"Completed:                       {completed}")
    print(f"Skipped:                         {skipped}")
    print(f"Already has signals:             {has_signals}")
    print(f"No website (N/A):                {no_website}")
    print()

    if in_progress:
        print("Currently being worked on:")
        for slug, info in in_progress.items():
            priority = info.get("priority", "?")
            claude = info.get("claude_id", "unknown")
            print(f"  - {slug} (Priority {priority}) by {claude}")
        print()

    print("Next 5 Priority A (add extract_news to existing extractor):")
    for item in queue.get("needs_news_extractor", [])[:5]:
        print(f"  - {item['slug']}: {item.get('extractor_file', '?')} ({item['category']})")

    print()
    print("Next 5 Priority B (fix broken extract_news):")
    for item in queue.get("has_news_no_signals", [])[:5]:
        print(f"  - {item['slug']}: {item.get('extractor_file', '?')} ({item['category']})")

    print()
    print("Next 5 Priority C (create new extractor):")
    for item in queue.get("needs_new_extractor", [])[:5]:
        print(f"  - {item['slug']}: {item['domain']} ({item['category']})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_status()
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "status":
        show_status()

    elif cmd == "claim":
        claude_id = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        priority = sys.argv[3] if len(sys.argv) > 3 else "auto"
        slug = claim_fund(claude_id, priority)
        if slug:
            print(slug)
        else:
            print("NO_FUNDS", file=sys.stderr)
            sys.exit(1)

    elif cmd == "complete":
        slug = sys.argv[2] if len(sys.argv) > 2 else None
        if slug and release_fund(slug, "complete"):
            print(f"Marked {slug} as complete")
        else:
            print(f"Failed to mark {slug} as complete", file=sys.stderr)
            sys.exit(1)

    elif cmd == "skip":
        slug = sys.argv[2] if len(sys.argv) > 2 else None
        if slug and release_fund(slug, "skipped"):
            print(f"Marked {slug} as skipped")
        else:
            print(f"Failed to mark {slug} as skipped", file=sys.stderr)
            sys.exit(1)

    elif cmd == "info":
        slug = sys.argv[2] if len(sys.argv) > 2 else None
        if slug:
            info = get_fund_info(slug)
            if info:
                print(json.dumps(info, indent=2))
            else:
                print(f"Fund {slug} not found in signal queue", file=sys.stderr)
                sys.exit(1)
        else:
            print("Usage: claim_signal_fund.py info <slug>", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print("Usage: claim_signal_fund.py {status|claim|complete|skip|info}", file=sys.stderr)
        sys.exit(1)
