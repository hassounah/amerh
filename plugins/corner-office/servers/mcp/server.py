"""SQL Database MCP server.

Provides two tools:
- sql_query: read-only SQL execution (SELECT, EXPLAIN, etc.)
- sql_execute: write SQL execution (INSERT, UPDATE, DELETE, etc.)

Named connections are loaded from ~/.claude/sql-connections.json.
Config is reloaded automatically when the file changes.
"""

import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import psycopg2
from dotenv import dotenv_values
from mcp.server.fastmcp import FastMCP

from sql_validator import validate_read_only, validate_write

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

mcp = FastMCP("corner-office")

_CONNECTIONS_FILE = Path.home() / ".claude" / "sql-connections.json"
_ENV_VAR_RE = re.compile(r'\$\{(\w+)\}')
_MAX_ROWS = 500
_CONNECT_TIMEOUT = 10

# DDL keywords that return "Statement executed successfully" instead of "0 row(s) affected"
_DDL_KEYWORDS = frozenset({'CREATE', 'ALTER', 'DROP'})

# Named connections with mtime-based reloading
_named_connections: dict = {}
_connections_mtime: float = 0.0


def _load_connections() -> dict:
    """Load named connections from ~/.claude/sql-connections.json."""
    if not _CONNECTIONS_FILE.exists():
        logger.warning("sql-connections.json not found at %s; named connections unavailable.", _CONNECTIONS_FILE)
        return {}
    try:
        with open(_CONNECTIONS_FILE) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("sql-connections.json must be a JSON object; ignoring.")
            return {}
        return data
    except Exception as exc:
        logger.warning("Failed to load sql-connections.json: %s", exc)
        return {}


def _get_connections() -> dict:
    """Get named connections, reloading if config file has changed."""
    global _named_connections, _connections_mtime
    try:
        current_mtime = _CONNECTIONS_FILE.stat().st_mtime
        if current_mtime != _connections_mtime:
            _named_connections = _load_connections()
            _connections_mtime = current_mtime
    except FileNotFoundError:
        if _named_connections:
            _named_connections = {}
            _connections_mtime = 0.0
    return _named_connections


def _load_env_file(env_file: str) -> dict[str, str]:
    """Load variables from a .env file without modifying os.environ.

    Uses python-dotenv for robust parsing (quoted values, escaped chars, export prefix, etc.).
    """
    env_path = Path(env_file).expanduser()
    if not env_path.exists():
        raise ValueError(f"env_file not found: {env_path}")
    values = dotenv_values(env_path)
    return {k: v for k, v in values.items() if v is not None}


def _interpolate_env(url: str, env_vars: Optional[dict[str, str]] = None) -> str:
    """Replace ${ENV_VAR} patterns with values from env_vars dict or os.environ.

    If env_vars is provided, looks up variables there first, then falls back to os.environ.
    Values are URL-encoded (safe='') so special characters in passwords don't break the URL.
    Raises ValueError if a referenced env var is not found in either source.
    """
    def _sub(m):
        name = m.group(1)
        if env_vars:
            val = env_vars.get(name)
            if val is not None:
                return quote(val, safe='')
        val = os.environ.get(name)
        if val is None:
            source_hint = "env_file or environment" if env_vars else "environment"
            raise ValueError(f"Variable '{name}' is not set in {source_hint}.")
        return quote(val, safe='')
    return _ENV_VAR_RE.sub(_sub, url)


def _detect_db_type(url: str) -> Optional[str]:
    """Auto-detect database type from connection URL."""
    if url.startswith('postgresql://') or url.startswith('postgres://'):
        return 'postgresql'
    if url.startswith('sqlite:///') or url.startswith('sqlite://'):
        return 'sqlite'
    if '://' not in url:
        return 'sqlite'
    return None


def _extract_sqlite_path(url: str) -> str:
    """Extract file path from SQLite URL or return as-is if already a path.

    sqlite:///tmp/test.db → /tmp/test.db (absolute path — 3rd slash is path start)
    sqlite://relative.db  → relative.db
    /tmp/test.db          → /tmp/test.db (already a path)
    """
    if url.startswith('sqlite://'):
        return url[len('sqlite://'):]
    return url


def _resolve_connection(
    connection_name: Optional[str],
    connection_string: Optional[str],
    database_type: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Resolve the connection URL and database type.

    Returns (url, db_type) or (None, None) if no connection found.
    Resolution order:
    1. named connection from sql-connections.json
    2. direct connection_string param
    """
    url = None
    cfg_type = None
    env_vars = None

    if connection_name:
        connections = _get_connections()
        entry = connections.get(connection_name)
        if entry is None:
            return None, None
        url = entry.get('url', '')
        cfg_type = entry.get('type')
        env_file = entry.get('env_file')
        if env_file:
            env_vars = _load_env_file(env_file)
    elif connection_string:
        url = connection_string
    else:
        return None, None

    url = _interpolate_env(url, env_vars)

    db_type = database_type or cfg_type or _detect_db_type(url)
    return url, db_type


def _format_results(cursor) -> str:
    """Format query results as a text table with headers.

    Fetches at most _MAX_ROWS rows. If more are available, appends a truncation notice.
    """
    rows = cursor.fetchmany(_MAX_ROWS + 1)
    if not rows:
        return "Query returned 0 rows."

    truncated = len(rows) > _MAX_ROWS
    if truncated:
        rows = rows[:_MAX_ROWS]

    columns = [desc[0] for desc in cursor.description]
    col_widths = [len(c) for c in columns]
    str_rows = []
    for row in rows:
        str_row = [str(v) if v is not None else 'NULL' for v in row]
        str_rows.append(str_row)
        for i, val in enumerate(str_row):
            col_widths[i] = max(col_widths[i], len(val))

    def fmt_row(values):
        return ' | '.join(v.ljust(col_widths[i]) for i, v in enumerate(values))

    separator = '-+-'.join('-' * w for w in col_widths)
    lines = [fmt_row(columns), separator]
    for row in str_rows:
        lines.append(fmt_row(row))

    if truncated:
        lines.append(f"\n(Showing {_MAX_ROWS} rows. Results truncated. Add LIMIT clause to reduce result set.)")
    else:
        lines.append(f"\n({len(rows)} row{'s' if len(rows) != 1 else ''} returned)")
    return '\n'.join(lines)


def _format_write_result(sql: str, rowcount: int) -> str:
    """Format the result of a write operation.

    Returns 'Statement executed successfully.' for DDL (rowcount 0 or -1),
    and 'N row(s) affected.' for DML.
    """
    if rowcount <= 0:
        normalized = sql.strip().upper()
        first_keyword = normalized.split()[0] if normalized else ''
        if first_keyword in _DDL_KEYWORDS:
            return "Statement executed successfully."
    if rowcount < 0:
        return "Statement executed successfully."
    return f"{rowcount} row(s) affected."


def _execute_postgresql(url: str, sql: str, params: Optional[list], read_only: bool) -> str:
    """Execute SQL against a PostgreSQL database."""
    conn = None
    try:
        conn = psycopg2.connect(url, connect_timeout=_CONNECT_TIMEOUT)
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            if read_only:
                return _format_results(cur)
            else:
                conn.commit()
                return _format_write_result(sql, cur.rowcount)
    except psycopg2.OperationalError:
        return "PostgreSQL error: Could not connect to database. Check connection string and server availability."
    except psycopg2.Error as exc:
        return f"PostgreSQL error: {exc.pgcode or 'unknown'} — {exc.pgerror or str(exc)}"
    finally:
        if conn:
            conn.close()


def _execute_sqlite(path: str, sql: str, params: Optional[list], read_only: bool) -> str:
    """Execute SQL against a SQLite database."""
    conn = None
    try:
        conn = sqlite3.connect(path)
        cur = conn.execute(sql, params or [])
        if read_only:
            return _format_results(cur)
        else:
            conn.commit()
            return _format_write_result(sql, cur.rowcount)
    except sqlite3.OperationalError as exc:
        return f"SQLite error: {exc}. Check that the file path exists and is readable."
    except sqlite3.Error as exc:
        return f"SQLite error: {exc}"
    finally:
        if conn:
            conn.close()


@mcp.tool()
def sql_query(
    sql: str,
    connection_name: str = None,
    connection_string: str = None,
    params: list = None,
    database_type: str = None,
) -> str:
    """Execute a read-only SQL query (SELECT, EXPLAIN, PRAGMA, etc.) and return results.

    Args:
        sql: The SQL query to execute. Must be read-only (SELECT, WITH, EXPLAIN, PRAGMA, SHOW, DESCRIBE).
            Note: Keyword validation does not prevent side-effect functions (e.g., pg_terminate_backend).
            Use restricted database roles for auto-approved connections.
        connection_name: Named connection key from ~/.claude/sql-connections.json.
            File format: {"mydb": {"url": "postgresql://user:${DB_PASS}@host/db", "type": "postgresql",
            "env_file": "~/.secrets/mydb.env"}}
            Supports ${ENV_VAR} interpolation. If env_file is set, variables are loaded from that
            file at connect time (secrets stay out of the shell environment).
        connection_string: Direct database connection URL (postgresql:// or file path for SQLite).
        params: Query parameters for parameterized queries (list of values).
        database_type: Override database type detection ('postgresql' or 'sqlite').

    Returns:
        Formatted query results as a text table (max 500 rows), or an error message.
    """
    try:
        validate_read_only(sql)
    except ValueError as exc:
        return f"Validation error: {exc}"

    try:
        url, db_type = _resolve_connection(connection_name, connection_string, database_type)
    except ValueError as exc:
        return f"Error: {exc}"

    if url is None:
        if connection_name:
            return f"Error: Named connection '{connection_name}' not found in sql-connections.json."
        return "Error: No connection specified. Provide 'connection_name' or 'connection_string'."

    if db_type is None:
        return f"Error: Cannot detect database type from URL. Provide 'database_type' parameter ('postgresql' or 'sqlite')."

    if db_type in ('postgresql', 'postgres'):
        return _execute_postgresql(url, sql, params, read_only=True)
    elif db_type == 'sqlite':
        return _execute_sqlite(_extract_sqlite_path(url), sql, params, read_only=True)
    else:
        return f"Error: Unsupported database type '{db_type}'. Use 'postgresql' or 'sqlite'."


@mcp.tool()
def sql_execute(
    sql: str,
    connection_name: str = None,
    connection_string: str = None,
    params: list = None,
    database_type: str = None,
) -> str:
    """Execute a write SQL statement (INSERT, UPDATE, DELETE, CREATE, etc.) and return result.

    Stored procedures (CALL) may have side effects beyond the statement text.

    Args:
        sql: The SQL statement to execute. Must be a write operation
            (INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, TRUNCATE, COPY, CALL, MERGE, REPLACE).
        connection_name: Named connection key from ~/.claude/sql-connections.json.
            File format: {"mydb": {"url": "postgresql://user:${DB_PASS}@host/db", "type": "postgresql",
            "env_file": "~/.secrets/mydb.env"}}
            Supports ${ENV_VAR} interpolation. If env_file is set, variables are loaded from that
            file at connect time (secrets stay out of the shell environment).
        connection_string: Direct database connection URL (postgresql:// or file path for SQLite).
        params: Query parameters for parameterized queries (list of values).
        database_type: Override database type detection ('postgresql' or 'sqlite').

    Returns:
        Affected row count or success message, or an error message.
    """
    try:
        validate_write(sql)
    except ValueError as exc:
        return f"Validation error: {exc}"

    try:
        url, db_type = _resolve_connection(connection_name, connection_string, database_type)
    except ValueError as exc:
        return f"Error: {exc}"

    if url is None:
        if connection_name:
            return f"Error: Named connection '{connection_name}' not found in sql-connections.json."
        return "Error: No connection specified. Provide 'connection_name' or 'connection_string'."

    if db_type is None:
        return f"Error: Cannot detect database type from URL. Provide 'database_type' parameter ('postgresql' or 'sqlite')."

    if db_type in ('postgresql', 'postgres'):
        return _execute_postgresql(url, sql, params, read_only=False)
    elif db_type == 'sqlite':
        return _execute_sqlite(_extract_sqlite_path(url), sql, params, read_only=False)
    else:
        return f"Error: Unsupported database type '{db_type}'. Use 'postgresql' or 'sqlite'."


def main():
    """Entry point for the MCP server."""
    # Trigger initial config load
    _get_connections()
    mcp.run()


if __name__ == '__main__':
    main()
