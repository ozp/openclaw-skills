// Unit test for task-tracker-completion-assistant.
// Run: node scripts/openclaw-plugins/task-tracker-envelope-signer/test-handler.mjs
import { EventEmitter } from "node:events";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";
import { join } from "node:path";

const HERE = new URL(".", import.meta.url).pathname;
const mod = await import(pathToFileURL(join(HERE, "index.js")).href);
const {
  decodeBrowseIntent,
  decodeCompletionIntent,
  handleInboundMessage,
  resolveForConfirm,
  verifyAllowedChat,
  verifyOwner,
} = mod;
const plugin = mod.default;

let failures = 0;
function check(cond, msg) {
  if (cond) console.log(`  ok: ${msg}`);
  else {
    console.error(`  FAIL: ${msg}`);
    failures++;
  }
}
function eq(a, b, msg) {
  check(JSON.stringify(a) === JSON.stringify(b), `${msg} (got ${JSON.stringify(a)})`);
}

const OWNER = "123456";
const OTHER = "654321";
const CONFIG = {
  commands: {
    ownerAllowFrom: [OWNER, "telegram:777777"],
    envelopeSignerAllowChats: ["telegram:chat:42"],
  },
};
const BASE_EVENT = {
  content: "done the JAMS thing",
  channel: "telegram",
  senderId: OWNER,
  messageId: "msg-1",
  timestamp: "2026-07-01T12:00:00Z",
  metadata: { originatingTo: "telegram:chat:42" },
};
const BASE_CTX = {
  channelId: "telegram",
  accountId: "default",
  conversationId: "chat:42",
};

function makeSpawn(handler) {
  const calls = [];
  const fakeSpawn = (cmd, args, opts) => {
    const call = { cmd, args, opts };
    calls.push(call);
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    queueMicrotask(() => {
      let response;
      try {
        response = handler(call, calls);
      } catch (error) {
        child.emit("error", error);
        return;
      }
      if (response?.stdout) child.stdout.emit("data", Buffer.from(response.stdout));
      if (response?.stderr) child.stderr.emit("data", Buffer.from(response.stderr));
      child.emit("close", response?.code ?? 0);
    });
    return child;
  };
  fakeSpawn.calls = calls;
  return fakeSpawn;
}

function assistantSpawn({ resolve, open, deferred } = {}) {
  return makeSpawn((call) => {
    const script = String(call.args[1] || "");
    if (script.includes("resolve_for_confirm")) {
      return { stdout: JSON.stringify(resolve || { ok: true, tier: "none", candidates: [], buttons: [] }) };
    }
    if (script.includes("open_tasks_for_browse")) {
      return {
        stdout: JSON.stringify(open || {
          ok: true,
          total: 1,
          page: 1,
          limit: 5,
          items: [{ task_id: "tsk_open", title: "Open task", buttons: [{ label: "Done", value: "tt:done:tsk_open" }] }],
          has_more: false,
          next_page: null,
        }),
      };
    }
    if (script.includes("record_deferred_candidate")) {
      return {
        stdout: JSON.stringify(deferred || {
          ok: true,
          action: "candidate",
          candidate_id: "cand_123",
          task_id: "tsk_jams",
        }),
      };
    }
    return { code: 99, stderr: "unexpected helper" };
  });
}

function makeApi(sent) {
  return {
    config: CONFIG,
    runtime: {
      channel: {
        outbound: {
          async loadAdapter() {
            return {
              async sendText(payload) {
                sent.push(payload);
              },
            };
          },
        },
      },
    },
  };
}

console.log("SDK registration:");
{
  let registration = null;
  plugin.register({
    on(hookName, handler, opts) {
      registration = { hookName, handler, opts };
    },
  });
  check(registration?.hookName === "message_received", "plugin registers message_received typed hook");
  check(typeof registration?.handler === "function", "message_received handler is registered");
  check(registration?.opts?.timeoutMs === 30000, "handler has a bounded timeout");
}

console.log("intent + owner/chat checks:");
eq(
  decodeCompletionIntent("done the JAMS thing"),
  { matched: true, mode: "complete", verb: "done", hint: "the JAMS thing" },
  "done parses to hint phrase",
);
eq(
  decodeCompletionIntent("finished lifetime outreach"),
  { matched: true, mode: "complete", verb: "finished", hint: "lifetime outreach" },
  "finished parses",
);
eq(
  decodeCompletionIntent("✅ YouTube ads"),
  { matched: true, mode: "complete", verb: "✅", hint: "YouTube ads" },
  "emoji completion parses",
);
eq(decodeCompletionIntent("done"), { matched: true, mode: "browse", verb: "done", hint: "" }, "verb-only browses");
eq(
  decodeCompletionIntent("did the standup notes"),
  { matched: true, mode: "complete", verb: "did", hint: "the standup notes" },
  "did parses to hint phrase",
);
// Every verb-only lead routes to browse (not just "done") — same shape across the verb set.
for (const verb of ["finished", "completed", "did", "✅"]) {
  const intent = decodeCompletionIntent(verb);
  check(intent.matched && intent.mode === "browse" && intent.hint === "", `verb-only "${verb}" browses`);
}
eq(decodeCompletionIntent("what's on my plate?"), { matched: false }, "non-verb text flows to agent");
// A question is never a completion claim, even when it leads with a completion verb.
eq(decodeCompletionIntent("did you send the JAMS report?"), { matched: false }, "verb-lead question flows to agent");
eq(decodeCompletionIntent("done reviewing the deck?"), { matched: false }, "question tail is not a completion");
// "did not ..." / "didn't ..." is a negation, not a completion.
eq(decodeCompletionIntent("did not finish the JAMS thing"), { matched: false }, "did-not negation flows to agent");
// "did <pronoun> ..." is a question/narration even WITHOUT a trailing "?" (common in Telegram).
eq(decodeCompletionIntent("did you send the JAMS report"), { matched: false }, "did-you question (no ?) flows to agent");
eq(decodeCompletionIntent("did we ship the release"), { matched: false }, "did-we question flows to agent");
eq(decodeCompletionIntent("did I finish the deck"), { matched: false }, "did-I self-question flows to agent");
// ...but a real completion leading with a task noun still parses.
eq(
  decodeCompletionIntent("did the quarterly review"),
  { matched: true, mode: "complete", verb: "did", hint: "the quarterly review" },
  "did + task noun still parses to a completion",
);
// A punctuation-only tail ("done!") carries no task reference -> verb-only browse, not a hint of "!".
eq(decodeCompletionIntent("done!"), { matched: true, mode: "browse", verb: "done", hint: "" }, "punctuation-only tail browses");
eq(decodeCompletionIntent(""), { matched: false }, "empty text does not match");
check(!decodeCompletionIntent(" ".repeat(9000)).matched, "huge whitespace input never throws and does not match");
eq(decodeBrowseIntent("/tasks 2"), { matched: true, mode: "browse", page: 2 }, "/tasks page parses");
check(verifyOwner({ config: CONFIG, event: BASE_EVENT, ctx: BASE_CTX }).ok, "bare owner id verifies");
check(
  verifyOwner({ config: CONFIG, event: { ...BASE_EVENT, senderId: "777777" }, ctx: BASE_CTX }).ok,
  "channel-prefixed owner entry verifies by exact key",
);
check(
  !verifyOwner({ config: CONFIG, event: { ...BASE_EVENT, senderId: OTHER }, ctx: BASE_CTX }).ok,
  "non-owner does not verify",
);
check(
  !verifyOwner({ config: { commands: { ownerAllowFrom: ["*"] } }, event: BASE_EVENT, ctx: BASE_CTX }).ok,
  "wildcard owner entry is not accepted",
);
check(verifyAllowedChat({ config: CONFIG, event: BASE_EVENT, ctx: BASE_CTX }).ok, "configured chat verifies");
check(
  !verifyAllowedChat({ config: { commands: { envelopeSignerAllowChats: [] } }, event: BASE_EVENT, ctx: BASE_CTX }).ok,
  "empty chat allowlist fails closed",
);

console.log("gates and ignored text:");
{
  const fakeSpawn = assistantSpawn();
  const sent = [];
  const result = await handleInboundMessage(
    { ...BASE_EVENT, senderId: OTHER },
    BASE_CTX,
    { config: CONFIG, api: makeApi(sent), spawnImpl: fakeSpawn },
  );
  check(result.handled && result.matched && result.reason === "sender-not-owner", "non-owner verb is gated");
  eq(fakeSpawn.calls.length, 0, "non-owner does not resolve or post");
  eq(sent.length, 0, "non-owner emits zero messages");
}
{
  const fakeSpawn = assistantSpawn();
  const sent = [];
  const result = await handleInboundMessage(
    { ...BASE_EVENT, metadata: { originatingTo: "telegram:chat:999" } },
    BASE_CTX,
    { config: CONFIG, api: makeApi(sent), spawnImpl: fakeSpawn },
  );
  check(result.reason === "chat-not-allowlisted", "wrong chat is gated");
  eq(fakeSpawn.calls.length, 0, "wrong chat does not resolve or post");
  eq(sent.length, 0, "wrong chat emits zero messages");
}
{
  const fakeSpawn = assistantSpawn();
  const sent = [];
  const result = await handleInboundMessage(
    { ...BASE_EVENT, content: "what's on my plate?" },
    BASE_CTX,
    { config: CONFIG, api: makeApi(sent), spawnImpl: fakeSpawn },
  );
  check(!result.handled && !result.matched, "non-completion message is unhandled");
  eq(fakeSpawn.calls.length, 0, "non-completion does not spawn");
  eq(sent.length, 0, "non-completion emits zero messages");
}

console.log("single confirmation:");
{
  const fakeSpawn = assistantSpawn({
    resolve: {
      ok: true,
      tier: "single",
      candidates: [{ task_id: "tsk_jams", title: "JAMS launch", score: 1.0 }],
      buttons: [
        { label: "✅ Yes", value: "tt:done:tsk_jams" },
        { label: "Not that one", value: "tt:dismiss:none" },
      ],
    },
  });
  const sent = [];
  const result = await handleInboundMessage(BASE_EVENT, BASE_CTX, {
    config: CONFIG,
    api: makeApi(sent),
    spawnImpl: fakeSpawn,
  });
  check(result.reason === "single-confirm" && result.posted, "single match posts a confirm");
  eq(sent.length, 1, "single confirm sends one message");
  check(/Mark this task done\?/.test(sent[0].text), "single confirm text asks for tap confirmation");
  check(!sent[0].text.includes("tsk_jams"), "task id is not visible in single confirm text");
  eq(sent[0].buttons.map((button) => button.label), ["✅ Yes", "Not that one"], "single confirm labels");
  eq(sent[0].buttons[0].value, "tt:done:tsk_jams", "single confirm Yes carries tt:done callback");
  check(sent[0].buttons.every((button) => !button.label.includes("tsk_")), "single confirm labels hide ids");
  check(fakeSpawn.calls.length === 2, "single confirm resolves and records deferred candidate only");
  check(
    fakeSpawn.calls.every((call) => !String(call.args[0]).endsWith("capture_envelope.py") && !String(call.args[0]).endsWith("tasks.py")),
    "single confirm never signs or invokes capture",
  );
}

console.log("multi confirmation and no-match browse:");
{
  const fakeSpawn = assistantSpawn({
    resolve: {
      ok: true,
      tier: "multi",
      candidates: [
        { task_id: "tsk_jams", title: "JAMS launch", score: 0.93 },
        { task_id: "tsk_jams2", title: "JAMS followup", score: 0.93 },
      ],
      buttons: [
        { label: "JAMS launch", value: "tt:done:tsk_jams" },
        { label: "JAMS followup", value: "tt:done:tsk_jams2" },
        { label: "Neither", value: "tt:dismiss:none" },
      ],
    },
  });
  const sent = [];
  const result = await handleInboundMessage(BASE_EVENT, BASE_CTX, {
    config: CONFIG,
    api: makeApi(sent),
    spawnImpl: fakeSpawn,
  });
  check(result.reason === "multi-confirm", "multi match posts disambiguation");
  eq(sent[0].buttons.map((button) => button.label), ["JAMS launch", "JAMS followup", "Neither"], "multi labels");
  eq(
    sent[0].buttons.map((button) => button.value),
    ["tt:done:tsk_jams", "tt:done:tsk_jams2", "tt:dismiss:none"],
    "multi callbacks include done buttons plus no-op neither",
  );
}
{
  const fakeSpawn = assistantSpawn({
    resolve: { ok: true, tier: "none", candidates: [], buttons: [] },
    open: {
      ok: true,
      total: 2,
      page: 1,
      limit: 5,
      items: [
        { task_id: "tsk_a", title: "First open", buttons: [{ label: "Done", value: "tt:done:tsk_a" }] },
        { task_id: "tsk_b", title: "Second open", buttons: [{ label: "Done", value: "tt:done:tsk_b" }] },
      ],
      has_more: true,
      next_page: 2,
    },
  });
  const sent = [];
  const result = await handleInboundMessage(
    { ...BASE_EVENT, content: "done tsk_abc123" },
    BASE_CTX,
    { config: CONFIG, api: makeApi(sent), spawnImpl: fakeSpawn },
  );
  check(result.reason === "no-match", "unmatched completion hint gets a text-only nudge, not a button wall");
  eq(sent.length, 1, "no-match posts exactly one message");
  check(!sent[0].buttons || sent[0].buttons.length === 0, "no-match message carries no live Done buttons");
  check(
    sent[0].text === "I couldn't match that to an open task. Send /tasks to see what's open.",
    "no-match nudges to /tasks instead of listing tappable tasks",
  );
  check(sent.every((msg) => !msg.text.includes("tsk_abc123")), "id-looking hint is not echoed visibly");
}

console.log("topic preservation:");
{
  const fakeSpawn = assistantSpawn({
    open: {
      ok: true,
      total: 1,
      page: 1,
      limit: 5,
      items: [{ task_id: "tsk_open", title: "Open task", buttons: [{ label: "Done", value: "tt:done:tsk_open" }] }],
      has_more: false,
      next_page: null,
    },
  });
  const sent = [];
  // Inbound arrives on a topic supplied via event.topicId (resolved by threadIdFor, but NOT
  // event.threadId). The posted buttons must go back into that SAME topic, not the parent chat.
  await handleInboundMessage(
    { ...BASE_EVENT, content: "open", topicId: "9001" },
    BASE_CTX,
    { config: CONFIG, api: makeApi(sent), spawnImpl: fakeSpawn },
  );
  check(sent.length >= 1, "browse in a topic posts at least one message");
  check(sent.every((msg) => msg.threadId === "9001"), "buttons post back into the resolved topic, not threadId:null");
}

console.log("browse routes:");
{
  const fakeSpawn = assistantSpawn({
    open: {
      ok: true,
      total: 0,
      page: 1,
      limit: 5,
      items: [],
      has_more: false,
      next_page: null,
    },
  });
  const sent = [];
  const result = await handleInboundMessage(
    { ...BASE_EVENT, content: "done" },
    BASE_CTX,
    { config: CONFIG, api: makeApi(sent), spawnImpl: fakeSpawn },
  );
  check(result.reason === "browse", "verb-only done routes to browse");
  eq(sent.map((msg) => msg.text), ["Nothing open."], "empty open list says nothing open");
}

console.log("real Python resolver smoke:");
{
  const oldRepo = process.env.TASK_TRACKER_REPO;
  const oldWorkFile = process.env.TASK_TRACKER_WORK_FILE;
  const temp = mkdtempSync(join(tmpdir(), "tt-completion-assistant-"));
  const work = join(temp, "Work Tasks.md");
  writeFileSync(
    work,
    "# Work\n\n## 🔴 Q1\n- [ ] **Lifetime outreach** task_id::tsk_life area:: Sales\n",
  );
  process.env.TASK_TRACKER_REPO = join(HERE, "..", "..", "..");
  process.env.TASK_TRACKER_WORK_FILE = work;
  try {
    const resolved = await resolveForConfirm("lifetime outreach");
    check(resolved.ok && resolved.tier === "single", "real resolver returns single");
    check(resolved.buttons[0].value === "tt:done:tsk_life", "real resolver returns confirm tt:done button");
  } finally {
    if (oldRepo == null) delete process.env.TASK_TRACKER_REPO;
    else process.env.TASK_TRACKER_REPO = oldRepo;
    if (oldWorkFile == null) delete process.env.TASK_TRACKER_WORK_FILE;
    else process.env.TASK_TRACKER_WORK_FILE = oldWorkFile;
    rmSync(temp, { recursive: true, force: true });
  }
}

console.log("malformed input resilience:");
for (const event of [
  {},
  { content: "done JAMS" },
  { content: "done JAMS", senderId: OWNER },
  { content: ["done", "JAMS"], senderId: OWNER, messageId: "msg-array" },
]) {
  const fakeSpawn = assistantSpawn();
  let threw = false;
  try {
    await handleInboundMessage(event, {}, { config: CONFIG, api: makeApi([]), spawnImpl: fakeSpawn });
  } catch {
    threw = true;
  }
  check(!threw, `malformed event never throws: ${JSON.stringify(event)}`);
}

if (failures) {
  console.error(`\nFAIL: ${failures} assertion(s) failed`);
  process.exit(1);
}
console.log("\nPASS: task-tracker-completion-assistant handler (owner/chat gated, id-free confirm, browse, no envelope auto-write)");
