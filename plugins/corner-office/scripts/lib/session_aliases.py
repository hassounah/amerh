"""
Session Aliases Library for Claude Code.
Manages session aliases stored in ~/.claude/session-aliases.json.
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone

from utils import ensure_dir, get_claude_dir, log, read_file

# Current alias storage format version
ALIAS_VERSION = '1.0'


def get_aliases_path():
    """Get the aliases file path."""
    return os.path.join(get_claude_dir(), 'session-aliases.json')


def get_default_aliases():
    """Default aliases file structure."""
    return {
        'version': ALIAS_VERSION,
        'aliases': {},
        'metadata': {
            'totalCount': 0,
            'lastUpdated': datetime.now(timezone.utc).isoformat(),
        },
    }


def load_aliases():
    """Load aliases from file."""
    aliases_path = get_aliases_path()

    if not os.path.exists(aliases_path):
        return get_default_aliases()

    content = read_file(aliases_path)
    if not content:
        return get_default_aliases()

    try:
        data = json.loads(content)

        # Validate structure
        if not isinstance(data.get('aliases'), dict):
            log('[Aliases] Invalid aliases file structure, resetting')
            return get_default_aliases()

        # Ensure version field
        if not data.get('version'):
            data['version'] = ALIAS_VERSION

        # Ensure metadata
        if not data.get('metadata'):
            data['metadata'] = {
                'totalCount': len(data['aliases']),
                'lastUpdated': datetime.now(timezone.utc).isoformat(),
            }

        return data
    except (json.JSONDecodeError, ValueError) as err:
        log(f'[Aliases] Error parsing aliases file: {err}')
        return get_default_aliases()


def save_aliases(aliases):
    """Save aliases to file with atomic write.

    Returns:
        True on success, False on failure.
    """
    aliases_path = get_aliases_path()
    temp_path = aliases_path + '.tmp'
    backup_path = aliases_path + '.bak'

    try:
        # Update metadata
        aliases['metadata'] = {
            'totalCount': len(aliases['aliases']),
            'lastUpdated': datetime.now(timezone.utc).isoformat(),
        }

        content = json.dumps(aliases, indent=2)

        # Ensure directory exists
        ensure_dir(os.path.dirname(aliases_path))

        # Create backup if file exists
        if os.path.exists(aliases_path):
            shutil.copy2(aliases_path, backup_path)

        # Atomic write: write to temp file, then rename
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Atomic replace — works cross-platform (POSIX and Windows)
        os.replace(temp_path, aliases_path)

        # Remove backup on success
        if os.path.exists(backup_path):
            os.unlink(backup_path)

        return True
    except OSError as err:
        log(f'[Aliases] Error saving aliases: {err}')

        # Restore from backup if exists
        if os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, aliases_path)
                log('[Aliases] Restored from backup')
            except OSError as restore_err:
                log(f'[Aliases] Failed to restore backup: {restore_err}')

        # Clean up temp file
        if os.path.exists(temp_path):
            os.unlink(temp_path)

        return False


def resolve_alias(alias):
    """Resolve an alias to get session path.

    Returns:
        Dict with alias data or None if not found.
    """
    # Validate alias name (alphanumeric, dash, underscore)
    if not re.match(r'^[a-zA-Z0-9_-]+$', alias):
        return None

    data = load_aliases()
    alias_data = data['aliases'].get(alias)

    if not alias_data:
        return None

    return {
        'alias': alias,
        'sessionPath': alias_data['sessionPath'],
        'createdAt': alias_data['createdAt'],
        'title': alias_data.get('title'),
    }


def set_alias(alias, session_path, title=None):
    """Set or update an alias for a session.

    Args:
        alias: Alias name (alphanumeric, dash, underscore).
        session_path: Session directory path.
        title: Optional title for the alias.

    Returns:
        Dict with success status and message.
    """
    # Validate alias name
    if not alias:
        return {'success': False, 'error': 'Alias name cannot be empty'}

    if not re.match(r'^[a-zA-Z0-9_-]+$', alias):
        return {'success': False, 'error': 'Alias name must contain only letters, numbers, dashes, and underscores'}

    # Reserved alias names
    reserved = ['list', 'help', 'remove', 'delete', 'create', 'set']
    if alias.lower() in reserved:
        return {'success': False, 'error': f"'{alias}' is a reserved alias name"}

    data = load_aliases()
    existing = data['aliases'].get(alias)
    is_new = existing is None

    data['aliases'][alias] = {
        'sessionPath': session_path,
        'createdAt': existing['createdAt'] if existing else datetime.now(timezone.utc).isoformat(),
        'updatedAt': datetime.now(timezone.utc).isoformat(),
        'title': title or None,
    }

    if save_aliases(data):
        return {
            'success': True,
            'isNew': is_new,
            'alias': alias,
            'sessionPath': session_path,
            'title': data['aliases'][alias]['title'],
        }

    return {'success': False, 'error': 'Failed to save alias'}


def list_aliases(search=None, limit=None):
    """List all aliases.

    Args:
        search: Filter aliases by name or title (partial match).
        limit: Maximum number of aliases to return.

    Returns:
        List of alias dicts.
    """
    data = load_aliases()

    aliases = [
        {
            'name': name,
            'sessionPath': info['sessionPath'],
            'createdAt': info.get('createdAt'),
            'updatedAt': info.get('updatedAt'),
            'title': info.get('title'),
        }
        for name, info in data['aliases'].items()
    ]

    # Sort by updated time (newest first)
    aliases.sort(
        key=lambda a: a.get('updatedAt') or a.get('createdAt') or '',
        reverse=True,
    )

    # Apply search filter
    if search:
        search_lower = search.lower()
        aliases = [
            a for a in aliases
            if search_lower in a['name'].lower()
            or (a.get('title') and search_lower in a['title'].lower())
        ]

    # Apply limit
    if limit and limit > 0:
        aliases = aliases[:limit]

    return aliases


def delete_alias(alias):
    """Delete an alias.

    Returns:
        Dict with success status.
    """
    data = load_aliases()

    if alias not in data['aliases']:
        return {'success': False, 'error': f"Alias '{alias}' not found"}

    deleted = data['aliases'][alias]
    del data['aliases'][alias]

    if save_aliases(data):
        return {
            'success': True,
            'alias': alias,
            'deletedSessionPath': deleted['sessionPath'],
        }

    return {'success': False, 'error': 'Failed to delete alias'}


def rename_alias(old_alias, new_alias):
    """Rename an alias.

    Returns:
        Dict with success status.
    """
    data = load_aliases()

    if old_alias not in data['aliases']:
        return {'success': False, 'error': f"Alias '{old_alias}' not found"}

    if new_alias in data['aliases']:
        return {'success': False, 'error': f"Alias '{new_alias}' already exists"}

    # Validate new alias name
    if not re.match(r'^[a-zA-Z0-9_-]+$', new_alias):
        return {'success': False, 'error': 'New alias name must contain only letters, numbers, dashes, and underscores'}

    alias_data = data['aliases'][old_alias]
    del data['aliases'][old_alias]

    alias_data['updatedAt'] = datetime.now(timezone.utc).isoformat()
    data['aliases'][new_alias] = alias_data

    if save_aliases(data):
        return {
            'success': True,
            'oldAlias': old_alias,
            'newAlias': new_alias,
            'sessionPath': alias_data['sessionPath'],
        }

    # Restore old alias on failure
    data['aliases'][old_alias] = alias_data
    return {'success': False, 'error': 'Failed to rename alias'}


def resolve_session_alias(alias_or_id):
    """Get session path by alias (convenience function).

    Args:
        alias_or_id: Alias name or session ID.

    Returns:
        Session path string.
    """
    # First try to resolve as alias
    resolved = resolve_alias(alias_or_id)
    if resolved:
        return resolved['sessionPath']

    # If not an alias, return as-is (might be a session path)
    return alias_or_id


def update_alias_title(alias, title):
    """Update alias title.

    Returns:
        Dict with success status.
    """
    data = load_aliases()

    if alias not in data['aliases']:
        return {'success': False, 'error': f"Alias '{alias}' not found"}

    data['aliases'][alias]['title'] = title
    data['aliases'][alias]['updatedAt'] = datetime.now(timezone.utc).isoformat()

    if save_aliases(data):
        return {
            'success': True,
            'alias': alias,
            'title': title,
        }

    return {'success': False, 'error': 'Failed to update alias title'}


def get_aliases_for_session(session_path):
    """Get all aliases for a specific session.

    Returns:
        List of alias dicts.
    """
    data = load_aliases()
    aliases = []

    for name, info in data['aliases'].items():
        if info['sessionPath'] == session_path:
            aliases.append({
                'name': name,
                'createdAt': info.get('createdAt'),
                'title': info.get('title'),
            })

    return aliases


def cleanup_aliases(session_exists_fn):
    """Clean up aliases for non-existent sessions.

    Args:
        session_exists_fn: Function that checks if a session exists.

    Returns:
        Dict with cleanup result.
    """
    data = load_aliases()
    removed = []

    for name in list(data['aliases'].keys()):
        info = data['aliases'][name]
        if not session_exists_fn(info['sessionPath']):
            removed.append({'name': name, 'sessionPath': info['sessionPath']})
            del data['aliases'][name]

    if removed:
        save_aliases(data)

    return {
        'totalChecked': len(data['aliases']) + len(removed),
        'removed': len(removed),
        'removedAliases': removed,
    }
