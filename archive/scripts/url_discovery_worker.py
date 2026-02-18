#!/usr/bin/env python3
"""
URL Discovery Worker - Find portfolio URLs and create extractors for funds.

This script manages the work queue for:
1. Funds with valid portfolio URLs that need extractors
2. Funds that need portfolio URL discovery (homepage works)
3. Funds that need headless browser access

Usage:
    python scripts/url_discovery_worker.py status        # Show queue status
    python scripts/url_discovery_worker.py claim <id>   # Claim a fund
    python scripts/url_discovery_worker.py info <fund>  # Get fund details
    python scripts/url_discovery_worker.py complete <fund>  # Mark as complete
    python scripts/url_discovery_worker.py skip <fund>  # Skip (can't extract)
"""

import json
import sys
import fcntl
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "data/derived/url_discovery_queue.json"
LOCK_FILE = BASE_DIR / "data/derived/.url_discovery_queue.lock"


def load_queue():
    with open(QUEUE_FILE) as f:
        return json.load(f)


def save_queue(queue):
    with open(QUEUE_FILE, 'w') as f:
        json.dump(queue, f, indent=2)


def with_lock(func):
    """Decorator to ensure atomic queue operations."""
    def wrapper(*args, **kwargs):
        LOCK_FILE.touch()
        with open(LOCK_FILE, 'r+') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                return func(*args, **kwargs)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return wrapper


def status():
    """Show current work queue status."""
    queue = load_queue()

    print("=" * 60)
    print("URL DISCOVERY WORK QUEUE STATUS")
    print("=" * 60)
    print()
    print(f"✓ Ready for extraction:        {len(queue.get('ready_for_extraction', []))}")
    print(f"🔍 Need portfolio discovery:   {len(queue.get('needs_portfolio_discovery', []))}")
    print(f"🖥️  Need headless browser:      {len(queue.get('needs_headless', []))}")
    print(f"🛡️  Bot protected (skip):       {len(queue.get('bot_protected', []))}")
    print(f"❌ Site errors:                {len(queue.get('site_errors', []))}")
    print(f"☠️  Site gone:                  {len(queue.get('site_gone', []))}")
    print(f"⏳ In progress:                {len(queue.get('in_progress', {}))}")
    print(f"✅ Completed:                  {len(queue.get('completed', []))}")
    print()

    # Show in progress
    if queue.get('in_progress'):
        print("Currently being worked on:")
        for fund_id, info in queue['in_progress'].items():
            print(f"  - {fund_id} ({info.get('task_type', 'unknown')}) by {info.get('claude_id', 'unknown')}")

    # Show next items
    print("\nNext 5 ready for extraction:")
    for item in queue.get('ready_for_extraction', [])[:5]:
        print(f"  - {item['fund_id']}: {item.get('portfolio_url', 'N/A')}")

    print("\nNext 5 needing portfolio discovery:")
    for item in queue.get('needs_portfolio_discovery', [])[:5]:
        print(f"  - {item['fund_id']}: {item.get('homepage', 'N/A')}")

    print("\nNeeds headless browser:")
    for item in queue.get('needs_headless', []):
        print(f"  - {item['fund_id']}: {item.get('homepage', 'N/A')}")


@with_lock
def claim(claude_id: str):
    """Claim the next available fund to work on."""
    queue = load_queue()

    # Priority order: ready_for_extraction > needs_headless > needs_portfolio_discovery
    sources = [
        ('ready_for_extraction', 'create_extractor'),
        ('needs_headless', 'headless_portfolio_discovery'),
        ('needs_portfolio_discovery', 'find_portfolio_url'),
    ]

    for source_key, task_type in sources:
        source_list = queue.get(source_key, [])
        if source_list:
            item = source_list.pop(0)
            fund_id = item['fund_id']

            # Add to in_progress
            if 'in_progress' not in queue:
                queue['in_progress'] = {}

            queue['in_progress'][fund_id] = {
                **item,
                'claude_id': claude_id,
                'task_type': task_type,
                'started_at': datetime.utcnow().isoformat() + 'Z'
            }

            save_queue(queue)
            print(f"Claimed: {fund_id}")
            print(f"Task type: {task_type}")
            print(f"Homepage: {item.get('homepage', 'N/A')}")
            if item.get('portfolio_url'):
                print(f"Portfolio URL: {item['portfolio_url']}")
            return fund_id

    print("No funds available to claim!")
    return None


def info(fund_id: str):
    """Get detailed info about a fund."""
    queue = load_queue()

    # Check in_progress first
    if fund_id in queue.get('in_progress', {}):
        item = queue['in_progress'][fund_id]
        print(json.dumps(item, indent=2))
        return

    # Check other lists
    for key in ['ready_for_extraction', 'needs_portfolio_discovery', 'needs_headless', 'bot_protected', 'site_errors']:
        for item in queue.get(key, []):
            if item.get('fund_id') == fund_id:
                print(f"Found in: {key}")
                print(json.dumps(item, indent=2))
                return

    print(f"Fund {fund_id} not found in queue")


@with_lock
def complete(fund_id: str, portfolio_url: str = None):
    """Mark a fund as complete."""
    queue = load_queue()

    if fund_id not in queue.get('in_progress', {}):
        print(f"Fund {fund_id} is not in progress")
        return False

    item = queue['in_progress'].pop(fund_id)

    # Add completion info
    item['completed_at'] = datetime.utcnow().isoformat() + 'Z'
    if portfolio_url:
        item['portfolio_url'] = portfolio_url

    if 'completed' not in queue:
        queue['completed'] = []
    queue['completed'].append(item)

    save_queue(queue)
    print(f"Marked {fund_id} as complete")
    return True


@with_lock
def skip(fund_id: str, reason: str = "unable_to_extract"):
    """Skip a fund (can't be extracted)."""
    queue = load_queue()

    if fund_id not in queue.get('in_progress', {}):
        print(f"Fund {fund_id} is not in progress")
        return False

    item = queue['in_progress'].pop(fund_id)
    item['skipped_at'] = datetime.utcnow().isoformat() + 'Z'
    item['skip_reason'] = reason

    # Add to site_errors or a new skipped list
    if 'skipped' not in queue:
        queue['skipped'] = []
    queue['skipped'].append(item)

    save_queue(queue)
    print(f"Skipped {fund_id}: {reason}")
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]

    if command == 'status':
        status()
    elif command == 'claim':
        if len(sys.argv) < 3:
            print("Usage: url_discovery_worker.py claim <claude_id>")
            return
        claim(sys.argv[2])
    elif command == 'info':
        if len(sys.argv) < 3:
            print("Usage: url_discovery_worker.py info <fund_id>")
            return
        info(sys.argv[2])
    elif command == 'complete':
        if len(sys.argv) < 3:
            print("Usage: url_discovery_worker.py complete <fund_id> [portfolio_url]")
            return
        portfolio_url = sys.argv[3] if len(sys.argv) > 3 else None
        complete(sys.argv[2], portfolio_url)
    elif command == 'skip':
        if len(sys.argv) < 3:
            print("Usage: url_discovery_worker.py skip <fund_id> [reason]")
            return
        reason = sys.argv[3] if len(sys.argv) > 3 else "unable_to_extract"
        skip(sys.argv[2], reason)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == '__main__':
    main()
