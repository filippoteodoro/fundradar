#!/usr/bin/env python3
"""
Atomic fund claiming for parallel extractor development.

Usage:
    python scripts/claim_fund.py status           # Show queue status
    python scripts/claim_fund.py claim <id>       # Claim next fund
    python scripts/claim_fund.py complete <fund>  # Mark as complete
    python scripts/claim_fund.py skip <fund>      # Mark as skipped
    python scripts/claim_fund.py info <fund>      # Get fund details
"""
import fcntl
import json
import sys
from datetime import datetime
from pathlib import Path

QUEUE_FILE = Path(__file__).parent.parent / "data/derived/extractor_work_queue.json"
LOCK_FILE = Path(__file__).parent.parent / "data/derived/.work_queue.lock"


def load_queue():
    """Load work queue with lock."""
    LOCK_FILE.touch()
    with open(QUEUE_FILE, 'r') as f:
        return json.load(f)


def save_queue(queue):
    """Save work queue."""
    with open(QUEUE_FILE, 'w') as f:
        json.dump(queue, f, indent=2)


def claim_fund(claude_id: str, task_type: str = 'fix') -> str | None:
    """Atomically claim a fund from the work queue."""
    LOCK_FILE.touch()

    with open(LOCK_FILE, 'r+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        try:
            queue = load_queue()

            # Determine which list to claim from
            if task_type == 'fix':
                source_list = queue.get('needs_fix', [])
                list_name = 'needs_fix'
            elif task_type == 'new':
                source_list = queue.get('needs_new', [])
                list_name = 'needs_new'
            else:
                # Auto-select: prioritize fixes, then new
                if queue.get('needs_fix'):
                    source_list = queue['needs_fix']
                    list_name = 'needs_fix'
                elif queue.get('needs_new'):
                    source_list = queue['needs_new']
                    list_name = 'needs_new'
                else:
                    return None

            if not source_list:
                return None

            # Pop first item
            fund = source_list.pop(0)
            fund_id = fund['fund_id']

            # Add to in_progress
            queue.setdefault('in_progress', {})[fund_id] = {
                **fund,
                'claude_id': claude_id,
                'task_type': list_name,
                'started_at': datetime.utcnow().isoformat() + 'Z'
            }

            save_queue(queue)
            return fund_id

        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def release_fund(fund_id: str, status: str = 'complete') -> bool:
    """Move a fund from in_progress to completed or back to queue."""
    LOCK_FILE.touch()

    with open(LOCK_FILE, 'r+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        try:
            queue = load_queue()

            if fund_id not in queue.get('in_progress', {}):
                return False

            fund = queue['in_progress'].pop(fund_id)
            fund['completed_at'] = datetime.utcnow().isoformat() + 'Z'
            fund['result'] = status

            queue.setdefault('completed', []).append(fund)
            save_queue(queue)
            return True

        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def get_fund_info(fund_id: str) -> dict | None:
    """Get detailed info about a fund."""
    queue = load_queue()

    # Check in_progress
    if fund_id in queue.get('in_progress', {}):
        return queue['in_progress'][fund_id]

    # Check needs_fix
    for item in queue.get('needs_fix', []):
        if item['fund_id'] == fund_id:
            return item

    # Check needs_new
    for item in queue.get('needs_new', []):
        if item['fund_id'] == fund_id:
            return item

    # Check completed
    for item in queue.get('completed', []):
        if item['fund_id'] == fund_id:
            return item

    return None


def show_status():
    """Show current queue status."""
    queue = load_queue()

    needs_fix = len(queue.get('needs_fix', []))
    needs_new = len(queue.get('needs_new', []))
    in_progress = queue.get('in_progress', {})
    completed = len(queue.get('completed', []))
    working = len(queue.get('working', []))
    no_urls = len(queue.get('no_urls', []))

    print("=" * 60)
    print("EXTRACTOR WORK QUEUE STATUS")
    print("=" * 60)
    print()
    print(f"Need FIX (broken extractors):  {needs_fix}")
    print(f"Need NEW extractor:            {needs_new}")
    print(f"In Progress:                   {len(in_progress)}")
    print(f"Completed this session:        {completed}")
    print(f"Already working well:          {working}")
    print(f"No URLs (skip):                {no_urls}")
    print()

    if in_progress:
        print("Currently being worked on:")
        for fid, info in in_progress.items():
            task = info.get('task_type', 'unknown')
            claude = info.get('claude_id', 'unknown')
            print(f"  - {fid} ({task}) by {claude}")
        print()

    # Show next items
    print("Next 5 to FIX:")
    for item in queue.get('needs_fix', [])[:5]:
        print(f"  - {item['fund_id']}: {item.get('domain', 'unknown')} ({item.get('reason', '')})")

    print()
    print("Next 5 to CREATE:")
    for item in queue.get('needs_new', [])[:5]:
        count = item.get('old_count', 0)
        print(f"  - {item['fund_id']}: {item.get('domain', 'unknown')} ({count} items)")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        show_status()
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'status':
        show_status()

    elif cmd == 'claim':
        claude_id = sys.argv[2] if len(sys.argv) > 2 else 'unknown'
        task_type = sys.argv[3] if len(sys.argv) > 3 else 'auto'
        fund_id = claim_fund(claude_id, task_type)
        if fund_id:
            print(fund_id)
        else:
            print("NO_FUNDS", file=sys.stderr)
            sys.exit(1)

    elif cmd == 'complete':
        fund_id = sys.argv[2] if len(sys.argv) > 2 else None
        if fund_id and release_fund(fund_id, 'complete'):
            print(f"Marked {fund_id} as complete")
        else:
            print(f"Failed to mark {fund_id} as complete", file=sys.stderr)
            sys.exit(1)

    elif cmd == 'skip':
        fund_id = sys.argv[2] if len(sys.argv) > 2 else None
        if fund_id and release_fund(fund_id, 'skipped'):
            print(f"Marked {fund_id} as skipped")
        else:
            print(f"Failed to mark {fund_id} as skipped", file=sys.stderr)
            sys.exit(1)

    elif cmd == 'info':
        fund_id = sys.argv[2] if len(sys.argv) > 2 else None
        if fund_id:
            info = get_fund_info(fund_id)
            if info:
                print(json.dumps(info, indent=2))
            else:
                print(f"Fund {fund_id} not found", file=sys.stderr)
                sys.exit(1)
    else:
        # Backwards compatibility: assume it's a claude_id
        fund_id = claim_fund(cmd)
        if fund_id:
            print(fund_id)
        else:
            print("NO_FUNDS", file=sys.stderr)
            sys.exit(1)
