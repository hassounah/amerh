#!/usr/bin/env python3
"""
Stop Hook (Session End) - Persist learnings when session ends

Cross-platform (Windows, macOS, Linux)

Runs when Claude session ends. Creates/updates session log file
with timestamp for continuity tracking, and generates a handoff
document for cross-session recovery via /seance.
"""

import json
import os
import re
import signal
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from utils import (
    ensure_dir,
    generate_handoff,
    get_date_string,
    get_home_dir,
    get_sessions_dir,
    get_session_id_short,
    get_time_string,
    log,
    read_session_id_from_stdin,
    replace_in_file,
    write_file,
)


def _signal_channel_server(short_id):
    """Signal the MCP channel server to re-watch for a new card.

    Sends SIGUSR1 before the card is deleted so the server knows to
    look for a replacement card (e.g., after /resume creates a new session).
    """
    card_path = os.path.join(get_home_dir(), '.claude', 'channels', f'{short_id}.json')
    try:
        with open(card_path, 'r', encoding='utf-8') as f:
            card = json.load(f)
        pid = card.get('pid')
        if isinstance(pid, int) and pid > 0:
            os.kill(pid, signal.SIGUSR1)
            log(f'[SessionEnd] Sent SIGUSR1 to channel server (pid={pid})')
    except ProcessLookupError:
        pass  # Server already dead
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass


def _remove_channel_card(short_id):
    """Remove the channel card for this session."""
    card_path = os.path.join(get_home_dir(), '.claude', 'channels', f'{short_id}.json')
    if os.path.exists(card_path):
        try:
            os.unlink(card_path)
            log(f'[SessionEnd] Removed channel card: {card_path}')
        except OSError:
            pass


def main():
    session_id = read_session_id_from_stdin()
    short_id = get_session_id_short(session_id=session_id)

    # Signal the MCP server before deleting the card, so it can re-watch
    # for a replacement card if a new session starts (e.g., /resume)
    try:
        _signal_channel_server(short_id)
    except Exception as e:
        log(f'[SessionEnd] Warning: channel server signal failed: {e}')

    # Remove channel card
    try:
        _remove_channel_card(short_id)
    except Exception as e:
        log(f'[SessionEnd] Warning: channel card removal failed: {e}')
    sessions_dir = get_sessions_dir()
    today = get_date_string()
    # Include session ID in filename for unique per-session tracking
    session_file = os.path.join(sessions_dir, f'{today}-{short_id}-session.tmp')

    ensure_dir(sessions_dir)

    current_time = get_time_string()

    # If session file exists for today, update the end time
    if os.path.exists(session_file):
        success = replace_in_file(
            session_file,
            re.compile(r'\*\*Last Updated:\*\*.*'),
            f'**Last Updated:** {current_time}',
        )

        if success:
            log(f'[SessionEnd] Updated session file: {session_file}')
    else:
        # Create new session file with template
        template = f"""# Session: {today}
**Date:** {today}
**Started:** {current_time}
**Last Updated:** {current_time}

---

## Current State

[Session context goes here]

### Completed
- [ ]

### In Progress
- [ ]

### Notes for Next Session
-

### Context to Load
```
[relevant files]
```
"""

        write_file(session_file, template)
        log(f'[SessionEnd] Created session file: {session_file}')

    # Generate handoff document for cross-session recovery
    try:
        result = generate_handoff(caller='SessionEnd')
        log('\n'.join(result['summary_lines']))
    except Exception as err:
        log(f'[SessionEnd] Handoff generation failed: {err}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'[SessionEnd] Error: {e}', file=sys.stderr)
        sys.exit(0)
