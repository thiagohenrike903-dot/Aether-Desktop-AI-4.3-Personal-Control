"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const {
  OneShotGrantStore,
  assertRendererBackendRequestAllowed,
  backendConfirmationHeaders,
  backendProjectHeaders,
  rendererBackendRequestAllowed,
  runWithScreenshotGrant,
  validatedProjectId,
} = require("./security-policy.cjs");

test("screenshot grants are short-lived and consumed exactly once", () => {
  let now = 1_000;
  const grants = new OneShotGrantStore({
    ttlMs: 1_000,
    now: () => now,
  });

  assert.equal(grants.consume(7).code, "SCREENSHOT_GRANT_REQUIRED");
  const granted = grants.grant(7);
  assert.equal(granted.expiresAt, 2_000);
  assert.equal(grants.status(7).active, true);
  assert.equal(grants.consume(7).ok, true);
  assert.equal(grants.consume(7).code, "SCREENSHOT_GRANT_REQUIRED");

  grants.grant(7);
  now = 2_000;
  assert.equal(grants.consume(7).code, "SCREENSHOT_GRANT_EXPIRED");
});

test("capture work cannot run without a valid one-shot grant", async () => {
  const grants = new OneShotGrantStore();
  let captures = 0;
  const capture = async () => {
    captures += 1;
    return { ok: true, image: "redacted" };
  };

  const blocked = await runWithScreenshotGrant(grants, "renderer", capture);
  assert.equal(blocked.blocked, true);
  assert.equal(captures, 0);

  grants.grant("renderer");
  const captured = await runWithScreenshotGrant(grants, "renderer", capture);
  assert.equal(captured.ok, true);
  assert.equal(captures, 1);

  const reused = await runWithScreenshotGrant(grants, "renderer", capture);
  assert.equal(reused.blocked, true);
  assert.equal(captures, 1);
});

test("renderer backend allowlist accepts declared 4.2 and 4.3 contracts", () => {
  for (const [method, route] of [
    ["GET", "/health"],
    ["GET", "/conversations?limit=200"],
    ["POST", "/projects/project-1/documents/import"],
    ["PUT", "/permissions/files/workspace"],
    ["PATCH", "/experience-profiles/work"],
    ["POST", "/safety-mode/emergency-suspend"],
    ["PUT", "/projects/project-1/safety-policy"],
    ["GET", "/audit/integrity?project_id=one"],
    ["POST", "/workflows/workflow-1/simulate"],
    ["POST", "/workflows/workflow-1/restore/revision-2"],
    ["POST", "/model-lab/runs/run-1/winner"],
    ["POST", "/evaluations/release-gate"],
    ["GET", "/projects/project-1/duplicates"],
    ["GET", "/agents/governance"],
    ["PUT", "/privacy/conversations/conversation-1"],
  ]) {
    assert.equal(
      rendererBackendRequestAllowed(method, route),
      true,
      `${method} ${route} should be allowed`,
    );
  }
});

test("renderer backend allowlist blocks unknown methods, routes and traversal", () => {
  assert.equal(rendererBackendRequestAllowed("POST", "/health"), false);
  assert.equal(rendererBackendRequestAllowed("GET", "/internal/secrets"), false);
  assert.equal(rendererBackendRequestAllowed("DELETE", "/projects"), false);
  assert.throws(
    () => assertRendererBackendRequestAllowed(
      "GET",
      "/projects/../health",
    ),
    /não permitido|inválido/i,
  );
  assert.throws(
    () => assertRendererBackendRequestAllowed(
      "GET",
      "/projects/%2e%2e/health",
    ),
    /codificado/i,
  );
  assert.throws(
    () => assertRendererBackendRequestAllowed(
      "GET",
      "/projects/id%2fdocuments",
    ),
    /codificado/i,
  );
});

test("renderer confirmation maps to one fixed header without arbitrary input", () => {
  assert.deepEqual(
    backendConfirmationHeaders(true),
    { "X-Aether-Confirmed": "true" },
  );
  assert.deepEqual(backendConfirmationHeaders(false), {});
  assert.deepEqual(
    backendConfirmationHeaders({
      headers: {
        Authorization: "Bearer attacker-controlled",
        "X-Aether-Confirmed": "true",
      },
    }),
    {},
  );
});

test("renderer project scope maps only a bounded safe id to a fixed header", () => {
  const uuid = "7a80e389-1228-44a0-9a0d-cc769b8e4315";
  assert.deepEqual(
    backendProjectHeaders(uuid),
    { "X-Aether-Project-Id": uuid },
  );
  assert.deepEqual(backendProjectHeaders(undefined), {});
  assert.deepEqual(backendProjectHeaders(null), {});
  assert.deepEqual(backendProjectHeaders(""), {});
  assert.equal(validatedProjectId("project_1.alpha-2"), "project_1.alpha-2");

  for (const invalid of [
    {},
    123,
    " leading-space",
    "trailing-space ",
    "project/child",
    "project\r\nX-Aether-Confirmed: true",
    "a".repeat(129),
  ]) {
    assert.throws(
      () => backendProjectHeaders(invalid),
      /projeto inválido/i,
    );
  }
});

test("every declared FastAPI route is allowlisted or has a dedicated IPC", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "..", "python", "jarvis", "app.py"),
    "utf8",
  );
  const dedicatedRoutes = new Set([
    "POST /requests/{request_id}/cancel",
    "POST /chat/stream",
  ]);
  const declaration =
    /@app\.(get|post|put|patch|delete)\("([^"]+)"\)/g;
  const missing = [];
  for (const match of source.matchAll(declaration)) {
    const method = match[1].toUpperCase();
    const declaredPath = match[2];
    const contract = `${method} ${declaredPath}`;
    if (dedicatedRoutes.has(contract)) {
      continue;
    }
    const examplePath = declaredPath
      .replace(/\{[^}:]+:path\}/g, "scope/path")
      .replace(/\{[^}]+\}/g, "id");
    if (!rendererBackendRequestAllowed(method, examplePath)) {
      missing.push(contract);
    }
  }
  assert.deepEqual(missing, []);
});
