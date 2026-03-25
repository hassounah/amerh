"""Tests for session_manager.py."""

import os
import time

import pytest

import session_manager


@pytest.fixture
def sessions_dir(tmp_home):
    """Provide sessions directory inside tmp_home."""
    return os.path.join(str(tmp_home), '.claude', 'sessions')


def _create_session(sessions_dir, filename, content='', mtime_offset=0):
    """Helper to create a session file with optional mtime adjustment."""
    path = os.path.join(sessions_dir, filename)
    with open(path, 'w') as f:
        f.write(content)
    if mtime_offset:
        t = time.time() + mtime_offset
        os.utime(path, (t, t))
    return path


SAMPLE_SESSION_CONTENT = """# Session: My Test Session
**Date:** 2026-03-01
**Started:** 09:00
**Last Updated:** 10:30

---

## Current State

Working on tests.

### Completed
- [x] Set up project
- [x] Write utils

### In Progress
- [ ] Write tests

### Notes for Next Session
Remember to check coverage.

### Context to Load
```
plugins/corner-office/scripts/lib/utils.py
```
"""


# --- parse_session_filename ---

class TestParseSessionFilename:
    def test_parse_filename_new_format(self):
        """Parses 2026-02-01-abc12345-session.tmp."""
        result = session_manager.parse_session_filename('2026-02-01-abc12345-session.tmp')
        assert result is not None
        assert result['date'] == '2026-02-01'
        assert result['shortId'] == 'abc12345'
        assert result['filename'] == '2026-02-01-abc12345-session.tmp'

    def test_parse_filename_old_format(self):
        """Parses 2026-02-01-session.tmp, shortId = 'no-id'."""
        result = session_manager.parse_session_filename('2026-02-01-session.tmp')
        assert result is not None
        assert result['date'] == '2026-02-01'
        assert result['shortId'] == 'no-id'

    def test_parse_filename_invalid(self):
        """Returns None for non-matching filenames."""
        assert session_manager.parse_session_filename('random.txt') is None
        assert session_manager.parse_session_filename('2026-02-01.tmp') is None
        assert session_manager.parse_session_filename('2026-02-01-ab-session.tmp') is None  # short id < 8 chars


# --- get_session_path ---

class TestGetSessionPath:
    def test_get_session_path(self, tmp_home):
        """Returns full path in sessions dir."""
        path = session_manager.get_session_path('2026-01-01-session.tmp')
        expected = os.path.join(str(tmp_home), '.claude', 'sessions', '2026-01-01-session.tmp')
        assert path == expected


# --- get_session_content ---

class TestGetSessionContent:
    def test_get_session_content_exists(self, sessions_dir):
        """Returns file content."""
        path = _create_session(sessions_dir, '2026-01-01-session.tmp', 'hello')
        assert session_manager.get_session_content(path) == 'hello'

    def test_get_session_content_missing(self):
        """Returns None for nonexistent file."""
        assert session_manager.get_session_content('/nonexistent/path.tmp') is None


# --- parse_session_metadata ---

class TestParseSessionMetadata:
    def test_parse_metadata_full(self):
        """Extracts all metadata fields from full content."""
        result = session_manager.parse_session_metadata(SAMPLE_SESSION_CONTENT)
        assert result['title'] == 'Session: My Test Session'
        assert result['date'] == '2026-03-01'
        assert result['started'] == '09:00'
        assert result['lastUpdated'] == '10:30'
        assert len(result['completed']) == 2
        assert 'Set up project' in result['completed']
        assert len(result['inProgress']) == 1
        assert 'Write tests' in result['inProgress']
        assert 'coverage' in result['notes']
        assert 'utils.py' in result['context']

    def test_parse_metadata_empty(self):
        """Returns defaults for empty/None content."""
        result = session_manager.parse_session_metadata(None)
        assert result['title'] is None
        assert result['completed'] == []
        result2 = session_manager.parse_session_metadata('')
        assert result2['title'] is None

    def test_parse_metadata_partial(self):
        """Handles content with only some sections."""
        content = "# Just a Title\n\nSome text."
        result = session_manager.parse_session_metadata(content)
        assert result['title'] == 'Just a Title'
        assert result['date'] is None
        assert result['completed'] == []


# --- get_session_stats ---

class TestGetSessionStats:
    def test_get_session_stats(self, sessions_dir):
        """Returns correct counts."""
        path = _create_session(sessions_dir, '2026-01-01-session.tmp', SAMPLE_SESSION_CONTENT)
        stats = session_manager.get_session_stats(path)
        assert stats['completedItems'] == 2
        assert stats['inProgressItems'] == 1
        assert stats['totalItems'] == 3
        assert stats['lineCount'] > 0
        assert stats['hasNotes'] is True
        assert stats['hasContext'] is True


# --- get_all_sessions ---

class TestGetAllSessions:
    def test_get_all_sessions_empty(self, tmp_home, monkeypatch):
        """Returns empty list when dir missing."""
        # Point to nonexistent dir
        monkeypatch.setattr(session_manager, 'get_sessions_dir', lambda: '/nonexistent')
        result = session_manager.get_all_sessions()
        assert result['sessions'] == []
        assert result['total'] == 0

    def test_get_all_sessions_pagination(self, sessions_dir):
        """Respects offset and limit."""
        for i in range(5):
            _create_session(
                sessions_dir,
                f'2026-01-0{i+1}-abcd1234-session.tmp',
                f'session {i}',
                mtime_offset=-i,  # different mtimes
            )
        result = session_manager.get_all_sessions(limit=2, offset=0)
        assert len(result['sessions']) == 2
        assert result['total'] == 5
        assert result['hasMore'] is True

        result2 = session_manager.get_all_sessions(limit=2, offset=4)
        assert len(result2['sessions']) == 1
        assert result2['hasMore'] is False

    def test_get_all_sessions_date_filter(self, sessions_dir):
        """Filters by date."""
        _create_session(sessions_dir, '2026-03-01-abcd1234-session.tmp', 'march')
        _create_session(sessions_dir, '2026-04-01-efgh5678-session.tmp', 'april')
        result = session_manager.get_all_sessions(date='2026-03-01')
        assert len(result['sessions']) == 1
        assert result['sessions'][0]['date'] == '2026-03-01'

    def test_get_all_sessions_search_filter(self, sessions_dir):
        """Filters by short ID."""
        _create_session(sessions_dir, '2026-01-01-abcd1234-session.tmp', 'a')
        _create_session(sessions_dir, '2026-01-01-efgh5678-session.tmp', 'b')
        result = session_manager.get_all_sessions(search='abcd')
        assert len(result['sessions']) == 1

    def test_get_all_sessions_sorted(self, sessions_dir):
        """Sorted by mtime newest first."""
        _create_session(sessions_dir, '2026-01-01-aaaa1111-session.tmp', 'old', mtime_offset=-100)
        _create_session(sessions_dir, '2026-01-02-bbbb2222-session.tmp', 'new', mtime_offset=0)
        result = session_manager.get_all_sessions()
        assert len(result['sessions']) == 2
        assert result['sessions'][0]['shortId'] == 'bbbb2222'


# --- get_session_by_id ---

class TestGetSessionById:
    def test_get_session_by_id_short(self, sessions_dir):
        """Finds session by short ID prefix."""
        _create_session(sessions_dir, '2026-01-01-abcd1234-session.tmp', 'found')
        result = session_manager.get_session_by_id('abcd1234')
        assert result is not None
        assert result['shortId'] == 'abcd1234'

    def test_get_session_by_id_filename(self, sessions_dir):
        """Finds session by full filename."""
        fname = '2026-01-01-abcd1234-session.tmp'
        _create_session(sessions_dir, fname, 'found')
        result = session_manager.get_session_by_id(fname)
        assert result is not None

    def test_get_session_by_id_with_content(self, sessions_dir):
        """Includes content and metadata when requested."""
        _create_session(sessions_dir, '2026-01-01-abcd1234-session.tmp', SAMPLE_SESSION_CONTENT)
        result = session_manager.get_session_by_id('abcd1234', include_content=True)
        assert result is not None
        assert result['content'] is not None
        assert result['metadata']['title'] == 'Session: My Test Session'
        assert 'stats' in result

    def test_get_session_by_id_not_found(self, sessions_dir):
        """Returns None."""
        result = session_manager.get_session_by_id('nonexistent')
        assert result is None


# --- get_session_title ---

class TestGetSessionTitle:
    def test_get_session_title(self, sessions_dir):
        """Extracts title from markdown."""
        path = _create_session(sessions_dir, '2026-01-01-session.tmp', '# My Title\nContent')
        assert session_manager.get_session_title(path) == 'My Title'

    def test_get_session_title_default(self, sessions_dir):
        """Returns 'Untitled Session' when no title."""
        path = _create_session(sessions_dir, '2026-01-01-session.tmp', 'No heading here')
        assert session_manager.get_session_title(path) == 'Untitled Session'


# --- get_session_size ---

class TestGetSessionSize:
    def test_get_session_size_bytes(self, sessions_dir):
        """Returns size in bytes for small files."""
        path = _create_session(sessions_dir, '2026-01-01-session.tmp', 'hi')
        size = session_manager.get_session_size(path)
        assert 'B' in size

    def test_get_session_size_kb(self, sessions_dir):
        """Returns size in KB for medium files."""
        path = _create_session(sessions_dir, '2026-01-01-session.tmp', 'x' * 2048)
        size = session_manager.get_session_size(path)
        assert 'KB' in size

    def test_get_session_size_missing(self):
        """Returns '0 B' for nonexistent file."""
        assert session_manager.get_session_size('/nonexistent') == '0 B'


# --- write_session_content ---

class TestWriteSessionContent:
    def test_write_session_content(self, sessions_dir):
        """Writes content to file."""
        path = os.path.join(sessions_dir, 'test.tmp')
        assert session_manager.write_session_content(path, 'hello') is True
        with open(path) as f:
            assert f.read() == 'hello'


# --- append_session_content ---

class TestAppendSessionContent:
    def test_append_session_content(self, sessions_dir):
        """Appends to existing file."""
        path = _create_session(sessions_dir, 'test.tmp', 'hello')
        assert session_manager.append_session_content(path, ' world') is True
        with open(path) as f:
            assert f.read() == 'hello world'


# --- delete_session ---

class TestDeleteSession:
    def test_delete_session(self, sessions_dir):
        """Deletes file, returns True."""
        path = _create_session(sessions_dir, 'test.tmp', 'data')
        assert session_manager.delete_session(path) is True
        assert not os.path.exists(path)

    def test_delete_session_missing(self):
        """Returns False for nonexistent file."""
        assert session_manager.delete_session('/nonexistent/file.tmp') is False


# --- session_exists ---

class TestSessionExists:
    def test_session_exists(self, sessions_dir):
        """Returns True for existing file."""
        path = _create_session(sessions_dir, 'test.tmp', 'data')
        assert session_manager.session_exists(path) is True
        assert session_manager.session_exists('/nonexistent') is False
