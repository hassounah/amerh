"""
Cross-platform utility functions for Claude Code hooks and scripts.
Works on Windows, macOS, and Linux.
"""

import os
import sys
import json
import re
import datetime
import shlex
import subprocess
import shutil
import tempfile
import fnmatch
import time

# Platform detection
is_windows = sys.platform == 'win32'
is_mac = sys.platform == 'darwin'
is_linux = sys.platform.startswith('linux')


def get_home_dir():
    """Get the user's home directory (cross-platform)."""
    return os.path.expanduser('~')


def get_claude_dir():
    """Get the Claude config directory."""
    return os.path.join(get_home_dir(), '.claude')


def get_sessions_dir():
    """Get the sessions directory."""
    return os.path.join(get_claude_dir(), 'sessions')


def get_aliases_path():
    """Get the session aliases file path."""
    return os.path.join(get_claude_dir(), 'session-aliases.json')


def get_learned_skills_dir():
    """Get the learned skills directory."""
    return os.path.join(get_claude_dir(), 'skills', 'learned')


def get_temp_dir():
    """Get the temp directory (cross-platform)."""
    return tempfile.gettempdir()


def ensure_dir(dir_path):
    """Ensure a directory exists (create if not)."""
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


def get_date_string():
    """Get current date in YYYY-MM-DD format."""
    return datetime.date.today().isoformat()


def get_time_string():
    """Get current time in HH:MM format."""
    return datetime.datetime.now().strftime('%H:%M')


def get_date_time_string():
    """Get current datetime in YYYY-MM-DD HH:MM:SS format."""
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def read_session_id_from_stdin():
    """Read full session_id from hook stdin JSON payload.

    Returns the session_id string if found, empty string otherwise.
    Stdin can only be read once per process — call this early and pass the
    result to get_session_id_short() via its session_id parameter.
    """
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            return data.get('session_id', data.get('sessionId', ''))
    except (json.JSONDecodeError, OSError):
        pass
    return ''


def get_session_id_short(fallback='default', session_id=None):
    """Get short session ID (last 8 chars).

    Resolution order:
    1. Explicit session_id parameter (from stdin payload or caller)
    2. CLAUDE_SESSION_ID environment variable
    3. Project name or fallback
    """
    if not session_id:
        session_id = os.environ.get('CLAUDE_SESSION_ID', '')
    if session_id:
        return session_id[-8:]
    return get_project_name() or fallback


def get_git_repo_name():
    """Get the git repository name."""
    result = run_command('git rev-parse --show-toplevel')
    if not result['success']:
        return None
    return os.path.basename(result['output'])


def get_project_name():
    """Get project name from git repo or current directory."""
    repo_name = get_git_repo_name()
    if repo_name:
        return repo_name
    return os.path.basename(os.getcwd()) or None


def get_workspace_slug():
    """Derive a filesystem-safe workspace name from git repo or cwd.

    Sanitizes to [a-zA-Z0-9_-], max 64 chars. Returns 'unknown' on failure.
    """
    try:
        name = get_git_repo_name() or os.path.basename(os.getcwd())
        slug = re.sub(r'[^a-zA-Z0-9_-]', '', name)[:64]
        if slug:
            return slug
    except Exception:
        pass
    print('[corner-office] Warning: could not determine workspace name, falling back to "unknown"', file=sys.stderr)
    return 'unknown'


def iso_now():
    """Return current UTC time as ISO 8601 timestamp with milliseconds.

    Format: YYYY-MM-DDTHH:MM:SS.mmmZ
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}Z'


def find_files(directory, pattern, max_age=None, recursive=False):
    """Find files matching a pattern in a directory.

    Args:
        directory: Directory to search.
        pattern: File pattern (e.g., '*.tmp', '*.md').
        max_age: Maximum age in days (None for no limit).
        recursive: Whether to search subdirectories.

    Returns:
        List of dicts with 'path' and 'mtime' keys, sorted newest first.
    """
    results = []

    if not os.path.isdir(directory):
        return results

    def search_dir(current_dir):
        try:
            with os.scandir(current_dir) as entries:
                for entry in entries:
                    if entry.is_file() and fnmatch.fnmatch(entry.name, pattern):
                        try:
                            stat = entry.stat()
                            mtime_ms = stat.st_mtime * 1000
                            if max_age is not None:
                                age_in_days = (time.time() - stat.st_mtime) / (60 * 60 * 24)
                                if age_in_days <= max_age:
                                    results.append({'path': entry.path, 'mtime': mtime_ms})
                            else:
                                results.append({'path': entry.path, 'mtime': mtime_ms})
                        except OSError:
                            pass
                    elif entry.is_dir() and recursive:
                        search_dir(entry.path)
        except OSError:
            pass

    search_dir(directory)
    results.sort(key=lambda x: x['mtime'], reverse=True)
    return results


def read_stdin_json():
    """Read JSON from stdin (for hook input). Synchronous."""
    data = sys.stdin.read()
    if data.strip():
        return json.loads(data)
    return {}


def log(message):
    """Log to stderr (visible to user in Claude Code)."""
    print(message, file=sys.stderr)


def output(data):
    """Output to stdout (returned to Claude)."""
    if isinstance(data, dict):
        print(json.dumps(data))
    else:
        print(data)


def read_file(file_path):
    """Read a text file safely. Returns None on failure."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except (OSError, IOError):
        return None


def write_file(file_path, content):
    """Write a text file, creating parent directories as needed."""
    ensure_dir(os.path.dirname(file_path))
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


def append_file(file_path, content):
    """Append to a text file, creating parent directories as needed."""
    ensure_dir(os.path.dirname(file_path))
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(content)


def command_exists(cmd):
    """Check if a command exists in PATH.
    Validates command name to prevent injection."""
    if not re.match(r'^[a-zA-Z0-9_.\-]+$', cmd):
        return False
    return shutil.which(cmd) is not None


def run_command(cmd, shell=False, **kwargs):
    """Run a command and return output.

    Args:
        cmd: Command string or list of args. Strings are split with shlex
             when shell=False.
        shell: If True, run via shell (use only with trusted, hardcoded
               commands). Defaults to False for safety.

    Returns:
        Dict with 'success' (bool) and 'output' (str) keys.
    """
    try:
        if isinstance(cmd, str) and not shell:
            cmd = shlex.split(cmd)
        result = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            **kwargs
        )
        if result.returncode == 0:
            return {'success': True, 'output': result.stdout.strip()}
        else:
            return {'success': False, 'output': result.stderr or result.stdout}
    except Exception as e:
        return {'success': False, 'output': str(e)}


def is_git_repo():
    """Check if current directory is a git repository."""
    return run_command('git rev-parse --git-dir')['success']


def get_git_modified_files(patterns=None):
    """Get git modified files, optionally filtered by regex patterns."""
    if not is_git_repo():
        return []

    result = run_command('git diff --name-only HEAD')
    if not result['success']:
        return []

    files = [f for f in result['output'].split('\n') if f]

    if patterns:
        files = [
            f for f in files
            if any(re.search(p, f) for p in patterns)
        ]

    return files


def replace_in_file(file_path, search, replace):
    """Replace text in a file. search can be a string or compiled regex."""
    content = read_file(file_path)
    if content is None:
        return False

    if isinstance(search, str):
        new_content = content.replace(search, replace)
    else:
        new_content = search.sub(replace, content)
    write_file(file_path, new_content)
    return True


def count_in_file(file_path, pattern):
    """Count occurrences of a pattern in a file."""
    content = read_file(file_path)
    if content is None:
        return 0

    if isinstance(pattern, str):
        return len(re.findall(pattern, content))
    else:
        return len(pattern.findall(content))


def grep_file(file_path, pattern):
    """Search for pattern in file and return matching lines with line numbers."""
    content = read_file(file_path)
    if content is None:
        return []

    if isinstance(pattern, str):
        regex = re.compile(pattern)
    else:
        regex = pattern

    results = []
    for index, line in enumerate(content.split('\n')):
        if regex.search(line):
            results.append({'lineNumber': index + 1, 'content': line})

    return results


def generate_handoff(caller='Hook'):
    """Generate a handoff document capturing current pipeline/task state.

    Reads .rix/active-pipeline.md for pipeline context and the task list
    for progress. Writes a timestamped handoff markdown file.

    Args:
        caller: Label for log messages (e.g., 'PreCompact', 'SessionEnd').

    Returns:
        Dict with 'handoff_file' (str path or None) and 'summary_lines' (list of str).
    """
    from datetime import datetime as _dt

    timestamp = get_date_time_string()
    file_timestamp = _dt.now().strftime('%Y-%m-%d_%H%M%S')

    # Detect git context
    git_root_result = run_command('git rev-parse --show-toplevel')
    git_root = git_root_result['output'] if git_root_result['success'] else None

    branch_result = run_command('git branch --show-current')
    current_branch = branch_result['output'] if branch_result['success'] else 'unknown'

    cwd = os.getcwd()

    # Read active pipeline
    pipeline_state = None
    feature_dir = None
    feature_name = 'Unknown'
    task_list_path = None

    if git_root:
        pipeline_file = os.path.join(git_root, '.rix', 'active-pipeline.md')
        pipeline_content = read_file(pipeline_file)

        if pipeline_content:
            pipeline_state = {}
            for match in re.finditer(r'^- \*\*([^*]+)\*\*:\s*(.+)$', pipeline_content, re.MULTILINE):
                pipeline_state[match.group(1).strip()] = match.group(2).strip()

            feature_dir = pipeline_state.get('Feature dir')
            feature_name = pipeline_state.get('Feature', 'Unknown')
            task_list_path = pipeline_state.get('Task list')

    # Parse task list
    completed_count = 0
    pending_count = 0
    skipped_count = 0
    pending_tasks = []

    if task_list_path:
        task_list_content = read_file(task_list_path)
        if task_list_content:
            for line in task_list_content.split('\n'):
                if re.search(r'- \[x\]', line, re.IGNORECASE):
                    completed_count += 1
                elif re.search(r'- \[~\]', line):
                    skipped_count += 1
                elif re.search(r'- \[ \]', line):
                    pending_count += 1
                    name_match = re.search(r'- \[ \]\s*(.+)', line)
                    if name_match:
                        pending_tasks.append(name_match.group(1).strip())

    # Determine handoff directory
    if feature_dir:
        handoffs_dir = os.path.join(feature_dir, 'handoffs')
    else:
        handoffs_dir = os.path.join(get_home_dir(), '.claude', 'homunculus', 'handoffs')

    ensure_dir(handoffs_dir)
    handoff_file = os.path.join(handoffs_dir, f'handoff-{file_timestamp}.md')

    # Build handoff document
    lines = []
    lines.append(f'# Handoff: {feature_name}')
    lines.append('')
    lines.append(f'**Timestamp:** {timestamp}')
    lines.append('')

    lines.append('## Pipeline State')
    lines.append('')
    if pipeline_state:
        for key, value in pipeline_state.items():
            lines.append(f'- **{key}**: {value}')
    else:
        lines.append('_No active pipeline found (.rix/active-pipeline.md not present)_')
    lines.append('')

    lines.append('## Task Progress')
    lines.append('')
    if task_list_path and (completed_count + pending_count + skipped_count > 0):
        lines.append(f'- **Completed:** {completed_count}')
        lines.append(f'- **Pending:** {pending_count}')
        if skipped_count > 0:
            lines.append(f'- **Skipped:** {skipped_count}')
        lines.append('')
        if pending_tasks:
            lines.append('**Pending tasks:**')
            lines.append('')
            for task in pending_tasks:
                lines.append(f'- [ ] {task}')
    else:
        lines.append('_No task list available_')
    lines.append('')

    lines.append('## Working Directory')
    lines.append('')
    lines.append(f'`{cwd}`')
    lines.append('')

    lines.append('## Git Branch')
    lines.append('')
    lines.append(f'`{current_branch}`')
    lines.append('')

    lines.append('## Recovery Instructions')
    lines.append('')
    lines.append('Run `/seance` to recover context from this handoff.')
    lines.append('')

    write_file(handoff_file, '\n'.join(lines))

    # Build summary for caller
    summary_lines = []
    summary_lines.append(f'[{caller}] Handoff saved: {handoff_file}')
    summary_lines.append(f'[{caller}] Feature: {feature_name} | Branch: {current_branch}')
    if pipeline_state:
        stage = pipeline_state.get('Stage', 'unknown')
        gate = pipeline_state.get('Gate', 'unknown')
        summary_lines.append(f'[{caller}] Pipeline: stage={stage}, gate={gate}')
    if completed_count + pending_count + skipped_count > 0:
        skipped_suffix = f', {skipped_count} skipped' if skipped_count > 0 else ''
        summary_lines.append(f'[{caller}] Tasks: {completed_count} completed, {pending_count} pending{skipped_suffix}')
    summary_lines.append(f'[{caller}] Recovery: Run /seance to restore context')

    return {'handoff_file': handoff_file, 'summary_lines': summary_lines}
