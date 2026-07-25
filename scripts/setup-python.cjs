"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const venvDirectory = path.join(root, ".venv");
const requirements = path.join(root, "python", "requirements.txt");
const envExample = path.join(root, ".env.example");
const envFile = path.join(root, ".env");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: "utf8",
    shell: false,
    stdio: options.capture ? "pipe" : "inherit",
  });
  return result;
}

function candidateVersion(candidate) {
  const result = run(candidate.command, [...candidate.prefix, "--version"], {
    capture: true,
  });
  if (result.error || result.status !== 0) {
    return null;
  }
  const output = `${result.stdout || ""} ${result.stderr || ""}`;
  const match = output.match(/Python\s+(\d+)\.(\d+)(?:\.(\d+))?/i);
  if (!match) {
    return null;
  }
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3] || 0),
  };
}

function findPython() {
  const candidates = [];
  if (process.env.JARVIS_PYTHON) {
    candidates.push({
      command: process.env.JARVIS_PYTHON,
      prefix: [],
    });
  }
  if (process.platform === "win32") {
    candidates.push(
      { command: "py", prefix: ["-3"] },
      { command: "python", prefix: [] },
      { command: "python3", prefix: [] },
    );
  } else {
    candidates.push(
      { command: "python3", prefix: [] },
      { command: "python", prefix: [] },
    );
  }

  for (const candidate of candidates) {
    const version = candidateVersion(candidate);
    if (
      version &&
      (version.major > 3 || (version.major === 3 && version.minor >= 10))
    ) {
      return { ...candidate, version };
    }
  }
  return null;
}

const python = findPython();
if (!python) {
  console.error(
    "Python 3.10 ou superior não foi encontrado. Instale o Python e tente novamente.",
  );
  process.exitCode = 1;
} else if (!fs.existsSync(requirements)) {
  console.error("python/requirements.txt não foi encontrado.");
  process.exitCode = 1;
} else {
  console.log(
    `[setup] Python ${python.version.major}.${python.version.minor}.${python.version.patch}`,
  );

  if (!fs.existsSync(venvDirectory)) {
    console.log("[setup] Criando ambiente virtual .venv…");
    const created = run(
      python.command,
      [...python.prefix, "-m", "venv", venvDirectory],
    );
    if (created.status !== 0) {
      console.error("[setup] Não foi possível criar o ambiente virtual.");
      process.exit(created.status || 1);
    }
  }

  const venvPython = path.join(
    venvDirectory,
    process.platform === "win32" ? "Scripts" : "bin",
    process.platform === "win32" ? "python.exe" : "python",
  );
  if (!fs.existsSync(venvPython)) {
    console.error("[setup] O Python da .venv não foi encontrado.");
    process.exitCode = 1;
  } else {
    console.log("[setup] Instalando dependências do núcleo Aether…");
    const installed = run(
      venvPython,
      ["-m", "pip", "install", "-r", requirements],
    );
    if (installed.status !== 0) {
      console.error("[setup] A instalação das dependências falhou.");
      process.exit(installed.status || 1);
    }

    if (!fs.existsSync(envFile) && fs.existsSync(envExample)) {
      fs.copyFileSync(envExample, envFile);
      console.log("[setup] Arquivo .env criado a partir do modelo seguro.");
    }

    console.log("");
    console.log("Configuração concluída.");
    console.log("1. Abra .env e informe a chave do provedor que deseja usar.");
    console.log("2. Execute npm start.");
  }
}
