"use strict";

const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const RUNTIME_MARKER = "requirements-state.json";
const VERIFY_IMPORTS = [
  "fastapi",
  "uvicorn",
  "pydantic",
  "httpx",
  "httpcore",
  "anyio",
  "bs4",
  "fitz",
].join(",");

function managedPythonPath(venvDirectory, platform = process.platform) {
  return path.join(
    venvDirectory,
    platform === "win32" ? "Scripts" : "bin",
    platform === "win32" ? "python.exe" : "python",
  );
}

function requirementsFingerprint(requirementsPath) {
  return crypto
    .createHash("sha256")
    .update(fs.readFileSync(requirementsPath))
    .digest("hex");
}

function readMarker(markerPath) {
  try {
    const value = JSON.parse(fs.readFileSync(markerPath, "utf8"));
    return typeof value?.requirementsSha256 === "string" ? value : null;
  } catch {
    return null;
  }
}

function writeMarker(markerPath, value) {
  const directory = path.dirname(markerPath);
  const temporary = path.join(
    directory,
    `.${path.basename(markerPath)}.${process.pid}.${crypto.randomBytes(6).toString("hex")}.tmp`,
  );
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  try {
    fs.writeFileSync(
      temporary,
      `${JSON.stringify(value, null, 2)}\n`,
      { flag: "wx", mode: 0o600 },
    );
    fs.renameSync(temporary, markerPath);
    try {
      fs.chmodSync(markerPath, 0o600);
    } catch {
      // Windows applies ACLs rather than POSIX modes.
    }
  } finally {
    try {
      fs.unlinkSync(temporary);
    } catch (error) {
      if (error?.code !== "ENOENT") {
        throw error;
      }
    }
  }
}

function runQuiet(command, args, options = {}) {
  const timeoutMs = Math.max(
    1_000,
    Math.min(Number(options.timeoutMs) || 10 * 60 * 1_000, 30 * 60 * 1_000),
  );
  return new Promise((resolve) => {
    let settled = false;
    let child;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };
    try {
      child = spawn(command, args, {
        cwd: options.cwd,
        env: options.env,
        windowsHide: true,
        shell: false,
        stdio: "ignore",
      });
    } catch {
      return resolve({ ok: false, code: null, timedOut: false });
    }
    const timer = setTimeout(() => {
      try {
        child.kill("SIGTERM");
      } catch {
        // The process already ended.
      }
      finish({ ok: false, code: null, timedOut: true });
    }, timeoutMs);
    timer.unref?.();
    child.once("error", () => {
      finish({ ok: false, code: null, timedOut: false });
    });
    child.once("close", (code) => {
      finish({ ok: code === 0, code, timedOut: false });
    });
  });
}

async function verifyRuntime(pythonExecutable, options = {}) {
  if (!fs.existsSync(pythonExecutable)) {
    return false;
  }
  const runner = options.runCommand || runQuiet;
  const result = await runner(
    pythonExecutable,
    [
      "-c",
      `import ${VERIFY_IMPORTS}; import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)`,
    ],
    {
      cwd: options.cwd,
      env: options.env,
      timeoutMs: 20_000,
    },
  );
  return Boolean(result?.ok);
}

async function preparePackagedPythonRuntime(options) {
  const {
    basePython,
    pythonDirectory,
    userDataDirectory,
    platform = process.platform,
    onStatus = () => {},
    runCommand = runQuiet,
  } = options || {};
  if (!basePython?.command || !Array.isArray(basePython.prefixArgs)) {
    throw new Error("O Python base do sistema não é válido.");
  }

  const requirementsPath = path.join(pythonDirectory, "requirements.txt");
  if (!fs.existsSync(requirementsPath)) {
    throw new Error("O arquivo de dependências do núcleo não foi encontrado.");
  }

  const runtimeRoot = path.join(userDataDirectory, "runtime");
  const venvDirectory = path.join(runtimeRoot, "python-venv");
  const pythonExecutable = managedPythonPath(venvDirectory, platform);
  const markerPath = path.join(runtimeRoot, RUNTIME_MARKER);
  const fingerprint = requirementsFingerprint(requirementsPath);
  const marker = readMarker(markerPath);
  const sharedOptions = {
    cwd: pythonDirectory,
    env: {
      ...process.env,
      PIP_DISABLE_PIP_VERSION_CHECK: "1",
      PIP_NO_INPUT: "1",
      PYTHONUTF8: "1",
    },
  };
  const runtimeVerified = fs.existsSync(pythonExecutable)
    ? await verifyRuntime(pythonExecutable, {
      ...sharedOptions,
      runCommand,
    })
    : false;

  if (
    marker?.requirementsSha256 === fingerprint &&
    runtimeVerified
  ) {
    return {
      command: pythonExecutable,
      prefixArgs: [],
      managed: true,
    };
  }

  fs.mkdirSync(runtimeRoot, { recursive: true, mode: 0o700 });
  if (!runtimeVerified) {
    onStatus("Preparando o ambiente Python privado da Aether…");
    const created = await runCommand(
      basePython.command,
      [
        ...basePython.prefixArgs,
        "-m",
        "venv",
        "--clear",
        venvDirectory,
      ],
      {
        ...sharedOptions,
        timeoutMs: 3 * 60 * 1_000,
      },
    );
    if (!created?.ok || !fs.existsSync(pythonExecutable)) {
      throw new Error(
        "Não foi possível criar o ambiente Python privado da Aether.",
      );
    }
  }

  onStatus("Instalando os componentes locais do Aether pela primeira vez…");
  const installed = await runCommand(
    pythonExecutable,
    [
      "-m",
      "pip",
      "install",
      "--disable-pip-version-check",
      "--no-input",
      "-r",
      requirementsPath,
    ],
    {
      ...sharedOptions,
      timeoutMs: 20 * 60 * 1_000,
    },
  );
  if (!installed?.ok) {
    throw new Error(
      "Não foi possível instalar os componentes Python. Verifique a conexão e tente novamente.",
    );
  }

  if (!await verifyRuntime(pythonExecutable, {
    ...sharedOptions,
    runCommand,
  })) {
    throw new Error(
      "O ambiente Python foi criado, mas os componentes obrigatórios não estão disponíveis.",
    );
  }

  writeMarker(markerPath, {
    requirementsSha256: fingerprint,
    preparedAt: new Date().toISOString(),
  });
  return {
    command: pythonExecutable,
    prefixArgs: [],
    managed: true,
  };
}

module.exports = {
  managedPythonPath,
  preparePackagedPythonRuntime,
  requirementsFingerprint,
  runQuiet,
  verifyRuntime,
};
