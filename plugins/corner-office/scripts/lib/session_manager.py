"""
Session Manager Library for Claude Code.
Provides core session CRUD operations for listing, loading, and managing sessions.

Sessions are stored as markdown files in ~/.claude/sessions/ with format:
- YYYY-MM-DD-session.tmp (old format)
- YYYY-MM-DD-<short-id>-session.tmp (new format)
"""

import os
import re

from utils import get_sessions_dir, log, read_file

# Session filename pattern: YYYY-MM-DD-[short-id]-session.tmp
# The short-id is optional (old format) and can be 8+ alphanumeric characters
# Matches: "2026-02-01-session.tmp" or "2026-02-01-a1b2c3d4-session.tmp"
SESSION_FILENAME_REGEX = re.compile(
    r'^(\d{4}-\d{2}-\d{2})(?:-([a-z0-9]{8,}))?-session\.tmp$'
)


def parse_session_filename(filename):
    """Parse session filename to extract metadata.

    Args:
        filename: Session filename (e.g., '2026-01-17-abc123de-session.tmp').

    Returns:
        Dict with parsed metadata or None if invalid.
    """
    match = SESSION_FILENAME_REGEX.match(filename)
    if not match:
        return None

    date_str = match.group(1)
    short_id = match.group(2) or 'no-id'

    return {
        'filename': filename,
        'shortId': short_id,
        'date': date_str,
        'datetime': date_str,
    }


def get_session_path(filename):
    """Get the full path to a session file."""
    return os.path.join(get_sessions_dir(), filename)


def get_session_content(session_path):
    """Read and parse session markdown content.

    Returns:
        Session content string or None if not found.
    """
    if not os.path.exists(session_path):
        return None

    return read_file(session_path)


def parse_session_metadata(content):
    """Parse session metadata from markdown content.

    Returns:
        Dict with parsed metadata fields.
    """
    metadata = {
        'title': None,
        'date': None,
        'started': None,
        'lastUpdated': None,
        'completed': [],
        'inProgress': [],
        'notes': '',
        'context': '',
    }

    if not content:
        return metadata

    # Extract title from first heading
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if title_match:
        metadata['title'] = title_match.group(1).strip()

    # Extract date
    date_match = re.search(r'\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})', content)
    if date_match:
        metadata['date'] = date_match.group(1)

    # Extract started time
    started_match = re.search(r'\*\*Started:\*\*\s*([\d:]+)', content)
    if started_match:
        metadata['started'] = started_match.group(1)

    # Extract last updated
    updated_match = re.search(r'\*\*Last Updated:\*\*\s*([\d:]+)', content)
    if updated_match:
        metadata['lastUpdated'] = updated_match.group(1)

    # Extract completed items
    completed_section = re.search(
        r'### Completed\s*\n([\s\S]*?)(?=###|\n\n|$)', content
    )
    if completed_section:
        items = re.findall(r'- \[x\]\s*(.+)', completed_section.group(1))
        if items:
            metadata['completed'] = [item.strip() for item in items]

    # Extract in-progress items
    progress_section = re.search(
        r'### In Progress\s*\n([\s\S]*?)(?=###|\n\n|$)', content
    )
    if progress_section:
        items = re.findall(r'- \[ \]\s*(.+)', progress_section.group(1))
        if items:
            metadata['inProgress'] = [item.strip() for item in items]

    # Extract notes
    notes_section = re.search(
        r'### Notes for Next Session\s*\n([\s\S]*?)(?=###|\n\n|$)', content
    )
    if notes_section:
        metadata['notes'] = notes_section.group(1).strip()

    # Extract context to load
    context_section = re.search(
        r'### Context to Load\s*\n```\n([\s\S]*?)```', content
    )
    if context_section:
        metadata['context'] = context_section.group(1).strip()

    return metadata


def get_session_stats(session_path):
    """Calculate statistics for a session.

    Returns:
        Dict with statistics.
    """
    content = get_session_content(session_path)
    metadata = parse_session_metadata(content)

    return {
        'totalItems': len(metadata['completed']) + len(metadata['inProgress']),
        'completedItems': len(metadata['completed']),
        'inProgressItems': len(metadata['inProgress']),
        'lineCount': len(content.split('\n')) if content else 0,
        'hasNotes': bool(metadata['notes']),
        'hasContext': bool(metadata['context']),
    }


def get_all_sessions(limit=50, offset=0, date=None, search=None):
    """Get all sessions with optional filtering and pagination.

    Args:
        limit: Maximum number of sessions to return.
        offset: Number of sessions to skip.
        date: Filter by date (YYYY-MM-DD format).
        search: Search in short ID.

    Returns:
        Dict with sessions array and pagination info.
    """
    sessions_dir = get_sessions_dir()

    if not os.path.exists(sessions_dir):
        return {'sessions': [], 'total': 0, 'offset': offset, 'limit': limit, 'hasMore': False}

    sessions = []

    for entry_name in os.listdir(sessions_dir):
        entry_path = os.path.join(sessions_dir, entry_name)

        # Skip non-files (only process .tmp files)
        if not os.path.isfile(entry_path) or not entry_name.endswith('.tmp'):
            continue

        metadata = parse_session_filename(entry_name)
        if not metadata:
            continue

        # Apply date filter
        if date and metadata['date'] != date:
            continue

        # Apply search filter (search in short ID)
        if search and search not in metadata['shortId']:
            continue

        # Get file stats
        stat = os.stat(entry_path)

        session = dict(metadata)
        session.update({
            'sessionPath': entry_path,
            'hasContent': stat.st_size > 0,
            'size': stat.st_size,
            'modifiedTime': stat.st_mtime,
            'createdTime': getattr(stat, 'st_birthtime', stat.st_ctime),
        })
        sessions.append(session)

    # Sort by modified time (newest first)
    sessions.sort(key=lambda s: s['modifiedTime'], reverse=True)

    # Apply pagination
    paginated_sessions = sessions[offset:offset + limit]

    return {
        'sessions': paginated_sessions,
        'total': len(sessions),
        'offset': offset,
        'limit': limit,
        'hasMore': offset + limit < len(sessions),
    }


def get_session_by_id(session_id, include_content=False):
    """Get a single session by ID (short ID or full path).

    Args:
        session_id: Short ID or session filename.
        include_content: Include session content.

    Returns:
        Session dict or None if not found.
    """
    sessions_dir = get_sessions_dir()

    if not os.path.exists(sessions_dir):
        return None

    for entry_name in os.listdir(sessions_dir):
        entry_path = os.path.join(sessions_dir, entry_name)

        if not os.path.isfile(entry_path) or not entry_name.endswith('.tmp'):
            continue

        metadata = parse_session_filename(entry_name)
        if not metadata:
            continue

        # Check if session ID matches (short ID or full filename without .tmp)
        short_id_match = (
            metadata['shortId'] != 'no-id'
            and metadata['shortId'].startswith(session_id)
        )
        filename_match = (
            entry_name == session_id
            or entry_name == f'{session_id}.tmp'
        )
        no_id_match = (
            metadata['shortId'] == 'no-id'
            and entry_name == f'{session_id}-session.tmp'
        )

        if not short_id_match and not filename_match and not no_id_match:
            continue

        stat = os.stat(entry_path)

        session = dict(metadata)
        session.update({
            'sessionPath': entry_path,
            'size': stat.st_size,
            'modifiedTime': stat.st_mtime,
            'createdTime': getattr(stat, 'st_birthtime', stat.st_ctime),
        })

        if include_content:
            session['content'] = get_session_content(entry_path)
            session['metadata'] = parse_session_metadata(session['content'])
            session['stats'] = get_session_stats(entry_path)

        return session

    return None


def get_session_title(session_path):
    """Get session title from content.

    Returns:
        Title string or 'Untitled Session'.
    """
    content = get_session_content(session_path)
    metadata = parse_session_metadata(content)

    return metadata['title'] or 'Untitled Session'


def get_session_size(session_path):
    """Format session size in human-readable format.

    Returns:
        Formatted size string (e.g., '1.2 KB').
    """
    if not os.path.exists(session_path):
        return '0 B'

    stat = os.stat(session_path)
    size = stat.st_size

    if size < 1024:
        return f'{size} B'
    if size < 1024 * 1024:
        return f'{size / 1024:.1f} KB'
    return f'{size / (1024 * 1024):.1f} MB'


def write_session_content(session_path, content):
    """Write session content to file.

    Returns:
        True on success, False on failure.
    """
    try:
        with open(session_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except OSError as err:
        log(f'[SessionManager] Error writing session: {err}')
        return False


def append_session_content(session_path, content):
    """Append content to a session.

    Returns:
        True on success, False on failure.
    """
    try:
        with open(session_path, 'a', encoding='utf-8') as f:
            f.write(content)
        return True
    except OSError as err:
        log(f'[SessionManager] Error appending to session: {err}')
        return False


def delete_session(session_path):
    """Delete a session file.

    Returns:
        True on success, False on failure.
    """
    try:
        if os.path.exists(session_path):
            os.unlink(session_path)
            return True
        return False
    except OSError as err:
        log(f'[SessionManager] Error deleting session: {err}')
        return False


def session_exists(session_path):
    """Check if a session exists.

    Returns:
        True if session file exists.
    """
    return os.path.isfile(session_path)
