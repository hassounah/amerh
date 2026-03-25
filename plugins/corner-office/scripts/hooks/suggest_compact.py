#!/usr/bin/env python3
"""
Strategic Compact Suggester

Cross-platform (Windows, macOS, Linux)

Runs on PreToolUse or periodically to suggest manual compaction at logical intervals

Why manual over auto-compact:
- Auto-compact happens at arbitrary points, often mid-task
- Strategic compacting preserves context through logical phases
- Compact after exploration, before execution
- Compact after completing a milestone, before starting next
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from utils import get_claude_dir, read_file, write_file, log, output


def main():
    # Drain stdin to prevent pipe blocking (PreToolUse hooks receive JSON on stdin)
    sys.stdin.read()

    # Track tool call count in ~/.claude/ (user-owned, not world-writable /tmp)
    session_id = os.environ.get('CLAUDE_SESSION_ID') or 'default'
    counter_dir = os.path.join(get_claude_dir(), 'tool-counts')
    os.makedirs(counter_dir, exist_ok=True)
    counter_file = os.path.join(counter_dir, f'claude-tool-count-{session_id}')
    threshold = int(os.environ.get('COMPACT_THRESHOLD', '50'))

    count = 1

    # Read existing count or start at 1
    existing = read_file(counter_file)
    if existing:
        count = int(existing.strip()) + 1

    # Save updated count
    write_file(counter_file, str(count))

    # Suggest compact after threshold tool calls
    if count == threshold:
        msg = f'[StrategicCompact] {threshold} tool calls reached - consider /compact if transitioning phases'
        log(msg)
        output(msg)

    # Suggest at regular intervals after threshold
    if count > threshold and count % 25 == 0:
        msg = f'[StrategicCompact] {count} tool calls - good checkpoint for /compact if context is stale'
        log(msg)
        output(msg)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'[StrategicCompact] Error: {e}', file=sys.stderr)
        sys.exit(0)
