"""Tests for session_aliases.py."""

import json
import os

import pytest

import session_aliases


@pytest.fixture
def aliases_home(tmp_home):
    """Provide tmp_home with aliases path accessible."""
    return tmp_home


def _write_aliases(tmp_home, data):
    """Helper to write aliases JSON to the expected path."""
    aliases_path = os.path.join(str(tmp_home), '.claude', 'session-aliases.json')
    os.makedirs(os.path.dirname(aliases_path), exist_ok=True)
    with open(aliases_path, 'w') as f:
        json.dump(data, f)


def _read_aliases(tmp_home):
    """Helper to read aliases JSON from the expected path."""
    aliases_path = os.path.join(str(tmp_home), '.claude', 'session-aliases.json')
    with open(aliases_path) as f:
        return json.load(f)


# --- load_aliases ---

class TestLoadAliases:
    def test_load_aliases_empty(self, aliases_home):
        """Returns default structure when file missing."""
        result = session_aliases.load_aliases()
        assert result['version'] == '1.0'
        assert result['aliases'] == {}
        assert 'metadata' in result

    def test_load_aliases_valid(self, aliases_home):
        """Parses existing aliases file."""
        data = {
            'version': '1.0',
            'aliases': {
                'my-session': {
                    'sessionPath': '/path/to/session',
                    'createdAt': '2026-01-01T00:00:00Z',
                    'updatedAt': '2026-01-01T00:00:00Z',
                    'title': 'Test Session',
                }
            },
            'metadata': {'totalCount': 1, 'lastUpdated': '2026-01-01T00:00:00Z'},
        }
        _write_aliases(aliases_home, data)
        result = session_aliases.load_aliases()
        assert 'my-session' in result['aliases']
        assert result['aliases']['my-session']['sessionPath'] == '/path/to/session'

    def test_load_aliases_invalid_json(self, aliases_home):
        """Returns default on corrupt JSON."""
        aliases_path = os.path.join(str(aliases_home), '.claude', 'session-aliases.json')
        with open(aliases_path, 'w') as f:
            f.write('not valid json{{{')
        result = session_aliases.load_aliases()
        assert result['aliases'] == {}

    def test_load_aliases_invalid_structure(self, aliases_home):
        """Returns default when aliases key is not a dict."""
        _write_aliases(aliases_home, {'aliases': 'not-a-dict'})
        result = session_aliases.load_aliases()
        assert result['aliases'] == {}


# --- save_aliases ---

class TestSaveAliases:
    def test_save_aliases_creates_file(self, aliases_home):
        """Creates file with correct JSON."""
        data = session_aliases.get_default_aliases()
        data['aliases']['test'] = {
            'sessionPath': '/test',
            'createdAt': '2026-01-01T00:00:00Z',
            'updatedAt': '2026-01-01T00:00:00Z',
            'title': None,
        }
        result = session_aliases.save_aliases(data)
        assert result is True
        saved = _read_aliases(aliases_home)
        assert 'test' in saved['aliases']
        assert saved['metadata']['totalCount'] == 1

    def test_save_aliases_atomic_write(self, aliases_home):
        """Temp file is cleaned up after successful write."""
        data = session_aliases.get_default_aliases()
        session_aliases.save_aliases(data)
        aliases_path = session_aliases.get_aliases_path()
        assert not os.path.exists(aliases_path + '.tmp')
        assert not os.path.exists(aliases_path + '.bak')

    def test_save_aliases_backup_on_failure(self, aliases_home, monkeypatch):
        """Restores from backup on write failure."""
        # First save a valid file
        data = session_aliases.get_default_aliases()
        data['aliases']['keeper'] = {
            'sessionPath': '/keep',
            'createdAt': '2026-01-01T00:00:00Z',
            'updatedAt': '2026-01-01T00:00:00Z',
            'title': None,
        }
        session_aliases.save_aliases(data)

        # Now make os.replace fail to trigger backup restore
        def failing_replace(src, dst):
            raise OSError('simulated failure')

        monkeypatch.setattr(os, 'replace', failing_replace)

        data['aliases']['new'] = {
            'sessionPath': '/new',
            'createdAt': '2026-01-01T00:00:00Z',
            'updatedAt': '2026-01-01T00:00:00Z',
            'title': None,
        }
        result = session_aliases.save_aliases(data)
        assert result is False


# --- set_alias ---

class TestSetAlias:
    def test_set_alias_new(self, aliases_home):
        """Creates new alias, returns isNew=True."""
        result = session_aliases.set_alias('myalias', '/path/session')
        assert result['success'] is True
        assert result['isNew'] is True
        assert result['alias'] == 'myalias'

    def test_set_alias_update(self, aliases_home):
        """Updates existing alias, preserves createdAt."""
        session_aliases.set_alias('myalias', '/path/session1')
        saved = _read_aliases(aliases_home)
        created_at = saved['aliases']['myalias']['createdAt']

        result = session_aliases.set_alias('myalias', '/path/session2')
        assert result['success'] is True
        assert result['isNew'] is False

        saved2 = _read_aliases(aliases_home)
        assert saved2['aliases']['myalias']['createdAt'] == created_at
        assert saved2['aliases']['myalias']['sessionPath'] == '/path/session2'

    def test_set_alias_empty_name(self, aliases_home):
        """Returns error for empty name."""
        result = session_aliases.set_alias('', '/path')
        assert result['success'] is False
        assert 'empty' in result['error'].lower()

    def test_set_alias_invalid_chars(self, aliases_home):
        """Returns error for special characters."""
        result = session_aliases.set_alias('my alias!', '/path')
        assert result['success'] is False
        assert 'letters' in result['error'].lower() or 'only' in result['error'].lower()

    def test_set_alias_reserved_name(self, aliases_home):
        """Returns error for reserved names."""
        for name in ['list', 'help', 'remove', 'delete', 'create', 'set']:
            result = session_aliases.set_alias(name, '/path')
            assert result['success'] is False
            assert 'reserved' in result['error'].lower()


# --- resolve_alias ---

class TestResolveAlias:
    def test_resolve_alias_found(self, aliases_home):
        """Returns alias data for existing alias."""
        session_aliases.set_alias('found', '/path/to/session')
        result = session_aliases.resolve_alias('found')
        assert result is not None
        assert result['alias'] == 'found'
        assert result['sessionPath'] == '/path/to/session'

    def test_resolve_alias_not_found(self, aliases_home):
        """Returns None for nonexistent alias."""
        result = session_aliases.resolve_alias('nonexistent')
        assert result is None

    def test_resolve_alias_invalid_name(self, aliases_home):
        """Returns None for invalid names."""
        result = session_aliases.resolve_alias('bad name!')
        assert result is None


# --- list_aliases ---

class TestListAliases:
    def test_list_aliases_all(self, aliases_home):
        """Returns all aliases sorted by update time."""
        session_aliases.set_alias('first', '/path/1')
        session_aliases.set_alias('second', '/path/2')
        result = session_aliases.list_aliases()
        assert len(result) == 2
        names = [a['name'] for a in result]
        assert 'first' in names
        assert 'second' in names

    def test_list_aliases_search(self, aliases_home):
        """Filters by name substring."""
        session_aliases.set_alias('alpha-project', '/path/1')
        session_aliases.set_alias('beta-project', '/path/2')
        session_aliases.set_alias('gamma', '/path/3')
        result = session_aliases.list_aliases(search='project')
        assert len(result) == 2

    def test_list_aliases_limit(self, aliases_home):
        """Respects limit parameter."""
        for i in range(5):
            session_aliases.set_alias(f'alias-{i}', f'/path/{i}')
        result = session_aliases.list_aliases(limit=2)
        assert len(result) == 2


# --- delete_alias ---

class TestDeleteAlias:
    def test_delete_alias(self, aliases_home):
        """Removes alias from file."""
        session_aliases.set_alias('todelete', '/path')
        result = session_aliases.delete_alias('todelete')
        assert result['success'] is True
        assert result['deletedSessionPath'] == '/path'
        assert session_aliases.resolve_alias('todelete') is None

    def test_delete_alias_not_found(self, aliases_home):
        """Returns error for nonexistent alias."""
        result = session_aliases.delete_alias('nonexistent')
        assert result['success'] is False
        assert 'not found' in result['error'].lower()


# --- rename_alias ---

class TestRenameAlias:
    def test_rename_alias(self, aliases_home):
        """Renames alias, preserves data."""
        session_aliases.set_alias('oldname', '/path/session')
        result = session_aliases.rename_alias('oldname', 'newname')
        assert result['success'] is True
        assert result['sessionPath'] == '/path/session'
        assert session_aliases.resolve_alias('oldname') is None
        assert session_aliases.resolve_alias('newname') is not None

    def test_rename_alias_target_exists(self, aliases_home):
        """Returns error if new name taken."""
        session_aliases.set_alias('name1', '/path/1')
        session_aliases.set_alias('name2', '/path/2')
        result = session_aliases.rename_alias('name1', 'name2')
        assert result['success'] is False
        assert 'exists' in result['error'].lower()

    def test_rename_alias_invalid_new_name(self, aliases_home):
        """Returns error for invalid new name."""
        session_aliases.set_alias('valid', '/path')
        result = session_aliases.rename_alias('valid', 'bad name!')
        assert result['success'] is False


# --- resolve_session_alias ---

class TestResolveSessionAlias:
    def test_resolve_session_alias(self, aliases_home):
        """Returns session path for alias, or input as-is."""
        session_aliases.set_alias('myalias', '/path/to/session')
        assert session_aliases.resolve_session_alias('myalias') == '/path/to/session'
        assert session_aliases.resolve_session_alias('not-an-alias') == 'not-an-alias'


# --- update_alias_title ---

class TestUpdateAliasTitle:
    def test_update_alias_title(self, aliases_home):
        """Updates title field."""
        session_aliases.set_alias('titled', '/path')
        result = session_aliases.update_alias_title('titled', 'New Title')
        assert result['success'] is True
        resolved = session_aliases.resolve_alias('titled')
        assert resolved['title'] == 'New Title'


# --- get_aliases_for_session ---

class TestGetAliasesForSession:
    def test_get_aliases_for_session(self, aliases_home):
        """Returns all aliases pointing to a session path."""
        session_aliases.set_alias('alias1', '/shared/path')
        session_aliases.set_alias('alias2', '/shared/path')
        session_aliases.set_alias('other', '/different/path')
        result = session_aliases.get_aliases_for_session('/shared/path')
        assert len(result) == 2
        names = [a['name'] for a in result]
        assert 'alias1' in names
        assert 'alias2' in names


# --- cleanup_aliases ---

class TestCleanupAliases:
    def test_cleanup_aliases(self, aliases_home):
        """Removes aliases for nonexistent sessions."""
        session_aliases.set_alias('alive', '/exists')
        session_aliases.set_alias('dead', '/gone')

        def exists_fn(path):
            return path == '/exists'

        result = session_aliases.cleanup_aliases(exists_fn)
        assert result['removed'] == 1
        assert result['totalChecked'] == 2
        assert session_aliases.resolve_alias('alive') is not None
        assert session_aliases.resolve_alias('dead') is None
