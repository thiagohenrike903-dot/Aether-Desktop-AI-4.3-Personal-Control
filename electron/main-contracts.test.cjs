"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const mainSource = fs.readFileSync(
  path.join(__dirname, "main.cjs"),
  "utf8",
);
const preloadSource = fs.readFileSync(
  path.join(__dirname, "preload.cjs"),
  "utf8",
);

const REQUIRED_HANDLES = Object.freeze([
  "aether:authorize-screenshot",
  "aether:capture-screenshot",
  "aether:credential-status",
  "aether:credential-authorize",
  "aether:credential-revoke",
  "aether:update-status",
  "aether:update-channel",
  "aether:update-verify",
  "aether:recovery-snapshot",
  "aether:recovery-list",
  "aether:recovery-rollback",
]);

function handlerSource(channel) {
  const marker = `ipcMain.handle("${channel}"`;
  const start = mainSource.indexOf(marker);
  assert.notEqual(start, -1, `handler ausente: ${channel}`);
  const next = mainSource.indexOf("\n  ipcMain.handle(", start + marker.length);
  return mainSource.slice(start, next === -1 ? undefined : next);
}

test("new privileged IPCs are registered, cleaned up and exposed narrowly", () => {
  const cleanupSection = mainSource.slice(
    mainSource.indexOf("const IPC_HANDLE_CHANNELS"),
    mainSource.indexOf("let mainWindow"),
  );
  for (const channel of REQUIRED_HANDLES) {
    assert.match(mainSource, new RegExp(
      `ipcMain\\.handle\\("${channel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`,
    ));
    assert.equal(
      cleanupSection.includes(`"${channel}"`),
      true,
      `canal sem cleanup: ${channel}`,
    );
    assert.equal(
      preloadSource.includes(`"${channel}"`),
      true,
      `canal não exposto pelo preload: ${channel}`,
    );
  }
  assert.equal(preloadSource.includes("ipcRenderer:"), false);
});

test("generic backend proxy asserts its method and route allowlist", () => {
  const source = handlerSource("aether:backend-request");
  const assertion = source.indexOf("assertRendererBackendRequestAllowed(");
  const request = source.indexOf("requestBackend(");
  assert.notEqual(assertion, -1);
  assert.notEqual(request, -1);
  assert.equal(assertion < request, true);
  assert.match(source, /confirmed:\s*options\.confirmed\s*===\s*true/);
  assert.match(source, /projectId:\s*options\.projectId/);
  assert.equal(source.includes("options.headers"), false);
});

test("screenshot capture consumes the one-shot grant before desktop capture", () => {
  const source = handlerSource("aether:capture-screenshot");
  const policy = source.indexOf("runWithScreenshotGrant(");
  const capture = source.indexOf("captureScreenshot(options)");
  assert.notEqual(policy, -1);
  assert.notEqual(capture, -1);
  assert.equal(policy < capture, true);
});

test("desktop vault enforcement includes OAuth JSON without standard exposure", () => {
  for (const key of [
    "GOOGLE_CLIENT_CREDENTIALS_JSON",
    "GMAIL_OAUTH_TOKEN_JSON",
    "CALENDAR_OAUTH_TOKEN_JSON",
  ]) {
    assert.equal(mainSource.includes(`${key}: "${key}"`), true);
    assert.equal(
      mainSource.includes(`"${key}",`),
      true,
      `${key} não está marcado como secure-only`,
    );
  }
  assert.match(mainSource, /AETHER_VAULT_ENFORCED:\s*"1"/);
  assert.match(mainSource, /secureOnlyCredentialEnvironment\s*\(/);
});

test("recovery surface deliberately exposes no install IPC", () => {
  const registered = [
    ...mainSource.matchAll(/ipcMain\.handle\("(aether:[^"]+)"/g),
  ].map((match) => match[1]);
  assert.equal(
    registered.some((channel) => /(?:install-update|update-install)/.test(channel)),
    false,
  );
});
