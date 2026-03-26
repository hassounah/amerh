#!/usr/bin/env python3
# Inlined: emit_activity.py intentionally uses stdlib only
import json
import os
import re
import sys
from datetime import datetime, timezone

MAX_STDIN = 262144       # 256KB
MAX_FIELD_SIZE = 32768   # 32KB per-field truncation
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB rotation threshold
EVENTS_ROOT = os.path.join(os.path.expanduser("~"), ".corner-office", "events")


def _truncate_fields(obj):
    """Recursively truncate string values > MAX_FIELD_SIZE."""
    if isinstance(obj, dict):
        return {k: _truncate_fields(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_truncate_fields(item) for item in obj]
    elif isinstance(obj, str) and len(obj) > MAX_FIELD_SIZE:
        original_len = len(obj)
        return obj[:MAX_FIELD_SIZE] + f"... [truncated from {original_len} bytes]"
    return obj


def _get_workspace_slug(cwd):
    """Derive a safe workspace slug from a directory path."""
    if not cwd:
        return "unknown"
    name = os.path.basename(cwd.rstrip("/"))
    slug = re.sub(r"[^a-zA-Z0-9_-]", "", name)[:64]
    return slug if slug else "unknown"


def main():
    if not os.path.exists(os.path.join(EVENTS_ROOT, "enabled")):
        return

    raw = sys.stdin.buffer.read(MAX_STDIN)
    if not raw:
        return

    # Warn if stdin was potentially truncated
    if len(raw) == MAX_STDIN:
        print("[emit_activity] WARNING: stdin truncated at 256KB", file=sys.stderr)

    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        print(f"[emit_activity] WARNING: invalid JSON stdin: {e}", file=sys.stderr)
        return

    # Normalize field names
    event = data.pop("hook_event_name", data.pop("event", "unknown"))
    session_id = data.pop("session_id", data.pop("sessionId", ""))
    short_id = session_id[-8:] if session_id else "unknown"

    cwd = data.get("cwd", "")
    workspace = _get_workspace_slug(cwd)

    # Recursively truncate large fields
    truncated = _truncate_fields(data)
    truncated_dict = truncated if isinstance(truncated, dict) else {}

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    entry: dict = {
        "event": event,
        "sessionId": session_id,
        "timestamp": ts,
        "workspace": workspace,
    }
    entry.update(truncated_dict)

    workspace_dir = os.path.join(EVENTS_ROOT, workspace)
    os.makedirs(workspace_dir, mode=0o700, exist_ok=True)

    filepath = os.path.join(workspace_dir, f"{short_id}.jsonl")

    # Rotate if file exceeds size threshold
    try:
        if os.path.exists(filepath) and os.path.getsize(filepath) >= MAX_FILE_SIZE:
            counter = 1
            while os.path.exists(f"{filepath}.{counter}"):
                counter += 1
            os.rename(filepath, f"{filepath}.{counter}")
    except OSError:
        pass  # race condition or permission error — proceed with append

    fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[emit_activity] ERROR: {e}", file=sys.stderr)
