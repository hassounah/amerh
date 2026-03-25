#!/usr/bin/env python3
"""
PreCompact Hook - Save state before context compaction

Runs before Claude compacts context, giving you a chance to
preserve important state that might get lost in summarization.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from utils import (
    append_file,
    ensure_dir,
    find_files,
    generate_handoff,
    get_date_time_string,
    get_home_dir,
    get_sessions_dir,
    get_time_string,
    log,
    output,
    run_command,
    write_file,
)


def main():
    sessions_dir = get_sessions_dir()
    compaction_log = os.path.join(sessions_dir, 'compaction-log.txt')

    ensure_dir(sessions_dir)

    # Log compaction event with timestamp
    timestamp = get_date_time_string()
    append_file(compaction_log, f'[{timestamp}] Context compaction triggered\n')

    # If there's an active session file, note the compaction
    sessions = find_files(sessions_dir, '*.tmp')

    if sessions:
        active_session = sessions[0]['path']
        time_str = get_time_string()
        append_file(active_session, f'\n---\n**[Compaction occurred at {time_str}]** - Context was summarized\n')

    log('[PreCompact] State saved before compaction')
    output('[PreCompact] State saved before compaction')

    # Handoff capture — wrapped in try/except so any failure never blocks compaction
    try:
        result = generate_handoff(caller='PreCompact')
        summary = '\n'.join(result['summary_lines'])
        log(summary)
        output(summary)
    except Exception as err:
        # Graceful degradation — minimal handoff on any error
        try:
            from datetime import datetime

            file_timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
            fallback_dir = os.path.join(get_home_dir(), '.claude', 'homunculus', 'handoffs')
            ensure_dir(fallback_dir)
            fallback_file = os.path.join(fallback_dir, f'handoff-{file_timestamp}.md')

            branch_result = run_command('git branch --show-current')
            branch = branch_result['output'] if branch_result['success'] else 'unknown'

            write_file(fallback_file, '\n'.join([
                '# Handoff (minimal)',
                '',
                f'**Timestamp:** {get_date_time_string()}',
                f'**Working Directory:** {os.getcwd()}',
                f'**Git Branch:** {branch}',
                '',
                '_Handoff capture encountered an error — limited information saved._',
                f'_Error: {err}_',
                '',
                '## Recovery Instructions',
                '',
                'Run `/seance` to recover context from this handoff.',
                '',
            ]))

            log(f'[PreCompact] Minimal handoff saved (error: {err})')
            output(f'[PreCompact] Minimal handoff saved. Run /seance to recover. (error during capture: {err})')
        except Exception:
            log('[PreCompact] Handoff capture failed entirely')


if __name__ == '__main__':
    try:
        main()
    except Exception as err:
        print(f'[PreCompact] Error: {err}', file=sys.stderr)
    sys.exit(0)
