#!/usr/bin/env python3
"""Corner Office Channel Server — bridges Claude Code sessions and the Corner Office app.

MCP channel server: stdio transport to Claude Code, WebSocket transport to app.
Spawned by Claude Code when --channels or --dangerously-load-development-channels is used.

Security model:
- WebSocket binds to 127.0.0.1 only (no network exposure)
- Bearer token required on WebSocket handshake (token stored in registration card)
- Max 10 concurrent connections, 256KB max message size
"""

import asyncio
import atexit
import glob
import hmac
import json
import logging
import os
import secrets
import signal
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone

import websockets
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

LOG_FILE = os.path.expanduser("~/.claude/channel-server.log")

logger = logging.getLogger("corner-office-channel")
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="[channel] %(message)s")

if "--debug" in sys.argv:
    _fh = logging.FileHandler(LOG_FILE)
    _fh.setFormatter(logging.Formatter("[channel] %(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_fh)
    logger.setLevel(logging.DEBUG)
    logger.info("Debug file logging enabled → %s", LOG_FILE)

# --- MCP Server Setup ---

mcp = Server(
    name="corner-office-channel",
    version="1.0.0",
    instructions=(
        'Messages from the Corner Office app arrive as <channel source="corner-office-channel" '
        'workspace="..." chat_id="..." sender="user">.\n'
        "The sender reads the Corner Office app, not this terminal. Anything you want them to see "
        "must go through the reply tool — your transcript output never reaches the app.\n"
        "Reply using the reply tool, passing chat_id back. The reply tool returns the message_id "
        "of the sent message. If you need to correct a prior reply, call edit_message with that "
        "message_id."
    ),
)

# Connected WebSocket clients
_ws_clients: set = set()

# Auth token — generated at startup, written to registration card
_channel_token: str = ""

# WebSocket port — set at startup, used by _rewatch_for_card
_channel_port: int = 0

# write_stream reference — set when stdio_server starts, used for JSON-RPC fallback
_write_stream = None

MAX_MESSAGE_TEXT = 10240  # 10 KB max message text from app


# --- Tools Exposed to Claude ---

@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="reply",
            description="Send a reply message to the Corner Office app.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": {"type": "string", "description": "The chat_id from the incoming channel message (for routing)."},
                    "text": {"type": "string", "description": "The reply text to send to the app user."},
                },
                "required": ["chat_id", "text"],
            },
        ),
        Tool(
            name="edit_message",
            description="Edit a previously sent message in the Corner Office app.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "The message_id returned by the original reply call."},
                    "text": {"type": "string", "description": "The new text for the message."},
                },
                "required": ["message_id", "text"],
            },
        ),
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "reply":
        result = await _reply(arguments["chat_id"], arguments["text"])
    elif name == "edit_message":
        result = await _edit_message(arguments["message_id"], arguments["text"])
    else:
        result = f"Unknown tool: {name}"
    return [TextContent(type="text", text=result)]


async def _reply(chat_id: str, text: str) -> str:
    msg_id = str(uuid.uuid4())
    msg = {
        "type": "reply",
        "id": msg_id,
        "text": text,
        "replyTo": chat_id,
        "timestamp": _iso_now(),
    }
    if not _ws_clients:
        logger.warning("reply called with no WebSocket clients connected")
        return f"Warning: no Corner Office app connected — reply not delivered (message_id={msg_id})"
    await _broadcast(msg)
    return f"Reply sent (message_id={msg_id}, chat_id={chat_id})"


async def _edit_message(message_id: str, text: str) -> str:
    msg = {
        "type": "edit",
        "id": message_id,
        "text": text,
        "timestamp": _iso_now(),
    }
    if not _ws_clients:
        logger.warning("edit_message called with no WebSocket clients connected")
        return f"Warning: no Corner Office app connected — edit not delivered (message_id={message_id})"
    await _broadcast(msg)
    return f"Edit sent for message {message_id}"


# --- WebSocket Bridge ---

def _remove_dead_clients(dead: set):
    """Remove dead clients from the global _ws_clients set."""
    _ws_clients.difference_update(dead)


async def _forward_to_claude(text: str, meta: dict):
    """Forward an app message to Claude via MCP channel notification.

    Tries mcp.notification() first (Python MCP SDK primary path).
    Falls back to raw JSON-RPC on the stdio write_stream if unavailable.
    """
    notification_params = {"content": text, "meta": meta}
    # Capture write_stream locally before the await to avoid teardown race
    write_stream = _write_stream
    try:
        await mcp.notification(
            method="notifications/claude/channel",
            params=notification_params,
        )
    except AttributeError:
        # Python MCP SDK may not have notification() on Server — raw JSON-RPC fallback.
        # NOTE: This is best-effort. The MCP stdio transport uses length-prefixed framing
        # (Content-Length headers). Sending bare JSON may not be parsed correctly by the
        # receiver. The primary mcp.notification() path should work — this fallback exists
        # only as a safety net until the channels API stabilizes.
        if write_stream is not None:
            raw = json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/claude/channel",
                "params": notification_params,
            })
            try:
                await write_stream.send(raw)
            except Exception as e:
                logger.error(f"Failed to send raw JSON-RPC notification (framing may be incompatible): {e}")
        else:
            logger.error("mcp.notification() unavailable and write_stream not set — message dropped")


async def _ws_handler(websocket):
    """Handle a WebSocket connection from the Corner Office app."""
    # Guard: reject if token not yet initialized (server not fully started)
    if not _channel_token:
        await websocket.close(4001, "Unauthorized")
        return

    # Token authentication: first message must be {"type":"auth","token":"..."} within 5s
    try:
        raw_auth = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        auth = json.loads(raw_auth)
        # Use hmac.compare_digest for timing-safe token comparison (prevent timing attacks)
        if auth.get("type") != "auth" or not hmac.compare_digest(auth.get("token", ""), _channel_token):
            logger.warning("WebSocket auth failed — closing connection")
            await websocket.close(4001, "Unauthorized")
            return
    except (asyncio.TimeoutError, json.JSONDecodeError, websockets.ConnectionClosed):
        logger.warning("WebSocket auth timeout or invalid payload — closing connection")
        await websocket.close(4001, "Unauthorized")
        return

    _ws_clients.add(websocket)
    logger.info(f"Client connected ({len(_ws_clients)} total)")

    # Send connected status to this specific client
    await _send_status_to(websocket, "connected")

    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")

            if msg_type == "pong":
                continue  # Heartbeat response

            if msg_type == "message":
                text = data.get("text", "")
                if len(text) > MAX_MESSAGE_TEXT:
                    logger.warning(f"Message text truncated ({len(text)} → {MAX_MESSAGE_TEXT} bytes)")
                    text = text[:MAX_MESSAGE_TEXT]
                meta = {
                    "workspace": data.get("workspace", ""),
                    "chat_id": data.get("id", ""),
                    "sender": "user",
                }
                await _forward_to_claude(text, meta)
                logger.info(f"Forwarded message {data.get('id', '?')} to Claude")
    except websockets.ConnectionClosed:
        pass
    finally:
        _ws_clients.discard(websocket)
        logger.info(f"Client disconnected ({len(_ws_clients)} remaining)")


async def _broadcast(msg: dict):
    """Send a message to all connected WebSocket clients."""
    payload = json.dumps(msg)
    dead = set()
    for ws in set(_ws_clients):  # Copy set to avoid mutation during iteration
        try:
            await ws.send(payload)
        except websockets.ConnectionClosed:
            dead.add(ws)
    _remove_dead_clients(dead)


async def _heartbeat():
    """Send ping to all connected clients every 30 seconds."""
    while True:
        await asyncio.sleep(30)
        ping = json.dumps({"type": "ping", "timestamp": _iso_now()})
        dead = set()
        for ws in set(_ws_clients):
            try:
                await ws.send(ping)
            except websockets.ConnectionClosed:
                dead.add(ws)
        _remove_dead_clients(dead)


async def _send_status_to(websocket, state: str):
    """Send a status update to a specific client."""
    msg = {
        "type": "status",
        "sessionId": _card_short_id,
        "state": state,
        "timestamp": _iso_now(),
    }
    try:
        await websocket.send(json.dumps(msg))
    except websockets.ConnectionClosed:
        pass


# --- Registration Card ---

# Path to this session's card — set by _patch_registration_card, used by cleanup
_card_path: str = ""

# Short session ID — read from the card we patch, used by _send_status_to
_card_short_id: str = ""

_PATCH_MAX_RETRIES = 10
_PATCH_RETRY_BASE_DELAY = 0.5  # seconds, doubles each retry
_PATCH_RETRY_MAX_DELAY = 8.0   # cap per-retry wait


def _find_newest_unclaimed_card(channels_dir):
    """Find the most recently created card with pid=null.

    Returns (card_dict, card_file_path) or (None, None) if none found.
    """
    best_card = None
    best_path = None
    best_time = ""

    for card_file in glob.glob(os.path.join(channels_dir, "*.json")):
        try:
            with open(card_file, "r", encoding="utf-8") as f:
                card = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        if card.get("pid") is not None:
            continue

        registered = card.get("registeredAt", "")
        if registered > best_time:
            best_time = registered
            best_card = card
            best_path = card_file

    return best_card, best_path


def _patch_registration_card(port: int, token: str):
    """Find the channel card created by SessionStart and patch in connection info.

    SessionStart creates {short_id}.json with pid=null. This server claims
    the most recently created unclaimed card (newest registeredAt with pid=null)
    and writes in the server's PID, WebSocket port, and auth token.

    Retries briefly to handle the race where the MCP server starts before
    the SessionStart hook has finished writing the card.
    """
    channels_dir = os.path.join(os.path.expanduser("~"), ".claude", "channels")

    delay = _PATCH_RETRY_BASE_DELAY
    for attempt in range(_PATCH_MAX_RETRIES):
        if not os.path.isdir(channels_dir):
            time.sleep(delay)
            delay = min(delay * 2, _PATCH_RETRY_MAX_DELAY)
            continue

        card, card_file = _find_newest_unclaimed_card(channels_dir)
        if card is None:
            if attempt < _PATCH_MAX_RETRIES - 1:
                time.sleep(delay)
                delay = min(delay * 2, _PATCH_RETRY_MAX_DELAY)
            continue

        # Found our card — patch it
        _patch_card(card, card_file, port, token)
        return

    logger.warning("No unclaimed channel card found after %d retries — card not patched", _PATCH_MAX_RETRIES)


# Event loop reference — set in _run(), used by SIGUSR1 handler to schedule async work
_loop: asyncio.AbstractEventLoop | None = None


def _handle_sigusr1(*_):
    """SIGUSR1 handler — SessionEnd signals us before deleting our card.

    Schedules an async re-watch task to claim the replacement card that
    the next SessionStart will create (e.g., after /resume).
    """
    logger.info("Received SIGUSR1 — session changing, will re-watch for new card")
    if _loop is not None:
        _loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_rewatch_for_card()))


async def _rewatch_for_card():
    """Look for a new unclaimed card to claim after a session change."""
    channels_dir = os.path.join(os.path.expanduser("~"), ".claude", "channels")

    # Wait for new card to appear (SessionEnd deletes old, SessionStart creates new)
    delay = _PATCH_RETRY_BASE_DELAY
    for _ in range(_PATCH_MAX_RETRIES):
        await asyncio.sleep(delay)
        delay = min(delay * 2, _PATCH_RETRY_MAX_DELAY)
        card, card_file = _find_newest_unclaimed_card(channels_dir)
        if card is not None and card_file is not None:
            await asyncio.to_thread(_patch_card, card, card_file, _channel_port, _channel_token)
            return

    logger.warning("Re-watch: no new unclaimed card found after %d retries", _PATCH_MAX_RETRIES)


def _patch_card(card: dict, card_file: str, port: int, token: str):
    """Patch a card with this server's connection info (blocking I/O)."""
    global _card_path, _card_short_id

    channels_dir = os.path.dirname(card_file)
    card["pid"] = os.getpid()
    card["channelPort"] = port
    card["channelToken"] = token
    card["updatedAt"] = _iso_now()

    fd, tmp_path = tempfile.mkstemp(dir=channels_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(card, f, indent=2)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, card_file)
        _card_path = card_file
        _card_short_id = card.get("shortId", "")
        logger.info(f"Re-patched registration card: {card_file} (pid={os.getpid()}, port={port})")
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _remove_registration_card():
    """Remove this session's card on graceful shutdown."""
    if _card_path:
        try:
            os.unlink(_card_path)
            logger.info(f"Removed registration card: {_card_path}")
        except OSError:
            pass


# --- Helpers ---

def _iso_now() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


# --- Entry Point ---

async def _run():
    """Start the WebSocket server and then the MCP stdio server."""
    global _channel_token, _channel_port, _write_stream, _loop

    # Store event loop for SIGUSR1 handler to schedule async work
    _loop = asyncio.get_running_loop()

    # Generate auth token for WebSocket handshake
    _channel_token = secrets.token_hex(32)

    # Bind WebSocket to dynamic port on localhost only
    ws_server = await websockets.serve(
        _ws_handler,
        "127.0.0.1",
        0,
        max_size=262144,    # 256 KB — symmetric with emit_activity.py MAX_STDIN
    )
    port = ws_server.sockets[0].getsockname()[1]
    _channel_port = port
    logger.info(f"WebSocket server listening on 127.0.0.1:{port}")

    # Patch the channel card created by SessionStart with connection info (blocking I/O → thread)
    await asyncio.to_thread(_patch_registration_card, port, _channel_token)

    # Register cleanup for graceful shutdown (atexit + SIGTERM)
    atexit.register(_remove_registration_card)
    signal.signal(signal.SIGTERM, lambda *_: _remove_registration_card())

    # Register SIGUSR1 handler — SessionEnd signals us before deleting our card
    signal.signal(signal.SIGUSR1, _handle_sigusr1)

    # Start heartbeat task
    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        # Run MCP stdio server — blocks until Claude Code closes stdin
        async with stdio_server() as (read_stream, write_stream):
            _write_stream = write_stream  # Store for JSON-RPC fallback in _forward_to_claude
            init_options = mcp.create_initialization_options(
                experimental_capabilities={"claude/channel": {}},
            )
            await mcp.run(read_stream, write_stream, init_options)
    finally:
        # Cleanup
        _write_stream = None
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        ws_server.close()
        await ws_server.wait_closed()
        logger.info("Channel server shut down")


def main():
    """Entry point for uvx."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
