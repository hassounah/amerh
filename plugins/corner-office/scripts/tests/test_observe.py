"""Tests for observe.py — the hot-path observation hook."""

import io
import json
import os
import signal
import sys

import pytest

import importlib.util


@pytest.fixture
def observe_mod():
    """Load the observe module."""
    observe_path = os.path.join(
        os.path.dirname(__file__), '..', '..', 'skills',
        'continuous-learning-v2', 'hooks', 'observe.py'
    )
    spec = importlib.util.spec_from_file_location('observe', observe_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Set up temp HOME so observe uses tmp config dir."""
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    cfg = home / '.claude' / 'homunculus'
    cfg.mkdir(parents=True)
    return cfg


def _run_observe(observe_mod, stdin_data, monkeypatch):
    """Helper to run observe.main() with given stdin."""
    monkeypatch.setattr('sys.stdin', io.StringIO(stdin_data))
    try:
        observe_mod.main()
    except SystemExit:
        pass


def _read_observations(config_dir):
    """Read observations JSONL file."""
    obs_file = config_dir / 'observations.jsonl'
    if not obs_file.exists():
        return []
    lines = obs_file.read_text().strip().split('\n')
    return [json.loads(line) for line in lines if line]


class TestObservePrePost:
    def test_pre_tool_event(self, observe_mod, config_dir, monkeypatch):
        """PreToolUse generates tool_start event."""
        data = json.dumps({
            'hook_type': 'PreToolUse',
            'tool_name': 'Read',
            'tool_input': {'path': '/test.py'},
            'session_id': 'sess123',
        })
        _run_observe(observe_mod, data, monkeypatch)
        obs = _read_observations(config_dir)
        assert len(obs) == 1
        assert obs[0]['event'] == 'tool_start'
        assert obs[0]['tool'] == 'Read'
        assert 'input' in obs[0]
        assert 'output' not in obs[0]

    def test_post_tool_event(self, observe_mod, config_dir, monkeypatch):
        """PostToolUse generates tool_complete event."""
        data = json.dumps({
            'hook_type': 'PostToolUse',
            'tool_name': 'Write',
            'tool_output': 'File written',
            'session_id': 'sess123',
        })
        _run_observe(observe_mod, data, monkeypatch)
        obs = _read_observations(config_dir)
        assert len(obs) == 1
        assert obs[0]['event'] == 'tool_complete'
        assert obs[0]['tool'] == 'Write'
        assert 'output' in obs[0]
        assert 'input' not in obs[0]


class TestObserveTruncation:
    def test_truncates_large_input(self, observe_mod, config_dir, monkeypatch):
        """Input over 5000 chars is truncated."""
        large_input = {'data': 'x' * 10000}
        data = json.dumps({
            'hook_type': 'PreToolUse',
            'tool_name': 'Read',
            'tool_input': large_input,
            'session_id': 'sess123',
        })
        _run_observe(observe_mod, data, monkeypatch)
        obs = _read_observations(config_dir)
        assert len(obs[0].get('input', '')) <= 5000

    def test_truncates_large_output(self, observe_mod, config_dir, monkeypatch):
        """Output over 5000 chars is truncated."""
        data = json.dumps({
            'hook_type': 'PostToolUse',
            'tool_name': 'Read',
            'tool_output': 'y' * 10000,
            'session_id': 'sess123',
        })
        _run_observe(observe_mod, data, monkeypatch)
        obs = _read_observations(config_dir)
        assert len(obs[0].get('output', '')) <= 5000


class TestObserveEdgeCases:
    def test_empty_stdin(self, observe_mod, config_dir, monkeypatch):
        """Exits cleanly with no input."""
        _run_observe(observe_mod, '', monkeypatch)
        obs = _read_observations(config_dir)
        assert len(obs) == 0

    def test_invalid_json(self, observe_mod, config_dir, monkeypatch):
        """Logs parse error for invalid JSON."""
        _run_observe(observe_mod, 'not valid json{{{', monkeypatch)
        obs = _read_observations(config_dir)
        assert len(obs) == 1
        assert obs[0]['event'] == 'parse_error'

    def test_disabled_sentinel(self, observe_mod, config_dir, monkeypatch):
        """Exits when disabled file exists."""
        (config_dir / 'disabled').write_text('')
        data = json.dumps({
            'hook_type': 'PreToolUse',
            'tool_name': 'Read',
            'session_id': 'sess123',
        })
        _run_observe(observe_mod, data, monkeypatch)
        obs = _read_observations(config_dir)
        assert len(obs) == 0


class TestObserveArchival:
    def test_archives_large_file(self, observe_mod, config_dir, monkeypatch):
        """Archives observations file when it exceeds 10MB."""
        obs_file = config_dir / 'observations.jsonl'
        # Create a file just over 10MB
        obs_file.write_text('x' * (10 * 1024 * 1024 + 1))

        data = json.dumps({
            'hook_type': 'PreToolUse',
            'tool_name': 'Read',
            'session_id': 'sess123',
        })
        _run_observe(observe_mod, data, monkeypatch)

        archive_dir = config_dir / 'observations.archive'
        assert archive_dir.exists()
        archived = list(archive_dir.glob('observations-*.jsonl'))
        assert len(archived) == 1


class TestObserveSignaling:
    def test_signals_observer(self, observe_mod, config_dir, monkeypatch):
        """Sends SIGUSR1 to observer PID."""
        pid_file = config_dir / '.observer.pid'
        pid_file.write_text(str(os.getpid()))

        signaled = [False]
        original_handler = signal.getsignal(signal.SIGUSR1)

        def handler(signum, frame):
            signaled[0] = True

        signal.signal(signal.SIGUSR1, handler)

        data = json.dumps({
            'hook_type': 'PreToolUse',
            'tool_name': 'Read',
            'session_id': 'sess123',
        })
        _run_observe(observe_mod, data, monkeypatch)

        signal.signal(signal.SIGUSR1, original_handler)
        assert signaled[0] is True

    def test_stale_pid(self, observe_mod, config_dir, monkeypatch):
        """Handles stale PID file gracefully."""
        pid_file = config_dir / '.observer.pid'
        pid_file.write_text('99999999')  # Very likely nonexistent PID

        data = json.dumps({
            'hook_type': 'PreToolUse',
            'tool_name': 'Read',
            'session_id': 'sess123',
        })
        # Should not raise
        _run_observe(observe_mod, data, monkeypatch)
        obs = _read_observations(config_dir)
        assert len(obs) == 1


class TestObserveJSONL:
    def test_jsonl_format(self, observe_mod, config_dir, monkeypatch):
        """Each observation is one line of valid JSON."""
        for i in range(3):
            monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps({
                'hook_type': 'PreToolUse',
                'tool_name': f'Tool{i}',
                'session_id': 'sess123',
            })))
            try:
                observe_mod.main()
            except SystemExit:
                pass

        obs_file = config_dir / 'observations.jsonl'
        lines = obs_file.read_text().strip().split('\n')
        assert len(lines) == 3
        for line in lines:
            parsed = json.loads(line)
            assert 'timestamp' in parsed
            assert 'event' in parsed
            assert 'tool' in parsed

    def test_creates_config_dir(self, observe_mod, tmp_path, monkeypatch):
        """Creates ~/.claude/homunculus if missing."""
        home = tmp_path / 'fresh_home'
        home.mkdir()
        monkeypatch.setenv('HOME', str(home))
        data = json.dumps({
            'hook_type': 'PreToolUse',
            'tool_name': 'Read',
            'session_id': 'sess123',
        })
        _run_observe(observe_mod, data, monkeypatch)
        assert (home / '.claude' / 'homunculus').exists()
