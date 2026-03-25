#!/usr/bin/env python3
"""
SessionStart Hook - Load previous context on new session

Cross-platform (Windows, macOS, Linux)

Runs when a new Claude session starts. Checks for recent session
files and notifies Claude of available context to load.
"""

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from utils import get_sessions_dir, get_learned_skills_dir, find_files, ensure_dir, log, get_home_dir, read_session_id_from_stdin, get_session_id_short
from package_manager import get_package_manager, get_selection_prompt
from session_aliases import list_aliases


def _iso_now():
    now = datetime.now(timezone.utc)
    return now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}Z'


def _run_git(args):
    """Run a git command silently, return stripped stdout or empty string."""
    try:
        result = subprocess.run(
            ['git'] + args,
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def _read_pipeline_state(project_root):
    """Read feature name and stage from .rix/active-pipeline.md."""
    pipeline_file = os.path.join(project_root, '.rix', 'active-pipeline.md')
    try:
        with open(pipeline_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError:
        return '', ''
    fields = {}
    for match in re.finditer(r'^- \*\*([^*]+)\*\*:\s*(.+)$', content, re.MULTILINE):
        fields[match.group(1).strip()] = match.group(2).strip()
    return fields.get('Feature', ''), fields.get('Stage', '')


def _get_plugin_version():
    """Read version from plugin.json."""
    plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
    if not plugin_root:
        plugin_root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
    plugin_json = os.path.join(plugin_root, '.claude-plugin', 'plugin.json')
    try:
        with open(plugin_json, 'r', encoding='utf-8') as f:
            return json.load(f).get('version', 'unknown')
    except (OSError, json.JSONDecodeError):
        return 'unknown'


def _cleanup_stale_cards():
    """Remove channel cards whose PIDs no longer exist.

    Cards with a pid are owned by the channel MCP server. When the server
    dies (graceful or sudden), the PID becomes invalid and this cleanup
    removes the orphaned card. Cards with pid=null older than 15 minutes
    are also removed — the MCP server should have claimed them by then.
    """
    channels_dir = os.path.join(get_home_dir(), '.claude', 'channels')
    if not os.path.isdir(channels_dir):
        return
    now = datetime.now(timezone.utc)
    for card_file in glob.glob(os.path.join(channels_dir, '*.json')):
        try:
            with open(card_file, 'r', encoding='utf-8') as f:
                card = json.load(f)
            pid = card.get('pid')
            if pid is None:
                registered = card.get('registeredAt', '')
                if registered:
                    try:
                        card_time = datetime.fromisoformat(registered.replace('Z', '+00:00'))
                        age_minutes = (now - card_time).total_seconds() / 60
                        if age_minutes > 15:
                            os.unlink(card_file)
                            log(f'[SessionStart] Cleaned up unclaimed card ({age_minutes:.0f}m old): {card_file}')
                    except (ValueError, TypeError):
                        pass
                continue
            if not isinstance(pid, int) or pid <= 0:
                continue
            os.kill(pid, 0)
        except ProcessLookupError:
            os.unlink(card_file)
            log(f'[SessionStart] Cleaned up stale card: {card_file}')
        except PermissionError:
            pass  # Process exists, owned by another user — not stale
        except (json.JSONDecodeError, OSError, TypeError):
            pass  # Skip unreadable/malformed cards


def _create_channel_card(session_id):
    """Create the channel card with session identity and project context.

    The card is created without pid/port/token — the channel MCP server
    will find it by projectRoot match and patch in its connection info.
    """
    short_id = get_session_id_short(session_id=session_id)
    if short_id == 'default':
        log('[SessionStart] No session ID available — skipping card creation')
        return

    channels_dir = os.path.join(get_home_dir(), '.claude', 'channels')
    os.makedirs(channels_dir, mode=0o700, exist_ok=True)

    project_root = _run_git(['rev-parse', '--show-toplevel']) or os.getcwd()
    repo_name = os.path.basename(project_root)
    branch = _run_git(['branch', '--show-current'])
    feature, pipeline_stage = _read_pipeline_state(project_root)

    display_parts = [p for p in [repo_name, branch] if p]
    display_name = (' — '.join(display_parts))[:60]
    now_str = _iso_now()

    card = {
        'version': 1,
        'sessionId': session_id,
        'shortId': short_id,
        'pid': None,
        'displayName': display_name,
        'projectRoot': project_root,
        'repoName': repo_name,
        'branch': branch,
        'feature': feature,
        'pipelineStage': pipeline_stage,
        'channelPort': None,
        'channelToken': None,
        'pluginVersion': _get_plugin_version(),
        'registeredAt': now_str,
        'updatedAt': now_str,
        'active': True,
    }

    card_path = os.path.join(channels_dir, f'{short_id}.json')
    fd, tmp_path = tempfile.mkstemp(dir=channels_dir, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(card, f, indent=2)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, card_path)
        log(f'[SessionStart] Created channel card: {card_path}')
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main():
    session_id = read_session_id_from_stdin()

    try:
        _cleanup_stale_cards()
    except Exception as e:
        log(f'[SessionStart] Warning: stale card cleanup failed: {e}')

    try:
        _create_channel_card(session_id)
    except Exception as e:
        log(f'[SessionStart] Warning: channel card creation failed: {e}')

    sessions_dir = get_sessions_dir()
    learned_dir = get_learned_skills_dir()

    # Ensure directories exist
    ensure_dir(sessions_dir)
    ensure_dir(learned_dir)

    # Check for recent session files (last 7 days)
    # Match both old format (YYYY-MM-DD-session.tmp) and new format (YYYY-MM-DD-shortid-session.tmp)
    recent_sessions = find_files(sessions_dir, '*-session.tmp', max_age=7)

    if recent_sessions:
        latest = recent_sessions[0]
        log(f'[SessionStart] Found {len(recent_sessions)} recent session(s)')
        log(f"[SessionStart] Latest: {latest['path']}")

    # Check for learned skills
    learned_skills = find_files(learned_dir, '*.md')

    if learned_skills:
        log(f'[SessionStart] {len(learned_skills)} learned skill(s) available in {learned_dir}')

    # Check for available session aliases
    aliases = list_aliases(limit=5)

    if aliases:
        alias_names = ', '.join(a['name'] for a in aliases)
        log(f'[SessionStart] {len(aliases)} session alias(es) available: {alias_names}')
        log('[SessionStart] Use /sessions load <alias> to continue a previous session')

    # Detect and report package manager
    pm = get_package_manager()
    log(f"[SessionStart] Package manager: {pm['name']} ({pm['source']})")

    # If package manager was detected via fallback, show selection prompt
    if pm['source'] in ('fallback', 'default'):
        log('[SessionStart] No package manager preference found.')
        log(get_selection_prompt())


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'[SessionStart] Error: {e}', file=sys.stderr)
        sys.exit(0)
