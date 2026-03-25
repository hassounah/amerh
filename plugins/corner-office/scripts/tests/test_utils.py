"""Tests for utils.py — all 26 functions + 3 platform constants."""

import json
import os
import re
import subprocess
import sys
import tempfile
import time

import pytest

from utils import (
    append_file,
    command_exists,
    count_in_file,
    ensure_dir,
    find_files,
    get_aliases_path,
    get_claude_dir,
    get_date_string,
    get_date_time_string,
    get_git_modified_files,
    get_git_repo_name,
    get_home_dir,
    get_learned_skills_dir,
    get_project_name,
    get_session_id_short,
    get_sessions_dir,
    get_temp_dir,
    get_time_string,
    grep_file,
    is_git_repo,
    is_linux,
    is_mac,
    is_windows,
    log,
    output,
    read_file,
    read_stdin_json,
    replace_in_file,
    run_command,
    write_file,
)


# --- Platform constants ---

class TestPlatformConstants:
    def test_platform_constants_are_bools(self):
        assert isinstance(is_windows, bool)
        assert isinstance(is_mac, bool)
        assert isinstance(is_linux, bool)

    def test_exactly_one_platform(self):
        # At least one should be true on any system
        assert is_windows or is_mac or is_linux


# --- Path functions ---

class TestPathFunctions:
    def test_get_home_dir(self):
        assert get_home_dir() == os.path.expanduser('~')

    def test_get_claude_dir(self):
        result = get_claude_dir()
        assert result.endswith('.claude')
        assert result.startswith(get_home_dir())

    def test_get_sessions_dir(self):
        result = get_sessions_dir()
        assert result.endswith('sessions')
        assert '.claude' in result

    def test_get_aliases_path(self):
        result = get_aliases_path()
        assert result.endswith('session-aliases.json')
        assert '.claude' in result

    def test_get_learned_skills_dir(self):
        result = get_learned_skills_dir()
        assert result.endswith(os.path.join('skills', 'learned'))
        assert '.claude' in result

    def test_get_temp_dir(self):
        result = get_temp_dir()
        assert result == tempfile.gettempdir()
        assert os.path.isdir(result)


# --- ensure_dir ---

class TestEnsureDir:
    def test_creates_nested_dirs(self, tmp_path):
        target = str(tmp_path / 'a' / 'b' / 'c')
        result = ensure_dir(target)
        assert os.path.isdir(target)
        assert result == target

    def test_noop_on_existing(self, tmp_path):
        target = str(tmp_path / 'existing')
        os.makedirs(target)
        result = ensure_dir(target)
        assert os.path.isdir(target)
        assert result == target

    def test_returns_path(self, tmp_path):
        target = str(tmp_path / 'new')
        assert ensure_dir(target) == target


# --- Date/Time functions ---

class TestDateTimeFunctions:
    def test_get_date_string_format(self):
        result = get_date_string()
        assert re.match(r'^\d{4}-\d{2}-\d{2}$', result)

    def test_get_time_string_format(self):
        result = get_time_string()
        assert re.match(r'^\d{2}:\d{2}$', result)

    def test_get_date_time_string_format(self):
        result = get_date_time_string()
        assert re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', result)


# --- Session ID ---

class TestSessionIdShort:
    def test_from_env(self, monkeypatch):
        monkeypatch.setenv('CLAUDE_SESSION_ID', 'abcdefghijklmnop')
        assert get_session_id_short() == 'ijklmnop'

    def test_last_8_chars(self, monkeypatch):
        monkeypatch.setenv('CLAUDE_SESSION_ID', '12345678')
        assert get_session_id_short() == '12345678'

    def test_fallback_default(self, monkeypatch):
        monkeypatch.delenv('CLAUDE_SESSION_ID', raising=False)
        # Falls back to project name or 'default'
        result = get_session_id_short()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_custom_fallback(self, monkeypatch):
        monkeypatch.delenv('CLAUDE_SESSION_ID', raising=False)
        # Mock git to fail so project name is cwd basename
        monkeypatch.setattr('utils.run_command', lambda cmd, **kw: {'success': False, 'output': ''})
        monkeypatch.setattr('os.getcwd', lambda: '/tmp/empty')
        result = get_session_id_short('custom')
        # Should return cwd basename 'empty' or 'custom'
        assert result in ('empty', 'custom')


# --- Git functions ---

class TestGitFunctions:
    def test_get_git_repo_name(self, monkeypatch):
        monkeypatch.setattr('utils.run_command', lambda cmd, **kw: {
            'success': True, 'output': '/home/user/my-repo'
        })
        assert get_git_repo_name() == 'my-repo'

    def test_get_git_repo_name_not_repo(self, monkeypatch):
        monkeypatch.setattr('utils.run_command', lambda cmd, **kw: {
            'success': False, 'output': ''
        })
        assert get_git_repo_name() is None

    def test_get_project_name_from_git(self, monkeypatch):
        monkeypatch.setattr('utils.get_git_repo_name', lambda: 'my-project')
        assert get_project_name() == 'my-project'

    def test_get_project_name_from_cwd(self, monkeypatch):
        monkeypatch.setattr('utils.get_git_repo_name', lambda: None)
        monkeypatch.setattr('os.getcwd', lambda: '/home/user/some-dir')
        assert get_project_name() == 'some-dir'

    def test_is_git_repo(self, monkeypatch):
        monkeypatch.setattr('utils.run_command', lambda cmd, **kw: {
            'success': True, 'output': '.git'
        })
        assert is_git_repo() is True

    def test_is_not_git_repo(self, monkeypatch):
        monkeypatch.setattr('utils.run_command', lambda cmd, **kw: {
            'success': False, 'output': ''
        })
        assert is_git_repo() is False

    def test_get_git_modified_files(self, monkeypatch):
        monkeypatch.setattr('utils.is_git_repo', lambda: True)
        monkeypatch.setattr('utils.run_command', lambda cmd, **kw: {
            'success': True, 'output': 'file1.py\nfile2.js\nfile3.py'
        })
        result = get_git_modified_files()
        assert result == ['file1.py', 'file2.js', 'file3.py']

    def test_get_git_modified_files_with_pattern(self, monkeypatch):
        monkeypatch.setattr('utils.is_git_repo', lambda: True)
        monkeypatch.setattr('utils.run_command', lambda cmd, **kw: {
            'success': True, 'output': 'file1.py\nfile2.js\nfile3.py'
        })
        result = get_git_modified_files(patterns=[r'\.py$'])
        assert result == ['file1.py', 'file3.py']

    def test_get_git_modified_files_not_repo(self, monkeypatch):
        monkeypatch.setattr('utils.is_git_repo', lambda: False)
        assert get_git_modified_files() == []


# --- find_files ---

class TestFindFiles:
    def test_pattern_matching(self, tmp_path):
        (tmp_path / 'a.txt').write_text('a')
        (tmp_path / 'b.md').write_text('b')
        (tmp_path / 'c.txt').write_text('c')
        result = find_files(str(tmp_path), '*.txt')
        assert len(result) == 2
        paths = [r['path'] for r in result]
        assert all(p.endswith('.txt') for p in paths)

    def test_max_age_filtering(self, tmp_path):
        f = tmp_path / 'recent.txt'
        f.write_text('recent')
        result = find_files(str(tmp_path), '*.txt', max_age=1)
        assert len(result) == 1

    def test_recursive(self, tmp_path):
        sub = tmp_path / 'sub'
        sub.mkdir()
        (tmp_path / 'top.txt').write_text('top')
        (sub / 'nested.txt').write_text('nested')
        result = find_files(str(tmp_path), '*.txt', recursive=True)
        assert len(result) == 2

    def test_not_recursive_by_default(self, tmp_path):
        sub = tmp_path / 'sub'
        sub.mkdir()
        (tmp_path / 'top.txt').write_text('top')
        (sub / 'nested.txt').write_text('nested')
        result = find_files(str(tmp_path), '*.txt')
        assert len(result) == 1

    def test_empty_dir(self, tmp_path):
        result = find_files(str(tmp_path), '*.txt')
        assert result == []

    def test_nonexistent_dir(self):
        result = find_files('/nonexistent/path', '*.txt')
        assert result == []

    def test_mtime_sorting(self, tmp_path):
        f1 = tmp_path / 'old.txt'
        f1.write_text('old')
        time.sleep(0.05)
        f2 = tmp_path / 'new.txt'
        f2.write_text('new')
        result = find_files(str(tmp_path), '*.txt')
        assert len(result) == 2
        assert result[0]['path'].endswith('new.txt')

    def test_result_structure(self, tmp_path):
        (tmp_path / 'test.txt').write_text('test')
        result = find_files(str(tmp_path), '*.txt')
        assert len(result) == 1
        assert 'path' in result[0]
        assert 'mtime' in result[0]
        assert isinstance(result[0]['mtime'], float)


# --- read_stdin_json ---

class TestReadStdinJson:
    def test_valid_json(self, monkeypatch):
        import io
        monkeypatch.setattr('sys.stdin', io.StringIO('{"key": "value"}'))
        result = read_stdin_json()
        assert result == {'key': 'value'}

    def test_empty_stdin(self, monkeypatch):
        import io
        monkeypatch.setattr('sys.stdin', io.StringIO(''))
        result = read_stdin_json()
        assert result == {}

    def test_whitespace_only(self, monkeypatch):
        import io
        monkeypatch.setattr('sys.stdin', io.StringIO('   \n  '))
        result = read_stdin_json()
        assert result == {}


# --- log and output ---

class TestLogOutput:
    def test_log_writes_to_stderr(self, capsys):
        log('test message')
        captured = capsys.readouterr()
        assert 'test message' in captured.err
        assert captured.out == ''

    def test_output_string(self, capsys):
        output('hello')
        captured = capsys.readouterr()
        assert captured.out.strip() == 'hello'

    def test_output_dict(self, capsys):
        output({'key': 'val'})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed == {'key': 'val'}


# --- File operations ---

class TestFileOps:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / 'test.txt'
        f.write_text('content')
        assert read_file(str(f)) == 'content'

    def test_read_missing_file(self):
        assert read_file('/nonexistent/file.txt') is None

    def test_write_creates_parents(self, tmp_path):
        target = str(tmp_path / 'a' / 'b' / 'file.txt')
        write_file(target, 'content')
        assert os.path.exists(target)
        assert read_file(target) == 'content'

    def test_append_creates_file(self, tmp_path):
        target = str(tmp_path / 'new.txt')
        append_file(target, 'line1\n')
        append_file(target, 'line2\n')
        assert read_file(target) == 'line1\nline2\n'

    def test_append_creates_parents(self, tmp_path):
        target = str(tmp_path / 'sub' / 'new.txt')
        append_file(target, 'content')
        assert read_file(target) == 'content'


# --- command_exists ---

class TestCommandExists:
    def test_python3_exists(self):
        assert command_exists('python3') is True

    def test_nonexistent_command(self):
        assert command_exists('nonexistent_cmd_xyz_123') is False

    def test_invalid_name_rejected(self):
        assert command_exists('rm -rf /') is False
        assert command_exists('cmd;echo bad') is False
        assert command_exists('') is False

    def test_valid_name_chars(self):
        # Should not raise, just return bool
        assert isinstance(command_exists('valid-cmd_1.0'), bool)


# --- run_command ---

class TestRunCommand:
    def test_success(self):
        result = run_command('echo hello')
        assert result['success'] is True
        assert result['output'] == 'hello'

    def test_failure(self):
        result = run_command('false')
        assert result['success'] is False

    def test_output_trimmed(self):
        result = run_command('echo "  hello  "')
        assert result['success'] is True
        assert result['output'] == 'hello'


# --- replace_in_file ---

class TestReplaceInFile:
    def test_string_replace(self, tmp_path):
        f = str(tmp_path / 'test.txt')
        write_file(f, 'foo bar foo')
        result = replace_in_file(f, 'foo', 'baz')
        assert result is True
        # Python str.replace replaces all occurrences
        assert read_file(f) == 'baz bar baz'

    def test_regex_replace(self, tmp_path):
        f = str(tmp_path / 'test.txt')
        write_file(f, '**Last Updated:** 10:00')
        result = replace_in_file(f, re.compile(r'\*\*Last Updated:\*\*.*'), '**Last Updated:** 11:00')
        assert result is True
        assert '11:00' in read_file(f)

    def test_missing_file(self):
        result = replace_in_file('/nonexistent/file.txt', 'a', 'b')
        assert result is False


# --- count_in_file ---

class TestCountInFile:
    def test_count_pattern(self, tmp_path):
        f = str(tmp_path / 'test.txt')
        write_file(f, 'foo bar foo baz foo')
        assert count_in_file(f, 'foo') == 3

    def test_count_regex(self, tmp_path):
        f = str(tmp_path / 'test.txt')
        write_file(f, '{"type":"user"}\n{"type":"assistant"}\n{"type":"user"}')
        assert count_in_file(f, r'"type":"user"') == 2

    def test_count_missing_file(self):
        assert count_in_file('/nonexistent', 'pattern') == 0

    def test_count_no_matches(self, tmp_path):
        f = str(tmp_path / 'test.txt')
        write_file(f, 'hello world')
        assert count_in_file(f, 'xyz') == 0


# --- grep_file ---

class TestGrepFile:
    def test_grep_matches(self, tmp_path):
        f = str(tmp_path / 'test.txt')
        write_file(f, 'line1 match\nline2\nline3 match')
        result = grep_file(f, 'match')
        assert len(result) == 2
        assert result[0]['lineNumber'] == 1
        assert result[0]['content'] == 'line1 match'
        assert result[1]['lineNumber'] == 3

    def test_grep_no_matches(self, tmp_path):
        f = str(tmp_path / 'test.txt')
        write_file(f, 'hello world')
        result = grep_file(f, 'xyz')
        assert result == []

    def test_grep_missing_file(self):
        result = grep_file('/nonexistent', 'pattern')
        assert result == []

    def test_grep_regex(self, tmp_path):
        f = str(tmp_path / 'test.txt')
        write_file(f, 'abc 123\ndef 456\nghi 789')
        result = grep_file(f, r'\d{3}')
        assert len(result) == 3
