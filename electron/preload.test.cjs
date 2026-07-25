"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function loadPreload(options = {}) {
  const source = fs.readFileSync(
    path.join(__dirname, "preload.cjs"),
    "utf8",
  );
  const events = new EventEmitter();
  const rendererEvents = new EventEmitter();
  const invocations = [];
  let exposedApi = null;
  let resolveStream;
  const streamCompletion = new Promise((resolve) => {
    resolveStream = resolve;
  });
  const ipcRenderer = {
    on: (channel, listener) => events.on(channel, listener),
    removeListener: (channel, listener) =>
      events.removeListener(channel, listener),
    send: (channel, ...args) => {
      invocations.push({ kind: "send", channel, args });
    },
    invoke: (channel, ...args) => {
      invocations.push({ kind: "invoke", channel, args });
      return channel === "aether:start-chat-stream"
        ? streamCompletion
        : Promise.resolve({ ok: true });
    },
  };
  const context = {
    console,
    Date,
    Math,
    Promise,
    Uint8Array,
    crypto: {
      randomUUID: () => "12345678-1234-1234-1234-123456789abc",
    },
    navigator: {
      userActivation: {
        isActive: Boolean(options.userActivation),
      },
    },
    addEventListener: (name, listener) =>
      rendererEvents.on(name, listener),
    require: (specifier) => {
      assert.equal(
        specifier,
        "electron",
        "sandboxed preload must not require unrestricted Node modules",
      );
      return {
        contextBridge: {
          exposeInMainWorld: (name, api) => {
            assert.equal(name, "aether");
            exposedApi = api;
          },
        },
        ipcRenderer,
      };
    },
  };
  context.globalThis = context;
  vm.runInNewContext(source, context, {
    filename: "electron/preload.cjs",
  });
  return {
    api: exposedApi,
    events,
    invocations,
    rendererEvents,
    resolveStream,
  };
}

test("sandbox preload exposes a narrow API without Node built-ins", () => {
  const loaded = loadPreload();
  assert.equal(typeof loaded.api.request, "function");
  assert.equal(typeof loaded.api.startChatStream, "function");
  assert.equal(typeof loaded.api.desktop.ready, "function");
  assert.equal(typeof loaded.api.desktop.authorizeScreenshot, "function");
  assert.equal(typeof loaded.api.desktop.captureScreenshot, "function");
  assert.equal(typeof loaded.api.desktop.readSelectedFiles, "function");
  assert.equal(typeof loaded.api.credentials.status, "function");
  assert.equal(typeof loaded.api.credentials.authorize, "function");
  assert.equal(typeof loaded.api.credentials.revoke, "function");
  assert.equal(typeof loaded.api.updates.status, "function");
  assert.equal(typeof loaded.api.updates.verify, "function");
  assert.equal(typeof loaded.api.updates.createSnapshot, "function");
  assert.equal(typeof loaded.api.updates.rollback, "function");
  assert.equal("ipcRenderer" in loaded.api, false);
});

test("screenshot authorization requires an explicit trusted gesture", async () => {
  const blocked = loadPreload();
  const denied = await blocked.api.desktop.authorizeScreenshot();
  assert.equal(denied.ok, false);
  assert.equal(denied.code, "TRUSTED_USER_GESTURE_REQUIRED");
  assert.equal(
    blocked.invocations.some(
      (item) => item.channel === "aether:authorize-screenshot",
    ),
    false,
  );

  const activated = loadPreload({ userActivation: true });
  await activated.api.desktop.authorizeScreenshot();
  await activated.api.desktop.captureScreenshot({ displayId: "1" });
  assert.equal(
    activated.invocations.some(
      (item) => item.channel === "aether:authorize-screenshot",
    ),
    true,
  );
  assert.equal(
    activated.invocations.some(
      (item) => item.channel === "aether:capture-screenshot",
    ),
    true,
  );
});

test("credentials and recovery APIs stay behind dedicated IPC channels", async () => {
  const loaded = loadPreload();
  await loaded.api.credentials.authorize("gemini", {
    integration: "research",
    policy: "temporary",
    ttlMs: 60_000,
  });
  await loaded.api.credentials.revoke("gemini", "research");
  await loaded.api.updates.setChannel("beta");
  await loaded.api.updates.listSnapshots();

  const channels = loaded.invocations.map((item) => item.channel);
  assert.equal(channels.includes("aether:credential-authorize"), true);
  assert.equal(channels.includes("aether:credential-revoke"), true);
  assert.equal(channels.includes("aether:update-channel"), true);
  assert.equal(channels.includes("aether:recovery-list"), true);
});

test("backend request exposes project scope but strips arbitrary headers", async () => {
  const loaded = loadPreload();
  await loaded.api.request("/memories", {
    method: "POST",
    body: { project_id: "project-1" },
    projectId: "project-1",
    confirmed: true,
    timeoutMs: 30_000,
    headers: {
      Authorization: "Bearer renderer-controlled",
      "X-Aether-Project-Id": "forged",
    },
    includeToken: false,
  });
  const invocation = loaded.invocations.find(
    (item) => item.channel === "aether:backend-request",
  );
  assert.deepEqual(JSON.parse(JSON.stringify(invocation.args)), [{
    path: "/memories",
    options: {
      method: "POST",
      body: { project_id: "project-1" },
      confirmed: true,
      projectId: "project-1",
      timeoutMs: 30_000,
    },
  }]);
});

test("selected file reads stay behind the narrow desktop IPC channel", async () => {
  const loaded = loadPreload();
  await loaded.api.desktop.readSelectedFiles(["/tmp/granted.txt"]);
  const invocation = loaded.invocations.find(
    (item) => item.channel === "aether:read-selected-files",
  );
  assert.deepEqual(invocation.args, [["/tmp/granted.txt"]]);
});

test("scoped SSE subscription is removed after completion", async () => {
  const loaded = loadPreload();
  const received = [];
  const stream = loaded.api.startChatStream(
    { message: "Olá" },
    (event) => received.push(event),
  );
  assert.equal(
    stream.requestId,
    "request_12345678123412341234123456789abc",
  );
  loaded.events.emit(
    "aether:chat-stream-event",
    {},
    { requestId: "other", type: "token" },
  );
  loaded.events.emit(
    "aether:chat-stream-event",
    {},
    { requestId: stream.requestId, type: "token", data: { text: "Oi" } },
  );
  assert.equal(received.length, 1);

  loaded.resolveStream({ ok: true });
  await stream.completion;
  loaded.events.emit(
    "aether:chat-stream-event",
    {},
    { requestId: stream.requestId, type: "token" },
  );
  assert.equal(received.length, 1);
  assert.equal(
    loaded.events.listenerCount("aether:chat-stream-event"),
    0,
  );
});

test("stream cancel uses only the correlated request id", async () => {
  const loaded = loadPreload();
  const stream = loaded.api.startChatStream(
    { request_id: "request_safe" },
    () => {},
  );
  await stream.cancel();
  const cancelInvocation = loaded.invocations.find(
    (item) => item.channel === "aether:cancel-request",
  );
  assert.deepEqual(cancelInvocation.args, ["request_safe"]);
  loaded.resolveStream({ ok: false, cancelled: true });
  await stream.completion;
});
