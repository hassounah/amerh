#!/usr/bin/env python3
"""
Continuous Learning - Session Evaluator

Cross-platform (Windows, macOS, Linux)

Runs on Stop hook to extract reusable patterns from Claude Code sessions

Why Stop hook instead of UserPromptSubmit:
- Stop runs once at session end (lightweight)
- UserPromptSubmit runs every message (heavy, adds latency)
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from utils import get_learned_skills_dir, ensure_dir, read_file, count_in_file, log, get_git_repo_name, get_session_id_short, read_session_id_from_stdin


def get_session_event_file():
    """Locate the JSONL event file for the current session.

    Uses os.path.basename(cwd) for workspace slug derivation — must match
    emit_activity.py's derivation (which uses cwd from the hook payload).
    Falls back to get_git_repo_name() if the cwd-based path doesn't exist.

    Returns the file path if it exists, else None.
    """
    short_id = get_session_id_short(session_id=read_session_id_from_stdin())
    events_dir = os.path.join(os.path.expanduser('~'), '.corner-office', 'events')

    # Primary: match emit_activity.py's derivation (basename of cwd)
    cwd_name = os.path.basename(os.getcwd())
    workspace = re.sub(r'[^a-zA-Z0-9_-]', '', cwd_name)[:64] or 'unknown'
    path = os.path.join(events_dir, workspace, f'{short_id}.jsonl')
    if os.path.exists(path):
        return path

    # Fallback: try git repo name (handles subdirectory case)
    repo_name = get_git_repo_name()
    if repo_name and repo_name != cwd_name:
        workspace = re.sub(r'[^a-zA-Z0-9_-]', '', repo_name)[:64] or 'unknown'
        path = os.path.join(events_dir, workspace, f'{short_id}.jsonl')
        if os.path.exists(path):
            return path

    return None


def count_events_in_session_file(filepath):
    """Count total events and tool events (PreToolUse/PostToolUse) in a JSONL file.

    Returns (total, tool_events) tuple. Skips corrupted lines.
    """
    total = 0
    tool_events = 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    total += 1
                    if entry.get('event') in ('PreToolUse', 'PostToolUse'):
                        tool_events += 1
                except json.JSONDecodeError:
                    log(f'[ContinuousLearning] Warning: skipping corrupted JSONL line in {filepath}')
    except OSError as e:
        log(f'[ContinuousLearning] Warning: could not read event file {filepath}: {e}')
    return (total, tool_events)


def main():
    # Get script directory to find config
    script_dir = os.path.dirname(__file__)
    config_file = os.path.join(
        script_dir, '..', '..', 'skills', 'continuous-learning-v2', 'config.json'
    )

    # Default configuration
    min_session_length = 10
    learned_skills_path = get_learned_skills_dir()

    # Load config if exists
    config_content = read_file(config_file)
    if config_content:
        try:
            config = json.loads(config_content)
            min_session_length = config.get('min_session_length', 10)

            if config.get('learned_skills_path'):
                # Handle ~ in path
                learned_skills_path = os.path.expanduser(config['learned_skills_path'])
        except (json.JSONDecodeError, KeyError):
            # Invalid config, use defaults
            pass

    # Ensure learned skills directory exists
    ensure_dir(learned_skills_path)

    # Try event file first (preferred source — written by emit_activity.py)
    event_file = get_session_event_file()
    if event_file:
        total, tool_events = count_events_in_session_file(event_file)
        log(f'[ContinuousLearning] Event file: {event_file} ({total} events, {tool_events} tool events)')
        if total < min_session_length:
            log(f'[ContinuousLearning] Session too short ({total} events), skipping')
            sys.exit(0)
        log(f'[ContinuousLearning] Session has {total} events - evaluate for extractable patterns')
        log(f'[ContinuousLearning] Save learned skills to: {learned_skills_path}')
        return

    # Fall through to existing CLAUDE_TRANSCRIPT_PATH logic
    transcript_path = os.environ.get('CLAUDE_TRANSCRIPT_PATH')

    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

    # Count user messages in session
    message_count = count_in_file(transcript_path, r'"type":"user"')

    # Skip short sessions
    if message_count < min_session_length:
        log(f'[ContinuousLearning] Session too short ({message_count} messages), skipping')
        sys.exit(0)

    # Signal to Claude that session should be evaluated for extractable patterns
    log(f'[ContinuousLearning] Session has {message_count} messages - evaluate for extractable patterns')
    log(f'[ContinuousLearning] Save learned skills to: {learned_skills_path}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'[ContinuousLearning] Error: {e}', file=sys.stderr)
        sys.exit(0)
