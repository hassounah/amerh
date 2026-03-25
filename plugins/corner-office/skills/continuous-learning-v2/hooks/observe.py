#!/usr/bin/env python3
"""
Continuous Learning v2 - Observation Hook

Captures tool use events for pattern analysis.
Claude Code passes hook data via stdin as JSON.
"""

import json
import os
import signal
import sys
from datetime import datetime, timezone


def main():
    config_dir = os.path.join(os.path.expanduser('~'), '.claude', 'homunculus')
    observations_file = os.path.join(config_dir, 'observations.jsonl')
    max_file_size_bytes = 10 * 1024 * 1024  # 10 MB

    os.makedirs(config_dir, exist_ok=True)

    # Skip if disabled
    if os.path.isfile(os.path.join(config_dir, 'disabled')):
        sys.exit(0)

    # Read JSON from stdin
    input_json = sys.stdin.read().strip()
    if not input_json:
        sys.exit(0)

    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Parse input
    try:
        data = json.loads(input_json)

        hook_type = data.get('hook_type', 'unknown')
        tool_name = data.get('tool_name', data.get('tool', 'unknown'))
        tool_input = data.get('tool_input', data.get('input', {}))
        tool_output = data.get('tool_output', data.get('output', ''))
        session_id = data.get('session_id', 'unknown')

        # Truncate large values
        if isinstance(tool_input, dict):
            tool_input_str = json.dumps(tool_input)[:5000]
        else:
            tool_input_str = str(tool_input)[:5000]

        if isinstance(tool_output, dict):
            tool_output_str = json.dumps(tool_output)[:5000]
        else:
            tool_output_str = str(tool_output)[:5000]

        event = 'tool_start' if 'Pre' in hook_type else 'tool_complete'

    except Exception:
        # Log parse error and exit
        raw_truncated = json.dumps(input_json[:1000])
        error_record = json.dumps({
            'timestamp': timestamp,
            'event': 'parse_error',
            'raw': raw_truncated,
        })
        with open(observations_file, 'a', encoding='utf-8') as f:
            f.write(error_record + '\n')
        sys.exit(0)

    # Archive if file too large
    if os.path.isfile(observations_file):
        try:
            file_size = os.path.getsize(observations_file)
            if file_size >= max_file_size_bytes:
                archive_dir = os.path.join(config_dir, 'observations.archive')
                os.makedirs(archive_dir, exist_ok=True)
                archive_name = datetime.now().strftime(
                    'observations-%Y%m%d-%H%M%S.jsonl'
                )
                os.rename(
                    observations_file,
                    os.path.join(archive_dir, archive_name),
                )
        except OSError:
            pass

    # Build and write observation
    observation = {
        'timestamp': timestamp,
        'event': event,
        'tool': tool_name,
        'session': session_id,
    }
    if event == 'tool_start' and tool_input_str:
        observation['input'] = tool_input_str
    if event == 'tool_complete' and tool_output_str:
        observation['output'] = tool_output_str

    with open(observations_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(observation) + '\n')

    # Signal observer if running
    pid_file = os.path.join(config_dir, '.observer.pid')
    if os.path.isfile(pid_file):
        try:
            with open(pid_file) as f:
                observer_pid = int(f.read().strip())
            os.kill(observer_pid, signal.SIGUSR1)
        except (ValueError, OSError, ProcessLookupError):
            pass


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        sys.stderr.write(f'[Observe] error: {e}\n')
    sys.exit(0)
