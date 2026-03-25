"""
Package Manager Detection and Selection.
Automatically detects the preferred package manager or lets user choose.

Supports: npm, pnpm, yarn, bun
"""

import json
import os
import shlex
from datetime import datetime, timezone

from utils import command_exists, get_claude_dir, read_file, write_file

# Package manager definitions
PACKAGE_MANAGERS = {
    'npm': {
        'name': 'npm',
        'lockFile': 'package-lock.json',
        'installCmd': 'npm install',
        'runCmd': 'npm run',
        'execCmd': 'npx',
        'testCmd': 'npm test',
        'buildCmd': 'npm run build',
        'devCmd': 'npm run dev',
    },
    'pnpm': {
        'name': 'pnpm',
        'lockFile': 'pnpm-lock.yaml',
        'installCmd': 'pnpm install',
        'runCmd': 'pnpm',
        'execCmd': 'pnpm dlx',
        'testCmd': 'pnpm test',
        'buildCmd': 'pnpm build',
        'devCmd': 'pnpm dev',
    },
    'yarn': {
        'name': 'yarn',
        'lockFile': 'yarn.lock',
        'installCmd': 'yarn',
        'runCmd': 'yarn',
        'execCmd': 'yarn dlx',
        'testCmd': 'yarn test',
        'buildCmd': 'yarn build',
        'devCmd': 'yarn dev',
    },
    'bun': {
        'name': 'bun',
        'lockFile': 'bun.lockb',
        'installCmd': 'bun install',
        'runCmd': 'bun run',
        'execCmd': 'bunx',
        'testCmd': 'bun test',
        'buildCmd': 'bun run build',
        'devCmd': 'bun run dev',
    },
}

# Priority order for detection
DETECTION_PRIORITY = ['pnpm', 'bun', 'yarn', 'npm']


def get_config_path():
    """Config file path."""
    return os.path.join(get_claude_dir(), 'package-manager.json')


def load_config():
    """Load saved package manager configuration."""
    config_path = get_config_path()
    content = read_file(config_path)

    if content:
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def save_config(config):
    """Save package manager configuration."""
    config_path = get_config_path()
    write_file(config_path, json.dumps(config, indent=2))


def detect_from_lock_file(project_dir=None):
    """Detect package manager from lock file in project directory."""
    if project_dir is None:
        project_dir = os.getcwd()

    for pm_name in DETECTION_PRIORITY:
        pm = PACKAGE_MANAGERS[pm_name]
        lock_file_path = os.path.join(project_dir, pm['lockFile'])

        if os.path.exists(lock_file_path):
            return pm_name

    return None


def detect_from_package_json(project_dir=None):
    """Detect package manager from package.json packageManager field."""
    if project_dir is None:
        project_dir = os.getcwd()

    package_json_path = os.path.join(project_dir, 'package.json')
    content = read_file(package_json_path)

    if content:
        try:
            pkg = json.loads(content)
            if pkg.get('packageManager'):
                # Format: "pnpm@8.6.0" or just "pnpm"
                pm_name = pkg['packageManager'].split('@')[0]
                if pm_name in PACKAGE_MANAGERS:
                    return pm_name
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def get_available_package_managers():
    """Get available package managers (installed on system)."""
    available = []

    for pm_name in PACKAGE_MANAGERS:
        if command_exists(pm_name):
            available.append(pm_name)

    return available


def get_package_manager(project_dir=None, fallback_order=None):
    """Get the package manager to use for current project.

    Detection priority:
    1. Environment variable CLAUDE_PACKAGE_MANAGER
    2. Project-specific config (in .claude/package-manager.json)
    3. package.json packageManager field
    4. Lock file detection
    5. Global user preference (in ~/.claude/package-manager.json)
    6. First available package manager (by priority)

    Returns:
        Dict with 'name', 'config', and 'source' keys.
    """
    if project_dir is None:
        project_dir = os.getcwd()
    if fallback_order is None:
        fallback_order = DETECTION_PRIORITY

    # 1. Check environment variable
    env_pm = os.environ.get('CLAUDE_PACKAGE_MANAGER')
    if env_pm and env_pm in PACKAGE_MANAGERS:
        return {
            'name': env_pm,
            'config': PACKAGE_MANAGERS[env_pm],
            'source': 'environment',
        }

    # 2. Check project-specific config
    project_config_path = os.path.join(project_dir, '.claude', 'package-manager.json')
    project_config = read_file(project_config_path)
    if project_config:
        try:
            config = json.loads(project_config)
            if config.get('packageManager') and config['packageManager'] in PACKAGE_MANAGERS:
                return {
                    'name': config['packageManager'],
                    'config': PACKAGE_MANAGERS[config['packageManager']],
                    'source': 'project-config',
                }
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Check package.json packageManager field
    from_package_json = detect_from_package_json(project_dir)
    if from_package_json:
        return {
            'name': from_package_json,
            'config': PACKAGE_MANAGERS[from_package_json],
            'source': 'package.json',
        }

    # 4. Check lock file
    from_lock_file = detect_from_lock_file(project_dir)
    if from_lock_file:
        return {
            'name': from_lock_file,
            'config': PACKAGE_MANAGERS[from_lock_file],
            'source': 'lock-file',
        }

    # 5. Check global user preference
    global_config = load_config()
    if global_config and global_config.get('packageManager') and global_config['packageManager'] in PACKAGE_MANAGERS:
        return {
            'name': global_config['packageManager'],
            'config': PACKAGE_MANAGERS[global_config['packageManager']],
            'source': 'global-config',
        }

    # 6. Use first available package manager
    available = get_available_package_managers()
    for pm_name in fallback_order:
        if pm_name in available:
            return {
                'name': pm_name,
                'config': PACKAGE_MANAGERS[pm_name],
                'source': 'fallback',
            }

    # Default to npm (always available with Node.js)
    return {
        'name': 'npm',
        'config': PACKAGE_MANAGERS['npm'],
        'source': 'default',
    }


def set_preferred_package_manager(pm_name):
    """Set user's preferred package manager (global)."""
    if pm_name not in PACKAGE_MANAGERS:
        raise ValueError(f'Unknown package manager: {pm_name}')

    config = load_config() or {}
    config['packageManager'] = pm_name
    config['setAt'] = datetime.now(timezone.utc).isoformat()
    save_config(config)

    return config


def set_project_package_manager(pm_name, project_dir=None):
    """Set project's preferred package manager."""
    if pm_name not in PACKAGE_MANAGERS:
        raise ValueError(f'Unknown package manager: {pm_name}')

    if project_dir is None:
        project_dir = os.getcwd()

    config_path = os.path.join(project_dir, '.claude', 'package-manager.json')
    config = {
        'packageManager': pm_name,
        'setAt': datetime.now(timezone.utc).isoformat(),
    }

    write_file(config_path, json.dumps(config, indent=2))
    return config


def get_run_command(script, project_dir=None):
    """Get the command to run a script.

    Args:
        script: Script name (e.g., 'dev', 'build', 'test').
        project_dir: Project directory (optional).
    """
    pm = get_package_manager(project_dir=project_dir)

    if script == 'install':
        return pm['config']['installCmd']
    elif script == 'test':
        return pm['config']['testCmd']
    elif script == 'build':
        return pm['config']['buildCmd']
    elif script == 'dev':
        return pm['config']['devCmd']
    else:
        return f"{pm['config']['runCmd']} {shlex.quote(script)}"


def get_exec_command(binary, args='', project_dir=None):
    """Get the command to execute a package binary.

    Args:
        binary: Binary name (e.g., 'prettier', 'eslint').
        args: Arguments to pass.
        project_dir: Project directory (optional).
    """
    pm = get_package_manager(project_dir=project_dir)
    if args:
        return f"{pm['config']['execCmd']} {shlex.quote(binary)} {shlex.quote(args)}"
    return f"{pm['config']['execCmd']} {shlex.quote(binary)}"


def get_selection_prompt():
    """Interactive prompt for package manager selection.
    Returns a message for Claude to show to user."""
    available = get_available_package_managers()
    current = get_package_manager()

    message = '[PackageManager] Available package managers:\n'

    for pm_name in available:
        indicator = ' (current)' if pm_name == current['name'] else ''
        message += f'  - {pm_name}{indicator}\n'

    message += '\nTo set your preferred package manager:\n'
    message += '  - Global: Set CLAUDE_PACKAGE_MANAGER environment variable\n'
    message += '  - Or add to ~/.claude/package-manager.json: {"packageManager": "pnpm"}\n'
    message += '  - Or add to package.json: {"packageManager": "pnpm@8"}\n'

    return message


def get_command_pattern(action):
    """Generate a regex pattern that matches commands for all package managers.

    Args:
        action: Action pattern (e.g., 'dev', 'install', 'test').
    """
    patterns = []

    if action == 'dev':
        patterns = [
            'npm run dev',
            'pnpm( run)? dev',
            'yarn dev',
            'bun run dev',
        ]
    elif action == 'install':
        patterns = [
            'npm install',
            'pnpm install',
            'yarn( install)?',
            'bun install',
        ]
    elif action == 'test':
        patterns = [
            'npm test',
            'pnpm test',
            'yarn test',
            'bun test',
        ]
    elif action == 'build':
        patterns = [
            'npm run build',
            'pnpm( run)? build',
            'yarn build',
            'bun run build',
        ]
    else:
        patterns = [
            f'npm run {action}',
            f'pnpm( run)? {action}',
            f'yarn {action}',
            f'bun run {action}',
        ]

    return f"({'|'.join(patterns)})"
