"""Tests for package_manager.py — all 11 functions + constants."""

import json
import os

import pytest

from package_manager import (
    DETECTION_PRIORITY,
    PACKAGE_MANAGERS,
    detect_from_lock_file,
    detect_from_package_json,
    get_available_package_managers,
    get_command_pattern,
    get_exec_command,
    get_package_manager,
    get_run_command,
    get_selection_prompt,
    set_preferred_package_manager,
    set_project_package_manager,
)


# --- Constants ---

class TestConstants:
    def test_package_managers_has_four(self):
        assert set(PACKAGE_MANAGERS.keys()) == {'npm', 'pnpm', 'yarn', 'bun'}

    def test_each_pm_has_required_fields(self):
        required = ['name', 'lockFile', 'installCmd', 'runCmd', 'execCmd', 'testCmd', 'buildCmd', 'devCmd']
        for pm_name, pm in PACKAGE_MANAGERS.items():
            for field in required:
                assert field in pm, f'{pm_name} missing {field}'

    def test_detection_priority(self):
        assert DETECTION_PRIORITY == ['pnpm', 'bun', 'yarn', 'npm']


# --- Lock file detection ---

class TestDetectFromLockFile:
    def test_npm(self, tmp_path):
        (tmp_path / 'package-lock.json').write_text('{}')
        assert detect_from_lock_file(str(tmp_path)) == 'npm'

    def test_pnpm(self, tmp_path):
        (tmp_path / 'pnpm-lock.yaml').write_text('')
        assert detect_from_lock_file(str(tmp_path)) == 'pnpm'

    def test_yarn(self, tmp_path):
        (tmp_path / 'yarn.lock').write_text('')
        assert detect_from_lock_file(str(tmp_path)) == 'yarn'

    def test_bun(self, tmp_path):
        (tmp_path / 'bun.lockb').write_text('')
        assert detect_from_lock_file(str(tmp_path)) == 'bun'

    def test_priority_pnpm_over_npm(self, tmp_path):
        (tmp_path / 'pnpm-lock.yaml').write_text('')
        (tmp_path / 'package-lock.json').write_text('{}')
        assert detect_from_lock_file(str(tmp_path)) == 'pnpm'

    def test_none_found(self, tmp_path):
        assert detect_from_lock_file(str(tmp_path)) is None


# --- package.json detection ---

class TestDetectFromPackageJson:
    def test_with_version(self, tmp_path):
        (tmp_path / 'package.json').write_text('{"packageManager": "pnpm@8.6.0"}')
        assert detect_from_package_json(str(tmp_path)) == 'pnpm'

    def test_without_version(self, tmp_path):
        (tmp_path / 'package.json').write_text('{"packageManager": "yarn"}')
        assert detect_from_package_json(str(tmp_path)) == 'yarn'

    def test_missing_file(self, tmp_path):
        assert detect_from_package_json(str(tmp_path)) is None

    def test_invalid_json(self, tmp_path):
        (tmp_path / 'package.json').write_text('not json')
        assert detect_from_package_json(str(tmp_path)) is None

    def test_no_package_manager_field(self, tmp_path):
        (tmp_path / 'package.json').write_text('{"name": "test"}')
        assert detect_from_package_json(str(tmp_path)) is None

    def test_unknown_pm(self, tmp_path):
        (tmp_path / 'package.json').write_text('{"packageManager": "unknown@1.0"}')
        assert detect_from_package_json(str(tmp_path)) is None


# --- 6-level priority chain ---

class TestGetPackageManager:
    def test_1_env_variable(self, monkeypatch, tmp_path):
        monkeypatch.setenv('CLAUDE_PACKAGE_MANAGER', 'bun')
        result = get_package_manager(project_dir=str(tmp_path))
        assert result['name'] == 'bun'
        assert result['source'] == 'environment'

    def test_2_project_config(self, monkeypatch, tmp_path):
        monkeypatch.delenv('CLAUDE_PACKAGE_MANAGER', raising=False)
        config_dir = tmp_path / '.claude'
        config_dir.mkdir()
        (config_dir / 'package-manager.json').write_text('{"packageManager": "yarn"}')
        result = get_package_manager(project_dir=str(tmp_path))
        assert result['name'] == 'yarn'
        assert result['source'] == 'project-config'

    def test_3_package_json(self, monkeypatch, tmp_path):
        monkeypatch.delenv('CLAUDE_PACKAGE_MANAGER', raising=False)
        (tmp_path / 'package.json').write_text('{"packageManager": "pnpm@8"}')
        result = get_package_manager(project_dir=str(tmp_path))
        assert result['name'] == 'pnpm'
        assert result['source'] == 'package.json'

    def test_4_lock_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv('CLAUDE_PACKAGE_MANAGER', raising=False)
        (tmp_path / 'yarn.lock').write_text('')
        result = get_package_manager(project_dir=str(tmp_path))
        assert result['name'] == 'yarn'
        assert result['source'] == 'lock-file'

    def test_5_global_config(self, monkeypatch, tmp_path):
        monkeypatch.delenv('CLAUDE_PACKAGE_MANAGER', raising=False)
        home = tmp_path / 'home'
        home.mkdir()
        monkeypatch.setenv('HOME', str(home))
        claude_dir = home / '.claude'
        claude_dir.mkdir()
        (claude_dir / 'package-manager.json').write_text('{"packageManager": "bun"}')
        # Use a project dir with nothing
        project = tmp_path / 'project'
        project.mkdir()
        result = get_package_manager(project_dir=str(project))
        assert result['name'] == 'bun'
        assert result['source'] == 'global-config'

    def test_6_fallback(self, monkeypatch, tmp_path):
        monkeypatch.delenv('CLAUDE_PACKAGE_MANAGER', raising=False)
        home = tmp_path / 'home'
        home.mkdir()
        monkeypatch.setenv('HOME', str(home))
        (home / '.claude').mkdir()
        project = tmp_path / 'project'
        project.mkdir()
        result = get_package_manager(project_dir=str(project))
        assert result['source'] in ('fallback', 'default')

    def test_default_npm(self, monkeypatch, tmp_path):
        monkeypatch.delenv('CLAUDE_PACKAGE_MANAGER', raising=False)
        home = tmp_path / 'home'
        home.mkdir()
        monkeypatch.setenv('HOME', str(home))
        (home / '.claude').mkdir()
        # Mock no PMs available
        monkeypatch.setattr('package_manager.get_available_package_managers', lambda: [])
        project = tmp_path / 'project'
        project.mkdir()
        result = get_package_manager(project_dir=str(project))
        assert result['name'] == 'npm'
        assert result['source'] == 'default'

    def test_env_invalid_pm(self, monkeypatch, tmp_path):
        monkeypatch.setenv('CLAUDE_PACKAGE_MANAGER', 'invalid_pm')
        home = tmp_path / 'home'
        home.mkdir()
        monkeypatch.setenv('HOME', str(home))
        (home / '.claude').mkdir()
        monkeypatch.setattr('package_manager.get_available_package_managers', lambda: [])
        project = tmp_path / 'project'
        project.mkdir()
        result = get_package_manager(project_dir=str(project))
        # Should skip invalid env and fall through
        assert result['source'] != 'environment'


# --- set_preferred/project ---

class TestSetPackageManager:
    def test_set_preferred(self, monkeypatch, tmp_path):
        home = tmp_path / 'home'
        home.mkdir()
        monkeypatch.setenv('HOME', str(home))
        (home / '.claude').mkdir()
        config = set_preferred_package_manager('pnpm')
        assert config['packageManager'] == 'pnpm'
        assert 'setAt' in config

    def test_set_preferred_unknown(self):
        with pytest.raises(ValueError, match='Unknown package manager'):
            set_preferred_package_manager('invalid')

    def test_set_project(self, tmp_path):
        config = set_project_package_manager('yarn', project_dir=str(tmp_path))
        assert config['packageManager'] == 'yarn'
        config_file = tmp_path / '.claude' / 'package-manager.json'
        assert config_file.exists()

    def test_set_project_unknown(self, tmp_path):
        with pytest.raises(ValueError, match='Unknown package manager'):
            set_project_package_manager('invalid', project_dir=str(tmp_path))


# --- get_run_command / get_exec_command ---

class TestRunExecCommands:
    def test_run_install(self, monkeypatch, tmp_path):
        monkeypatch.setenv('CLAUDE_PACKAGE_MANAGER', 'npm')
        assert get_run_command('install', project_dir=str(tmp_path)) == 'npm install'

    def test_run_test(self, monkeypatch, tmp_path):
        monkeypatch.setenv('CLAUDE_PACKAGE_MANAGER', 'pnpm')
        assert get_run_command('test', project_dir=str(tmp_path)) == 'pnpm test'

    def test_run_build(self, monkeypatch, tmp_path):
        monkeypatch.setenv('CLAUDE_PACKAGE_MANAGER', 'yarn')
        assert get_run_command('build', project_dir=str(tmp_path)) == 'yarn build'

    def test_run_dev(self, monkeypatch, tmp_path):
        monkeypatch.setenv('CLAUDE_PACKAGE_MANAGER', 'bun')
        assert get_run_command('dev', project_dir=str(tmp_path)) == 'bun run dev'

    def test_run_custom(self, monkeypatch, tmp_path):
        monkeypatch.setenv('CLAUDE_PACKAGE_MANAGER', 'npm')
        assert get_run_command('lint', project_dir=str(tmp_path)) == 'npm run lint'

    def test_exec_command(self, monkeypatch, tmp_path):
        monkeypatch.setenv('CLAUDE_PACKAGE_MANAGER', 'npm')
        assert get_exec_command('prettier', project_dir=str(tmp_path)) == 'npx prettier'

    def test_exec_with_args(self, monkeypatch, tmp_path):
        monkeypatch.setenv('CLAUDE_PACKAGE_MANAGER', 'pnpm')
        assert get_exec_command('eslint', '--fix', project_dir=str(tmp_path)) == 'pnpm dlx eslint --fix'


# --- get_selection_prompt ---

class TestSelectionPrompt:
    def test_contains_available(self, monkeypatch, tmp_path):
        monkeypatch.setenv('CLAUDE_PACKAGE_MANAGER', 'npm')
        prompt = get_selection_prompt()
        assert 'Available package managers' in prompt
        assert 'CLAUDE_PACKAGE_MANAGER' in prompt


# --- get_command_pattern ---

class TestCommandPattern:
    def test_dev_pattern(self):
        pattern = get_command_pattern('dev')
        assert 'npm run dev' in pattern
        assert 'yarn dev' in pattern

    def test_install_pattern(self):
        pattern = get_command_pattern('install')
        assert 'npm install' in pattern
        assert 'pnpm install' in pattern

    def test_test_pattern(self):
        pattern = get_command_pattern('test')
        assert 'npm test' in pattern

    def test_build_pattern(self):
        pattern = get_command_pattern('build')
        assert 'npm run build' in pattern

    def test_custom_pattern(self):
        pattern = get_command_pattern('lint')
        assert 'npm run lint' in pattern
        assert 'yarn lint' in pattern
