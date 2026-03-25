"""SQL validation module for the sql-database MCP server.

Validates SQL statements for read-only or write-only operations.
No external dependencies — stdlib only.
"""

import re

_LINE_COMMENT_RE = re.compile(r'--[^\n]*')
_BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
_WHITESPACE_RE = re.compile(r'\s+')

# Keywords that indicate read-only queries
_READ_KEYWORDS = frozenset({'SELECT', 'WITH', 'EXPLAIN', 'PRAGMA', 'SHOW', 'DESCRIBE'})

# Keywords that indicate write operations.
# IMPORTANT: Never add COPY, CALL, MERGE, or REPLACE to _READ_KEYWORDS — they have side effects.
_WRITE_KEYWORDS = frozenset({
    'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'TRUNCATE',
    'COPY', 'CALL', 'MERGE', 'REPLACE',
})


def normalize_sql(sql: str) -> str:
    """Strip SQL comments, collapse whitespace, return uppercased string."""
    sql = _LINE_COMMENT_RE.sub('', sql)
    sql = _BLOCK_COMMENT_RE.sub('', sql)
    sql = _WHITESPACE_RE.sub(' ', sql)
    return sql.strip().upper()


def has_multiple_statements(sql: str) -> bool:
    """Detect unquoted semicolons indicating multiple statements.

    Semicolons inside single or double quoted strings are ignored.
    A trailing semicolon (only whitespace/comments after it) is not treated
    as multiple statements.
    Returns True if multiple statements detected.
    """
    # Normalize first to strip comments, so "SELECT 1; --comment" is handled
    normalized = normalize_sql(sql)

    in_single_quote = False
    in_double_quote = False
    i = 0
    while i < len(normalized):
        ch = normalized[i]
        if ch == "'" and not in_double_quote:
            if in_single_quote and i + 1 < len(normalized) and normalized[i + 1] == "'":
                i += 2
                continue
            in_single_quote = not in_single_quote
        elif ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif ch == ';' and not in_single_quote and not in_double_quote:
            # Only flag as multiple if non-whitespace follows the semicolon
            remaining = normalized[i + 1:].strip()
            if remaining:
                return True
        i += 1
    return False


def _contains_write_keyword(sql: str) -> bool:
    """Check if normalized SQL contains any write keyword outside quoted strings.

    Works on the original (non-normalized) SQL to preserve quotes.
    Uses a simple tokenizer to skip quoted sections.
    """
    in_single_quote = False
    in_double_quote = False
    word = []

    def check_word(w: str) -> bool:
        return w.upper() in _WRITE_KEYWORDS

    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double_quote:
            if in_single_quote and i + 1 < len(sql) and sql[i + 1] == "'":
                i += 2
                continue
            in_single_quote = not in_single_quote
            if word:
                if check_word(''.join(word)):
                    return True
                word = []
        elif ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            if word:
                if check_word(''.join(word)):
                    return True
                word = []
        elif not in_single_quote and not in_double_quote:
            if ch.isalnum() or ch == '_':
                word.append(ch)
            else:
                if word:
                    if check_word(''.join(word)):
                        return True
                    word = []
        else:
            # Inside a quoted string — reset word accumulator
            if word:
                word = []
        i += 1

    if word and check_word(''.join(word)):
        return True

    return False


def validate_read_only(sql: str) -> None:
    """Raise ValueError if SQL is not a read-only statement.

    Checks:
    - First keyword must be a read keyword (SELECT, WITH, EXPLAIN, PRAGMA, SHOW, DESCRIBE)
    - Must not contain write keywords outside quoted strings
    - Must not be a multi-statement query
    """
    normalized = normalize_sql(sql)
    if not normalized:
        raise ValueError("SQL statement is empty.")

    first_keyword = normalized.split()[0]
    if first_keyword not in _READ_KEYWORDS:
        raise ValueError(
            f"SQL is not read-only: starts with '{first_keyword}'. "
            f"Expected one of: {', '.join(sorted(_READ_KEYWORDS))}."
        )

    if _contains_write_keyword(sql):
        raise ValueError(
            f"SQL contains write keywords ({', '.join(sorted(_WRITE_KEYWORDS))}) "
            "which are not allowed in read-only queries."
        )

    if has_multiple_statements(sql):
        raise ValueError(
            "SQL contains multiple statements (unquoted semicolon detected). "
            "Only single statements are allowed."
        )


def validate_write(sql: str) -> None:
    """Raise ValueError if SQL is not a write operation.

    Checks:
    - First keyword must be a write keyword (INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, etc.)
    - Must not be a SELECT statement
    - Must not be a multi-statement query
    """
    normalized = normalize_sql(sql)
    if not normalized:
        raise ValueError("SQL statement is empty.")

    first_keyword = normalized.split()[0]
    if first_keyword == 'SELECT':
        raise ValueError(
            "SQL is a SELECT statement. Use sql_query for read-only operations, not sql_execute."
        )

    if first_keyword not in _WRITE_KEYWORDS:
        raise ValueError(
            f"SQL is not a write operation: starts with '{first_keyword}'. "
            f"Expected one of: {', '.join(sorted(_WRITE_KEYWORDS))}."
        )

    if has_multiple_statements(sql):
        raise ValueError(
            "SQL contains multiple statements (unquoted semicolon detected). "
            "Only single statements are allowed."
        )
