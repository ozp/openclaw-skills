// KTD8 task-tracker gateway conversational completion assistant.
//
// Free-form chat is evidence only. This plugin owner-verifies and chat-scopes
// inbound conversational completion/browse intents, resolves them to visible
// choices, and posts tt:done buttons. The existing task-tracker-interactive
// plugin remains the only chat completion authority: a board write requires the
// owner-authenticated tt:done:<task_id> callback path.
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const LOG_PREFIX = "[task-tracker-completion-assistant]";
const MAX_STDOUT_CHARS = 1024 * 1024;
const MAX_STDERR_CHARS = 32 * 1024;
const MAX_MESSAGE_CHARS = 8192;
const OPEN_LIST_LIMIT = 5;

const HERE = dirname(fileURLToPath(import.meta.url));
const DEFAULT_REPO = join(HERE, "..", "..", "..");

const RESOLVE_FOR_CONFIRM_SCRIPT = String.raw`
import json
import sys
import telegram_buttons
from chat_capture import resolve_for_confirm

hint = sys.argv[1] if len(sys.argv) > 1 else ""
payload = resolve_for_confirm(hint)
if payload.get("tier") == "single" and payload.get("candidates"):
    payload["buttons"] = telegram_buttons.confirm_row(payload["candidates"][0]["task_id"])
elif payload.get("tier") == "multi":
    payload["buttons"] = telegram_buttons.disambiguation_rows(payload.get("candidates") or [])
else:
    payload["buttons"] = []
print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
`;

const OPEN_TASKS_SCRIPT = String.raw`
import json
import sys
from chat_capture import open_tasks_for_browse

page = int(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "1")
limit = int(sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else "5")
print(json.dumps(open_tasks_for_browse(page=page, limit=limit), separators=(",", ":"), ensure_ascii=False))
`;

const RECORD_DEFERRED_SCRIPT = String.raw`
import json
import sys
from chat_capture import record_deferred_candidate

args = json.loads(sys.argv[1] if len(sys.argv) > 1 else "{}")
payload = record_deferred_candidate(
    args.get("text") or "",
    sender=args.get("sender"),
    source=args.get("source") or "chat",
    channel=args.get("channel"),
    message_id=args.get("message_id"),
    decision_reason=args.get("decision_reason") or "confirm-prompt-posted",
)
print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
`;

function repoRoot() {
  return process.env.TASK_TRACKER_REPO || DEFAULT_REPO;
}

function pythonBin() {
  return process.env.TASK_TRACKER_PYTHON || "python3";
}

function scriptsDir() {
  return join(repoRoot(), "scripts");
}

function safeMessage(error) {
  const raw = error && typeof error === "object" && "message" in error ? error.message : String(error || "");
  return raw.split("\n")[0].trim() || "unknown error";
}

function trimAppend(current, chunk, maxChars) {
  if (current.length >= maxChars) return current;
  const next = current + String(chunk);
  return next.length > maxChars ? next.slice(0, maxChars) : next;
}

export function runProcess(command, args, options = {}) {
  const spawnImpl = options.spawnImpl || spawn;
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let child;
    try {
      child = spawnImpl(command, args, {
        cwd: options.cwd,
        env: options.env || process.env,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (error) {
      resolve({ code: -1, stdout: "", stderr: "", error });
      return;
    }

    child.stdout?.on?.("data", (chunk) => {
      stdout = trimAppend(stdout, chunk, MAX_STDOUT_CHARS);
    });
    child.stderr?.on?.("data", (chunk) => {
      stderr = trimAppend(stderr, chunk, MAX_STDERR_CHARS);
    });
    child.on?.("error", (error) => {
      resolve({ code: -1, stdout, stderr, error });
    });
    child.on?.("close", (code) => {
      resolve({ code: code ?? -1, stdout, stderr });
    });
  });
}

export function parseLastJson(stdout) {
  const raw = String(stdout || "").trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    // Fall through.
  }
  const lines = raw.split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line.startsWith("{")) continue;
    try {
      return JSON.parse(line);
    } catch {
      // Try an enclosing block below.
    }
  }
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start !== -1 && end > start) {
    try {
      return JSON.parse(raw.slice(start, end + 1));
    } catch {
      return null;
    }
  }
  return null;
}

function normalizedText(value) {
  if (typeof value === "string" || typeof value === "number") {
    return String(value).slice(0, MAX_MESSAGE_CHARS);
  }
  return "";
}

export function decodeCompletionIntent(text) {
  const raw = normalizedText(text);
  if (!raw.trim()) return { matched: false };
  // A question is never a completion claim ("did you send the JAMS report?"). Yield it to the
  // agent rather than posting a live tt:done confirm the owner never asked for.
  if (/\?\s*$/u.test(raw)) return { matched: false };

  let verb = null;
  let rest = null;
  let match = /^\s*(done|finished|completed)\b\s*(.*)$/iu.exec(raw);
  if (match) {
    verb = match[1];
    rest = match[2];
  }
  if (verb === null) {
    // "did" is an ambiguous auxiliary. Two non-completion shapes to reject:
    //   - negation: "did not finish X" ("didn't ..." already fails `did\b` — no boundary before "n't")
    //   - question / narration: "did you send X", "did we ship it", "did I finish X" (common in
    //     Telegram WITHOUT a trailing "?"). A real completion leads with a task noun ("did the
    //     standup notes"), not a subject pronoun.
    match = /^\s*(did)\b\s*(.*)$/iu.exec(raw);
    if (match && !/^\s*(?:not|you|u|we|they|he|she|i)\b/iu.test(match[2] || "")) {
      verb = "did";
      rest = match[2];
    }
  }
  if (verb === null) {
    match = /^\s*(✅)\s*(.*)$/u.exec(raw);
    if (match) {
      verb = "✅";
      rest = match[2];
    }
  }
  if (verb === null) return { matched: false };

  const hint = String(rest || "").trim();
  // A hint with no letters or digits (punctuation only, e.g. "done!") is not a task reference —
  // treat it as a verb-only browse request instead of resolving "!" against the board.
  const hasContent = /[\p{L}\p{N}]/u.test(hint);
  return { matched: true, mode: hasContent ? "complete" : "browse", verb, hint: hasContent ? hint : "" };
}

export function decodeBrowseIntent(text) {
  const raw = normalizedText(text);
  const match = /^\s*(?:open|\/tasks)(?:\s+(\d+))?\s*$/iu.exec(raw);
  if (!match) return { matched: false };
  const page = match[1] ? Math.max(1, Number.parseInt(match[1], 10) || 1) : 1;
  return { matched: true, mode: "browse", page };
}

function decodeInboundIntent(text) {
  const browse = decodeBrowseIntent(text);
  if (browse.matched) return browse;
  return decodeCompletionIntent(text);
}

function normalizeString(value) {
  return typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
}

function ownerList(config) {
  const raw = config?.commands?.ownerAllowFrom;
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeString).filter(Boolean);
}

function chatAllowList(config) {
  const commands = config?.commands || {};
  // Prefer the new key only when it is a NON-EMPTY array. An empty
  // `completionAssistantAllowChats: []` (e.g. the operator declared the key before migrating
  // entries) must not silently shadow a populated legacy `envelopeSignerAllowChats`. When both
  // are empty/absent, `raw` is undefined and the plugin fails closed (deny all).
  const preferred = commands.completionAssistantAllowChats;
  const raw =
    Array.isArray(preferred) && preferred.length > 0 ? preferred : commands.envelopeSignerAllowChats;
  if (!Array.isArray(raw)) return [];
  return raw;
}

function ownerCandidateKeys(senderId, channel) {
  const sender = normalizeString(senderId);
  const normalizedChannel = normalizeString(channel).toLowerCase();
  if (!sender) return [];
  const keys = [sender];
  if (normalizedChannel) {
    keys.push(`${normalizedChannel}:${sender}`);
    if (normalizedChannel === "telegram") keys.push(`tg:${sender}`);
  }
  return keys;
}

export function verifyOwner({ config, event = {}, ctx = {} }) {
  const owners = ownerList(config);
  if (owners.length === 0) {
    return { ok: false, reason: "owner-list-unavailable" };
  }
  const senderId = normalizeString(event.senderId) || normalizeString(ctx.senderId);
  const channel = normalizeString(event.channel) || normalizeString(ctx.channelId);
  const ownerSet = new Set(owners);
  for (const key of ownerCandidateKeys(senderId, channel)) {
    if (key !== "*" && ownerSet.has(key)) {
      return { ok: true, senderId, matchedOwner: key };
    }
  }
  return { ok: false, reason: "sender-not-owner", senderId };
}

function chatIdFor(event = {}, ctx = {}) {
  return (
    normalizeString(event?.chatId) ||
    normalizeString(event?.chat_id) ||
    normalizeString(event?.metadata?.chatId) ||
    normalizeString(event?.metadata?.chat_id) ||
    normalizeString(event?.metadata?.originatingTo) ||
    normalizeString(event?.metadata?.to) ||
    normalizeString(ctx?.chatId) ||
    normalizeString(ctx?.chat_id) ||
    normalizeString(ctx?.conversationId)
  );
  // Note: `event.from` (the SENDER id) is deliberately NOT a chat-id fallback — keeping the
  // sender-id and chat-id spaces disjoint so an owner-id can never accidentally satisfy the
  // chat allowlist under an unusual event shape (defense-in-depth for verifyAllowedChat).
}

function threadIdFor(event = {}, ctx = {}) {
  return (
    normalizeString(event?.threadId) ||
    normalizeString(event?.topicId) ||
    normalizeString(event?.messageThreadId) ||
    normalizeString(event?.metadata?.threadId) ||
    normalizeString(event?.metadata?.topicId) ||
    normalizeString(event?.metadata?.messageThreadId) ||
    normalizeString(ctx?.threadId) ||
    normalizeString(ctx?.topicId) ||
    normalizeString(ctx?.messageThreadId)
  );
}

function chatMatchesAllowedEntry(entry, chatId, threadId) {
  if (typeof entry === "string" || typeof entry === "number") {
    return normalizeString(entry) === chatId;
  }
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return false;
  const allowedChatId = normalizeString(entry.chatId) || normalizeString(entry.chat_id);
  if (!allowedChatId || allowedChatId !== chatId) return false;
  const allowedThreadId =
    normalizeString(entry.threadId) ||
    normalizeString(entry.thread_id) ||
    normalizeString(entry.topicId) ||
    normalizeString(entry.topic_id);
  return !allowedThreadId || allowedThreadId === threadId;
}

export function verifyAllowedChat({ config, event = {}, ctx = {} }) {
  const allowlist = chatAllowList(config);
  if (allowlist.length === 0) {
    return { ok: false, reason: "chat-allowlist-unavailable" };
  }
  const chatId = chatIdFor(event, ctx);
  const threadId = threadIdFor(event, ctx);
  if (!chatId) {
    return { ok: false, reason: "chat-not-allowlisted", chatId, threadId };
  }
  if (allowlist.some((entry) => chatMatchesAllowedEntry(entry, chatId, threadId))) {
    return { ok: true, chatId, threadId };
  }
  return { ok: false, reason: "chat-not-allowlisted", chatId, threadId };
}

function isForwardedMessage(event = {}, ctx = {}) {
  const metadata = event?.metadata || {};
  return Boolean(
    event?.isForwarded ||
      event?.forwardOrigin ||
      event?.forward_from ||
      event?.forward_date ||
      event?.forwardFrom ||
      event?.forwardDate ||
      metadata?.isForwarded ||
      metadata?.forwardOrigin ||
      metadata?.forward_from ||
      metadata?.forward_date ||
      metadata?.forwardFrom ||
      metadata?.forwardDate ||
      ctx?.isForwarded ||
      ctx?.forwardOrigin ||
      ctx?.forward_from ||
      ctx?.forward_date,
  );
}

function channelName(event, ctx) {
  return normalizeString(event?.channel) || normalizeString(ctx?.channelId);
}

function messageIdFor(event, ctx) {
  return (
    normalizeString(event?.messageId) ||
    normalizeString(ctx?.messageId) ||
    normalizeString(event?.metadata?.messageId)
  );
}

function ackTarget(event, ctx) {
  return (
    normalizeString(event?.metadata?.originatingTo) ||
    normalizeString(event?.metadata?.to) ||
    normalizeString(ctx?.conversationId) ||
    normalizeString(event?.from)
  );
}

async function runJsonScript(script, args, options = {}) {
  const result = await runProcess(
    pythonBin(),
    ["-c", script, ...args],
    {
      cwd: scriptsDir(),
      env: { ...process.env, HOME: process.env.HOME || "/data" },
      spawnImpl: options.spawnImpl,
    },
  );
  const parsed = parseLastJson(result.stdout);
  if (result.code !== 0 || !parsed || parsed.ok !== true) {
    return { ok: false, reason: "helper-failed", code: result.code };
  }
  return parsed;
}

export async function resolveForConfirm(hint, options = {}) {
  return runJsonScript(RESOLVE_FOR_CONFIRM_SCRIPT, [String(hint || "")], options);
}

export async function openTaskList(page = 1, options = {}) {
  return runJsonScript(OPEN_TASKS_SCRIPT, [String(page || 1), String(OPEN_LIST_LIMIT)], options);
}

export async function recordDeferredCandidate({ text, sender, channel, messageId }, options = {}) {
  return runJsonScript(
    RECORD_DEFERRED_SCRIPT,
    [
      JSON.stringify({
        text: text || "",
        sender: sender || null,
        channel: channel || null,
        message_id: messageId || null,
        source: "chat",
        decision_reason: "confirm-prompt-posted",
      }),
    ],
    options,
  );
}

function visibleTitle(title, taskId) {
  let safe = normalizeString(title);
  const id = normalizeString(taskId);
  safe = safe.replace(/\b(?:task_id|id)::\s*[A-Za-z0-9._:-]*[A-Za-z0-9._-]\b/giu, "").trim();
  if (id) safe = safe.split(id).join("").trim();
  safe = safe.replace(/\s+/g, " ").trim();
  return safe || "Untitled task";
}

async function postMessage(api, event, ctx, text, buttons = null, options = {}) {
  if (!api || !text) return false;
  try {
    const target = ackTarget(event, ctx);
    if (!target) return false;
    const channel = channelName(event, ctx);
    const adapter = await api.runtime?.channel?.outbound?.loadAdapter?.(channel);
    if (!adapter?.sendText) return false;
    const payload = {
      cfg: api.config || {},
      to: target,
      text,
      accountId: ctx?.accountId || event?.accountId || null,
      // Reply in the SAME thread the message came from. Use the fully-resolved thread id
      // (event.threadId is only one of the fields threadIdFor/verifyAllowedChat accept), so a
      // confirm/browse posted to an allowed topic can't fall back to the parent chat.
      threadId: threadIdFor(event, ctx) || null,
    };
    if (buttons && buttons.length) payload.buttons = buttons;
    await adapter.sendText(payload);
    return true;
  } catch (error) {
    console.error(`${LOG_PREFIX} send failed: ${safeMessage(error)}`);
    return false;
  }
}

async function postOpenList(api, event, ctx, payload, options = {}, prefix = null) {
  if (!payload.ok) {
    await (options.sendMessage || postMessage)(
      api,
      event,
      ctx,
      "I couldn't read the task board right now.",
      null,
      options,
    );
    return;
  }
  if (prefix) {
    await (options.sendMessage || postMessage)(api, event, ctx, prefix, null, options);
  }
  if (!payload.items || payload.items.length === 0) {
    await (options.sendMessage || postMessage)(api, event, ctx, "Nothing open.", null, options);
    return;
  }
  for (const item of payload.items) {
    await (options.sendMessage || postMessage)(
      api,
      event,
      ctx,
      `• ${visibleTitle(item.title, item.task_id)}`,
      item.buttons || [],
      options,
    );
  }
  if (payload.has_more && payload.next_page) {
    await (options.sendMessage || postMessage)(
      api,
      event,
      ctx,
      `More open tasks are available. Send /tasks ${payload.next_page}.`,
      null,
      options,
    );
  }
}

function baseResult(overrides = {}) {
  return {
    handled: false,
    matched: false,
    posted: false,
    captureInvoked: false,
    signed: false,
    reason: "ignored",
    ...overrides,
  };
}

async function handleBrowse({ api, event, ctx, page, options, prefix = null }) {
  const open = await openTaskList(page || 1, options);
  await postOpenList(api, event, ctx, open, options, prefix);
  return baseResult({ handled: true, matched: true, posted: true, reason: "browse", open });
}

export async function handleInboundMessage(event = {}, ctx = {}, options = {}) {
  const api = options.api;
  try {
    const text = event?.content ?? event?.body ?? "";
    const intent = decodeInboundIntent(text);
    if (!intent.matched) return baseResult();

    const channel = channelName(event, ctx).toLowerCase();
    if (channel !== "telegram") {
      return baseResult({ handled: true, matched: true, reason: "unsupported-channel" });
    }

    const config = options.config || api?.config || {};
    const owner = verifyOwner({ config, event, ctx });
    if (!owner.ok) {
      console.info(`${LOG_PREFIX} ignored: ${owner.reason}`);
      return baseResult({ handled: true, matched: true, reason: owner.reason });
    }

    const allowedChat = verifyAllowedChat({ config, event, ctx });
    if (!allowedChat.ok) {
      console.info(`${LOG_PREFIX} ignored: ${allowedChat.reason}`);
      return baseResult({ handled: true, matched: true, reason: allowedChat.reason });
    }

    if (isForwardedMessage(event, ctx)) {
      console.info(`${LOG_PREFIX} ignored: forwarded-message`);
      return baseResult({ handled: true, matched: true, reason: "forwarded-message" });
    }

    if (intent.mode === "browse") {
      return handleBrowse({ api, event, ctx, page: intent.page || 1, options });
    }

    const resolved = await resolveForConfirm(intent.hint, options);
    if (!resolved.ok) {
      await (options.sendMessage || postMessage)(
        api,
        event,
        ctx,
        "I couldn't read the task board right now.",
        null,
        options,
      );
      return baseResult({ handled: true, matched: true, posted: true, reason: resolved.reason || "resolve-failed" });
    }

    if (resolved.tier === "single" && resolved.candidates?.length === 1) {
      const candidate = resolved.candidates[0];
      const title = visibleTitle(candidate.title, candidate.task_id);
      await (options.sendMessage || postMessage)(
        api,
        event,
        ctx,
        `Mark this task done?\n${title}`,
        resolved.buttons || [],
        options,
      );
      const deferred = await recordDeferredCandidate(
        {
          text: intent.hint,
          sender: owner.senderId,
          channel,
          messageId: messageIdFor(event, ctx),
        },
        options,
      );
      return baseResult({
        handled: true,
        matched: true,
        posted: true,
        reason: "single-confirm",
        tier: "single",
        candidates: resolved.candidates,
        deferred,
      });
    }

    if (resolved.tier === "multi" && resolved.candidates?.length > 1) {
      await (options.sendMessage || postMessage)(
        api,
        event,
        ctx,
        "Which task did you mean?",
        resolved.buttons || [],
        options,
      );
      const deferred = await recordDeferredCandidate(
        {
          text: intent.hint,
          sender: owner.senderId,
          channel,
          messageId: messageIdFor(event, ctx),
        },
        options,
      );
      return baseResult({
        handled: true,
        matched: true,
        posted: true,
        reason: "multi-confirm",
        tier: "multi",
        candidates: resolved.candidates,
        deferred,
      });
    }

    // Unmatched completion hint: post a TEXT-ONLY nudge, not a wall of live tt:done buttons for
    // unrelated tasks. Browsing stays an explicit, owner-initiated action (`open` / `/tasks`), so a
    // mistyped or off-board completion phrase can't prime an accidental tap on the wrong task.
    await (options.sendMessage || postMessage)(
      api,
      event,
      ctx,
      "I couldn't match that to an open task. Send /tasks to see what's open.",
      null,
      options,
    );
    return baseResult({ handled: true, matched: true, posted: true, reason: "no-match" });
  } catch (error) {
    console.error(`${LOG_PREFIX} flow failed: ${safeMessage(error)}`);
    return baseResult({ handled: true, matched: true, reason: "error" });
  }
}

export default {
  id: "task-tracker-envelope-signer",
  name: "Task Tracker Completion Assistant",
  description:
    "Owner-verifies conversational Telegram completion/open-list messages and posts tt:done confirm buttons. Prose never writes the board; only the existing interactive tt:done tap path commits.",
  configSchema: {
    type: "object",
    additionalProperties: true,
    properties: {
      commands: {
        type: "object",
        additionalProperties: true,
        properties: {
          ownerAllowFrom: { type: "array", items: { type: ["string", "number"] } },
          completionAssistantAllowChats: {
            type: "array",
            items: {
              anyOf: [
                { type: ["string", "number"] },
                {
                  type: "object",
                  additionalProperties: true,
                  required: ["chatId"],
                  properties: {
                    chatId: { type: ["string", "number"] },
                    threadId: { type: ["string", "number"] },
                    topicId: { type: ["string", "number"] },
                  },
                },
              ],
            },
          },
          envelopeSignerAllowChats: {
            type: "array",
            items: {
              anyOf: [
                { type: ["string", "number"] },
                {
                  type: "object",
                  additionalProperties: true,
                  required: ["chatId"],
                  properties: {
                    chatId: { type: ["string", "number"] },
                    threadId: { type: ["string", "number"] },
                    topicId: { type: ["string", "number"] },
                  },
                },
              ],
            },
          },
        },
      },
    },
  },
  register(api) {
    api.on("message_received", async (event, ctx) => {
      await handleInboundMessage(event, ctx, { api });
    }, { timeoutMs: 30_000 });
  },
};
