"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const virtualEnvironmentPython =
  process.platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");

function executableWorks(command) {
  const result = spawnSync(command, ["--version"], {
    cwd: root,
    encoding: "utf8",
    shell: false,
    windowsHide: true,
  });
  return result.status === 0;
}

function systemPython() {
  for (const command of process.platform === "win32"
    ? ["py", "python"]
    : ["python3", "python"]) {
    if (executableWorks(command)) {
      return command;
    }
  }
  return null;
}

function runPython(command, args, environment) {
  const result = spawnSync(command, args, {
    cwd: root,
    env: environment,
    encoding: "utf8",
    shell: false,
    windowsHide: true,
    stdio: "inherit",
  });
  if (result.error) {
    console.error(`[python] Falha ao iniciar ${command}: ${result.error.message}`);
    return false;
  }
  return result.status === 0;
}

const hasVirtualEnvironment =
  fs.existsSync(virtualEnvironmentPython) &&
  executableWorks(virtualEnvironmentPython);
const python = hasVirtualEnvironment
  ? virtualEnvironmentPython
  : systemPython();

if (!python) {
  console.error(
    "[python] Nenhum Python utilizável foi encontrado para compilar o núcleo.",
  );
  process.exitCode = 1;
} else {
  const cacheDirectory = fs.mkdtempSync(
    path.join(os.tmpdir(), "aether-pycache-"),
  );
  const environment = {
    ...process.env,
    PYTHONPATH: [
      path.join(root, "python"),
      process.env.PYTHONPATH,
    ].filter(Boolean).join(path.delimiter),
    PYTHONPYCACHEPREFIX: cacheDirectory,
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONUTF8: "1",
  };

  try {
    const compiled = runPython(
      python,
      ["-m", "compileall", "-q", "python/jarvis", "python/tests"],
      environment,
    );
    if (!compiled) {
      console.error("[python] compileall encontrou erro(s) de sintaxe.");
      process.exitCode = 1;
    } else if (hasVirtualEnvironment) {
      const tested = runPython(
        python,
        ["-m", "pytest", "-q", "-p", "no:cacheprovider", "python/tests"],
        environment,
      );
      if (!tested) {
        console.error("[python] pytest falhou dentro da .venv preparada.");
        process.exitCode = 1;
      } else {
        console.log("[python] compileall e pytest aprovados.");
      }
    } else if (process.env.AETHER_REQUIRE_PYTHON_VENV === "1") {
      console.error(
        "[python] .venv ausente. Execute `npm run setup`; a validação estrita exige pytest.",
      );
      process.exitCode = 1;
    } else {
      console.log(
        "[python] compileall aprovado; pytest não executado porque a .venv está ausente. Execute `npm run setup` ou use AETHER_REQUIRE_PYTHON_VENV=1 no CI.",
      );
    }
  } finally {
    fs.rmSync(cacheDirectory, { recursive: true, force: true });
  }
}
