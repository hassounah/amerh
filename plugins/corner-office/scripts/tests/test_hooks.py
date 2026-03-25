"""Tests for all 6 hook scripts by importing their main() function."""

import importlib.util
import io
import json
import os
import re
import sys
import tempfile

import pytest


def _load_hook(name, path):
    """Load a hook module by file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HOOKS_DIR = os.path.join(os.path.dirname(__file__), '..', 'hooks')


@pytest.fixture
def hook_home(tmp_path, monkeypatch):
    """Set up a temporary HOME with .claude structure for hook tests."""
    home = tmp_path / 'home'
    home.mkdir()
    claude_dir = home / '.claude'
    claude_dir.mkdir()
    (claude_dir / 'sessions').mkdir()
    (claude_dir / 'skills' / 'learned').mkdir(parents=True)
    monkeypatch.setenv('HOME', str(home))
    return home


# ===================== suggest_compact =====================

class TestSuggestCompact:
    @pytest.fixture(autouse=True)
    def setup(self, hook_home, monkeypatch):
        self.home = hook_home
        self.mod = _load_hook('suggest_compact', os.path.join(HOOKS_DIR, 'suggest_compact.py'))
        monkeypatch.setenv('CLAUDE_SESSION_ID', 'test-sc-12345678')
        # Mock stdin.read to prevent pytest capture error
        monkeypatch.setattr('sys.stdin', io.StringIO(''))
        # Clean counter file (now in ~/.claude/tool-counts/)
        counter_dir = os.path.join(self.home, '.claude', 'tool-counts')
        counter = os.path.join(counter_dir, 'claude-tool-count-test-sc-12345678')
        if os.path.exists(counter):
            os.unlink(counter)

    def test_below_threshold(self, capsys, monkeypatch):
        """No output when count < threshold."""
        monkeypatch.setenv('COMPACT_THRESHOLD', '50')
        self.mod.main()
        captured = capsys.readouterr()
        assert captured.out == ''

    def test_at_threshold(self, capsys, monkeypatch):
        """Outputs suggestion at exactly threshold."""
        monkeypatch.setenv('COMPACT_THRESHOLD', '3')
        self.mod.main()  # 1
        monkeypatch.setattr('sys.stdin', io.StringIO(''))
        self.mod.main()  # 2
        capsys.readouterr()  # discard
        monkeypatch.setattr('sys.stdin', io.StringIO(''))
        self.mod.main()  # 3 = threshold
        captured = capsys.readouterr()
        assert 'tool calls reached' in captured.out
        assert 'tool calls reached' in captured.err

    def test_interval_after_threshold(self, capsys, monkeypatch):
        """Outputs at 25-call intervals after threshold."""
        monkeypatch.setenv('COMPACT_THRESHOLD', '2')
        for _ in range(2):
            monkeypatch.setattr('sys.stdin', io.StringIO(''))
            self.mod.main()
        capsys.readouterr()
        # Run from 3 to 27 (25 calls after threshold)
        for _ in range(25):
            monkeypatch.setattr('sys.stdin', io.StringIO(''))
            self.mod.main()
        captured = capsys.readouterr()
        assert 'checkpoint' in captured.err

    def test_counter_persistence(self, monkeypatch):
        """Counter file persists between calls."""
        monkeypatch.setenv('COMPACT_THRESHOLD', '999')
        self.mod.main()
        monkeypatch.setattr('sys.stdin', io.StringIO(''))
        self.mod.main()
        counter = os.path.join(self.home, '.claude', 'tool-counts', 'claude-tool-count-test-sc-12345678')
        assert os.path.exists(counter)
        with open(counter) as f:
            assert f.read().strip() == '2'


# ===================== session_end =====================

class TestSessionEnd:
    @pytest.fixture(autouse=True)
    def setup(self, hook_home, monkeypatch):
        self.home = hook_home
        self.mod = _load_hook('session_end', os.path.join(HOOKS_DIR, 'session_end.py'))
        monkeypatch.setenv('CLAUDE_SESSION_ID', 'test-se-12345678')

    def test_creates_new_file(self, capsys):
        """Creates session file with template."""
        self.mod.main()
        captured = capsys.readouterr()
        assert 'Created session file' in captured.err
        sessions_dir = self.home / '.claude' / 'sessions'
        files = list(sessions_dir.glob('*-session.tmp'))
        assert len(files) == 1
        content = files[0].read_text()
        assert '## Current State' in content
        assert '**Date:**' in content
        assert '**Started:**' in content

    def test_updates_existing_file(self, capsys):
        """Updates Last Updated timestamp on second call."""
        self.mod.main()
        capsys.readouterr()
        self.mod.main()
        captured = capsys.readouterr()
        assert 'Updated session file' in captured.err

    def test_template_format(self):
        """Template has all required sections."""
        self.mod.main()
        sessions_dir = self.home / '.claude' / 'sessions'
        files = list(sessions_dir.glob('*-session.tmp'))
        content = files[0].read_text()
        assert '### Completed' in content
        assert '### In Progress' in content
        assert '### Notes for Next Session' in content
        assert '### Context to Load' in content


# ===================== evaluate_session =====================

class TestEvaluateSession:
    @pytest.fixture(autouse=True)
    def setup(self, hook_home, monkeypatch):
        self.home = hook_home
        self.mod = _load_hook('evaluate_session', os.path.join(HOOKS_DIR, 'evaluate_session.py'))

    def test_short_session_skipped(self, capsys, monkeypatch, tmp_path):
        """Sessions under min length are skipped."""
        transcript = tmp_path / 'transcript.jsonl'
        transcript.write_text('{"type":"user"}\n' * 3)
        monkeypatch.setenv('CLAUDE_TRANSCRIPT_PATH', str(transcript))
        with pytest.raises(SystemExit):
            self.mod.main()
        captured = capsys.readouterr()
        assert 'too short' in captured.err

    def test_long_session_logged(self, capsys, monkeypatch, tmp_path):
        """Sessions over min length trigger evaluation message."""
        transcript = tmp_path / 'transcript.jsonl'
        transcript.write_text('{"type":"user"}\n' * 15)
        monkeypatch.setenv('CLAUDE_TRANSCRIPT_PATH', str(transcript))
        self.mod.main()
        captured = capsys.readouterr()
        assert '15 messages' in captured.err
        assert 'evaluate for extractable patterns' in captured.err

    def test_no_transcript(self, capsys, monkeypatch):
        """Exits silently when no transcript."""
        monkeypatch.delenv('CLAUDE_TRANSCRIPT_PATH', raising=False)
        with pytest.raises(SystemExit):
            self.mod.main()

    def test_config_override(self, capsys, monkeypatch, tmp_path):
        """Respects min_session_length from config.json."""
        # Resolve real path so dirname(dirname(...)) traverses correctly
        real_hooks = os.path.realpath(HOOKS_DIR)
        config_dir = os.path.join(
            os.path.dirname(os.path.dirname(real_hooks)),
            'skills', 'continuous-learning-v2'
        )
        os.makedirs(config_dir, exist_ok=True)
        config_file = os.path.join(config_dir, 'config.json')
        # Back up existing config
        backup = None
        if os.path.exists(config_file):
            with open(config_file) as f:
                backup = f.read()
        try:
            with open(config_file, 'w') as f:
                json.dump({'min_session_length': 20}, f)

            transcript = tmp_path / 'transcript.jsonl'
            transcript.write_text('{"type":"user"}\n' * 15)
            monkeypatch.setenv('CLAUDE_TRANSCRIPT_PATH', str(transcript))
            with pytest.raises(SystemExit):
                self.mod.main()
            captured = capsys.readouterr()
            assert 'too short' in captured.err
        finally:
            # Restore original config
            if backup is not None:
                with open(config_file, 'w') as f:
                    f.write(backup)


# ===================== session_start =====================

class TestSessionStart:
    @pytest.fixture(autouse=True)
    def setup(self, hook_home, monkeypatch):
        self.home = hook_home
        self.mod = _load_hook('session_start', os.path.join(HOOKS_DIR, 'session_start.py'))

    def test_no_sessions(self, capsys):
        """Runs without error when no sessions exist."""
        self.mod.main()
        captured = capsys.readouterr()
        assert 'Package manager' in captured.err

    def test_finds_recent_sessions(self, capsys):
        """Finds and reports recent session files."""
        sessions_dir = self.home / '.claude' / 'sessions'
        (sessions_dir / '2026-03-08-abcd1234-session.tmp').write_text('test')
        self.mod.main()
        captured = capsys.readouterr()
        assert '1 recent session' in captured.err

    def test_detects_package_manager(self, capsys):
        """Reports detected package manager."""
        self.mod.main()
        captured = capsys.readouterr()
        assert 'Package manager:' in captured.err

    def test_pm_fallback_prompt(self, capsys, monkeypatch):
        """Shows selection prompt for fallback/default PM source."""
        # Ensure no PM detection triggers
        monkeypatch.delenv('CLAUDE_PACKAGE_MANAGER', raising=False)
        self.mod.main()
        captured = capsys.readouterr()
        # Should be fallback or default
        assert 'Package manager' in captured.err

    def test_shows_aliases(self, capsys):
        """Reports aliases when they exist."""
        # Create an aliases file
        aliases_data = {
            'version': '1.0',
            'aliases': {
                'my-project': {
                    'sessionPath': '/path/to/session',
                    'createdAt': '2026-01-01T00:00:00Z',
                    'updatedAt': '2026-01-01T00:00:00Z',
                    'title': 'Test',
                }
            },
            'metadata': {'totalCount': 1, 'lastUpdated': '2026-01-01T00:00:00Z'},
        }
        aliases_path = self.home / '.claude' / 'session-aliases.json'
        aliases_path.write_text(json.dumps(aliases_data))
        self.mod.main()
        captured = capsys.readouterr()
        assert 'alias' in captured.err.lower()
        assert 'my-project' in captured.err


# ===================== pre_compact =====================

class TestPreCompact:
    @pytest.fixture(autouse=True)
    def setup(self, hook_home, monkeypatch):
        self.home = hook_home
        self.mod = _load_hook('pre_compact', os.path.join(HOOKS_DIR, 'pre_compact.py'))

    def test_logs_compaction(self, capsys):
        """Logs compaction event."""
        self.mod.main()
        captured = capsys.readouterr()
        assert 'State saved before compaction' in captured.err

    def test_notes_active_session(self, capsys):
        """Appends compaction note to active session file."""
        sessions_dir = self.home / '.claude' / 'sessions'
        session_file = sessions_dir / '2026-03-08-abcd1234-session.tmp'
        session_file.write_text('# Session\n')
        self.mod.main()
        content = session_file.read_text()
        assert 'Compaction occurred' in content

    def test_output_summary(self, capsys):
        """Outputs summary to stdout."""
        self.mod.main()
        captured = capsys.readouterr()
        assert 'State saved before compaction' in captured.out

    def test_handoff_without_pipeline(self, capsys, monkeypatch):
        """Creates handoff even without .rix/active-pipeline.md."""
        # Mock git to return a git root
        monkeypatch.setattr(
            'utils.run_command',
            lambda cmd, **kw: {
                'success': 'branch' in cmd,
                'output': 'main' if 'branch' in cmd else '',
            },
        )
        self.mod.main()
        captured = capsys.readouterr()
        # Should still have handoff output
        assert 'Handoff saved' in captured.err or 'State saved' in captured.err

    def test_graceful_degradation(self, capsys, monkeypatch):
        """Falls back to minimal handoff on error."""
        # Mock generate_handoff in the utils module (loaded via sys.path.insert)
        utils_mod = sys.modules.get('utils')
        if utils_mod:
            def failing_handoff(caller='Hook'):
                raise RuntimeError('forced error')
            monkeypatch.setattr(utils_mod, 'generate_handoff', failing_handoff)
        self.mod.main()
        captured = capsys.readouterr()
        # Should have minimal handoff or graceful message
        assert 'PreCompact' in captured.err


# ===================== check_console_log =====================

class TestCheckConsoleLog:
    @pytest.fixture(autouse=True)
    def setup(self, hook_home, monkeypatch):
        self.mod = _load_hook('check_console_log', os.path.join(HOOKS_DIR, 'check_console_log.py'))

    def test_passthrough(self, capsys, monkeypatch):
        """Always outputs stdin data."""
        monkeypatch.setattr('sys.stdin', io.StringIO('original data'))
        # Mock git to fail (not a repo)
        import subprocess
        monkeypatch.setattr(
            subprocess, 'run',
            lambda *a, **kw: type('R', (), {'returncode': 1, 'stdout': '', 'stderr': ''})()
        )
        self.mod.main()
        captured = capsys.readouterr()
        assert 'original data' in captured.out

    def test_warns_on_console_log(self, capsys, monkeypatch, tmp_path):
        """Warns when modified JS files contain console.log."""
        monkeypatch.setattr('sys.stdin', io.StringIO('passthrough'))
        monkeypatch.chdir(tmp_path)

        # Create a JS file with console.log
        js_file = tmp_path / 'test.js'
        js_file.write_text('console.log("debug")')

        import subprocess
        call_count = [0]
        def mock_run(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else kwargs.get('args', [])
            result = type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
            if 'rev-parse' in cmd:
                result.returncode = 0
            elif 'diff' in cmd:
                result.stdout = 'test.js\n'
            return result

        monkeypatch.setattr(subprocess, 'run', mock_run)
        self.mod.main()
        captured = capsys.readouterr()
        assert 'passthrough' in captured.out
        assert 'console.log' in captured.err

    def test_no_git(self, capsys, monkeypatch):
        """Passes through when not in git repo."""
        monkeypatch.setattr('sys.stdin', io.StringIO('data'))
        import subprocess
        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(1, 'git')
        monkeypatch.setattr(subprocess, 'run', mock_run)
        self.mod.main()
        captured = capsys.readouterr()
        assert 'data' in captured.out

    def test_no_modified_files(self, capsys, monkeypatch):
        """No warnings when no JS/TS files modified."""
        monkeypatch.setattr('sys.stdin', io.StringIO('data'))
        import subprocess
        def mock_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get('args', [])
            result = type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
            if 'diff' in cmd:
                result.stdout = 'readme.md\n'
            return result
        monkeypatch.setattr(subprocess, 'run', mock_run)
        self.mod.main()
        captured = capsys.readouterr()
        assert 'data' in captured.out
        assert 'console.log' not in captured.err


# ===================== emit_activity =====================

class _FakeBinaryStdin:
    """Wraps bytes as a stdin-like object with a .buffer attribute."""
    def __init__(self, data: bytes):
        self.buffer = io.BytesIO(data)


class TestEmitActivity:
    @pytest.fixture(autouse=True)
    def setup(self, hook_home, monkeypatch):
        self.home = hook_home
        self.mod = _load_hook('emit_activity', os.path.join(HOOKS_DIR, 'emit_activity.py'))

    def _stdin(self, data: dict):
        return _FakeBinaryStdin(json.dumps(data).encode())

    def _event_path(self, cwd, session_id):
        name = os.path.basename(cwd.rstrip('/'))
        workspace = re.sub(r'[^a-zA-Z0-9_-]', '', name)[:64] or 'unknown'
        short_id = session_id[-8:] if session_id else 'unknown'
        return self.home / '.corner-office' / 'events' / workspace / f'{short_id}.jsonl'

    def test_writes_jsonl_event(self, monkeypatch):
        """Valid JSON stdin → JSONL at expected path with required fields."""
        cwd = '/projects/myrepo'
        session_id = 'abc12345def67890'
        monkeypatch.setattr(sys, 'stdin', self._stdin(
            {'hook_event_name': 'PreToolUse', 'session_id': session_id, 'cwd': cwd}
        ))
        self.mod.main()
        path = self._event_path(cwd, session_id)
        assert path.exists()
        entry = json.loads(path.read_text().strip())
        assert entry['event'] == 'PreToolUse'
        assert entry['sessionId'] == session_id
        assert 'timestamp' in entry
        assert entry['workspace'] == 'myrepo'

    def test_workspace_slug_sanitization(self, monkeypatch):
        """cwd with special chars → clean alphanumeric slug."""
        cwd = '/projects/my repo--with spaces!'
        session_id = 'test12345678'
        monkeypatch.setattr(sys, 'stdin', self._stdin(
            {'hook_event_name': 'Stop', 'session_id': session_id, 'cwd': cwd}
        ))
        self.mod.main()
        workspace_dir = self.home / '.corner-office' / 'events'
        dirs = list(workspace_dir.iterdir())
        assert len(dirs) == 1
        assert re.match(r'^[a-zA-Z0-9_-]+$', dirs[0].name)

    def test_unknown_event_type(self, monkeypatch):
        """Unusual hook_event_name passes through and is recorded."""
        cwd = '/projects/test'
        session_id = 'futu1234'
        monkeypatch.setattr(sys, 'stdin', self._stdin(
            {'hook_event_name': 'SomeFutureEvent', 'session_id': session_id, 'cwd': cwd}
        ))
        self.mod.main()
        path = self._event_path(cwd, session_id)
        assert path.exists()
        entry = json.loads(path.read_text().strip())
        assert entry['event'] == 'SomeFutureEvent'

    def test_large_field_truncation(self, monkeypatch):
        """tool_input > 32KB → truncated with '[truncated from N bytes]' suffix."""
        large_value = 'x' * 40000  # > 32KB
        monkeypatch.setattr(sys, 'stdin', self._stdin({
            'hook_event_name': 'PreToolUse',
            'session_id': 'bigf5678',
            'cwd': '/projects/test',
            'tool_input': {'content': large_value},
        }))
        self.mod.main()
        path = self.home / '.corner-office' / 'events' / 'test' / 'bigf5678.jsonl'
        entry = json.loads(path.read_text().strip())
        content = entry['tool_input']['content']
        assert len(content) < 40000
        assert '[truncated from' in content

    def test_empty_stdin(self, monkeypatch):
        """Empty stdin → no crash, no output file created."""
        monkeypatch.setattr(sys, 'stdin', _FakeBinaryStdin(b''))
        self.mod.main()
        events_dir = self.home / '.corner-office' / 'events'
        assert not events_dir.exists()

    def test_per_session_file_isolation(self, monkeypatch):
        """Two calls with different session IDs → two separate JSONL files."""
        cwd = '/projects/myrepo'
        monkeypatch.setattr(sys, 'stdin', self._stdin(
            {'hook_event_name': 'Stop', 'session_id': 'aaaa1234', 'cwd': cwd}
        ))
        self.mod.main()
        monkeypatch.setattr(sys, 'stdin', self._stdin(
            {'hook_event_name': 'Stop', 'session_id': 'bbbb5678', 'cwd': cwd}
        ))
        self.mod.main()
        workspace_dir = self.home / '.corner-office' / 'events' / 'myrepo'
        files = list(workspace_dir.glob('*.jsonl'))
        assert len(files) == 2

    def test_file_permissions(self, monkeypatch):
        """JSONL file is 0o600, events directory is 0o700."""
        monkeypatch.setattr(sys, 'stdin', self._stdin(
            {'hook_event_name': 'Stop', 'session_id': 'permtest', 'cwd': '/projects/myrepo'}
        ))
        self.mod.main()
        workspace_dir = self.home / '.corner-office' / 'events' / 'myrepo'
        assert oct(workspace_dir.stat().st_mode & 0o777) == oct(0o700)
        jsonl_file = workspace_dir / 'permtest.jsonl'  # session_id[-8:] == 'permtest'
        assert oct(jsonl_file.stat().st_mode & 0o777) == oct(0o600)


# ===================== session_registration =====================

class TestStaleCardCleanup:
    """Channel cards are created by the MCP channel server. session_start.py
    only runs PID-based cleanup for cards whose owning process has died."""

    @pytest.fixture(autouse=True)
    def setup(self, hook_home, monkeypatch):
        self.home = hook_home
        self.start_mod = _load_hook('session_start', os.path.join(HOOKS_DIR, 'session_start.py'))

    def _channels_dir(self):
        return self.home / '.claude' / 'channels'

    def test_stale_card_cleanup(self, monkeypatch):
        """Card with dead PID is removed by _cleanup_stale_cards."""
        channels_dir = self._channels_dir()
        channels_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        stale = channels_dir / 'stale-dead.json'
        stale.write_text(json.dumps({'pid': 9999997, 'sessionId': 'dead'}))
        real_kill = os.kill
        def mock_kill(pid, sig):
            if pid == 9999997:
                raise ProcessLookupError
            real_kill(pid, sig)
        monkeypatch.setattr(os, 'kill', mock_kill)
        self.start_mod._cleanup_stale_cards()
        assert not stale.exists()

    def test_live_card_preserved(self, monkeypatch):
        """Card with live PID is not removed."""
        channels_dir = self._channels_dir()
        channels_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        live = channels_dir / 'live-card.json'
        live.write_text(json.dumps({'pid': os.getpid(), 'sessionId': 'live'}))
        self.start_mod._cleanup_stale_cards()
        assert live.exists()

    def test_no_channels_dir(self):
        """No channels directory → no crash."""
        self.start_mod._cleanup_stale_cards()  # Should not raise


# ===================== refresh_registration =====================

class TestRefreshRegistration:
    @pytest.fixture(autouse=True)
    def setup(self, hook_home, monkeypatch):
        self.home = hook_home
        (hook_home / '.claude' / 'channels').mkdir(parents=True, exist_ok=True)
        self.mod = _load_hook('refresh_registration', os.path.join(HOOKS_DIR, 'refresh_registration.py'))
        monkeypatch.setenv('CLAUDE_SESSION_ID', 'rfrsh12345678')
        # short_id = '12345678' (last 8 of 'rfrsh12345678')
        utils_mod = sys.modules.get('utils')
        assert utils_mod is not None, "utils not in sys.modules — patch not applied"
        monkeypatch.setattr(utils_mod, 'run_command', lambda cmd, **kw: {
            'success': False, 'output': '',
        })

    def _card_path(self):
        return self.home / '.claude' / 'channels' / '12345678.json'

    def _write_card(self, feature='old-feature', pipelineStage='design'):
        # Use the same schema as session_start.py (pipelineStage, not stage)
        card = {
            'sessionId': 'rfrsh12345678',
            'shortId': '12345678',
            'feature': feature,
            'pipelineStage': pipelineStage,
            'updatedAt': '2026-01-01T00:00:00.000Z',
        }
        self._card_path().write_text(json.dumps(card))
        return self._card_path()

    def _write_pipeline(self, feature='new-feature', stage='implement', tmp_path=None):
        base = tmp_path or self.home
        pipeline_path = base / 'project' / '.rix' / 'active-pipeline.md'
        pipeline_path.parent.mkdir(parents=True, exist_ok=True)
        pipeline_path.write_text(f'- **Feature**: {feature}\n- **Stage**: {stage}\n')
        return pipeline_path

    def test_updates_pipeline_fields(self, monkeypatch, tmp_path):
        """Write event to active-pipeline.md → card feature/pipelineStage updated."""
        self._write_card('old-feature', 'design')
        pipeline_path = self._write_pipeline('new-feature', 'implement', tmp_path)
        event = {'tool_name': 'Write', 'tool_input': {'file_path': str(pipeline_path)}}
        monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(event)))
        self.mod.main()
        card = json.loads(self._card_path().read_text())
        assert card['feature'] == 'new-feature'
        assert card['pipelineStage'] == 'implement'
        assert 'stage' not in card  # Must not create a spurious 'stage' key

    def test_noop_for_non_pipeline_write(self, monkeypatch, tmp_path):
        """Write to README.md → card unchanged."""
        self._write_card('old-feature', 'design')
        event = {'tool_name': 'Write', 'tool_input': {'file_path': str(tmp_path / 'README.md')}}
        monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(event)))
        self.mod.main()
        card = json.loads(self._card_path().read_text())
        assert card['feature'] == 'old-feature'

    def test_noop_for_non_write_tool(self, monkeypatch, tmp_path):
        """Edit event → returns early, card unchanged."""
        self._write_card('old-feature', 'design')
        pipeline_path = self._write_pipeline('new-feature', 'implement', tmp_path)
        event = {'tool_name': 'Edit', 'tool_input': {'file_path': str(pipeline_path)}}
        monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(event)))
        self.mod.main()
        card = json.loads(self._card_path().read_text())
        assert card['feature'] == 'old-feature'

    def test_missing_card(self, monkeypatch, tmp_path):
        """No card present → no error raised."""
        pipeline_path = self._write_pipeline(tmp_path=tmp_path)
        event = {'tool_name': 'Write', 'tool_input': {'file_path': str(pipeline_path)}}
        monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(event)))
        self.mod.main()  # Should not raise

    def test_empty_stdin(self, monkeypatch):
        """Empty stdin → no crash."""
        monkeypatch.setattr(sys, 'stdin', io.StringIO(''))
        self.mod.main()  # Should not raise

    def test_malformed_json_stdin(self, monkeypatch):
        """Invalid JSON stdin → no crash."""
        monkeypatch.setattr(sys, 'stdin', io.StringIO('not json {{{'))
        self.mod.main()  # Should not raise


# ===================== evaluate_session (enhanced) =====================

class TestEvaluateSessionEnhanced:
    @pytest.fixture(autouse=True)
    def setup(self, hook_home, monkeypatch):
        self.home = hook_home
        self.mod = _load_hook('evaluate_session', os.path.join(HOOKS_DIR, 'evaluate_session.py'))
        monkeypatch.setenv('CLAUDE_SESSION_ID', 'eval-sess12345678')
        # short_id = '12345678' (last 8 of 'eval-sess12345678')
        monkeypatch.delenv('CLAUDE_TRANSCRIPT_PATH', raising=False)
        self.workspace = 'myproject'
        self.short_id = 'eval-sess12345678'[-8:]  # '12345678'
        # Fail git so workspace = basename(cwd)
        utils_mod = sys.modules.get('utils')
        assert utils_mod is not None, "utils not in sys.modules — patch not applied"
        monkeypatch.setattr(utils_mod, 'run_command', lambda cmd, **kw: {
            'success': False, 'output': '',
        })

    def _create_event_file(self, num_events, monkeypatch, tmp_path):
        project_dir = tmp_path / self.workspace
        project_dir.mkdir(exist_ok=True)
        monkeypatch.chdir(project_dir)
        events_dir = self.home / '.corner-office' / 'events' / self.workspace
        events_dir.mkdir(parents=True, exist_ok=True)
        event_file = events_dir / f'{self.short_id}.jsonl'
        lines = [json.dumps({'event': 'PreToolUse', 'sessionId': 'x'}) for _ in range(num_events)]
        event_file.write_text('\n'.join(lines) + '\n')
        return event_file

    def test_reads_session_event_file(self, capsys, monkeypatch, tmp_path):
        """JSONL with > min_session_length events → log shows count."""
        self._create_event_file(15, monkeypatch, tmp_path)
        self.mod.main()
        captured = capsys.readouterr()
        assert '15 events' in captured.err
        assert 'evaluate for extractable patterns' in captured.err

    def test_falls_back_to_transcript(self, capsys, monkeypatch, tmp_path):
        """No event file → falls back to CLAUDE_TRANSCRIPT_PATH logic."""
        project_dir = tmp_path / self.workspace
        project_dir.mkdir(exist_ok=True)
        monkeypatch.chdir(project_dir)
        transcript = tmp_path / 'transcript.jsonl'
        transcript.write_text('{"type":"user"}\n' * 15)
        monkeypatch.setenv('CLAUDE_TRANSCRIPT_PATH', str(transcript))
        self.mod.main()
        captured = capsys.readouterr()
        assert '15 messages' in captured.err

    def test_short_session_from_events(self, capsys, monkeypatch, tmp_path):
        """Event file with few events → 'too short' log and sys.exit."""
        self._create_event_file(3, monkeypatch, tmp_path)
        with pytest.raises(SystemExit):
            self.mod.main()
        captured = capsys.readouterr()
        assert 'too short' in captured.err

    def test_corrupted_jsonl_lines_skipped(self, capsys, monkeypatch, tmp_path):
        """Corrupted JSONL lines are skipped with stderr warning, valid lines counted."""
        project_dir = tmp_path / self.workspace
        project_dir.mkdir(exist_ok=True)
        monkeypatch.chdir(project_dir)
        events_dir = self.home / '.corner-office' / 'events' / self.workspace
        events_dir.mkdir(parents=True, exist_ok=True)
        event_file = events_dir / f'{self.short_id}.jsonl'
        valid_line = json.dumps({'event': 'PreToolUse', 'sessionId': 'x'})
        # Mix valid and corrupted lines (15 valid → above min threshold)
        lines = [valid_line] * 7 + ['not json {{{'] + [valid_line] * 8
        event_file.write_text('\n'.join(lines) + '\n')
        self.mod.main()
        captured = capsys.readouterr()
        assert 'corrupted' in captured.err or 'skipping' in captured.err
        assert '15 events' in captured.err
