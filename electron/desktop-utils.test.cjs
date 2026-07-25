"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  constrainWindowState,
  createRedactingLineBuffer,
  createSseParser,
  extractExternalIntents,
  isValidRequestId,
  normaliseAccelerator,
  normaliseProgressValue,
  redactSensitiveText,
  sanitiseDeepLink,
  sanitiseDialogFilters,
  selectDesktopActivityState,
} = require("./desktop-utils.cjs");

test("validates request identifiers without accepting paths", () => {
  assert.equal(isValidRequestId("request_123-abc"), true);
  assert.equal(isValidRequestId("../request"), false);
  assert.equal(isValidRequestId(""), false);
  assert.equal(isValidRequestId("a".repeat(129)), false);
});

test("normalises configurable accelerators and supports disabling", () => {
  assert.equal(
    normaliseAccelerator("  CommandOrControl+Shift+Space  "),
    "CommandOrControl+Shift+Space",
  );
  assert.equal(normaliseAccelerator(null), null);
  assert.throws(() => normaliseAccelerator("A\nB"), /inválido/i);
});

test("normalises operation progress from fractions or percentages", () => {
  assert.equal(normaliseProgressValue(0.45), 0.45);
  assert.equal(normaliseProgressValue(45), 0.45);
  assert.equal(normaliseProgressValue(140), 1);
  assert.equal(normaliseProgressValue(-2), 0);
  assert.equal(normaliseProgressValue("invalid"), null);
});

test("selects a deterministic desktop activity state", () => {
  assert.equal(selectDesktopActivityState("ready", 0), "online");
  assert.equal(selectDesktopActivityState("ready", 2), "working");
  assert.equal(selectDesktopActivityState("starting", 0), "working");
  assert.equal(selectDesktopActivityState("offline", 0), "offline");
});

test("restores valid window bounds on the matching display", () => {
  const restored = constrainWindowState(
    { x: 2_100, y: 120, width: 1_200, height: 760, maximized: true },
    [
      { x: 0, y: 0, width: 1_920, height: 1_040 },
      { x: 1_920, y: 0, width: 1_600, height: 900 },
    ],
  );
  assert.deepEqual(restored, {
    x: 2_100,
    y: 120,
    width: 1_200,
    height: 760,
    maximized: true,
  });
});

test("recentres off-screen window state inside the primary work area", () => {
  const restored = constrainWindowState(
    { x: 8_000, y: -4_000, width: 4_000, height: 3_000 },
    [{ x: 0, y: 0, width: 1_600, height: 900 }],
  );
  assert.deepEqual(restored, {
    x: 0,
    y: 0,
    width: 1_600,
    height: 900,
    maximized: false,
  });
});

test("sanitises native dialog filters", () => {
  assert.deepEqual(
    sanitiseDialogFilters([
      { name: "Documentos", extensions: ["PDF", "docx", "../exe", "pdf"] },
      { name: "", extensions: ["txt"] },
    ]),
    [{ name: "Documentos", extensions: ["pdf", "docx"] }],
  );
});

test("redacts credentials in embedded URLs, headers, and named values", () => {
  const credentials = [
    "weather-test-credential-123",
    "access-test-credential-456",
    "header-test-credential-789",
    "signed-test-credential-012",
    "password-test-credential-345",
    "fragment-test-credential-678",
    "cli-test-credential-901",
  ];
  const message = [
    `Request failed for url 'https://url-user:${credentials[4]}@service.invalid/v1?view=full&appid=${credentials[0]}&access_token=${credentials[1]}'`,
    `Authorization: Bearer ${credentials[2]}\n`,
    `callback=https://service.invalid/object?X-Amz-Signature=${credentials[3]}.`,
    `redirect=https://service.invalid/callback#access_token=${credentials[5]}`,
    `--api-key ${credentials[6]}`,
  ].join(" ");

  const redacted = redactSensitiveText(message);

  for (const credential of credentials) {
    assert.equal(redacted.includes(credential), false);
  }
  assert.equal(redacted.includes("url-user"), false);
  assert.match(redacted, /view=full/);
  assert.match(redacted, /appid=\[redigido\]/);
  assert.match(redacted, /#access_token=\[redigido\]/);
  assert.match(redacted, /--api-key \[redigido\]/);
  assert.match(redacted, /Authorization: \[redigido\]/);
});

test("redacts a credential split across backend log chunks", () => {
  const credential = "split-test-credential-123";
  const records = [];
  const buffer = createRedactingLineBuffer((record) => records.push(record));

  buffer.push("Provider failed for https://service.invalid/v1?mode=test&appid=split-");
  buffer.push("test-credential-123\nnext safe line");
  assert.equal(records.length, 1);
  buffer.finish();

  const output = records.join("");
  assert.equal(output.includes(credential), false);
  assert.match(output, /mode=test/);
  assert.match(output, /appid=\[redigido\]/);
  assert.match(output, /next safe line/);
});

test("fails closed when an oversized log line crosses the buffer limit", () => {
  const credential = "overflow-test-credential-123";
  const records = [];
  const buffer = createRedactingLineBuffer(
    (record) => records.push(record),
    { maximumPendingChars: 1_024 },
  );

  buffer.push(`${"x".repeat(1_020)}&appid=`);
  buffer.push(`${credential}\nvisible safe line\n`);
  buffer.finish();

  const output = records.join("");
  assert.equal(output.includes(credential), false);
  assert.match(output, /linha de log omitida/);
  assert.match(output, /visible safe line/);
});

test("accepts only bounded Aether deep-link actions", () => {
  assert.deepEqual(
    sanitiseDeepLink("aether://ask?text=Ol%C3%A1"),
    { type: "ask-text", text: "Olá", source: "deep-link" },
  );
  assert.deepEqual(
    sanitiseDeepLink("aether://new-chat"),
    { type: "new-chat", source: "deep-link" },
  );
  assert.equal(sanitiseDeepLink("https://example.com"), null);
  assert.equal(sanitiseDeepLink("aether://unknown"), null);
});

test("extracts only explicitly marked existing files", () => {
  const intents = extractExternalIntents(
    ["app", "--ask-file", "/tmp/example.txt", "aether://settings"],
    { existingFile: (candidate) => candidate === "/tmp/example.txt" },
  );
  assert.deepEqual(intents, [
    {
      type: "ask-file",
      paths: ["/tmp/example.txt"],
      source: "command-line",
    },
    { type: "open-settings", source: "deep-link" },
  ]);
});

test("parses fragmented JSON SSE events", () => {
  const events = [];
  const parser = createSseParser((event) => events.push(event));
  parser.push("event: token\ndata: {\"type\":\"token\",");
  parser.push("\"text\":\"Oi\"}\n\n");
  parser.push(": heartbeat\n\ndata: plain");
  parser.push(" text\n\n");
  parser.finish();

  assert.deepEqual(events, [
    {
      event: "token",
      id: null,
      data: { type: "token", text: "Oi" },
    },
    {
      event: "message",
      id: null,
      data: "plain text",
    },
  ]);
});

test("preserves UTF-8 split across network chunks", () => {
  const events = [];
  const parser = createSseParser((event) => events.push(event));
  const encoded = Buffer.from('data: {"type":"token","text":"Olá 👋"}\n\n');
  const emojiOffset = encoded.indexOf(Buffer.from("👋"));
  parser.push(encoded.subarray(0, emojiOffset + 1));
  parser.push(encoded.subarray(emojiOffset + 1));
  parser.finish();
  assert.equal(events[0].data.text, "Olá 👋");
});

test("accepts many bounded events in one network chunk", () => {
  const events = [];
  const parser = createSseParser((event) => events.push(event), {
    maximumEventBytes: 24,
    maximumStreamBytes: 1_000,
  });
  parser.push("data: one\n\ndata: two\n\ndata: three\n\n");
  parser.finish();
  assert.equal(events.length, 3);
});

test("enforces per-event and total SSE limits", () => {
  const parser = createSseParser(() => {}, {
    maximumEventBytes: 20,
    maximumStreamBytes: 30,
  });
  assert.throws(
    () => parser.push(`data: ${"x".repeat(20)}`),
    /evento de streaming/i,
  );
});
