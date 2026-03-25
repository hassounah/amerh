#!/usr/bin/env python3
"""
PostToolUse Hook - Refresh session registration card on pipeline file writes.

When Claude writes to .rix/active-pipeline.md, re-reads the file and updates
the Feature/Stage fields in the session registration card so the Corner Office
app always shows the current pipeline context.
"""

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from utils import get_home_dir, get_session_id_short, read_file, log


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    # Only act on Write tool calls to the active pipeline file
    tool_name = data.get('tool_name', '')
    file_path = data.get('tool_input', {}).get('file_path', '')
    if tool_name != 'Write' or not file_path.endswith('.rix/active-pipeline.md'):
        return

    # Read session_id from payload first, fall back to env var
    sid = data.get('session_id', data.get('sessionId', ''))
    short_id = sid[-8:] if sid else get_session_id_short()
    card_path = os.path.join(get_home_dir(), '.claude', 'channels', f'{short_id}.json')

    card_content = read_file(card_path)
    if card_content is None:
        return  # No card to update

    try:
        card = json.loads(card_content)
    except json.JSONDecodeError:
        return

    # Read the pipeline file that was just written
    pipeline_content = read_file(file_path)
    if pipeline_content is None:
        return

    # Extract Feature and Stage fields
    pipeline_fields = {}
    for match in re.finditer(r'^- \*\*([^*]+)\*\*:\s*(.+)$', pipeline_content, re.MULTILINE):
        pipeline_fields[match.group(1).strip()] = match.group(2).strip()

    feature = pipeline_fields.get('Feature')
    stage = pipeline_fields.get('Stage')

    updated = False
    if feature is not None and card.get('feature') != feature:
        card['feature'] = feature
        updated = True
    if stage is not None and card.get('pipelineStage') != stage:
        card['pipelineStage'] = stage
        updated = True

    if not updated:
        return

    now = datetime.now(timezone.utc)
    card['updatedAt'] = now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}Z'

    # Atomic write: tempfile → chmod → replace
    card_dir = os.path.dirname(card_path)
    fd, tmp_path = tempfile.mkstemp(dir=card_dir)
    try:
        os.chmod(tmp_path, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(card, f, indent=2)
        os.replace(tmp_path, card_path)
        log(f'[refresh_registration] Updated card: feature={feature}, stage={stage}')
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'[refresh_registration] ERROR: {e}', file=sys.stderr)
