#!/usr/bin/env python3
"""
UserPromptSubmit Hook - Generate handoff before /clear

With 1M context windows, compaction rarely triggers, so /clear becomes
the primary context reset. This hook detects /clear prompts and generates
a handoff document before the conversation is wiped, ensuring /seance
(or Rix startup) can recover context.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from utils import generate_handoff, log


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    prompt = data.get('prompt', '').strip()

    # Only fire on /clear commands (with or without trailing text)
    if not prompt.startswith('/clear'):
        return

    log('[PreClear] /clear detected — generating handoff before context wipe')

    try:
        result = generate_handoff(caller='Clear')
        summary = '\n'.join(result['summary_lines'])
        log(summary)
    except Exception as err:
        log(f'[PreClear] Handoff generation failed: {err}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'[PreClear] Error: {e}', file=sys.stderr)
        sys.exit(0)
