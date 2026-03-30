#!/usr/bin/env bun
/**
 * Corner Office Channel Server (Bun) — bridges Claude Code sessions and the Corner Office app.
 *
 * MCP channel server: stdio transport to Claude Code, WebSocket transport to app.
 * Minimal port of the Python server, following Anthropic's fakechat example exactly.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { randomUUID } from "crypto";
import { readFileSync, writeFileSync, readdirSync, mkdirSync, unlinkSync, existsSync, chmodSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { tmpdir } from "os";

const DEBUG = process.argv.includes("--debug");
const LOG_FILE = join(homedir(), ".claude", "channel-server-bun.log");

function log(msg: string) {
  const line = `[channel-bun] ${new Date().toISOString()} ${msg}`;
  process.stderr.write(line + "\n");
  if (DEBUG) {
    try {
      const fd = Bun.file(LOG_FILE);
      Bun.write(LOG_FILE, (existsSync(LOG_FILE) ? readFileSync(LOG_FILE, "utf-8") : "") + line + "\n");
    } catch {}
  }
}

function isoNow(): string {
  return new Date().toISOString();
}

// --- State ---

const wsClients = new Set<any>();
let channelToken = "";
let channelPort = 0;
let cardPath = "";
let cardShortId = "";

const MAX_MESSAGE_TEXT = 10240;
const MAX_WS_CLIENTS = 10;

const PATCH_MAX_RETRIES = 10;
const PATCH_BASE_DELAY = 500; // ms
const PATCH_MAX_DELAY = 8000; // ms

// --- Schemas ---

const PermissionRequestSchema = z.object({
  method: z.literal("notifications/claude/channel/permission_request"),
  params: z.object({
    request_id: z.string(),
    tool_name: z.string(),
    description: z.string(),  // call-specific context from Claude Code (e.g. "Run git status"), not a static tool description
    input_preview: z.string(),
  }),
});

const MAX_INPUT_PREVIEW = 2048;
const pendingPermissions = new Set<string>();

// --- MCP Server Setup (following Anthropic's fakechat example) ---

const mcp = new Server(
  { name: "corner-office-channel", version: "1.0.0" },
  {
    capabilities: {
      experimental: {
        "claude/channel": {},
        "claude/channel/permission": {},
      },
      tools: {},
    },
    instructions:
      'Messages from the Corner Office app arrive as <channel source="corner-office-channel" ' +
      'workspace="..." chat_id="..." sender="user">.\n' +
      "The sender reads the Corner Office app, not this terminal. Anything you want them to see " +
      "must go through the reply tool — your transcript output never reaches the app.\n" +
      "Reply using the reply tool, passing chat_id back. The reply tool returns the message_id " +
      "of the sent message. If you need to correct a prior reply, call edit_message with that " +
      "message_id.",
  }
);

// --- Tools ---

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "reply",
      description: "Send a reply message to the Corner Office app.",
      inputSchema: {
        type: "object" as const,
        properties: {
          chat_id: { type: "string", description: "The chat_id from the incoming channel message (for routing)." },
          text: { type: "string", description: "The reply text to send to the app user." },
        },
        required: ["chat_id", "text"],
      },
    },
    {
      name: "edit_message",
      description: "Edit a previously sent message in the Corner Office app.",
      inputSchema: {
        type: "object" as const,
        properties: {
          message_id: { type: "string", description: "The message_id returned by the original reply call." },
          text: { type: "string", description: "The new text for the message." },
        },
        required: ["message_id", "text"],
      },
    },
  ],
}));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  if (name === "reply") {
    const { chat_id, text } = args as { chat_id: string; text: string };
    const msgId = randomUUID();
    const msg = JSON.stringify({ type: "reply", id: msgId, text, replyTo: chat_id, timestamp: isoNow() });
    if (wsClients.size === 0) {
      log(`WARN reply called with no WebSocket clients connected`);
      return { content: [{ type: "text", text: `Warning: no Corner Office app connected — reply not delivered (message_id=${msgId})` }] };
    }
    broadcast(msg);
    return { content: [{ type: "text", text: `Reply sent (message_id=${msgId}, chat_id=${chat_id})` }] };
  }
  if (name === "edit_message") {
    const { message_id, text } = args as { message_id: string; text: string };
    const msg = JSON.stringify({ type: "edit", id: message_id, text, timestamp: isoNow() });
    if (wsClients.size === 0) {
      log(`WARN edit_message called with no WebSocket clients connected`);
      return { content: [{ type: "text", text: `Warning: no Corner Office app connected — edit not delivered (message_id=${message_id})` }] };
    }
    broadcast(msg);
    return { content: [{ type: "text", text: `Edit sent for message ${message_id}` }] };
  }
  throw new Error(`Unknown tool: ${name}`);
});

mcp.setNotificationHandler(PermissionRequestSchema, async (notification) => {
  const { request_id, tool_name, description, input_preview } = notification.params;

  pendingPermissions.add(request_id);

  if (wsClients.size === 0) {
    log(`WARN permission_request received with no WebSocket clients connected (request_id=${request_id})`);
    return;
  }

  const msg = JSON.stringify({
    type: "permission_request",
    request_id,
    tool_name,
    description,
    input_preview: input_preview.length > MAX_INPUT_PREVIEW ? input_preview.slice(0, MAX_INPUT_PREVIEW) : input_preview,
    timestamp: isoNow(),
  });
  broadcast(msg);
  log(`INFO Forwarded permission_request ${request_id} for ${tool_name}`);
});

// --- WebSocket Bridge ---

function broadcast(msg: string) {
  const dead: any[] = [];
  for (const ws of wsClients) {
    try {
      ws.send(msg);
    } catch {
      dead.push(ws);
    }
  }
  for (const ws of dead) wsClients.delete(ws);
}

// --- Card Patching ---

function findNewestUnclaimedCard(channelsDir: string): { card: any; cardFile: string } | null {
  if (!existsSync(channelsDir)) return null;

  let bestCard: any = null;
  let bestPath = "";
  let bestTime = "";

  for (const file of readdirSync(channelsDir)) {
    if (!file.endsWith(".json")) continue;
    const filePath = join(channelsDir, file);
    try {
      const card = JSON.parse(readFileSync(filePath, "utf-8"));
      if (card.pid != null) continue;
      const registered = card.registeredAt || "";
      if (registered > bestTime) {
        bestTime = registered;
        bestCard = card;
        bestPath = filePath;
      }
    } catch {
      continue;
    }
  }

  return bestCard ? { card: bestCard, cardFile: bestPath } : null;
}

function patchCard(card: any, cardFile: string, port: number, token: string) {
  card.pid = process.pid;
  card.channelPort = port;
  card.channelToken = token;
  card.updatedAt = isoNow();

  const tmpFile = cardFile + ".tmp";
  writeFileSync(tmpFile, JSON.stringify(card, null, 2));
  chmodSync(tmpFile, 0o600);
  // Atomic rename
  const fs = require("fs");
  fs.renameSync(tmpFile, cardFile);

  cardPath = cardFile;
  cardShortId = card.shortId || "";
  log(`INFO Patched registration card: ${cardFile} (pid=${process.pid}, port=${port})`);
}

async function patchRegistrationCard(port: number, token: string) {
  const channelsDir = join(homedir(), ".claude", "channels");
  let delay = PATCH_BASE_DELAY;

  for (let attempt = 0; attempt < PATCH_MAX_RETRIES; attempt++) {
    if (!existsSync(channelsDir)) {
      await Bun.sleep(delay);
      delay = Math.min(delay * 2, PATCH_MAX_DELAY);
      continue;
    }

    const result = findNewestUnclaimedCard(channelsDir);
    if (!result) {
      if (attempt < PATCH_MAX_RETRIES - 1) {
        await Bun.sleep(delay);
        delay = Math.min(delay * 2, PATCH_MAX_DELAY);
      }
      continue;
    }

    patchCard(result.card, result.cardFile, port, token);
    return;
  }

  log(`WARN No unclaimed channel card found after ${PATCH_MAX_RETRIES} retries — card not patched`);
}

function removeRegistrationCard() {
  if (cardPath) {
    try {
      unlinkSync(cardPath);
      log(`INFO Removed registration card: ${cardPath}`);
    } catch {}
  }
}

// --- Main ---

// Generate auth token
channelToken = randomUUID() + randomUUID();

// Start WebSocket server
const wsServer = Bun.serve({
  port: 0,
  hostname: "127.0.0.1",
  fetch(req, server) {
    if (server.upgrade(req)) return undefined;
    return new Response("Not Found", { status: 404 });
  },
  websocket: {
    open(ws) {
      // Auth not yet done — store pending state
      (ws as any)._authed = false;
      (ws as any)._authTimer = setTimeout(() => {
        if (!(ws as any)._authed) {
          log("WARN WebSocket auth timeout — closing connection");
          ws.close(4001, "Unauthorized");
        }
      }, 5000);
    },
    message(ws, raw) {
      const msg = typeof raw === "string" ? raw : new TextDecoder().decode(raw);

      // Auth check
      if (!(ws as any)._authed) {
        try {
          const auth = JSON.parse(msg);
          if (auth.type !== "auth" || auth.token !== channelToken) {
            log("WARN WebSocket auth failed — closing connection");
            ws.close(4001, "Unauthorized");
            return;
          }
          (ws as any)._authed = true;
          clearTimeout((ws as any)._authTimer);
          wsClients.add(ws);
          log(`INFO Client connected (${wsClients.size} total)`);
          ws.send(JSON.stringify({ type: "status", status: "connected", timestamp: isoNow() }));
          return;
        } catch {
          ws.close(4001, "Unauthorized");
          return;
        }
      }

      // Handle messages
      try {
        const data = JSON.parse(msg);
        if (data.type === "pong") return;

        if (data.type === "message") {
          let text = data.text || "";
          if (text.length > MAX_MESSAGE_TEXT) {
            log(`WARN Message text truncated (${text.length} -> ${MAX_MESSAGE_TEXT} bytes)`);
            text = text.slice(0, MAX_MESSAGE_TEXT);
          }
          const meta = {
            workspace: data.workspace || "",
            chat_id: data.id || "",
            sender: "user",
          };
          mcp.notification({
            method: "notifications/claude/channel",
            params: { content: text, meta },
          });
          log(`INFO Forwarded message ${data.id || "?"} to Claude`);
        }

        if (data.type === "permission_verdict") {
          const { request_id, behavior } = data;
          if (!request_id || (behavior !== "allow" && behavior !== "deny")) {
            log(`WARN Malformed permission_verdict — missing request_id or invalid behavior`);
            ws.send(JSON.stringify({ type: "error", code: "malformed_verdict", detail: "permission_verdict requires string request_id and behavior 'allow' or 'deny'" }));
          } else if (!pendingPermissions.has(request_id)) {
            log(`WARN permission_verdict for unknown request_id=${request_id} — ignoring`);
            ws.send(JSON.stringify({ type: "error", code: "unknown_request_id", detail: `No pending permission request with id '${request_id}'` }));
          } else {
            pendingPermissions.delete(request_id);
            mcp.notification({
              method: "notifications/claude/channel/permission",
              params: { request_id, behavior },
            });
            log(`INFO Forwarded permission_verdict ${request_id}: ${behavior}`);
          }
        }
      } catch (e) {
        log(`WARN WebSocket message handler error: ${e}`);
      }
    },
    close(ws) {
      wsClients.delete(ws);
      clearTimeout((ws as any)._authTimer);
      log(`INFO Client disconnected (${wsClients.size} remaining)`);
    },
  },
});

channelPort = wsServer.port;
log(`INFO WebSocket server listening on 127.0.0.1:${channelPort}`);

// Patch registration card
await patchRegistrationCard(channelPort, channelToken);

// Cleanup on exit — do NOT remove the card on signal termination.
// Card cleanup is handled by SessionEnd (_remove_channel_card) and
// SessionStart (_cleanup_stale_cards).  Removing here causes a race
// when Claude Code restarts the MCP server: the old process deletes
// the card before the new process can patch it, leaving the channel dead.
process.on("SIGTERM", () => { process.exit(0); });
process.on("SIGINT", () => { process.exit(0); });

// Heartbeat
setInterval(() => {
  const ping = JSON.stringify({ type: "ping", timestamp: isoNow() });
  broadcast(ping);
}, 30000);

// Connect MCP stdio transport
await mcp.connect(new StdioServerTransport());
