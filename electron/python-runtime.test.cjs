"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");

const {
  managedPythonPath,
  preparePackagedPythonRuntime,
  requirementsFingerprint,
} = require("./python-runtime.cjs");

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "aether-runtime-test-"));
  const pythonDirectory = path.join(root, "python");
  const userDataDirectory = path.join(root, "user-data");
  fs.mkdirSync(pythonDirectory, { recursive: true });
  fs.writeFileSync(
    path.join(pythonDirectory, "requirements.txt"),
    "fastapi==0.115.0\n",
  );
  return {
    root,
    pythonDirectory,
    userDataDirectory,
    cleanup: () => fs.rmSync(root, { recursive: true, force: true }),
  };
}

test("managed runtime path is platform-correct", () => {
  assert.equal(
    managedPythonPath("/runtime/venv", "linux"),
    path.join("/runtime/venv", "bin", "python"),
  );
  assert.equal(
    managedPythonPath("C:\\runtime\\venv", "win32"),
    path.join("C:\\runtime\\venv", "Scripts", "python.exe"),
  );
});

test("packaged runtime creates venv, installs, verifies and records state", async () => {
  const item = fixture();
  const calls = [];
  try {
    const runtimePython = managedPythonPath(
      path.join(item.userDataDirectory, "runtime", "python-venv"),
      "linux",
    );
    const result = await preparePackagedPythonRuntime({
      basePython: { command: "python3", prefixArgs: [] },
      pythonDirectory: item.pythonDirectory,
      userDataDirectory: item.userDataDirectory,
      platform: "linux",
      runCommand: async (command, args) => {
        calls.push([command, args]);
        if (args.includes("venv")) {
          fs.mkdirSync(path.dirname(runtimePython), { recursive: true });
          fs.writeFileSync(runtimePython, "");
        }
        return { ok: true, code: 0, timedOut: false };
      },
    });
    assert.equal(result.command, runtimePython);
    assert.equal(result.managed, true);
    assert.equal(calls.length, 3);
    assert.ok(calls[0][1].includes("venv"));
    assert.ok(calls[1][1].includes("pip"));
    assert.ok(calls[2][1].some((value) => String(value).includes("fastapi")));
    const marker = JSON.parse(
      fs.readFileSync(
        path.join(item.userDataDirectory, "runtime", "requirements-state.json"),
        "utf8",
      ),
    );
    assert.equal(
      marker.requirementsSha256,
      requirementsFingerprint(
        path.join(item.pythonDirectory, "requirements.txt"),
      ),
    );
  } finally {
    item.cleanup();
  }
});

test("matching verified runtime skips installation", async () => {
  const item = fixture();
  try {
    const runtimeRoot = path.join(item.userDataDirectory, "runtime");
    const runtimePython = managedPythonPath(
      path.join(runtimeRoot, "python-venv"),
      "linux",
    );
    fs.mkdirSync(path.dirname(runtimePython), { recursive: true });
    fs.writeFileSync(runtimePython, "");
    fs.mkdirSync(runtimeRoot, { recursive: true });
    fs.writeFileSync(
      path.join(runtimeRoot, "requirements-state.json"),
      JSON.stringify({
        requirementsSha256: requirementsFingerprint(
          path.join(item.pythonDirectory, "requirements.txt"),
        ),
      }),
    );
    const calls = [];
    const result = await preparePackagedPythonRuntime({
      basePython: { command: "python3", prefixArgs: [] },
      pythonDirectory: item.pythonDirectory,
      userDataDirectory: item.userDataDirectory,
      platform: "linux",
      runCommand: async (command, args) => {
        calls.push([command, args]);
        return { ok: true, code: 0, timedOut: false };
      },
    });
    assert.equal(result.command, runtimePython);
    assert.equal(calls.length, 1);
    assert.ok(calls[0][1].some((value) => String(value).includes("fastapi")));
  } finally {
    item.cleanup();
  }
});

test("invalid existing runtime is rebuilt before dependencies are installed", async () => {
  const item = fixture();
  try {
    const runtimeRoot = path.join(item.userDataDirectory, "runtime");
    const runtimePython = managedPythonPath(
      path.join(runtimeRoot, "python-venv"),
      "linux",
    );
    fs.mkdirSync(path.dirname(runtimePython), { recursive: true });
    fs.writeFileSync(runtimePython, "broken");
    fs.writeFileSync(
      path.join(runtimeRoot, "requirements-state.json"),
      JSON.stringify({
        requirementsSha256: requirementsFingerprint(
          path.join(item.pythonDirectory, "requirements.txt"),
        ),
      }),
    );
    let verificationCount = 0;
    const calls = [];
    await preparePackagedPythonRuntime({
      basePython: { command: "python3", prefixArgs: [] },
      pythonDirectory: item.pythonDirectory,
      userDataDirectory: item.userDataDirectory,
      platform: "linux",
      runCommand: async (command, args) => {
        calls.push([command, args]);
        if (args[0] === "-c") {
          verificationCount += 1;
          return {
            ok: verificationCount > 1,
            code: verificationCount > 1 ? 0 : 1,
          };
        }
        if (args.includes("venv")) {
          fs.writeFileSync(runtimePython, "rebuilt");
        }
        return { ok: true, code: 0, timedOut: false };
      },
    });
    assert.ok(calls.some(([, args]) => args.includes("venv")));
    assert.ok(calls.some(([, args]) => args.includes("pip")));
    assert.equal(verificationCount, 2);
  } finally {
    item.cleanup();
  }
});

test("installation errors do not expose child-process output", async () => {
  const item = fixture();
  const runtimePython = managedPythonPath(
    path.join(item.userDataDirectory, "runtime", "python-venv"),
    "linux",
  );
  try {
    await assert.rejects(
      preparePackagedPythonRuntime({
        basePython: { command: "python3", prefixArgs: [] },
        pythonDirectory: item.pythonDirectory,
        userDataDirectory: item.userDataDirectory,
        platform: "linux",
        runCommand: async (_command, args) => {
          if (args.includes("venv")) {
            fs.mkdirSync(path.dirname(runtimePython), { recursive: true });
            fs.writeFileSync(runtimePython, "");
            return { ok: true, code: 0, timedOut: false };
          }
          return {
            ok: false,
            code: 1,
            timedOut: false,
            output: "https://example.invalid/?token=must-not-appear",
          };
        },
      }),
      (error) => {
        assert.doesNotMatch(error.message, /must-not-appear/);
        return true;
      },
    );
  } finally {
    item.cleanup();
  }
});
