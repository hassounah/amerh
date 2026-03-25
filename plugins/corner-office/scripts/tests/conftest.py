import os
import sys

import pytest

# Add lib to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """Provide a temporary home directory with .claude structure."""
    home = tmp_path / "home"
    home.mkdir()
    claude_dir = home / ".claude"
    claude_dir.mkdir()
    (claude_dir / "sessions").mkdir()
    (claude_dir / "skills" / "learned").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def tmp_project(tmp_path):
    """Provide a temporary project directory."""
    project = tmp_path / "project"
    project.mkdir()
    return project


@pytest.fixture
def mock_env(monkeypatch):
    """Helper to set/unset environment variables."""
    def _set(**kwargs):
        for key, value in kwargs.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
    return _set


@pytest.fixture
def no_git(monkeypatch):
    """Ensure git commands fail (for non-repo tests)."""
    monkeypatch.setenv("GIT_DIR", "/nonexistent")
