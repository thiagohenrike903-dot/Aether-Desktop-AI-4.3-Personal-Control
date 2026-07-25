"use strict";

const {
  app,
  BrowserWindow,
  desktopCapturer,
  dialog,
  globalShortcut,
  ipcMain,
  Menu,
  nativeImage,
  nativeTheme,
  Notification,
  safeStorage,
  screen,
  shell,
  systemPreferences,
  Tray,
} = require("electron");
const { spawn, spawnSync } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const {
  cleanText,
  constrainWindowState,
  createRedactingLineBuffer,
  createSseParser,
  extractExternalIntents,
  isValidRequestId,
  normaliseAccelerator,
  normaliseProgressValue,
  redactSensitiveText,
  sanitiseDialogFilters,
  selectDesktopActivityState,
} = require("./desktop-utils.cjs");
const {
  preparePackagedPythonRuntime,
} = require("./python-runtime.cjs");
const {
  CredentialVaultStore,
  secureOnlyCredentialEnvironment,
  withoutManagedCredentialEnvironment,
} = require("./credential-vault.cjs");
const {
  OneShotGrantStore,
  assertRendererBackendRequestAllowed,
  backendConfirmationHeaders,
  backendProjectHeaders,
  runWithScreenshotGrant,
} = require("./security-policy.cjs");
const {
  UpdateRecoveryManager,
} = require("./update-recovery.cjs");

app.enableSandbox();

const BACKEND_HOST = "127.0.0.1";
const BACKEND_PORT = parsePort(process.env.JARVIS_PORT, 8765);
const BACKEND_ORIGIN = `http://${BACKEND_HOST}:${BACKEND_PORT}`;
const API_TOKEN = crypto.randomBytes(32).toString("base64url");
const ALLOWED_HTTP_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);
// A 10 MiB image grows to roughly 13.4 MiB as a base64 data URL.
const MAX_REQUEST_BODY_BYTES = 16 * 1024 * 1024;
const MAX_RESPONSE_BODY_BYTES = 32 * 1024 * 1024;
const BACKEND_START_TIMEOUT_MS = 30_000;
const MIN_SPLASH_TIME_MS = 700;
const DEFAULT_GLOBAL_SHORTCUT = "CommandOrControl+Shift+Space";
const MAX_SCREENSHOT_PIXELS = 40_000_000;
const MAX_SCREENSHOT_BYTES = 16 * 1024 * 1024;
const MAX_SELECTED_FILES = 100;
const MAX_GRANTED_FILE_BYTES = 10 * 1024 * 1024;
const MAX_GRANTED_FILES_PER_READ = 20;
const MAX_GRANTED_FILES_TOTAL_BYTES = 20 * 1024 * 1024;
const FILE_GRANT_TTL_MS = 5 * 60 * 1000;
const MAX_NOTIFICATION_TEXT = 500;
const DESKTOP_SETTINGS_FILE = "desktop-settings.json";
const WINDOW_STATE_FILE = "window-state.json";
const WINDOW_STATE_SAVE_DELAY_MS = 250;
const CREDENTIAL_VAULT_FILE = "credentials.safe";
const UPDATE_PUBLIC_KEY_FILE = "update-public-key.pem";
const RENDERER_CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "media-src 'self' data: blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-src 'none'",
  "frame-ancestors 'none'",
].join("; ");
const CREDENTIAL_ENVIRONMENT_KEYS = Object.freeze({
  gemini: "GEMINI_API_KEY",
  llm: "LLM_API_KEY",
  elevenlabs: "ELEVENLABS_API_KEY",
  weather: "WEATHER_API_KEY",
  GOOGLE_CLIENT_CREDENTIALS_JSON: "GOOGLE_CLIENT_CREDENTIALS_JSON",
  GMAIL_OAUTH_TOKEN_JSON: "GMAIL_OAUTH_TOKEN_JSON",
  CALENDAR_OAUTH_TOKEN_JSON: "CALENDAR_OAUTH_TOKEN_JSON",
});
const SECURE_ONLY_CREDENTIAL_ENVIRONMENT_KEYS = new Set([
  "GOOGLE_CLIENT_CREDENTIALS_JSON",
  "GMAIL_OAUTH_TOKEN_JSON",
  "CALENDAR_OAUTH_TOKEN_JSON",
]);
const RESTRICTED_CREDENTIAL_INTEGRATIONS = Object.freeze({
  GOOGLE_CLIENT_CREDENTIALS_JSON: Object.freeze(["gmail", "calendar"]),
  GMAIL_OAUTH_TOKEN_JSON: Object.freeze(["gmail"]),
  CALENDAR_OAUTH_TOKEN_JSON: Object.freeze(["calendar"]),
});
const READABLE_ATTACHMENT_TYPES = Object.freeze({
  ".pdf": "application/pdf",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".csv": "text/csv",
  ".tsv": "text/tab-separated-values",
  ".txt": "text/plain",
  ".md": "text/markdown",
  ".rst": "text/plain",
  ".json": "application/json",
  ".xml": "application/xml",
  ".html": "text/html",
  ".htm": "text/html",
  ".py": "text/x-python",
  ".js": "text/javascript",
  ".ts": "text/typescript",
  ".tsx": "text/typescript",
  ".jsx": "text/javascript",
  ".css": "text/css",
  ".yaml": "application/yaml",
  ".yml": "application/yaml",
  ".toml": "application/toml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
});
const TERMINAL_STREAM_EVENT_TYPES = new Set([
  "done",
  "cancelled",
  "error",
]);
const IPC_HANDLE_CHANNELS = Object.freeze([
  "aether:get-runtime-info",
  "aether:get-desktop-capabilities",
  "aether:get-desktop-settings",
  "aether:update-desktop-settings",
  "aether:renderer-ready",
  "aether:get-backend-status",
  "aether:backend-retry",
  "aether:backend-restart",
  "aether:choose-workspace",
  "aether:choose-files",
  "aether:read-selected-files",
  "aether:choose-folder",
  "aether:get-displays",
  "aether:authorize-screenshot",
  "aether:capture-screenshot",
  "aether:cancel-request",
  "aether:start-chat-stream",
  "aether:backend-request",
  "aether:open-external",
  "aether:notify",
  "aether:credential-status",
  "aether:credential-set",
  "aether:credential-delete",
  "aether:credential-authorize",
  "aether:credential-revoke",
  "aether:update-status",
  "aether:update-channel",
  "aether:update-verify",
  "aether:recovery-snapshot",
  "aether:recovery-list",
  "aether:recovery-rollback",
  "aether:window-state",
]);

let mainWindow = null;
let splashWindow = null;
let tray = null;
let backendProcess = null;
let backendLogStream = null;
let backendStartPromise = null;
let ownsBackendProcess = false;
let quitting = false;
let shutdownComplete = false;
let ipcRegistered = false;
let mainEntryPath = null;
let desktopSettings = null;
let registeredGlobalShortcut = null;
let protocolClientRegistered = false;
let rendererLoaded = false;
let rendererListenersReady = false;
let notificationSequence = 0;
let windowStateSaveTimer = null;
let trayPresentationKey = null;
let credentialVaultStore = null;
let updateRecoveryManager = null;
let recoveryOperationActive = false;
const activeBackendRequests = new Map();
const backendLogRedactors = new Map();
const pendingExternalIntents = [];
const notifiedRequestIds = new Set();
const grantedFileReads = new Map();
const screenshotGrants = new OneShotGrantStore();

let backendStatus = {
  state: "idle",
  message: "Backend ainda não iniciado.",
  managed: false,
  updatedAt: Date.now(),
};

function parsePort(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isInteger(parsed) && parsed >= 1024 && parsed <= 65535
    ? parsed
    : fallback;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function publicBackendStatus() {
  return { ...backendStatus };
}

function updateBackendStatus(state, message, managed = ownsBackendProcess) {
  backendStatus = {
    state,
    message,
    managed: Boolean(managed),
    updatedAt: Date.now(),
  };

  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(
      "aether:backend-status",
      publicBackendStatus(),
    );
  }
  refreshDesktopActivityIndicators();
}

function safeErrorMessage(error, fallback = "Ocorreu um erro interno.") {
  if (!error || typeof error.message !== "string") {
    return fallback;
  }

  const message = redactSensitiveText(error.message)
    .replace(/\s+/g, " ")
    .trim();
  return message.slice(0, 300) || fallback;
}

function sendToRenderer(channel, payload, target = mainWindow?.webContents) {
  if (!target || target.isDestroyed()) {
    return false;
  }
  target.send(channel, payload);
  return true;
}

function desktopSettingsPath() {
  return path.join(app.getPath("userData"), DESKTOP_SETTINGS_FILE);
}

function defaultDesktopSettings() {
  return {
    globalShortcut: DEFAULT_GLOBAL_SHORTCUT,
    closeToTray: true,
    notifications: true,
    notifyOnlyWhenBackground: true,
  };
}

function sanitiseDesktopSettings(value) {
  const defaults = defaultDesktopSettings();
  const source = value && typeof value === "object" ? value : {};
  let globalAccelerator = defaults.globalShortcut;
  try {
    globalAccelerator = normaliseAccelerator(source.globalShortcut);
  } catch {
    globalAccelerator = defaults.globalShortcut;
  }
  return {
    globalShortcut: globalAccelerator,
    closeToTray:
      typeof source.closeToTray === "boolean"
        ? source.closeToTray
        : defaults.closeToTray,
    notifications:
      typeof source.notifications === "boolean"
        ? source.notifications
        : defaults.notifications,
    notifyOnlyWhenBackground:
      typeof source.notifyOnlyWhenBackground === "boolean"
        ? source.notifyOnlyWhenBackground
        : defaults.notifyOnlyWhenBackground,
  };
}

function loadDesktopSettings() {
  if (desktopSettings) {
    return { ...desktopSettings };
  }

  try {
    const raw = fs.readFileSync(desktopSettingsPath(), "utf8");
    desktopSettings = sanitiseDesktopSettings(JSON.parse(raw));
  } catch (error) {
    if (error?.code !== "ENOENT") {
      console.warn(
        "[desktop] Configurações inválidas; usando padrões:",
        safeErrorMessage(error),
      );
    }
    desktopSettings = defaultDesktopSettings();
  }
  return { ...desktopSettings };
}

function writePrivateFile(destination, data) {
  const directory = path.dirname(destination);
  const temporary = path.join(
    directory,
    `.${path.basename(destination)}.${process.pid}.${crypto.randomBytes(6).toString("hex")}.tmp`,
  );
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  try {
    fs.writeFileSync(temporary, data, { flag: "wx", mode: 0o600 });
    fs.renameSync(temporary, destination);
    try {
      fs.chmodSync(destination, 0o600);
    } catch {
      // Windows ACLs are managed by the OS; chmod may be a no-op there.
    }
  } finally {
    try {
      fs.unlinkSync(temporary);
    } catch (error) {
      if (error?.code !== "ENOENT") {
        console.warn("[desktop] Falha ao remover arquivo temporário:", safeErrorMessage(error));
      }
    }
  }
}

function saveDesktopSettings() {
  const serialised = `${JSON.stringify(loadDesktopSettings(), null, 2)}\n`;
  writePrivateFile(desktopSettingsPath(), serialised);
}

function windowStatePath() {
  return path.join(app.getPath("userData"), WINDOW_STATE_FILE);
}

function currentDisplayWorkAreas() {
  const primary = screen.getPrimaryDisplay();
  const displays = screen.getAllDisplays();
  return [
    primary,
    ...displays.filter((display) => display.id !== primary.id),
  ].map((display) => display.workArea);
}

function loadWindowState() {
  let saved = {};
  try {
    saved = JSON.parse(fs.readFileSync(windowStatePath(), "utf8"));
  } catch (error) {
    if (error?.code !== "ENOENT") {
      console.warn(
        "[window] Estado anterior inválido; usando posição segura:",
        safeErrorMessage(error),
      );
    }
  }
  return constrainWindowState(saved, currentDisplayWorkAreas(), {
    defaultWidth: 1_440,
    defaultHeight: 920,
    minimumWidth: 900,
    minimumHeight: 640,
  });
}

function persistWindowState(window = mainWindow) {
  if (!window || window.isDestroyed()) {
    return false;
  }
  try {
    const bounds = window.getNormalBounds();
    const state = constrainWindowState(
      {
        ...bounds,
        maximized: window.isMaximized(),
      },
      currentDisplayWorkAreas(),
      {
        defaultWidth: 1_440,
        defaultHeight: 920,
        minimumWidth: 900,
        minimumHeight: 640,
      },
    );
    if (!state) {
      return false;
    }
    writePrivateFile(
      windowStatePath(),
      `${JSON.stringify(state, null, 2)}\n`,
    );
    return true;
  } catch (error) {
    console.warn(
      "[window] Não foi possível salvar posição e tamanho:",
      safeErrorMessage(error),
    );
    return false;
  }
}

function scheduleWindowStateSave(window = mainWindow) {
  if (windowStateSaveTimer) {
    clearTimeout(windowStateSaveTimer);
  }
  windowStateSaveTimer = setTimeout(() => {
    windowStateSaveTimer = null;
    persistWindowState(window);
  }, WINDOW_STATE_SAVE_DELAY_MS);
  windowStateSaveTimer.unref?.();
}

function clearWindowStateSaveTimer() {
  if (windowStateSaveTimer) {
    clearTimeout(windowStateSaveTimer);
    windowStateSaveTimer = null;
  }
}

function credentialVaultPath() {
  return path.join(app.getPath("userData"), CREDENTIAL_VAULT_FILE);
}

function getCredentialVault() {
  const expectedPath = credentialVaultPath();
  if (
    !credentialVaultStore ||
    credentialVaultStore.filePath !== expectedPath
  ) {
    credentialVaultStore = new CredentialVaultStore({
      filePath: expectedPath,
      environmentKeys: CREDENTIAL_ENVIRONMENT_KEYS,
      restrictedIntegrations: RESTRICTED_CREDENTIAL_INTEGRATIONS,
      safeStorage,
      platform: process.platform,
      writeFile: writePrivateFile,
      logger: console,
    });
  }
  return credentialVaultStore;
}

function publicCredentialStatus() {
  return {
    ...getCredentialVault().status(),
    restrictedIntegrations: RESTRICTED_CREDENTIAL_INTEGRATIONS,
    restartRequired: Boolean(backendProcess),
  };
}

function secureCredentialEnvironment() {
  return secureOnlyCredentialEnvironment(
    getCredentialVault().environment(),
    SECURE_ONLY_CREDENTIAL_ENVIRONMENT_KEYS,
  );
}

function inheritedBackendEnvironment() {
  return withoutManagedCredentialEnvironment(
    process.env,
    Object.values(CREDENTIAL_ENVIRONMENT_KEYS),
    ["AETHER_UPDATE_PUBLIC_KEY", "OPENWEATHER_API_KEY"],
  );
}

function updatePublicKeyPath() {
  return resolveProjectPath("build", UPDATE_PUBLIC_KEY_FILE);
}

function getUpdateRecoveryManager() {
  const userDataPath = app.getPath("userData");
  if (
    !updateRecoveryManager ||
    updateRecoveryManager.userDataPath !== path.resolve(userDataPath)
  ) {
    updateRecoveryManager = new UpdateRecoveryManager({
      userDataPath,
      appVersion: app.getVersion(),
      platform: process.platform,
      arch: process.arch,
      publicKeyEnvironment:
        app.isPackaged
          ? null
          : process.env.AETHER_UPDATE_PUBLIC_KEY || null,
      publicKeyPath: updatePublicKeyPath(),
      writeFile: writePrivateFile,
    });
  }
  return updateRecoveryManager;
}

async function runExclusiveRecoveryOperation(callback) {
  if (recoveryOperationActive) {
    throw new Error("Já existe uma operação de recuperação em andamento.");
  }
  recoveryOperationActive = true;
  try {
    return await callback();
  } finally {
    recoveryOperationActive = false;
  }
}

function currentScreenPermission() {
  if (process.platform !== "darwin") {
    return "not-applicable";
  }
  try {
    return systemPreferences.getMediaAccessStatus("screen");
  } catch {
    return "unknown";
  }
}

function getDesktopCapabilities() {
  const settings = loadDesktopSettings();
  return {
    tray: {
      available: typeof Tray === "function" && Boolean(resolveTrayImage()),
      active: Boolean(tray && !tray.isDestroyed()),
      closeToTray: Boolean(settings.closeToTray),
    },
    globalShortcut: {
      available: Boolean(globalShortcut?.register),
      configured: settings.globalShortcut,
      registered: registeredGlobalShortcut,
      active: Boolean(registeredGlobalShortcut),
    },
    notifications: {
      available: Boolean(Notification?.isSupported?.()),
      enabled: Boolean(settings.notifications),
      onlyWhenBackground: Boolean(settings.notifyOnlyWhenBackground),
    },
    filePicker: {
      files: true,
      folders: true,
      maximumFilesPerSelection: MAX_SELECTED_FILES,
      temporaryReadGrants: true,
      maximumAttachmentBytes: MAX_GRANTED_FILE_BYTES,
      maximumAttachmentTotalBytes: MAX_GRANTED_FILES_TOTAL_BYTES,
      readableExtensions: Object.keys(READABLE_ATTACHMENT_TYPES),
    },
    screenshot: {
      available: Boolean(desktopCapturer?.getSources && screen?.getAllDisplays),
      permission: currentScreenPermission(),
      explicitGestureGrantRequired: true,
      grantDurationMs: screenshotGrants.ttlMs,
      oneShotGrant: true,
      fullDisplay: true,
      regionCoordinates: true,
      interactiveRegionSelection: false,
      hideAetherWindowDuringCapture: true,
      note:
        "A região é recortada a partir de coordenadas fornecidas pela interface; não há sobreposição nativa de seleção.",
    },
    contextMenu: {
      selectedTextInsideAether: true,
      linksInsideAether: true,
      externalTextSelection: false,
      externalFileShellMenu:
        process.platform === "win32" && app.isPackaged
          ? "installer-only"
          : false,
    },
    deepLink: {
      supported: true,
      protocol: "aether",
      registered: protocolClientRegistered,
      secondInstance: true,
    },
    streaming: {
      available: true,
      protocol: "sse",
      endpoint: "/chat/stream",
      cancellable: true,
      eventChannel: "aether:chat-stream-event",
    },
    operationProgress: {
      available: true,
      eventChannel: "aether:operation-progress",
      simulated: false,
    },
    credentialVault: {
      ...publicCredentialStatus(),
      supportedKeys: Object.keys(CREDENTIAL_ENVIRONMENT_KEYS),
    },
    updateRecovery: getUpdateRecoveryManager().status(),
  };
}

function resolveProjectPath(...segments) {
  return path.join(app.getAppPath(), ...segments);
}

function resolvePythonDirectory() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "python")
    : resolveProjectPath("python");
}

function resolveRendererEntry() {
  const preferred = app.isPackaged
    ? resolveProjectPath("dist", "index.html")
    : resolveProjectPath("renderer", "index.html");
  const fallback = app.isPackaged
    ? resolveProjectPath("renderer", "index.html")
    : resolveProjectPath("dist", "index.html");

  if (fs.existsSync(preferred)) {
    return preferred;
  }
  if (fs.existsSync(fallback)) {
    return fallback;
  }
  throw new Error("Interface não encontrada em renderer/index.html ou dist/index.html.");
}

function resolveWindowIcon() {
  if (app.isPackaged) {
    if (process.platform === "win32") {
      return undefined;
    }
    const packagedIcon = path.join(process.resourcesPath, "icon.png");
    return fs.existsSync(packagedIcon) ? packagedIcon : undefined;
  }

  const extension = process.platform === "win32" ? "ico" : "png";
  const iconPath = resolveProjectPath("build", `icon.${extension}`);
  return fs.existsSync(iconPath) ? iconPath : undefined;
}

function ensurePackagedEnvironmentFile() {
  if (!app.isPackaged) {
    return;
  }

  const destination = path.join(app.getPath("userData"), ".env");
  const template = path.join(process.resourcesPath, ".env.example");
  if (fs.existsSync(destination) || !fs.existsSync(template)) {
    return;
  }

  try {
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.copyFileSync(template, destination, fs.constants.COPYFILE_EXCL);
  } catch (error) {
    if (error?.code !== "EEXIST") {
      console.warn(
        "[config] Não foi possível preparar o arquivo .env:",
        safeErrorMessage(error),
      );
    }
  }
}

function isTrustedRendererUrl(urlValue) {
  if (!mainEntryPath || typeof urlValue !== "string") {
    return false;
  }

  try {
    const expected = new URL(pathToFileURL(mainEntryPath).href);
    const candidate = new URL(urlValue);
    return (
      candidate.protocol === "file:" &&
      candidate.host === expected.host &&
      decodeURIComponent(candidate.pathname) ===
        decodeURIComponent(expected.pathname)
    );
  } catch {
    return false;
  }
}

function assertTrustedIpcSender(event) {
  const senderWindow = BrowserWindow.fromWebContents(event.sender);
  const senderUrl = event.senderFrame?.url || event.sender.getURL();
  if (
    !mainWindow ||
    senderWindow !== mainWindow ||
    event.sender !== mainWindow.webContents ||
    !isTrustedRendererUrl(senderUrl)
  ) {
    throw new Error("Origem IPC não autorizada.");
  }
}

function isSafeExternalUrl(urlValue) {
  if (typeof urlValue !== "string" || urlValue.length > 4096) {
    return false;
  }
  if (/[\r\n]|%0a|%0d/i.test(urlValue)) {
    return false;
  }

  try {
    const url = new URL(urlValue);
    if (url.protocol === "mailto:") {
      return Boolean(url.pathname && !url.username && !url.password);
    }
    return (
      (url.protocol === "https:" || url.protocol === "http:") &&
      !url.username &&
      !url.password
    );
  } catch {
    return false;
  }
}

function normaliseBackendPath(resourcePath) {
  if (
    typeof resourcePath !== "string" ||
    !resourcePath.startsWith("/") ||
    resourcePath.startsWith("//") ||
    resourcePath.length > 8192
  ) {
    throw new Error("Caminho de API inválido.");
  }

  const url = new URL(resourcePath, BACKEND_ORIGIN);
  if (
    url.origin !== BACKEND_ORIGIN ||
    url.username ||
    url.password ||
    url.hash
  ) {
    throw new Error("Caminho de API não permitido.");
  }
  return url;
}

function serialiseJsonBody(body) {
  if (body === undefined) {
    return null;
  }

  let json;
  try {
    json = JSON.stringify(body);
  } catch {
    throw new Error("O corpo da requisição precisa ser um valor JSON válido.");
  }

  if (json === undefined) {
    throw new Error("O corpo da requisição não pode ser serializado como JSON.");
  }
  if (Buffer.byteLength(json, "utf8") > MAX_REQUEST_BODY_BYTES) {
    throw new Error("O corpo da requisição excede o limite permitido.");
  }
  return json;
}

function parseBackendResponse(buffer, contentType) {
  const lowerContentType = String(contentType || "").toLowerCase();
  const isJson =
    lowerContentType.includes("application/json") ||
    lowerContentType.includes("+json");

  if (isJson) {
    if (buffer.length === 0) {
      return { data: null };
    }
    try {
      return { data: JSON.parse(buffer.toString("utf8")) };
    } catch {
      return {
        data: null,
        error: "O backend retornou JSON inválido.",
      };
    }
  }

  const isText =
    lowerContentType.startsWith("text/") ||
    lowerContentType.includes("application/xml") ||
    lowerContentType.includes("application/javascript");

  if (isText) {
    return { data: buffer.toString("utf8") };
  }

  return {
    data: buffer.toString("base64"),
    encoding: "base64",
  };
}

function emitOperationProgress(entry, phase, details = {}) {
  if (!entry?.requestId) {
    return;
  }
  let desktopProgress = normaliseProgressValue(details.progress);
  if (
    desktopProgress === null &&
    Number.isFinite(Number(details.bytesReceived)) &&
    Number.isFinite(Number(details.contentLength)) &&
    Number(details.contentLength) > 0
  ) {
    desktopProgress = normaliseProgressValue(
      Number(details.bytesReceived) / Number(details.contentLength),
    );
  }
  if (desktopProgress !== null) {
    entry.desktopProgress = desktopProgress;
  }
  sendToRenderer(
    "aether:operation-progress",
    {
      requestId: entry.requestId,
      kind: entry.kind || "backend",
      path: entry.resourcePath,
      phase,
      timestamp: Date.now(),
      cancellable: !["completed", "failed", "cancelled"].includes(phase),
      ...details,
    },
    entry.sender,
  );
  refreshDesktopActivityIndicators();
}

function removeActiveRequest(requestId, entry) {
  if (requestId && activeBackendRequests.get(requestId) === entry) {
    activeBackendRequests.delete(requestId);
    refreshDesktopActivityIndicators();
  }
}

function abortActiveRequest(requestId, reason = "cancelled") {
  const entry = activeBackendRequests.get(requestId);
  if (!entry) {
    return false;
  }
  entry.cancelled = true;
  entry.cancelReason = reason;
  emitOperationProgress(entry, "cancelling", {
    message: "Interrompendo a conexão local e avisando o núcleo.",
    cancellable: false,
  });
  try {
    entry.abort?.();
  } catch {
    // A conexão pode já ter sido encerrada pelo backend.
  }
  return true;
}

function abortRequestsForSender(sender) {
  for (const [requestId, entry] of activeBackendRequests) {
    if (!sender || entry.sender === sender) {
      abortActiveRequest(requestId, "renderer-disposed");
    }
  }
  if (sender?.id !== undefined) {
    screenshotGrants.revoke(sender.id);
  } else if (!sender) {
    screenshotGrants.clear();
  }
}

function requestBackend(resourcePath, options = {}, lifecycle = null) {
  const url = normaliseBackendPath(resourcePath);
  const method = String(options.method || "GET").toUpperCase();
  if (!ALLOWED_HTTP_METHODS.has(method)) {
    return Promise.reject(new Error("Método HTTP não permitido."));
  }

  if (method === "GET" && options.body !== undefined) {
    return Promise.reject(new Error("Requisições GET não aceitam corpo."));
  }

  const requestBody = serialiseJsonBody(options.body);
  const requestedTimeout = Number(options.timeoutMs);
  const timeoutMs = Number.isFinite(requestedTimeout)
    ? Math.min(Math.max(requestedTimeout, 1_000), 300_000)
    : 120_000;

  const headers = {
    Accept: "application/json, text/plain, */*",
    ...backendConfirmationHeaders(options.confirmed),
    ...backendProjectHeaders(options.projectId),
  };
  if (options.includeToken !== false) {
    headers["X-Aether-Token"] = API_TOKEN;
  }
  if (requestBody !== null) {
    headers["Content-Type"] = "application/json; charset=utf-8";
    headers["Content-Length"] = Buffer.byteLength(requestBody, "utf8");
  }

  return new Promise((resolve, reject) => {
    const entry = lifecycle?.requestId
      ? {
        requestId: lifecycle.requestId,
        resourcePath: url.pathname,
        sender: lifecycle.sender,
        kind: lifecycle.kind || "backend",
        startedAt: Date.now(),
        cancelled: false,
        abort: null,
      }
      : null;
    if (entry && activeBackendRequests.has(entry.requestId)) {
      reject(new Error("Já existe uma solicitação ativa com este identificador."));
      return;
    }

    let settled = false;
    const settle = (callback, value, phase, details = {}) => {
      if (settled) {
        return;
      }
      settled = true;
      removeActiveRequest(entry?.requestId, entry);
      if (entry) {
        emitOperationProgress(entry, entry.cancelled ? "cancelled" : phase, details);
      }
      callback(value);
    };
    const request = http.request(
      {
        protocol: "http:",
        hostname: BACKEND_HOST,
        port: BACKEND_PORT,
        method,
        path: `${url.pathname}${url.search}`,
        headers,
        timeout: timeoutMs,
      },
      (response) => {
        const chunks = [];
        let size = 0;
        let lastProgressAt = 0;
        const declaredLength = Number.parseInt(
          String(response.headers["content-length"] || ""),
          10,
        );

        response.on("data", (chunk) => {
          size += chunk.length;
          if (size > MAX_RESPONSE_BODY_BYTES) {
            response.destroy(new Error("A resposta do backend é grande demais."));
            return;
          }
          chunks.push(chunk);
          if (entry && Date.now() - lastProgressAt >= 100) {
            lastProgressAt = Date.now();
            emitOperationProgress(entry, "receiving", {
              bytesReceived: size,
              contentLength:
                Number.isFinite(declaredLength) && declaredLength >= 0
                  ? declaredLength
                  : null,
            });
          }
        });

        response.on("end", () => {
          const contentType = String(response.headers["content-type"] || "");
          const parsed = parseBackendResponse(Buffer.concat(chunks), contentType);
          const status = Number(response.statusCode || 0);
          const result = {
            ok: status >= 200 && status < 300 && !parsed.error,
            status,
            contentType,
            ...parsed,
          };
          settle(
            resolve,
            result,
            result.ok ? "completed" : "failed",
            {
              status,
              bytesReceived: size,
              message: result.ok
                ? "Operação concluída."
                : "O backend recusou a operação.",
            },
          );
        });

        response.on("error", (error) => {
          settle(
            reject,
            error,
            "failed",
            { message: safeErrorMessage(error) },
          );
        });
      },
    );
    if (entry) {
      entry.abort = () => {
        request.destroy(
          Object.assign(new Error("Solicitação cancelada."), {
            code: "AETHER_CANCELLED",
          }),
        );
      };
      activeBackendRequests.set(entry.requestId, entry);
      emitOperationProgress(entry, "started", {
        message: "Solicitação enviada ao núcleo local.",
      });
    }

    request.on("timeout", () => {
      request.destroy(new Error("Tempo limite da requisição ao backend excedido."));
    });
    request.on("error", (error) => {
      settle(
        reject,
        error,
        error?.code === "AETHER_CANCELLED" ? "cancelled" : "failed",
        {
          message:
            error?.code === "AETHER_CANCELLED"
              ? "Solicitação cancelada."
              : safeErrorMessage(error),
        },
      );
    });

    if (requestBody !== null) {
      request.write(requestBody);
    }
    request.end();
  });
}

function startBackendChatStream(payload, sender) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return Promise.reject(new Error("Conteúdo de streaming inválido."));
  }
  const requestId = isValidRequestId(payload.request_id)
    ? payload.request_id
    : crypto.randomUUID();
  const requestPayload = {
    ...payload,
    request_id: requestId,
  };
  const requestBody = serialiseJsonBody(requestPayload);
  if (activeBackendRequests.has(requestId)) {
    return Promise.reject(
      new Error("Já existe uma solicitação ativa com este identificador."),
    );
  }

  return new Promise((resolve, reject) => {
    const entry = {
      requestId,
      resourcePath: "/chat/stream",
      sender,
      kind: "chat-stream",
      startedAt: Date.now(),
      cancelled: false,
      terminalType: null,
      abort: null,
    };
    let settled = false;
    let responseStatus = 0;
    let terminalReceived = false;
    let errorBuffer = Buffer.alloc(0);
    const settle = (callback, value, phase, message) => {
      if (settled) {
        return;
      }
      settled = true;
      removeActiveRequest(requestId, entry);
      emitOperationProgress(
        entry,
        entry.cancelled ? "cancelled" : phase,
        { message },
      );
      callback(value);
    };
    const cancellationResult = () => ({
      ok: false,
      cancelled: true,
      requestId,
      status: responseStatus,
      terminalType: entry.terminalType || "cancelled",
    });
    const settleTransportError = (error) => {
      if (entry.cancelled || error?.code === "AETHER_CANCELLED") {
        settle(
          resolve,
          cancellationResult(),
          "cancelled",
          "Streaming cancelado.",
        );
        return;
      }
      settle(
        reject,
        error,
        "failed",
        safeErrorMessage(error),
      );
    };
    const emitStreamEvent = (parsed) => {
      const data = parsed.data;
      const eventType = cleanText(
        data && typeof data === "object" ? data.type : parsed.event,
        80,
        "message",
      );
      if (
        data &&
        typeof data === "object" &&
        data.request_id !== undefined &&
        data.request_id !== requestId
      ) {
        throw new Error("O backend enviou um evento para outra solicitação.");
      }

      sendToRenderer(
        "aether:chat-stream-event",
        {
          requestId,
          type: eventType,
          event: parsed.event,
          id: parsed.id,
          data,
          timestamp: Date.now(),
        },
        sender,
      );

      if (["accepted", "status", "action", "operation"].includes(eventType)) {
        const progress = Number(data?.progress);
        emitOperationProgress(entry, eventType, {
          message: cleanText(
            data?.message || data?.detail || data?.stage,
            300,
            "Atualização recebida do núcleo.",
          ),
          ...(Number.isFinite(progress)
            ? { progress: Math.min(Math.max(progress, 0), 100) }
            : {}),
          ...(data?.stage
            ? { stage: cleanText(data.stage, 100) }
            : {}),
        });
      }

      if (TERMINAL_STREAM_EVENT_TYPES.has(eventType)) {
        terminalReceived = true;
        entry.terminalType = eventType;
        if (eventType === "cancelled") {
          entry.cancelled = true;
        }
        maybeNotifyStreamCompletion(entry, data, eventType);
      }
    };
    const parser = createSseParser(emitStreamEvent);

    const request = http.request(
      {
        protocol: "http:",
        hostname: BACKEND_HOST,
        port: BACKEND_PORT,
        method: "POST",
        path: "/chat/stream",
        headers: {
          Accept: "text/event-stream",
          "Cache-Control": "no-cache",
          "Content-Type": "application/json; charset=utf-8",
          "Content-Length": Buffer.byteLength(requestBody, "utf8"),
          "X-Aether-Token": API_TOKEN,
        },
        timeout: 300_000,
      },
      (response) => {
        responseStatus = Number(response.statusCode || 0);
        const contentType = String(response.headers["content-type"] || "")
          .toLowerCase();
        const successful =
          responseStatus >= 200 &&
          responseStatus < 300 &&
          contentType.includes("text/event-stream");

        response.on("data", (chunk) => {
          if (!successful) {
            if (errorBuffer.length < 65_536) {
              errorBuffer = Buffer.concat([
                errorBuffer,
                chunk.subarray(0, 65_536 - errorBuffer.length),
              ]);
            }
            return;
          }
          try {
            parser.push(chunk);
          } catch (error) {
            response.destroy(error);
          }
        });

        response.on("end", () => {
          if (!successful) {
            const parsed = parseBackendResponse(
              errorBuffer,
              response.headers["content-type"],
            );
            const message = cleanText(
              parsed.data?.detail ||
                parsed.data?.error ||
                parsed.data ||
                `Erro HTTP ${responseStatus}.`,
              300,
              `Erro HTTP ${responseStatus}.`,
            );
            settle(
              reject,
              new Error(message),
              "failed",
              message,
            );
            return;
          }

          try {
            parser.finish();
          } catch (error) {
            settle(
              reject,
              error,
              "failed",
              safeErrorMessage(error),
            );
            return;
          }

          if (!terminalReceived && !entry.cancelled) {
            const error = new Error(
              "O streaming terminou sem um evento final confirmado.",
            );
            settle(reject, error, "failed", error.message);
            return;
          }
          settle(
            resolve,
            {
              ok: !entry.cancelled && entry.terminalType === "done",
              cancelled: entry.cancelled,
              requestId,
              status: responseStatus,
              terminalType: entry.terminalType,
            },
            entry.cancelled
              ? "cancelled"
              : entry.terminalType === "done"
                ? "completed"
                : "failed",
            entry.cancelled
              ? "Streaming cancelado."
              : entry.terminalType === "done"
                ? "Streaming concluído."
                : "O streaming terminou com erro.",
          );
        });
        response.on("error", (error) => {
          settleTransportError(error);
        });
      },
    );

    entry.abort = () => {
      request.destroy(
        Object.assign(new Error("Streaming cancelado."), {
          code: "AETHER_CANCELLED",
        }),
      );
    };
    activeBackendRequests.set(requestId, entry);
    emitOperationProgress(entry, "started", {
      message: "Streaming conectado ao núcleo local.",
    });

    request.on("timeout", () => {
      request.destroy(new Error("O streaming ficou inativo por tempo demais."));
    });
    request.on("error", (error) => {
      settleTransportError(error);
    });
    request.write(requestBody);
    request.end();
  });
}

async function probeBackend(includeToken = true) {
  try {
    const result = await requestBackend("/health", {
      method: "GET",
      timeoutMs: 1_500,
      includeToken,
    });
    const service = result.data?.service;
    const version = result.data?.version;
    const expectedMajor = Number.parseInt(app.getVersion().split(".")[0], 10);
    const backendMajor =
      typeof version === "string"
        ? Number.parseInt(version.split(".")[0], 10)
        : Number.NaN;
    const identityMatches = service === "aether-core";
    const versionMatches =
      Number.isInteger(backendMajor) &&
      Number.isInteger(expectedMajor) &&
      backendMajor === expectedMajor;

    return {
      reachable: true,
      ready:
        result.ok &&
        result.data?.ok === true &&
        identityMatches &&
        versionMatches,
      status: result.status,
      identityMatches,
      versionMatches,
      version: typeof version === "string" ? version : null,
    };
  } catch {
    return {
      reachable: false,
      ready: false,
      status: 0,
      identityMatches: false,
      versionMatches: false,
      version: null,
    };
  }
}

async function probeBackendAuthentication() {
  try {
    const result = await requestBackend("/capabilities", {
      method: "GET",
      timeoutMs: 1_500,
      includeToken: true,
    });
    const expectedMajor = Number.parseInt(app.getVersion().split(".")[0], 10);
    const backendMajor =
      typeof result.data?.version === "string"
        ? Number.parseInt(result.data.version.split(".")[0], 10)
        : Number.NaN;
    return (
      result.ok &&
      result.data?.ok === true &&
      Number.isInteger(expectedMajor) &&
      backendMajor === expectedMajor
    );
  } catch {
    return false;
  }
}

function pythonCandidates() {
  const candidates = [];
  const configured = process.env.JARVIS_PYTHON?.trim();
  if (configured) {
    candidates.push({ command: configured, prefixArgs: [], configured: true });
  }

  if (!app.isPackaged) {
    const localVirtualEnv = resolveProjectPath(
      ".venv",
      process.platform === "win32" ? "Scripts" : "bin",
      process.platform === "win32" ? "python.exe" : "python",
    );
    candidates.push({ command: localVirtualEnv, prefixArgs: [] });
  }

  const virtualEnv = process.env.VIRTUAL_ENV?.trim();
  if (virtualEnv) {
    const executable = path.join(
      virtualEnv,
      process.platform === "win32" ? "Scripts" : "bin",
      process.platform === "win32" ? "python.exe" : "python",
    );
    candidates.push({ command: executable, prefixArgs: [] });
  }

  if (process.platform === "win32") {
    candidates.push(
      { command: "py", prefixArgs: ["-3"] },
      { command: "python", prefixArgs: [] },
      { command: "python3", prefixArgs: [] },
    );
  } else {
    candidates.push(
      { command: "python3", prefixArgs: [] },
      { command: "python", prefixArgs: [] },
    );
  }

  return candidates;
}

function findPython() {
  for (const candidate of pythonCandidates()) {
    const check = spawnSync(
      candidate.command,
      [
        ...candidate.prefixArgs,
        "-c",
        "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)",
      ],
      {
        windowsHide: true,
        stdio: "ignore",
        shell: false,
        timeout: 3_000,
      },
    );

    if (!check.error && check.status === 0) {
      return candidate;
    }
    if (candidate.configured) {
      throw new Error(
        "O executável definido em JARVIS_PYTHON não pôde ser iniciado.",
      );
    }
  }

  throw new Error(
    "Python 3.10 ou superior não foi encontrado. Instale o Python ou configure JARVIS_PYTHON.",
  );
}

function openBackendLog() {
  try {
    backendLogRedactors.clear();
    const logsDirectory = path.join(app.getPath("userData"), "logs");
    fs.mkdirSync(logsDirectory, { recursive: true });
    backendLogStream = fs.createWriteStream(
      path.join(logsDirectory, "backend.log"),
      { flags: "a", encoding: "utf8" },
    );
    backendLogStream.on("error", (error) => {
      console.warn(
        "[backend] Falha ao gravar o log:",
        safeErrorMessage(error),
      );
      backendLogStream = null;
    });
    backendLogStream.write(
      `\n[${new Date().toISOString()}] Iniciando backend Aether\n`,
    );
  } catch (error) {
    backendLogStream = null;
    console.warn("[backend] Não foi possível abrir o arquivo de log:", safeErrorMessage(error));
  }
}

function appendBackendLogRecord(source, record) {
  if (!backendLogStream || backendLogStream.destroyed) {
    return;
  }
  backendLogStream.write(
    `[${new Date().toISOString()}] [${source}] ${record}`,
  );
}

function writeBackendLog(source, chunk) {
  if (!backendLogStream || backendLogStream.destroyed) {
    return;
  }
  const label = String(source || "backend").slice(0, 40);
  let redactor = backendLogRedactors.get(label);
  if (!redactor) {
    redactor = createRedactingLineBuffer(
      (record) => appendBackendLogRecord(label, record),
    );
    backendLogRedactors.set(label, redactor);
  }
  redactor.push(chunk);
}

function flushBackendLogRedactors() {
  for (const redactor of backendLogRedactors.values()) {
    redactor.finish();
  }
  backendLogRedactors.clear();
}

function closeBackendLog() {
  if (backendLogStream && !backendLogStream.destroyed) {
    flushBackendLogRedactors();
    backendLogStream.end();
  } else {
    backendLogRedactors.clear();
  }
  backendLogStream = null;
}

async function stopOwnedBackend() {
  const child = backendProcess;
  const shouldStop = Boolean(child && ownsBackendProcess);

  backendProcess = null;
  ownsBackendProcess = false;

  if (!shouldStop || child.exitCode !== null) {
    closeBackendLog();
    return;
  }
  if (!Number.isInteger(child.pid)) {
    closeBackendLog();
    return;
  }

  if (process.platform === "win32") {
    await new Promise((resolve) => {
      const windowsDirectory =
        process.env.SystemRoot || process.env.WINDIR || "C:\\Windows";
      const systemTaskkill = path.join(
        windowsDirectory,
        "System32",
        "taskkill.exe",
      );
      const killer = spawn(
        fs.existsSync(systemTaskkill) ? systemTaskkill : "taskkill",
        ["/pid", String(child.pid), "/T", "/F"],
        {
          windowsHide: true,
          stdio: "ignore",
          shell: false,
        },
      );
      const finish = () => resolve();
      killer.once("error", finish);
      killer.once("exit", finish);
      setTimeout(finish, 3_000).unref();
    });
  } else {
    const exited = new Promise((resolve) => child.once("exit", resolve));
    child.kill("SIGTERM");
    await Promise.race([exited, delay(2_500)]);
    if (child.exitCode === null) {
      child.kill("SIGKILL");
    }
  }

  closeBackendLog();
}

async function startBackendInternal() {
  updateBackendStatus("starting", "Preparando o núcleo local da Aether…", false);

  const existing = await probeBackend(false);
  if (existing.ready) {
    if (!app.isPackaged && await probeBackendAuthentication()) {
      updateBackendStatus(
        "ready",
        "Backend local conectado.",
        false,
      );
      return publicBackendStatus();
    }
    throw new Error(
      `Já existe outra instância da Aether na porta ${BACKEND_PORT}.`,
    );
  }
  if (existing.reachable) {
    if (existing.identityMatches && !existing.versionMatches) {
      throw new Error(
        `Existe um backend Aether incompatível na porta ${BACKEND_PORT}.`,
      );
    }
    throw new Error(
      `A porta ${BACKEND_PORT} já está ocupada por outro serviço local.`,
    );
  }

  if (backendProcess) {
    await stopOwnedBackend();
  }

  const pythonDirectory = resolvePythonDirectory();
  if (!fs.existsSync(path.join(pythonDirectory, "jarvis", "__main__.py"))) {
    throw new Error("Os arquivos do backend Python não foram encontrados.");
  }

  const basePython = findPython();
  const python = app.isPackaged
    ? await preparePackagedPythonRuntime({
      basePython,
      pythonDirectory,
      userDataDirectory: app.getPath("userData"),
      onStatus: (message) => {
        updateBackendStatus("starting", message, false);
      },
    })
    : basePython;
  const userEnvFile = path.join(app.getPath("userData"), ".env");
  const projectEnvFile = resolveProjectPath(".env");
  const environmentFile = process.env.JARVIS_ENV_FILE ||
    (app.isPackaged ? userEnvFile : projectEnvFile);
  const pythonPath = [pythonDirectory, process.env.PYTHONPATH]
    .filter(Boolean)
    .join(path.delimiter);

  openBackendLog();

  let spawnFailure = null;
  const child = spawn(
    python.command,
    [...python.prefixArgs, "-m", "jarvis"],
    {
      cwd: pythonDirectory,
      env: {
        ...inheritedBackendEnvironment(),
        ...secureCredentialEnvironment(),
        AETHER_API_TOKEN: API_TOKEN,
        AETHER_DESKTOP: "1",
        AETHER_VAULT_ENFORCED: "1",
        JARVIS_API_URL: BACKEND_ORIGIN,
        JARVIS_DATA_DIR:
          process.env.JARVIS_DATA_DIR ||
          path.join(app.getPath("userData"), "data"),
        JARVIS_ENV_FILE: environmentFile,
        JARVIS_HOST: BACKEND_HOST,
        JARVIS_PORT: String(BACKEND_PORT),
        PYTHONPATH: pythonPath,
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
        PYTHONUTF8: "1",
      },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      shell: false,
    },
  );

  backendProcess = child;
  ownsBackendProcess = true;

  child.stdout?.on("data", (chunk) => writeBackendLog("stdout", chunk));
  child.stderr?.on("data", (chunk) => writeBackendLog("stderr", chunk));
  child.once("error", (error) => {
    spawnFailure = error;
    writeBackendLog("error", `${safeErrorMessage(error)}\n`);
  });
  child.once("close", (code, signal) => {
    writeBackendLog(
      "exit",
      `Processo finalizado (código=${code ?? "null"}, sinal=${signal ?? "null"}).\n`,
    );
    if (backendProcess !== child) {
      return;
    }
    backendProcess = null;
    ownsBackendProcess = false;
    closeBackendLog();
    if (!quitting) {
      updateBackendStatus(
        "offline",
        "O backend local foi encerrado inesperadamente.",
        false,
      );
    }
  });

  const deadline = Date.now() + BACKEND_START_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (spawnFailure) {
      throw new Error(`Falha ao iniciar o Python: ${safeErrorMessage(spawnFailure)}`);
    }
    if (child.exitCode !== null) {
      throw new Error(
        `O backend foi encerrado durante a inicialização (código ${child.exitCode}).`,
      );
    }

    const health = await probeBackend(true);
    if (health.ready && await probeBackendAuthentication()) {
      updateBackendStatus(
        "ready",
        "Backend local protegido e pronto.",
        true,
      );
      return publicBackendStatus();
    }
    await delay(300);
  }

  await stopOwnedBackend();
  throw new Error("O backend não respondeu dentro do tempo esperado.");
}

function ensureBackend() {
  if (backendStartPromise) {
    return backendStartPromise;
  }

  backendStartPromise = startBackendInternal()
    .catch((error) => {
      updateBackendStatus(
        "offline",
        safeErrorMessage(error, "Não foi possível iniciar o backend."),
        false,
      );
      return publicBackendStatus();
    })
    .finally(() => {
      backendStartPromise = null;
    });

  return backendStartPromise;
}

function desktopActivityState() {
  return selectDesktopActivityState(
    backendStatus.state,
    activeBackendRequests.size,
  );
}

function desktopActivityLabel(state = desktopActivityState()) {
  return {
    online: "Online",
    working: "Trabalhando",
    offline: "Offline",
  }[state] || "Offline";
}

function trayAssetsPath(...segments) {
  return app.isPackaged
    ? path.join(process.resourcesPath, "tray", ...segments)
    : resolveProjectPath("build", "tray", ...segments);
}

function resolveTrayImage(state = desktopActivityState()) {
  const safeState = ["online", "working", "offline"].includes(state)
    ? state
    : "offline";
  const templateName =
    `Aether${safeState[0].toUpperCase()}${safeState.slice(1)}Template.png`;
  const themeName = nativeTheme.shouldUseDarkColors ? "dark" : "light";
  const candidates = process.platform === "darwin"
    ? [trayAssetsPath(templateName)]
    : [
      trayAssetsPath(`tray-${themeName}-${safeState}.png`),
      app.isPackaged
        ? path.join(process.resourcesPath, "icon.png")
        : resolveProjectPath("build", "icon.png"),
    ];
  for (const candidate of candidates.filter(Boolean)) {
    if (!fs.existsSync(candidate)) {
      continue;
    }
    const image = nativeImage.createFromPath(candidate);
    if (!image.isEmpty()) {
      if (process.platform === "darwin") {
        image.setTemplateImage(true);
      }
      return image;
    }
  }
  return null;
}

function resolveNotificationImage() {
  const candidate = app.isPackaged
    ? path.join(process.resourcesPath, "icon.png")
    : resolveProjectPath("build", "icon.png");
  if (!fs.existsSync(candidate)) {
    return null;
  }
  const image = nativeImage.createFromPath(candidate);
  return image.isEmpty() ? null : image;
}

function updateWindowProgress() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  const entries = [...activeBackendRequests.values()];
  if (entries.length === 0) {
    mainWindow.setProgressBar(-1);
    return;
  }
  const progressValues = entries
    .map((entry) => normaliseProgressValue(entry.desktopProgress))
    .filter((value) => value !== null);
  if (progressValues.length === 0) {
    mainWindow.setProgressBar(2);
    return;
  }
  mainWindow.setProgressBar(Math.max(...progressValues));
}

function refreshDesktopActivityIndicators() {
  const state = desktopActivityState();
  const theme = nativeTheme.shouldUseDarkColors ? "dark" : "light";
  const presentationKey = `${state}:${theme}`;

  if (
    tray &&
    !tray.isDestroyed() &&
    trayPresentationKey !== presentationKey
  ) {
    const image = resolveTrayImage(state);
    if (image) {
      tray.setImage(image);
    }
    tray.setToolTip(`Aether Desktop AI — ${desktopActivityLabel(state)}`);
    trayPresentationKey = presentationKey;
    rebuildTrayMenu();
  }
  updateWindowProgress();
}

function showMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return createMainWindow().then((window) => {
      window.show();
      window.focus();
      flushExternalIntents();
      return window;
    });
  }
  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  mainWindow.show();
  mainWindow.focus();
  flushExternalIntents();
  return Promise.resolve(mainWindow);
}

function sendDesktopAction(name) {
  return showMainWindow()
    .then(() => sendShortcut(name))
    .catch((error) => {
      console.warn("[desktop] Não foi possível abrir a janela:", safeErrorMessage(error));
    });
}

function rebuildTrayMenu() {
  if (!tray || tray.isDestroyed()) {
    return;
  }
  const settings = loadDesktopSettings();
  tray.setContextMenu(Menu.buildFromTemplate([
    {
      label: `Estado: ${desktopActivityLabel()}`,
      enabled: false,
    },
    { type: "separator" },
    {
      label: "Abrir Aether",
      click: () => void showMainWindow(),
    },
    {
      label: "Nova conversa",
      click: () => void sendDesktopAction("new-chat"),
    },
    {
      label: "Configurações",
      click: () => void sendDesktopAction("open-settings"),
    },
    { type: "separator" },
    {
      label: "Fechar para a bandeja",
      type: "checkbox",
      checked: Boolean(settings.closeToTray),
      click: (menuItem) => {
        const previous = loadDesktopSettings();
        desktopSettings = {
          ...previous,
          closeToTray: Boolean(menuItem.checked),
        };
        try {
          saveDesktopSettings();
        } catch (error) {
          desktopSettings = previous;
          console.warn(
            "[tray] Não foi possível salvar a preferência:",
            safeErrorMessage(error),
          );
          rebuildTrayMenu();
          return;
        }
        sendToRenderer("aether:desktop-settings-changed", {
          ...desktopSettings,
        });
        rebuildTrayMenu();
      },
    },
    { type: "separator" },
    {
      label: "Sair",
      click: () => {
        app.quit();
      },
    },
  ]));
}

function createTray() {
  if (tray && !tray.isDestroyed()) {
    return true;
  }
  const image = resolveTrayImage();
  if (!image) {
    return false;
  }
  try {
    tray = new Tray(image);
    trayPresentationKey = null;
    tray.on("click", () => void showMainWindow());
    tray.on("double-click", () => void showMainWindow());
    refreshDesktopActivityIndicators();
    return true;
  } catch (error) {
    tray = null;
    console.warn("[tray] Bandeja indisponível:", safeErrorMessage(error));
    return false;
  }
}

function activateGlobalShortcut(accelerator) {
  const requested = normaliseAccelerator(accelerator);
  if (requested === registeredGlobalShortcut) {
    return {
      ok: true,
      accelerator: registeredGlobalShortcut,
      registered: Boolean(registeredGlobalShortcut),
    };
  }

  if (requested === null) {
    if (registeredGlobalShortcut) {
      globalShortcut.unregister(registeredGlobalShortcut);
    }
    registeredGlobalShortcut = null;
    return { ok: true, accelerator: null, registered: false };
  }

  let registered = false;
  try {
    registered = globalShortcut.register(requested, () => {
      void showMainWindow().then(() => {
        sendToRenderer("aether:external-intent", {
          type: "focus-composer",
          source: "global-shortcut",
        });
        sendShortcut("focus-composer");
      });
    });
  } catch (error) {
    return {
      ok: false,
      accelerator: registeredGlobalShortcut,
      registered: Boolean(registeredGlobalShortcut),
      error: safeErrorMessage(error, "Não foi possível registrar o atalho."),
    };
  }
  if (!registered) {
    return {
      ok: false,
      accelerator: registeredGlobalShortcut,
      registered: Boolean(registeredGlobalShortcut),
      error: "A combinação já está em uso por outro aplicativo.",
    };
  }

  if (registeredGlobalShortcut) {
    globalShortcut.unregister(registeredGlobalShortcut);
  }
  registeredGlobalShortcut = requested;
  return { ok: true, accelerator: requested, registered: true };
}

function applyInitialDesktopSettings() {
  const settings = loadDesktopSettings();
  const shortcutResult = activateGlobalShortcut(settings.globalShortcut);
  if (!shortcutResult.ok) {
    console.warn("[shortcut]", shortcutResult.error);
  }
  createTray();
}

function updateDesktopSettings(patch) {
  if (!patch || typeof patch !== "object" || Array.isArray(patch)) {
    throw new Error("Configurações de desktop inválidas.");
  }
  const current = loadDesktopSettings();
  const next = { ...current };
  for (const key of [
    "closeToTray",
    "notifications",
    "notifyOnlyWhenBackground",
  ]) {
    if (Object.hasOwn(patch, key)) {
      if (typeof patch[key] !== "boolean") {
        throw new Error(`A configuração ${key} precisa ser booleana.`);
      }
      next[key] = patch[key];
    }
  }
  const shortcutChanged = Object.hasOwn(patch, "globalShortcut");
  const requestedShortcut = shortcutChanged
    ? normaliseAccelerator(patch.globalShortcut)
    : current.globalShortcut;
  if (shortcutChanged) {
    const result = activateGlobalShortcut(requestedShortcut);
    if (!result.ok) {
      return {
        ok: false,
        settings: current,
        shortcut: result,
      };
    }
    next.globalShortcut = requestedShortcut;
  }

  desktopSettings = sanitiseDesktopSettings(next);
  try {
    saveDesktopSettings();
  } catch (error) {
    desktopSettings = { ...current };
    if (shortcutChanged) {
      const rollback = activateGlobalShortcut(current.globalShortcut);
      if (!rollback.ok) {
        console.warn(
          "[shortcut] Não foi possível restaurar o atalho anterior:",
          rollback.error,
        );
      }
    }
    throw error;
  }
  rebuildTrayMenu();
  sendToRenderer("aether:desktop-settings-changed", {
    ...desktopSettings,
  });
  return {
    ok: true,
    settings: { ...desktopSettings },
    shortcut: {
      accelerator: registeredGlobalShortcut,
      registered: Boolean(registeredGlobalShortcut),
    },
  };
}

function showDesktopNotification(payload = {}) {
  const settings = loadDesktopSettings();
  if (
    !settings.notifications ||
    !Notification?.isSupported?.() ||
    (
      settings.notifyOnlyWhenBackground &&
      mainWindow &&
      !mainWindow.isDestroyed() &&
      mainWindow.isFocused()
    )
  ) {
    return { shown: false, reason: "disabled-or-focused" };
  }

  const title = cleanText(
    payload.title,
    100,
    "Aether Desktop AI",
  );
  const body = cleanText(
    payload.body,
    MAX_NOTIFICATION_TEXT,
    "A operação foi concluída.",
  );
  const notification = new Notification({
    title,
    body,
    silent: Boolean(payload.silent),
    icon: resolveNotificationImage() || undefined,
  });
  notification.on("click", () => void showMainWindow());
  notification.show();
  notificationSequence += 1;
  return { shown: true, id: `notification-${notificationSequence}` };
}

function maybeNotifyStreamCompletion(entry, data, eventType) {
  if (notifiedRequestIds.has(entry.requestId)) {
    return;
  }
  notifiedRequestIds.add(entry.requestId);
  if (notifiedRequestIds.size > 500) {
    const first = notifiedRequestIds.values().next().value;
    notifiedRequestIds.delete(first);
  }
  const title =
    eventType === "done"
      ? "Aether concluiu a tarefa"
      : eventType === "cancelled"
        ? "Tarefa cancelada"
        : "Aether encontrou um erro";
  const body = cleanText(
    data?.message || data?.detail,
    MAX_NOTIFICATION_TEXT,
    eventType === "done"
      ? "A resposta está pronta."
      : eventType === "cancelled"
        ? "A operação foi interrompida."
        : "Abra o Aether para ver os detalhes.",
  );
  showDesktopNotification({ title, body });
}

function selectedPathMetadata(filePath) {
  try {
    const stat = fs.statSync(filePath);
    return {
      path: filePath,
      name: path.basename(filePath),
      kind: stat.isDirectory() ? "folder" : stat.isFile() ? "file" : "other",
      size: stat.isFile() ? stat.size : null,
      modifiedAt: stat.mtimeMs,
    };
  } catch {
    return null;
  }
}

function purgeExpiredFileGrants(now = Date.now()) {
  for (const [filePath, grant] of grantedFileReads) {
    if (!grant || grant.expiresAt <= now) {
      grantedFileReads.delete(filePath);
    }
  }
  while (grantedFileReads.size > 256) {
    const oldest = grantedFileReads.keys().next().value;
    grantedFileReads.delete(oldest);
  }
}

function canonicalGrantedFile(filePath) {
  if (typeof filePath !== "string" || !filePath || filePath.length > 32_768) {
    throw new Error("Caminho de arquivo inválido.");
  }
  const canonicalPath = fs.realpathSync.native
    ? fs.realpathSync.native(filePath)
    : fs.realpathSync(filePath);
  const stat = fs.statSync(canonicalPath);
  if (!stat.isFile()) {
    throw new Error("O item selecionado não é um arquivo regular.");
  }
  return { canonicalPath, stat };
}

function fileIdentity(stat) {
  return {
    dev: Number(stat.dev),
    ino: Number(stat.ino),
    size: Number(stat.size),
    mtimeMs: Number(stat.mtimeMs),
  };
}

function sameFileIdentity(left, right) {
  if (!left || !right) {
    return false;
  }
  return (
    left.dev === Number(right.dev) &&
    left.ino === Number(right.ino) &&
    left.size === Number(right.size) &&
    left.mtimeMs === Number(right.mtimeMs)
  );
}

function grantSelectedFile(filePath, source = "picker") {
  try {
    const { canonicalPath, stat } = canonicalGrantedFile(filePath);
    const extension = path.extname(canonicalPath).toLowerCase();
    grantedFileReads.set(canonicalPath, {
      source,
      expiresAt: Date.now() + FILE_GRANT_TTL_MS,
      identity: fileIdentity(stat),
    });
    purgeExpiredFileGrants();
    return {
      path: canonicalPath,
      name: path.basename(canonicalPath),
      kind: "file",
      size: stat.size,
      modifiedAt: stat.mtimeMs,
      readableAttachment: Boolean(READABLE_ATTACHMENT_TYPES[extension]),
      withinReadLimit: stat.size <= MAX_GRANTED_FILE_BYTES,
    };
  } catch {
    return null;
  }
}

function grantExternalIntentFiles(intent) {
  if (intent?.type !== "ask-file" || !Array.isArray(intent.paths)) {
    return intent;
  }
  const files = intent.paths
    .slice(0, MAX_GRANTED_FILES_PER_READ)
    .map((filePath) => grantSelectedFile(filePath, "external-intent"))
    .filter(Boolean);
  if (!files.length) {
    return null;
  }
  return {
    ...intent,
    paths: files.map((file) => file.path),
    files,
  };
}

function readGrantedFiles(rawPaths) {
  if (!Array.isArray(rawPaths) || rawPaths.length === 0) {
    throw new Error("Selecione ao menos um arquivo.");
  }
  if (rawPaths.length > MAX_GRANTED_FILES_PER_READ) {
    throw new Error(
      `No máximo ${MAX_GRANTED_FILES_PER_READ} arquivos podem ser lidos por vez.`,
    );
  }
  purgeExpiredFileGrants();
  const files = [];
  let totalBytes = 0;
  for (const rawPath of rawPaths) {
    let resolved;
    try {
      resolved = canonicalGrantedFile(rawPath);
    } catch {
      throw new Error("Um arquivo selecionado não está mais disponível.");
    }
    const grant = grantedFileReads.get(resolved.canonicalPath);
    if (!grant || grant.expiresAt <= Date.now()) {
      throw new Error(
        "A permissão temporária deste arquivo expirou. Selecione-o novamente.",
      );
    }
    if (!sameFileIdentity(grant.identity, resolved.stat)) {
      grantedFileReads.delete(resolved.canonicalPath);
      throw new Error(
        "O arquivo mudou desde a seleção. Selecione-o novamente.",
      );
    }
    const extension = path.extname(resolved.canonicalPath).toLowerCase();
    const contentType = READABLE_ATTACHMENT_TYPES[extension];
    if (!contentType) {
      throw new Error(`O formato ${extension || "sem extensão"} não pode ser anexado.`);
    }
    if (resolved.stat.size > MAX_GRANTED_FILE_BYTES) {
      throw new Error("Um arquivo excede o limite seguro de 10 MiB.");
    }
    totalBytes += resolved.stat.size;
    if (totalBytes > MAX_GRANTED_FILES_TOTAL_BYTES) {
      throw new Error("Os arquivos selecionados excedem o limite total de 20 MiB.");
    }
    let descriptor;
    let bytes;
    try {
      descriptor = fs.openSync(resolved.canonicalPath, fs.constants.O_RDONLY);
      const openedStat = fs.fstatSync(descriptor);
      if (!sameFileIdentity(grant.identity, openedStat)) {
        throw new Error(
          "O arquivo mudou durante a abertura; selecione-o novamente.",
        );
      }
      bytes = fs.readFileSync(descriptor);
      const finalStat = fs.fstatSync(descriptor);
      if (
        !sameFileIdentity(grant.identity, finalStat) ||
        bytes.length !== finalStat.size ||
        bytes.length > MAX_GRANTED_FILE_BYTES
      ) {
        throw new Error(
          "O arquivo mudou durante a leitura; selecione-o novamente.",
        );
      }
    } finally {
      if (descriptor !== undefined) {
        fs.closeSync(descriptor);
      }
    }
    files.push({
      path: resolved.canonicalPath,
      name: path.basename(resolved.canonicalPath),
      size: bytes.length,
      modifiedAt: resolved.stat.mtimeMs,
      contentType,
      dataBase64: bytes.toString("base64"),
      source: grant.source,
    });
  }
  // Grants are capabilities, not durable path permissions. A successful read
  // consumes each exact grant; retry requires a fresh user selection.
  for (const file of files) {
    grantedFileReads.delete(file.path);
  }
  return {
    ok: true,
    files,
    totalBytes,
    grantsConsumed: true,
  };
}

async function chooseFilesForWindow(window, rawOptions = {}) {
  const options = rawOptions && typeof rawOptions === "object"
    ? rawOptions
    : {};
  const properties = ["openFile"];
  if (options.multiple !== false) {
    properties.push("multiSelections");
  }
  const result = await dialog.showOpenDialog(window, {
    title: cleanText(options.title, 120, "Selecionar arquivos"),
    buttonLabel: cleanText(options.buttonLabel, 60, "Selecionar"),
    properties,
    filters: sanitiseDialogFilters(options.filters),
  });
  if (result.canceled) {
    return [];
  }
  return result.filePaths
    .slice(0, MAX_SELECTED_FILES)
    .map((filePath) => grantSelectedFile(filePath, "picker"))
    .filter((item) => item?.kind === "file");
}

async function chooseFolderForWindow(window, rawOptions = {}) {
  const options = rawOptions && typeof rawOptions === "object"
    ? rawOptions
    : {};
  const result = await dialog.showOpenDialog(window, {
    title: cleanText(options.title, 120, "Selecionar pasta"),
    buttonLabel: cleanText(options.buttonLabel, 60, "Selecionar pasta"),
    properties: ["openDirectory", ...(options.createDirectory ? ["createDirectory"] : [])],
  });
  if (result.canceled || !result.filePaths[0]) {
    return null;
  }
  const metadata = selectedPathMetadata(result.filePaths[0]);
  return metadata?.kind === "folder" ? metadata : null;
}

function publicDisplays() {
  return screen.getAllDisplays().map((display) => ({
    id: String(display.id),
    label: display.label || `Tela ${display.id}`,
    primary: display.id === screen.getPrimaryDisplay().id,
    bounds: {
      x: display.bounds.x,
      y: display.bounds.y,
      width: display.bounds.width,
      height: display.bounds.height,
    },
    scaleFactor: display.scaleFactor,
    rotation: display.rotation,
  }));
}

function screenshotThumbnailSize(display) {
  const rawWidth = Math.max(
    1,
    Math.round(display.bounds.width * display.scaleFactor),
  );
  const rawHeight = Math.max(
    1,
    Math.round(display.bounds.height * display.scaleFactor),
  );
  const pixelScale = Math.min(
    1,
    8192 / Math.max(rawWidth, rawHeight),
    Math.sqrt(MAX_SCREENSHOT_PIXELS / (rawWidth * rawHeight)),
  );
  return {
    width: Math.max(1, Math.round(rawWidth * pixelScale)),
    height: Math.max(1, Math.round(rawHeight * pixelScale)),
  };
}

function normaliseScreenshotRegion(region, display, imageSize) {
  if (!region || typeof region !== "object") {
    return null;
  }
  const values = ["x", "y", "width", "height"].map((key) => Number(region[key]));
  if (
    values.some((value) => !Number.isFinite(value)) ||
    values[2] <= 0 ||
    values[3] <= 0
  ) {
    throw new Error("Região de captura inválida.");
  }
  const [x, y, width, height] = values;
  const left = Math.max(0, Math.min(display.bounds.width, x));
  const top = Math.max(0, Math.min(display.bounds.height, y));
  const right = Math.max(left, Math.min(display.bounds.width, x + width));
  const bottom = Math.max(top, Math.min(display.bounds.height, y + height));
  if (right - left < 1 || bottom - top < 1) {
    throw new Error("A região está fora da tela selecionada.");
  }
  const scaleX = imageSize.width / display.bounds.width;
  const scaleY = imageSize.height / display.bounds.height;
  const pixelLeft = Math.max(0, Math.floor(left * scaleX));
  const pixelTop = Math.max(0, Math.floor(top * scaleY));
  const pixelRight = Math.min(imageSize.width, Math.ceil(right * scaleX));
  const pixelBottom = Math.min(imageSize.height, Math.ceil(bottom * scaleY));
  return {
    x: pixelLeft,
    y: pixelTop,
    width: Math.max(1, pixelRight - pixelLeft),
    height: Math.max(1, pixelBottom - pixelTop),
  };
}

async function captureScreenshot(rawOptions = {}) {
  const options = rawOptions && typeof rawOptions === "object"
    ? rawOptions
    : {};
  const displays = screen.getAllDisplays();
  const display =
    displays.find((item) => String(item.id) === String(options.displayId)) ||
    screen.getPrimaryDisplay();
  const shouldRestoreWindow = Boolean(
    options.hideAetherWindow &&
    mainWindow &&
    !mainWindow.isDestroyed() &&
    mainWindow.isVisible(),
  );
  if (shouldRestoreWindow) {
    mainWindow.hide();
    const settleMs = Math.min(
      Math.max(Number(options.settleMs) || 120, 50),
      500,
    );
    await delay(settleMs);
  }

  try {
    const thumbnailSize = screenshotThumbnailSize(display);
    const sources = await desktopCapturer.getSources({
      types: ["screen"],
      thumbnailSize,
      fetchWindowIcons: false,
    });
    const displayIndex = displays.findIndex((item) => item.id === display.id);
    const source =
      sources.find((item) => String(item.display_id) === String(display.id)) ||
      sources[displayIndex] ||
      (display.id === screen.getPrimaryDisplay().id ? sources[0] : null);
    if (!source || source.thumbnail.isEmpty()) {
      throw new Error(
        "A captura de tela não está disponível ou não recebeu permissão do sistema.",
      );
    }

    let image = source.thumbnail;
    const region = normaliseScreenshotRegion(
      options.region,
      display,
      image.getSize(),
    );
    if (region) {
      image = image.crop(region);
    }
    const format = options.format === "jpeg" ? "jpeg" : "png";
    const bytes = format === "jpeg"
      ? image.toJPEG(Math.min(Math.max(Number(options.quality) || 90, 40), 100))
      : image.toPNG();
    if (bytes.length > MAX_SCREENSHOT_BYTES) {
      throw new Error("A imagem capturada excede o limite seguro de 16 MiB.");
    }
    return {
      ok: true,
      displayId: String(display.id),
      mode: region ? "region" : "full-display",
      interactiveSelection: false,
      aetherWindowHidden: shouldRestoreWindow,
      width: image.getSize().width,
      height: image.getSize().height,
      contentType: format === "jpeg" ? "image/jpeg" : "image/png",
      size: bytes.length,
      dataUrl: `data:${format === "jpeg" ? "image/jpeg" : "image/png"};base64,${bytes.toString("base64")}`,
    };
  } finally {
    if (
      shouldRestoreWindow &&
      mainWindow &&
      !mainWindow.isDestroyed()
    ) {
      mainWindow.show();
      mainWindow.focus();
    }
  }
}

function queueExternalIntent(intent) {
  if (!intent || typeof intent !== "object") {
    return;
  }
  const grantedIntent = grantExternalIntentFiles(intent);
  if (!grantedIntent) {
    return;
  }
  pendingExternalIntents.push(grantedIntent);
  if (pendingExternalIntents.length > 16) {
    pendingExternalIntents.shift();
  }
  flushExternalIntents();
}

function flushExternalIntents() {
  if (
    !rendererLoaded ||
    !rendererListenersReady ||
    !mainWindow ||
    mainWindow.isDestroyed()
  ) {
    return;
  }
  while (pendingExternalIntents.length > 0) {
    sendToRenderer(
      "aether:external-intent",
      pendingExternalIntents.shift(),
    );
  }
}

function existingSupportedPath(candidate) {
  try {
    const stat = fs.statSync(candidate);
    return stat.isFile() || stat.isDirectory();
  } catch {
    return false;
  }
}

function queueExternalIntentsFromArgv(argv) {
  for (const intent of extractExternalIntents(argv, {
    existingFile: existingSupportedPath,
  })) {
    queueExternalIntent(intent);
  }
}

function registerProtocolClient() {
  try {
    if (app.isPackaged) {
      protocolClientRegistered = app.setAsDefaultProtocolClient("aether");
    } else if (process.argv[1]) {
      protocolClientRegistered = app.setAsDefaultProtocolClient(
        "aether",
        process.execPath,
        [path.resolve(process.argv[1])],
      );
    }
  } catch (error) {
    protocolClientRegistered = false;
    console.warn("[deep-link] Registro indisponível:", safeErrorMessage(error));
  }
  return protocolClientRegistered;
}

function registerIpcHandlers() {
  if (ipcRegistered) {
    return;
  }
  ipcRegistered = true;

  ipcMain.handle("aether:get-runtime-info", (event) => {
    assertTrustedIpcSender(event);
    return {
      appName: app.getName(),
      version: app.getVersion(),
      platform: process.platform,
      arch: process.arch,
      packaged: app.isPackaged,
      backendUrl: BACKEND_ORIGIN,
      capabilities: getDesktopCapabilities(),
    };
  });

  ipcMain.handle("aether:get-desktop-capabilities", (event) => {
    assertTrustedIpcSender(event);
    return getDesktopCapabilities();
  });

  ipcMain.handle("aether:get-desktop-settings", (event) => {
    assertTrustedIpcSender(event);
    return loadDesktopSettings();
  });

  ipcMain.handle("aether:update-desktop-settings", (event, patch) => {
    assertTrustedIpcSender(event);
    return updateDesktopSettings(patch);
  });

  ipcMain.handle("aether:renderer-ready", (event) => {
    assertTrustedIpcSender(event);
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window || window !== mainWindow || window.isDestroyed()) {
      throw new Error("Janela principal indisponível.");
    }
    rendererListenersReady = true;
    const queued = pendingExternalIntents.length;
    flushExternalIntents();
    return { ok: true, deliveredExternalIntents: queued };
  });

  ipcMain.handle("aether:get-backend-status", (event) => {
    assertTrustedIpcSender(event);
    return publicBackendStatus();
  });

  ipcMain.handle("aether:backend-retry", async (event) => {
    assertTrustedIpcSender(event);
    if (backendStartPromise) {
      await backendStartPromise;
    }

    const health = await probeBackend(true);
    if (health.ready && await probeBackendAuthentication()) {
      updateBackendStatus(
        "ready",
        ownsBackendProcess
          ? "Backend local protegido e pronto."
          : "Backend local conectado.",
        ownsBackendProcess,
      );
      return publicBackendStatus();
    }

    await stopOwnedBackend();
    return ensureBackend();
  });

  ipcMain.handle("aether:backend-restart", async (event) => {
    assertTrustedIpcSender(event);
    abortRequestsForSender();
    await stopOwnedBackend();
    return ensureBackend();
  });

  ipcMain.handle("aether:choose-workspace", async (event) => {
    assertTrustedIpcSender(event);
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window || window !== mainWindow || window.isDestroyed()) {
      throw new Error("Janela principal indisponível.");
    }

    const result = await chooseFolderForWindow(window, {
      title: "Selecionar pasta de trabalho",
      buttonLabel: "Selecionar pasta",
    });
    return result?.path || null;
  });

  ipcMain.handle("aether:choose-files", async (event, options) => {
    assertTrustedIpcSender(event);
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window || window !== mainWindow || window.isDestroyed()) {
      throw new Error("Janela principal indisponível.");
    }
    return chooseFilesForWindow(window, options);
  });

  ipcMain.handle("aether:read-selected-files", (event, paths) => {
    assertTrustedIpcSender(event);
    return readGrantedFiles(paths);
  });

  ipcMain.handle("aether:choose-folder", async (event, options) => {
    assertTrustedIpcSender(event);
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window || window !== mainWindow || window.isDestroyed()) {
      throw new Error("Janela principal indisponível.");
    }
    return chooseFolderForWindow(window, options);
  });

  ipcMain.handle("aether:get-displays", (event) => {
    assertTrustedIpcSender(event);
    return publicDisplays();
  });

  ipcMain.handle("aether:authorize-screenshot", (event) => {
    assertTrustedIpcSender(event);
    const grant = screenshotGrants.grant(event.sender.id);
    return {
      ok: true,
      expiresAt: grant.expiresAt,
      oneShot: true,
    };
  });

  ipcMain.handle("aether:capture-screenshot", async (event, options) => {
    assertTrustedIpcSender(event);
    return runWithScreenshotGrant(
      screenshotGrants,
      event.sender.id,
      () => captureScreenshot(options),
    );
  });

  ipcMain.handle("aether:cancel-request", async (event, requestId) => {
    try {
      assertTrustedIpcSender(event);
      if (!isValidRequestId(requestId)) {
        throw new Error("Identificador de solicitação inválido.");
      }
      const localCancelled = abortActiveRequest(requestId);
      const backendResult = await requestBackend(
        `/requests/${encodeURIComponent(requestId)}/cancel`,
        {
          method: "POST",
          timeoutMs: 15_000,
        },
      );
      return {
        ...backendResult,
        requestId,
        localCancelled,
        backendAcknowledged: Boolean(backendResult.ok),
      };
    } catch (error) {
      return {
        ok: false,
        status: 0,
        contentType: "",
        data: null,
        error: safeErrorMessage(error, "Falha ao cancelar a solicitação."),
      };
    }
  });

  ipcMain.handle("aether:start-chat-stream", async (event, payload) => {
    assertTrustedIpcSender(event);
    return startBackendChatStream(payload, event.sender);
  });

  ipcMain.handle("aether:backend-request", async (event, payload) => {
    try {
      assertTrustedIpcSender(event);
      if (!payload || typeof payload !== "object") {
        throw new Error("Requisição IPC inválida.");
      }
      const options =
        payload.options && typeof payload.options === "object"
          ? payload.options
          : {};
      const method = String(options.method || "GET").toUpperCase();
      assertRendererBackendRequestAllowed(method, payload.path);
      const candidateRequestId =
        options.requestId ??
        options.body?.request_id;
      if (
        candidateRequestId !== undefined &&
        !isValidRequestId(candidateRequestId)
      ) {
        throw new Error("Identificador de solicitação inválido.");
      }
      const result = await requestBackend(payload.path, {
        method,
        body: options.body,
        confirmed: options.confirmed === true,
        projectId: options.projectId,
        timeoutMs: options.timeoutMs,
      }, candidateRequestId
        ? {
          requestId: candidateRequestId,
          sender: event.sender,
          kind: "backend",
        }
        : null);
      return {
        ...result,
        ...(candidateRequestId ? { requestId: candidateRequestId } : {}),
      };
    } catch (error) {
      return {
        ok: false,
        cancelled: error?.code === "AETHER_CANCELLED",
        status: 0,
        contentType: "",
        data: null,
        code: error?.code || null,
        blocked: error?.code === "AETHER_BACKEND_ROUTE_BLOCKED",
        error: safeErrorMessage(error, "Falha ao acessar o backend."),
      };
    }
  });

  ipcMain.handle("aether:open-external", async (event, url) => {
    assertTrustedIpcSender(event);
    if (!isSafeExternalUrl(url)) {
      return false;
    }
    await shell.openExternal(url);
    return true;
  });

  ipcMain.handle("aether:notify", (event, payload) => {
    assertTrustedIpcSender(event);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new Error("Notificação inválida.");
    }
    return showDesktopNotification(payload);
  });

  ipcMain.handle("aether:credential-status", (event) => {
    assertTrustedIpcSender(event);
    return publicCredentialStatus();
  });

  ipcMain.handle("aether:credential-set", (event, payload) => {
    assertTrustedIpcSender(event);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new Error("Credencial inválida.");
    }
    const key = cleanText(payload.key, 40);
    const result = getCredentialVault().setSecret(
      key,
      cleanText(payload.value, 16_384),
      {
        authorizeDefault: !SECURE_ONLY_CREDENTIAL_ENVIRONMENT_KEYS.has(
          CREDENTIAL_ENVIRONMENT_KEYS[key],
        ),
      },
    );
    return {
      ...result,
      restartRequired: Boolean(backendProcess),
    };
  });

  ipcMain.handle("aether:credential-delete", (event, keyValue) => {
    assertTrustedIpcSender(event);
    const result = getCredentialVault().deleteSecret(
      cleanText(keyValue, 40),
    );
    return {
      ...result,
      restartRequired: Boolean(backendProcess),
    };
  });

  ipcMain.handle("aether:credential-authorize", (event, payload) => {
    assertTrustedIpcSender(event);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new Error("Autorização de credencial inválida.");
    }
    const key = cleanText(payload.key, 40);
    const integration = cleanText(payload.integration || payload.key, 64);
    const restrictedIntegrations =
      RESTRICTED_CREDENTIAL_INTEGRATIONS[key];
    if (
      restrictedIntegrations &&
      !restrictedIntegrations.includes(integration)
    ) {
      throw new Error("Esta credencial não pode autorizar essa integração.");
    }
    const result = getCredentialVault().authorize({
      key,
      integration,
      policy: cleanText(payload.policy || "session", 20),
      expiresAt:
        typeof payload.expiresAt === "string"
          ? payload.expiresAt.slice(0, 64)
          : null,
      ttlMs: Number(payload.ttlMs),
    });
    return {
      ...result,
      restartRequired: Boolean(backendProcess),
    };
  });

  ipcMain.handle("aether:credential-revoke", (event, payload) => {
    assertTrustedIpcSender(event);
    const request =
      typeof payload === "string"
        ? { key: payload }
        : payload;
    if (!request || typeof request !== "object" || Array.isArray(request)) {
      throw new Error("Revogação de credencial inválida.");
    }
    const result = getCredentialVault().revoke({
      key: cleanText(request.key, 40),
      integration:
        request.integration == null
          ? null
          : cleanText(request.integration, 64),
    });
    return {
      ...result,
      restartRequired: Boolean(backendProcess),
    };
  });

  ipcMain.handle("aether:update-status", (event) => {
    assertTrustedIpcSender(event);
    return getUpdateRecoveryManager().status();
  });

  ipcMain.handle("aether:update-channel", (event, payload) => {
    assertTrustedIpcSender(event);
    const channel =
      typeof payload === "string"
        ? payload
        : payload?.channel;
    return getUpdateRecoveryManager().setChannel(
      cleanText(channel, 20),
    );
  });

  ipcMain.handle("aether:update-verify", (event, payload) => {
    assertTrustedIpcSender(event);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new Error("Dados de atualização inválidos.");
    }
    return getUpdateRecoveryManager().verifyUpdate(payload);
  });

  ipcMain.handle("aether:recovery-snapshot", async (event, payload) => {
    assertTrustedIpcSender(event);
    return runExclusiveRecoveryOperation(async () => {
      if (backendStatus.state === "ready" && !ownsBackendProcess) {
        throw new Error(
          "O backend externo precisa ser encerrado antes do snapshot.",
        );
      }
      const restartBackend = Boolean(backendProcess && ownsBackendProcess);
      abortRequestsForSender();
      if (restartBackend) {
        await stopOwnedBackend();
      }
      let result;
      let snapshotError = null;
      try {
        result = getUpdateRecoveryManager().createSnapshot({
          reason:
            typeof payload?.reason === "string"
              ? payload.reason
              : "manual",
        });
      } catch (error) {
        snapshotError = error;
      }
      let restartError = null;
      if (restartBackend) {
        try {
          await ensureBackend();
        } catch (error) {
          restartError = error;
        }
      }
      if (snapshotError) {
        throw snapshotError;
      }
      if (restartError) {
        throw new Error(
          `Snapshot concluído, mas o núcleo não reiniciou: ${safeErrorMessage(restartError)}`,
        );
      }
      return {
        ...result,
        backendQuiesced: restartBackend,
        backendRestarted: restartBackend,
      };
    });
  });

  ipcMain.handle("aether:recovery-list", (event) => {
    assertTrustedIpcSender(event);
    return {
      ok: true,
      snapshots: getUpdateRecoveryManager().listSnapshots(),
    };
  });

  ipcMain.handle("aether:recovery-rollback", async (event, payload) => {
    assertTrustedIpcSender(event);
    return runExclusiveRecoveryOperation(async () => {
      if (backendStatus.state === "ready" && !ownsBackendProcess) {
        throw new Error(
          "O backend externo precisa ser encerrado antes da restauração.",
        );
      }
      const id =
        typeof payload === "string"
          ? payload
          : payload?.id;
      abortRequestsForSender();
      const backendWasRunning = Boolean(backendProcess && ownsBackendProcess);
      if (backendWasRunning) {
        await stopOwnedBackend();
      }
      const result = getUpdateRecoveryManager().rollback(
        cleanText(id, 96),
      );
      desktopSettings = null;
      getCredentialVault().clearSessionGrants();
      screenshotGrants.clear();
      grantedFileReads.clear();
      return {
        ...result,
        backendStopped: backendWasRunning,
        restartRequired: true,
      };
    });
  });

  ipcMain.on("aether:window-action", (event, action) => {
    try {
      assertTrustedIpcSender(event);
    } catch {
      return;
    }
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window || window !== mainWindow) {
      return;
    }

    if (action === "minimize") {
      window.minimize();
    } else if (action === "toggle-maximize") {
      window.isMaximized() ? window.unmaximize() : window.maximize();
    } else if (action === "close") {
      window.close();
    } else if (action === "hide") {
      window.hide();
    }
  });

  ipcMain.handle("aether:window-state", (event) => {
    assertTrustedIpcSender(event);
    const window = BrowserWindow.fromWebContents(event.sender);
    return Boolean(window && window === mainWindow && window.isMaximized());
  });
}

function unregisterIpcHandlers() {
  if (!ipcRegistered) {
    return;
  }
  for (const channel of IPC_HANDLE_CHANNELS) {
    ipcMain.removeHandler(channel);
  }
  ipcMain.removeAllListeners("aether:window-action");
  ipcRegistered = false;
}

function sendShortcut(name) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("aether:shortcut", name);
  }
}

function installWindowShortcuts(window) {
  window.webContents.on("before-input-event", (event, input) => {
    if (input.type !== "keyDown") {
      return;
    }

    const commandKey = process.platform === "darwin" ? input.meta : input.control;
    const key = String(input.key || "").toLowerCase();

    if (key === "f11") {
      event.preventDefault();
      window.setFullScreen(!window.isFullScreen());
      return;
    }

    if (key === "escape" && window.isFullScreen()) {
      event.preventDefault();
      window.setFullScreen(false);
      return;
    }

    if (commandKey && key === "n") {
      event.preventDefault();
      sendShortcut("new-chat");
      return;
    }
    if (commandKey && key === "k") {
      event.preventDefault();
      sendShortcut("open-command");
      return;
    }
    if (commandKey && key === ",") {
      event.preventDefault();
      sendShortcut("open-settings");
      return;
    }
    if (commandKey && key === "\\") {
      event.preventDefault();
      sendShortcut("toggle-sidebar");
      return;
    }

    const isReload =
      key === "f5" ||
      (commandKey && key === "r");
    const isDevTools =
      key === "f12" ||
      (commandKey && input.shift && key === "i");

    if (isReload || isDevTools) {
      event.preventDefault();
      if (!app.isPackaged) {
        isDevTools
          ? window.webContents.toggleDevTools()
          : window.webContents.reload();
      }
    }
  });
}

function configureRendererSecurity(window) {
  const session = window.webContents.session;

  session.setPermissionRequestHandler((webContents, permission, callback, details) => {
    const trusted = webContents === window.webContents &&
      isTrustedRendererUrl(details.requestingUrl || webContents.getURL());
    const mediaTypes = Array.isArray(details.mediaTypes)
      ? details.mediaTypes
      : [];
    const audioOnly = mediaTypes.length > 0 &&
      mediaTypes.every((type) => type === "audio");
    callback(Boolean(trusted && permission === "media" && audioOnly));
  });

  session.setPermissionCheckHandler(
    (webContents, permission, _requestingOrigin, details) => {
      const requestingUrl =
        details?.requestingUrl ||
        details?.embeddingOrigin ||
        webContents?.getURL?.();
      return Boolean(
        webContents === window.webContents &&
        permission === "media" &&
        isTrustedRendererUrl(requestingUrl),
      );
    },
  );

  if (typeof session.setDisplayMediaRequestHandler === "function") {
    session.setDisplayMediaRequestHandler((_request, callback) => {
      callback({});
    });
  }

  session.webRequest.onHeadersReceived(
    { urls: ["file://*/*"] },
    (details, callback) => {
      if (
        details.resourceType !== "mainFrame" ||
        !isTrustedRendererUrl(details.url)
      ) {
        callback({ responseHeaders: details.responseHeaders });
        return;
      }
      const responseHeaders = Object.fromEntries(
        Object.entries(details.responseHeaders || {}).filter(
          ([name]) => name.toLowerCase() !== "content-security-policy",
        ),
      );
      responseHeaders["Content-Security-Policy"] = [RENDERER_CSP];
      callback({ responseHeaders });
    },
  );

  window.webContents.on("will-attach-webview", (event) => {
    event.preventDefault();
  });

  window.webContents.on("will-navigate", (event, targetUrl) => {
    if (isTrustedRendererUrl(targetUrl)) {
      return;
    }
    event.preventDefault();
    if (isSafeExternalUrl(targetUrl)) {
      void shell.openExternal(targetUrl);
    }
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (isSafeExternalUrl(url)) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });

  window.webContents.on("context-menu", (_event, parameters) => {
    const selectionText = cleanText(parameters.selectionText, 8_192);
    const linkUrl = isSafeExternalUrl(parameters.linkURL)
      ? parameters.linkURL
      : null;
    const template = [];

    if (selectionText) {
      template.push({
        label: "Perguntar ao Aether sobre a seleção",
        click: () => {
          queueExternalIntent({
            type: "ask-text",
            text: selectionText,
            source: "in-app-context-menu",
          });
        },
      });
      template.push({ type: "separator" });
    } else if (linkUrl) {
      template.push({
        label: "Perguntar ao Aether sobre este link",
        click: () => {
          queueExternalIntent({
            type: "ask-text",
            text: linkUrl,
            source: "in-app-context-menu",
          });
        },
      });
      template.push({ type: "separator" });
    }

    if (parameters.isEditable) {
      template.push(
        { role: "undo", label: "Desfazer" },
        { role: "redo", label: "Refazer" },
        { type: "separator" },
        { role: "cut", label: "Recortar" },
        { role: "copy", label: "Copiar" },
        { role: "paste", label: "Colar" },
        { role: "selectAll", label: "Selecionar tudo" },
      );
    } else if (selectionText) {
      template.push({ role: "copy", label: "Copiar" });
    }

    if (linkUrl) {
      if (template.length > 0) {
        template.push({ type: "separator" });
      }
      template.push({
        label: "Abrir link no navegador",
        click: () => void shell.openExternal(linkUrl),
      });
    }

    if (template.length > 0) {
      Menu.buildFromTemplate(template).popup({ window });
    }
  });
}

function createSplashWindow() {
  const splashPath = resolveProjectPath("build", "splash.html");
  if (!fs.existsSync(splashPath)) {
    return null;
  }

  const window = new BrowserWindow({
    width: 420,
    height: 300,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    center: true,
    icon: resolveWindowIcon(),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      nodeIntegrationInWorker: false,
      nodeIntegrationInSubFrames: false,
      sandbox: true,
      devTools: false,
      webSecurity: true,
      webviewTag: false,
    },
  });

  window.once("ready-to-show", () => {
    if (!window.isDestroyed()) {
      window.show();
    }
  });
  void window.loadFile(splashPath);
  splashWindow = window;
  return window;
}

async function createMainWindow() {
  mainEntryPath = resolveRendererEntry();
  const restoredWindowState = loadWindowState() || {
    width: 1_440,
    height: 920,
    maximized: false,
  };

  const browserOptions = {
    width: restoredWindowState.width,
    height: restoredWindowState.height,
    minWidth: 900,
    minHeight: 640,
    show: false,
    center: false,
    backgroundColor: "#0f0f10",
    autoHideMenuBar: true,
    icon: resolveWindowIcon(),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      nodeIntegrationInWorker: false,
      nodeIntegrationInSubFrames: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      navigateOnDragDrop: false,
      spellcheck: true,
      devTools: !app.isPackaged,
      webviewTag: false,
    },
  };
  if (
    Number.isFinite(restoredWindowState.x) &&
    Number.isFinite(restoredWindowState.y)
  ) {
    browserOptions.x = restoredWindowState.x;
    browserOptions.y = restoredWindowState.y;
  } else {
    browserOptions.center = true;
  }

  if (process.platform === "darwin") {
    browserOptions.titleBarStyle = "hiddenInset";
  } else {
    browserOptions.frame = false;
  }

  const window = new BrowserWindow(browserOptions);
  mainWindow = window;
  rendererLoaded = false;
  rendererListenersReady = false;
  if (restoredWindowState.maximized) {
    window.maximize();
  }
  refreshDesktopActivityIndicators();

  configureRendererSecurity(window);
  installWindowShortcuts(window);

  window.on("maximize", () => {
    scheduleWindowStateSave(window);
    window.webContents.send("aether:window-maximized-changed", true);
  });
  window.on("unmaximize", () => {
    scheduleWindowStateSave(window);
    window.webContents.send("aether:window-maximized-changed", false);
  });
  window.on("move", () => scheduleWindowStateSave(window));
  window.on("resize", () => scheduleWindowStateSave(window));
  window.on("close", (event) => {
    clearWindowStateSaveTimer();
    persistWindowState(window);
    const settings = loadDesktopSettings();
    if (
      !quitting &&
      settings.closeToTray &&
      tray &&
      !tray.isDestroyed()
    ) {
      event.preventDefault();
      window.hide();
    }
  });
  window.on("closed", () => {
    clearWindowStateSaveTimer();
    abortRequestsForSender(window.webContents);
    if (mainWindow === window) {
      mainWindow = null;
      rendererLoaded = false;
      rendererListenersReady = false;
    }
  });

  window.webContents.on("did-start-loading", () => {
    rendererLoaded = false;
    rendererListenersReady = false;
  });

  window.webContents.on("did-finish-load", () => {
    rendererLoaded = true;
    window.webContents.send(
      "aether:backend-status",
      publicBackendStatus(),
    );
    window.webContents.send(
      "aether:desktop-settings-changed",
      loadDesktopSettings(),
    );
    flushExternalIntents();
  });

  window.webContents.once("destroyed", () => {
    abortRequestsForSender(window.webContents);
  });

  window.webContents.on("render-process-gone", (_event, details) => {
    console.error("[renderer] Processo encerrado:", details.reason);
  });

  await window.loadFile(mainEntryPath);
  return window;
}

async function bootstrap() {
  if (process.platform === "win32") {
    app.setAppUserModelId("ai.aether.desktop");
  }
  ensurePackagedEnvironmentFile();
  Menu.setApplicationMenu(null);
  registerIpcHandlers();
  registerProtocolClient();
  nativeTheme.on("updated", refreshDesktopActivityIndicators);
  applyInitialDesktopSettings();
  queueExternalIntentsFromArgv(process.argv);

  const startedAt = Date.now();
  createSplashWindow();
  await ensureBackend();

  const window =
    mainWindow && !mainWindow.isDestroyed()
      ? mainWindow
      : await createMainWindow();
  const remainingSplashTime =
    MIN_SPLASH_TIME_MS - (Date.now() - startedAt);
  if (remainingSplashTime > 0) {
    await delay(remainingSplashTime);
  }

  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.close();
  }
  splashWindow = null;

  if (!window.isDestroyed()) {
    window.show();
    window.focus();
  }
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", (_event, argv) => {
    queueExternalIntentsFromArgv(argv);
    void showMainWindow();
  });

  app.on("open-url", (event, url) => {
    event.preventDefault();
    queueExternalIntentsFromArgv([url]);
    if (app.isReady()) {
      void showMainWindow();
    }
  });

  app.on("open-file", (event, filePath) => {
    if (!existingSupportedPath(filePath)) {
      return;
    }
    event.preventDefault();
    queueExternalIntent({
      type: "ask-file",
      paths: [path.resolve(filePath)],
      source: "open-file",
    });
    if (app.isReady()) {
      void showMainWindow();
    }
  });

  app.whenReady()
    .then(bootstrap)
    .catch((error) => {
      const message = safeErrorMessage(
        error,
        "Não foi possível abrir a interface da Aether.",
      );
      console.error("[startup]", message);
      dialog.showErrorBox("Aether Desktop AI", message);
      app.quit();
    });

  app.on("activate", () => {
    void showMainWindow()
      .then(() => ensureBackend())
      .catch((error) => {
        dialog.showErrorBox(
          "Aether Desktop AI",
          safeErrorMessage(error),
        );
      });
  });

  app.on("window-all-closed", () => {
    const keepAlive =
      loadDesktopSettings().closeToTray &&
      tray &&
      !tray.isDestroyed();
    if (process.platform !== "darwin" && !keepAlive) {
      app.quit();
    }
  });

  app.on("before-quit", (event) => {
    if (shutdownComplete) {
      return;
    }
    event.preventDefault();
    if (quitting) {
      return;
    }

    quitting = true;
    clearWindowStateSaveTimer();
    persistWindowState(mainWindow);
    abortRequestsForSender();
    globalShortcut.unregisterAll();
    registeredGlobalShortcut = null;
    nativeTheme.removeListener(
      "updated",
      refreshDesktopActivityIndicators,
    );
    unregisterIpcHandlers();
    if (tray && !tray.isDestroyed()) {
      tray.destroy();
    }
    tray = null;
    trayPresentationKey = null;
    void stopOwnedBackend().finally(() => {
      shutdownComplete = true;
      app.quit();
    });
  });
}
