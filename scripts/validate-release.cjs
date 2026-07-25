"use strict";

const { spawnSync } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const failures = [];
const notes = [];

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function requireFile(relativePath) {
  const absolutePath = path.join(root, relativePath);
  if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) {
    failures.push(`Arquivo obrigatório ausente: ${relativePath}`);
    return false;
  }
  return true;
}

function sha256(relativePath) {
  return crypto
    .createHash("sha256")
    .update(fs.readFileSync(path.join(root, relativePath)))
    .digest("hex");
}

function readBuffer(relativePath) {
  return fs.readFileSync(path.join(root, relativePath));
}

function inspectPng(relativePath) {
  if (!requireFile(relativePath)) {
    return null;
  }
  const buffer = readBuffer(relativePath);
  const signature = Buffer.from([
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
  ]);
  if (
    buffer.length < 33 ||
    !buffer.subarray(0, signature.length).equals(signature) ||
    buffer.toString("ascii", 12, 16) !== "IHDR"
  ) {
    failures.push(`PNG inválido: ${relativePath}`);
    return null;
  }
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
    bitDepth: buffer[24],
    colorType: buffer[25],
  };
}

function inspectBmp(relativePath) {
  if (!requireFile(relativePath)) {
    return null;
  }
  const buffer = readBuffer(relativePath);
  if (
    buffer.length < 54 ||
    buffer.toString("ascii", 0, 2) !== "BM"
  ) {
    failures.push(`BMP inválido: ${relativePath}`);
    return null;
  }
  return {
    width: Math.abs(buffer.readInt32LE(18)),
    height: Math.abs(buffer.readInt32LE(22)),
    bitsPerPixel: buffer.readUInt16LE(28),
  };
}

function inspectIco(relativePath) {
  if (!requireFile(relativePath)) {
    return null;
  }
  const buffer = readBuffer(relativePath);
  if (
    buffer.length < 6 ||
    buffer.readUInt16LE(0) !== 0 ||
    buffer.readUInt16LE(2) !== 1
  ) {
    failures.push(`ICO inválido: ${relativePath}`);
    return null;
  }
  const count = buffer.readUInt16LE(4);
  if (buffer.length < 6 + count * 16) {
    failures.push(`Diretório ICO truncado: ${relativePath}`);
    return null;
  }
  const sizes = [];
  for (let index = 0; index < count; index += 1) {
    const offset = 6 + index * 16;
    const width = buffer[offset] || 256;
    const height = buffer[offset + 1] || 256;
    sizes.push([width, height]);
  }
  return sizes;
}

function checkSyntax(relativePath) {
  const result = spawnSync(process.execPath, ["--check", relativePath], {
    cwd: root,
    encoding: "utf8",
    shell: false,
  });
  if (result.status !== 0) {
    failures.push(
      `Sintaxe inválida em ${relativePath}: ${(result.stderr || result.stdout || "").trim()}`,
    );
  }
}

const requiredFiles = [
  "package.json",
  "package-lock.json",
  "renderer/index.html",
  "renderer/app.js",
  "renderer/styles.css",
  "dist/index.html",
  "dist/app.js",
  "dist/styles.css",
  "electron/main.cjs",
  "electron/main-contracts.test.cjs",
  "electron/preload.cjs",
  "electron/python-runtime.cjs",
  "electron/credential-vault.cjs",
  "electron/security-policy.cjs",
  "electron/update-recovery.cjs",
  "scripts/prepare-update-trust.cjs",
  "scripts/validate-python.cjs",
  "build/icon.svg",
  "build/icon.png",
  "build/icon.ico",
  "build/splash.html",
  "build/assets/aether-wordmark.png",
  "build/assets/aether-wordmark-transparent.png",
  "build/portable-splash.bmp",
  "build/installerHeader.bmp",
  "build/installerSidebar.bmp",
  "build/uninstallerSidebar.bmp",
  "python/jarvis/app.py",
  "python/jarvis/__init__.py",
  ".env.example",
  "README.md",
  "SECURITY.md",
  "docs/VALIDACAO-4.3.md",
];
requiredFiles.forEach(requireFile);

const packageJson = JSON.parse(read("package.json"));
const packageLock = JSON.parse(read("package-lock.json"));
const expectedVersion = String(packageJson.version || "");
if (!/^4\.3\.\d+$/.test(expectedVersion)) {
  failures.push(`Versão inesperada no package.json: ${expectedVersion || "vazia"}`);
}
if (
  packageLock.version !== expectedVersion ||
  packageLock.packages?.[""]?.version !== expectedVersion
) {
  failures.push("package-lock.json não corresponde à versão do pacote.");
}
for (const dependency of ["electron", "electron-builder"]) {
  const declared = packageJson.devDependencies?.[dependency];
  const locked = packageLock.packages?.[`node_modules/${dependency}`]?.version;
  if (!declared || declared !== locked) {
    failures.push(
      `Dependência de release divergente no lockfile: ${dependency}.`,
    );
  }
}

const iconPng = inspectPng("build/icon.png");
if (
  iconPng &&
  (
    iconPng.width !== 1_024 ||
    iconPng.height !== 1_024 ||
    iconPng.bitDepth !== 8 ||
    iconPng.colorType !== 6
  )
) {
  failures.push(
    "build/icon.png precisa ser PNG RGBA 8-bit de 1024×1024.",
  );
}

const transparentWordmark = inspectPng(
  "build/assets/aether-wordmark-transparent.png",
);
if (
  transparentWordmark &&
  (
    transparentWordmark.width < 600 ||
    transparentWordmark.height < 200 ||
    ![4, 6].includes(transparentWordmark.colorType)
  )
) {
  failures.push(
    "O wordmark de splash precisa ter resolução útil e canal alpha.",
  );
}

const icoSizes = inspectIco("build/icon.ico");
const expectedIcoSizes = [16, 20, 24, 32, 40, 48, 64, 128, 256];
if (icoSizes) {
  const squareSizes = icoSizes
    .filter(([width, height]) => width === height)
    .map(([width]) => width)
    .sort((first, second) => first - second);
  if (JSON.stringify(squareSizes) !== JSON.stringify(expectedIcoSizes)) {
    failures.push(
      `Frames inesperados em build/icon.ico: ${squareSizes.join(", ")}`,
    );
  }
}

for (const [relativePath, width, height] of [
  ["build/portable-splash.bmp", 420, 240],
  ["build/installerHeader.bmp", 150, 57],
  ["build/installerSidebar.bmp", 164, 314],
  ["build/uninstallerSidebar.bmp", 164, 314],
]) {
  const bitmap = inspectBmp(relativePath);
  if (
    bitmap &&
    (
      bitmap.width !== width ||
      bitmap.height !== height ||
      bitmap.bitsPerPixel !== 24
    )
  ) {
    failures.push(
      `${relativePath} precisa ser BMP 24-bit de ${width}×${height}.`,
    );
  }
}

for (const state of ["online", "working", "offline"]) {
  for (const [theme, suffix, size] of [
    ["light", "", 16],
    ["light", "@1.25x", 20],
    ["light", "@1.5x", 24],
    ["light", "@2x", 32],
    ["dark", "", 16],
    ["dark", "@1.25x", 20],
    ["dark", "@1.5x", 24],
    ["dark", "@2x", 32],
  ]) {
    const relativePath =
      `build/tray/tray-${theme}-${state}${suffix}.png`;
    const image = inspectPng(relativePath);
    if (
      image &&
      (
        image.width !== size ||
        image.height !== size ||
        ![4, 6].includes(image.colorType)
      )
    ) {
      failures.push(
        `Asset de bandeja inválido: ${relativePath} deve ser ${size}×${size} com alpha.`,
      );
    }
  }
  const templateName =
    `Aether${state[0].toUpperCase()}${state.slice(1)}Template`;
  for (const [suffix, size] of [["", 18], ["@2x", 36]]) {
    const relativePath = `build/tray/${templateName}${suffix}.png`;
    const image = inspectPng(relativePath);
    if (
      image &&
      (
        image.width !== size ||
        image.height !== size ||
        ![4, 6].includes(image.colorType)
      )
    ) {
      failures.push(
        `Template macOS inválido: ${relativePath} deve ser ${size}×${size} com alpha.`,
      );
    }
  }
}

const iconSource = read("build/icon.svg");
const splashHtml = read("build/splash.html");
const legacyBrandColours =
  /#(?:17b897|4277e9|22c9a6|17afa0|4d74ee)\b/i;
if (legacyBrandColours.test(iconSource) || legacyBrandColours.test(splashHtml)) {
  failures.push("Ícone ou splash ainda contém cores da identidade antiga.");
}
if (
  !/aether-wordmark-transparent\.png/.test(splashHtml) ||
  !/img-src\s+'self'/.test(splashHtml)
) {
  failures.push(
    "O splash não carrega o wordmark local sob uma CSP explícita.",
  );
}

const builderConfig = JSON.parse(read("build/electron-builder.json"));
if (!/\.bmp$/i.test(String(builderConfig.portable?.splashImage || ""))) {
  failures.push("O splash do executável portátil precisa ser um BMP.");
}
for (const [key, expected] of [
  ["installerIcon", "build/icon.ico"],
  ["uninstallerIcon", "build/icon.ico"],
  ["installerHeader", "build/installerHeader.bmp"],
  ["installerSidebar", "build/installerSidebar.bmp"],
  ["uninstallerSidebar", "build/uninstallerSidebar.bmp"],
]) {
  if (builderConfig.nsis?.[key] !== expected) {
    failures.push(`Branding NSIS ausente ou divergente: nsis.${key}`);
  }
}
if (
  !builderConfig.extraResources?.some(
    (item) => item?.from === "build/tray" && item?.to === "tray",
  )
) {
  failures.push("Os assets dedicados da bandeja não entram em extraResources.");
}
if (
  !builderConfig.files?.includes(
    "build/assets/aether-wordmark-transparent.png",
  )
) {
  failures.push("O wordmark usado pelo splash não entra no ASAR.");
}
if (!builderConfig.files?.includes("build/update-public-key.pem")) {
  failures.push(
    "A chave pública Ed25519 opcional não está declarada nos arquivos do ASAR.",
  );
}
const updatePublicKeyPath = path.join(root, "build", "update-public-key.pem");
if (fs.existsSync(updatePublicKeyPath)) {
  const publicKeyContents = fs.readFileSync(updatePublicKeyPath, "utf8");
  if (/BEGIN [A-Z ]*PRIVATE KEY/.test(publicKeyContents)) {
    failures.push(
      "build/update-public-key.pem contém material de chave privada.",
    );
  } else {
    try {
      const updatePublicKey = crypto.createPublicKey(publicKeyContents);
      if (updatePublicKey.asymmetricKeyType !== "ed25519") {
        failures.push(
          "build/update-public-key.pem precisa ser uma chave pública Ed25519.",
        );
      }
    } catch {
      failures.push("build/update-public-key.pem não é uma chave pública válida.");
    }
  }
} else {
  notes.push(
    "Chave pública de atualização não provisionada; a verificação ficará indisponível até o build ou o ambiente fornecer uma Ed25519.",
  );
}
if (builderConfig.win?.verifyUpdateCodeSignature !== true) {
  failures.push(
    "A verificação da assinatura de código das atualizações Windows precisa estar ativa.",
  );
}
for (const [key, expected] of [
  ["runAsNode", false],
  ["enableCookieEncryption", true],
  ["enableNodeOptionsEnvironmentVariable", false],
  ["enableNodeCliInspectArguments", false],
  ["enableEmbeddedAsarIntegrityValidation", true],
  ["onlyLoadAppFromAsar", true],
  ["loadBrowserProcessSpecificV8Snapshot", false],
  ["grantFileProtocolExtraPrivileges", false],
]) {
  if (builderConfig.electronFuses?.[key] !== expected) {
    failures.push(`Fuse Electron ausente ou inseguro: electronFuses.${key}`);
  }
}
const pythonResource = builderConfig.extraResources?.find(
  (item) => item?.from === "python" && item?.to === "python",
);
for (const requiredExclusion of [
  "!**/.env*",
  "!**/*credentials*.json",
  "!**/*.pem",
  "!**/*.key",
  "!tests/**",
]) {
  if (!pythonResource?.filter?.includes(requiredExclusion)) {
    failures.push(
      `Filtro de empacotamento Python ausente: ${requiredExclusion}`,
    );
  }
}
if (packageJson.scripts?.["build:icons"] !== "node build/make-icon.cjs") {
  failures.push("O projeto não expõe o gerador de branding em build:icons.");
}
if (
  !String(packageJson.scripts?.validate || "").includes(
    "npm run validate:python",
  )
) {
  failures.push("npm run validate não inclui a validação Python.");
}
if (
  packageJson.scripts?.["prepare:update-trust"] !==
    "node scripts/prepare-update-trust.cjs" ||
  !String(packageJson.scripts?.["build:win:trusted"] || "").includes(
    "npm run prepare:update-trust",
  )
) {
  failures.push(
    "O build confiável não exige a preparação explícita da chave pública Ed25519.",
  );
}

const versionFiles = [
  ["pyproject.toml", /version\s*=\s*"([^"]+)"/],
  ["python/pyproject.toml", /version\s*=\s*"([^"]+)"/],
  ["python/jarvis/__init__.py", /__version__\s*=\s*"([^"]+)"/],
  ["python/jarvis/app.py", /APP_VERSION\s*=\s*"([^"]+)"/],
];
for (const [relativePath, pattern] of versionFiles) {
  if (!requireFile(relativePath)) {
    continue;
  }
  const match = read(relativePath).match(pattern);
  if (!match) {
    failures.push(`Versão não encontrada em ${relativePath}`);
  } else if (match[1] !== expectedVersion) {
    failures.push(
      `Versão divergente em ${relativePath}: ${match[1]} (esperada ${expectedVersion})`,
    );
  }
}

for (const filename of ["index.html", "app.js", "styles.css"]) {
  const rendererPath = `renderer/${filename}`;
  const distPath = `dist/${filename}`;
  if (
    requireFile(rendererPath) &&
    requireFile(distPath) &&
    sha256(rendererPath) !== sha256(distPath)
  ) {
    failures.push(`dist/${filename} não corresponde à fonte em renderer/${filename}`);
  }
}

[
  "electron/main.cjs",
  "electron/main-contracts.test.cjs",
  "electron/preload.cjs",
  "electron/desktop-utils.cjs",
  "electron/desktop-utils.test.cjs",
  "electron/preload.test.cjs",
  "electron/python-runtime.cjs",
  "electron/python-runtime.test.cjs",
  "electron/credential-vault.cjs",
  "electron/credential-vault.test.cjs",
  "electron/security-policy.cjs",
  "electron/security-policy.test.cjs",
  "electron/update-recovery.cjs",
  "electron/update-recovery.test.cjs",
  "renderer/app.js",
  "scripts/build-renderer.cjs",
  "scripts/setup-python.cjs",
  "scripts/prepare-update-trust.cjs",
  "scripts/validate-python.cjs",
  "scripts/validate-release.cjs",
  "build/make-icon.cjs",
].forEach((relativePath) => {
  if (requireFile(relativePath)) {
    checkSyntax(relativePath);
  }
});

const indexHtml = read("renderer/index.html");
if (!/Content-Security-Policy/i.test(indexHtml)) {
  failures.push("A interface não declara Content-Security-Policy.");
}

const declaredIds = new Set();
const duplicateIds = new Set();
for (const match of indexHtml.matchAll(/\bid=["']([^"']+)["']/g)) {
  if (declaredIds.has(match[1])) {
    duplicateIds.add(match[1]);
  }
  declaredIds.add(match[1]);
}
for (const duplicateId of duplicateIds) {
  failures.push(`ID HTML duplicado: ${duplicateId}`);
}

const rendererScript = read("renderer/app.js");
const rendererStyles = read("renderer/styles.css");
for (const match of rendererStyles.matchAll(/font-size:\s*([0-9.]+)px/gi)) {
  if (Number(match[1]) < 12) {
    failures.push(
      `Texto menor que 12 px no renderer: ${match[0]}`,
    );
  }
}

function nonNeutralHexColor(value) {
  const compact = value.slice(1);
  const expanded = compact.length <= 4
    ? compact.split("").map((character) => character.repeat(2)).join("")
    : compact;
  if (![6, 8].includes(expanded.length)) return false;
  const channels = [0, 2, 4].map(
    (offset) => Number.parseInt(expanded.slice(offset, offset + 2), 16),
  );
  return channels[0] !== channels[1] || channels[1] !== channels[2];
}

for (const match of rendererStyles.matchAll(/#[0-9a-f]{3,8}\b/gi)) {
  if (nonNeutralHexColor(match[0])) {
    failures.push(
      `Cor fora da identidade monocromática no renderer: ${match[0]}`,
    );
  }
}
for (
  const match of rendererStyles.matchAll(
    /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/gi,
  )
) {
  const channels = match.slice(1, 4).map(Number);
  if (channels[0] !== channels[1] || channels[1] !== channels[2]) {
    failures.push(
      `Cor RGB fora da identidade monocromática no renderer: ${match[0]}`,
    );
  }
}

function cssVariables(selectorPattern) {
  const block = rendererStyles.match(
    new RegExp(`${selectorPattern}\\s*\\{([\\s\\S]*?)\\}`),
  )?.[1] || "";
  return Object.fromEntries(
    [...block.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-f]{6})\s*;/gi)]
      .map((match) => [match[1], match[2]]),
  );
}

function relativeLuminance(hex) {
  const channels = hex
    .slice(1)
    .match(/.{2}/g)
    .map((value) => Number.parseInt(value, 16) / 255)
    .map((value) => (
      value <= 0.04045
        ? value / 12.92
        : ((value + 0.055) / 1.055) ** 2.4
    ));
  return (
    0.2126 * channels[0] +
    0.7152 * channels[1] +
    0.0722 * channels[2]
  );
}

function contrastRatio(foreground, background) {
  const first = relativeLuminance(foreground);
  const second = relativeLuminance(background);
  return (
    (Math.max(first, second) + 0.05) /
    (Math.min(first, second) + 0.05)
  );
}

for (const [theme, variables] of [
  ["claro", cssVariables(":root")],
  ["escuro", cssVariables(':root\\[data-theme="dark"\\]')],
]) {
  for (const [foregroundName, backgroundName] of [
    ["text", "bg"],
    ["text-secondary", "surface"],
    ["sidebar-muted", "sidebar-bg"],
    ["accent", "surface"],
    ["accent", "accent-soft"],
    ["danger", "surface"],
    ["danger", "danger-soft"],
    ["warning", "surface"],
    ["warning", "warning-soft"],
    ["success", "surface"],
    ["success", "success-soft"],
  ]) {
    const foreground = variables[foregroundName];
    const background = variables[backgroundName];
    if (
      foreground &&
      background &&
      contrastRatio(foreground, background) < 4.5
    ) {
      failures.push(
        `Contraste abaixo de 4.5:1 no tema ${theme}: --${foregroundName} sobre --${backgroundName}.`,
      );
    }
  }
}

const referencedIds = new Set();
for (const pattern of [
  /\$\(["']#([^"']+)["']\)/g,
  /getElementById\(["']([^"']+)["']\)/g,
]) {
  for (const match of rendererScript.matchAll(pattern)) {
    referencedIds.add(match[1]);
  }
}
for (const referencedId of referencedIds) {
  if (!declaredIds.has(referencedId)) {
    failures.push(`renderer/app.js referencia um ID HTML ausente: ${referencedId}`);
  }
}

for (const match of indexHtml.matchAll(/\baria-controls=["']([^"']+)["']/g)) {
  for (const controlledId of match[1].split(/\s+/).filter(Boolean)) {
    if (!declaredIds.has(controlledId)) {
      failures.push(`aria-controls aponta para um ID ausente: ${controlledId}`);
    }
  }
}

const rendererContracts = [
  ["streaming SSE real", /startChatStream\s*\(/],
  ["Central de Controle", /["'`]\/operations/],
  ["permissões por escopo", /["'`]\/permissions/],
  ["memórias editáveis", /["'`]\/memories/],
  ["projetos", /["'`]\/projects/],
  ["pesquisa de páginas", /["'`]\/research/],
  ["perfis de modelo", /["'`]\/model-profiles/],
  ["automações", /["'`]\/automations/],
  ["captura de região", /function\s+openRegionCapture\s*\(/],
  ["cofre seguro", /credentials\.(?:status|set)\s*\(/],
  ["intents externos", /\bonExternalIntent\b/],
  ["progresso de operações", /\bonOperationProgress\b/],
  ["configurações desktop reativas", /onSettingsChanged\s*\(/],
  ["modo de proteção global", /["'`]\/safety-mode/],
  ["inspetor de contexto", /["'`]\/context\/preview/],
  ["auditoria exportável", /["'`]\/audit\/export/],
  ["perfis de experiência", /["'`]\/experience-profiles/],
  ["políticas por projeto", /\/safety-policy/],
  ["mapa de privacidade", /["'`]\/privacy/],
  ["relatório de auditoria", /["'`]\/audit\/report/],
  ["Model Lab", /["'`]\/model-lab/],
  ["workflows versionados", /["'`]\/workflows/],
  ["modo de ensaio", /["'`]\/simulations/],
  ["backup completo", /["'`]\/user-backup/],
  ["saúde e reparos", /["'`]\/system-health/],
  ["avaliações pessoais", /["'`]\/evaluations/],
  ["verificador de resposta", /["'`]\/responses\/verify/],
  ["governança de agentes", /["'`]\/agents\/governance/],
];
for (const [label, pattern] of rendererContracts) {
  if (!pattern.test(rendererScript)) {
    failures.push(`Contrato 4.2 ausente no renderer: ${label}`);
  }
}
if (/Configuração do gatilho \(JSON\)/i.test(rendererScript)) {
  failures.push("Automações ainda expõem JSON técnico em vez de campos visuais.");
}

const electronMain = read("electron/main.cjs");
for (const [label, pattern] of [
  ["contextIsolation", /contextIsolation\s*:\s*true/],
  ["sandbox", /sandbox\s*:\s*true/],
  ["nodeIntegration", /nodeIntegration\s*:\s*false/],
]) {
  if (!pattern.test(electronMain)) {
    failures.push(`Proteção Electron ausente ou desativada: ${label}`);
  }
}
if (!/preparePackagedPythonRuntime\s*\(/.test(electronMain)) {
  failures.push(
    "O aplicativo empacotado não prepara um ambiente Python privado.",
  );
}
for (const [label, pattern] of [
  ["restauração segura da janela", /constrainWindowState\s*\(/],
  ["persistência da janela", /WINDOW_STATE_FILE/],
  ["progresso nativo", /\.setProgressBar\s*\(/],
  ["ícone separado de notificação", /resolveNotificationImage\s*\(/],
  ["estado visual da bandeja", /selectDesktopActivityState\s*\(/],
  ["cofre v2 com concessões", /CredentialVaultStore/],
  ["allowlist por rota e método", /assertRendererBackendRequestAllowed\s*\(/],
  ["concessão curta de captura", /authorize-screenshot/],
  ["atualização e rollback verificados", /UpdateRecoveryManager/],
]) {
  if (!pattern.test(electronMain)) {
    failures.push(`Integração desktop ausente: ${label}.`);
  }
}

const envExample = read(".env.example");
const secretNames =
  /(?:API_KEY|ACCESS_TOKEN|CLIENT_SECRET|PASSWORD|PRIVATE_KEY|AUTH_TOKEN)$/i;
for (const rawLine of envExample.split(/\r?\n/)) {
  const line = rawLine.trim();
  if (!line || line.startsWith("#") || !line.includes("=")) {
    continue;
  }
  const separator = line.indexOf("=");
  const key = line.slice(0, separator).trim();
  const value = line.slice(separator + 1).trim().replace(/^["']|["']$/g, "");
  if (
    secretNames.test(key) &&
    value &&
    !/^(?:your[-_]|replace|change[-_]?me|example|placeholder|<)/i.test(value)
  ) {
    failures.push(`Possível credencial preenchida em .env.example: ${key}`);
  }
}

const credentialPatterns = [
  ["chave Google", /AIza[0-9A-Za-z_-]{30,}/],
  ["chave OpenAI compatível", /\bsk-[0-9A-Za-z_-]{20,}\b/],
  ["token GitHub", /\bghp_[0-9A-Za-z]{30,}\b/],
  ["chave privada", /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/],
];
const sourceFiles = [
  ".env.example",
  "README.md",
  "SECURITY.md",
  "CHANGELOG.md",
  "electron/main.cjs",
  "electron/preload.cjs",
  "electron/credential-vault.cjs",
  "electron/security-policy.cjs",
  "electron/update-recovery.cjs",
  "renderer/index.html",
  "renderer/app.js",
  "python/jarvis/config.py",
  "python/jarvis/app.py",
];
for (const relativePath of sourceFiles) {
  if (!requireFile(relativePath)) {
    continue;
  }
  const contents = read(relativePath);
  for (const [label, pattern] of credentialPatterns) {
    if (pattern.test(contents)) {
      failures.push(`Possível ${label} real em ${relativePath}`);
    }
  }
}

const forbiddenArtifacts = [
  ".env",
  "python/.env",
  "jarvis_data",
  "python/jarvis_data",
  ".venv",
  ".venv-test",
  "python/.pytest_cache",
];
for (const relativePath of forbiddenArtifacts) {
  if (fs.existsSync(path.join(root, relativePath))) {
    notes.push(`Ignorar no pacote final: ${relativePath}`);
  }
}

if (failures.length) {
  console.error(`Validação falhou com ${failures.length} problema(s):`);
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exitCode = 1;
} else {
  console.log(`Aether ${expectedVersion}: validação estrutural aprovada.`);
}

for (const note of notes) {
  console.log(`[nota] ${note}`);
}
