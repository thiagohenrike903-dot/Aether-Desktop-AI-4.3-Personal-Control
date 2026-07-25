"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const CHANNELS = Object.freeze({
  backendRequest: "aether:backend-request",
  backendRestart: "aether:backend-restart",
  backendRetry: "aether:backend-retry",
  backendStatus: "aether:backend-status",
  cancelRequest: "aether:cancel-request",
  authorizeScreenshot: "aether:authorize-screenshot",
  captureScreenshot: "aether:capture-screenshot",
  chatStreamEvent: "aether:chat-stream-event",
  chooseFiles: "aether:choose-files",
  chooseFolder: "aether:choose-folder",
  chooseWorkspace: "aether:choose-workspace",
  credentialDelete: "aether:credential-delete",
  credentialAuthorize: "aether:credential-authorize",
  credentialRevoke: "aether:credential-revoke",
  credentialSet: "aether:credential-set",
  credentialStatus: "aether:credential-status",
  desktopCapabilities: "aether:get-desktop-capabilities",
  desktopSettings: "aether:get-desktop-settings",
  desktopSettingsChanged: "aether:desktop-settings-changed",
  displays: "aether:get-displays",
  externalIntent: "aether:external-intent",
  getBackendStatus: "aether:get-backend-status",
  getRuntimeInfo: "aether:get-runtime-info",
  notify: "aether:notify",
  openExternal: "aether:open-external",
  operationProgress: "aether:operation-progress",
  readSelectedFiles: "aether:read-selected-files",
  rendererReady: "aether:renderer-ready",
  recoveryList: "aether:recovery-list",
  recoveryRollback: "aether:recovery-rollback",
  recoverySnapshot: "aether:recovery-snapshot",
  shortcut: "aether:shortcut",
  startChatStream: "aether:start-chat-stream",
  updateDesktopSettings: "aether:update-desktop-settings",
  updateChannel: "aether:update-channel",
  updateStatus: "aether:update-status",
  updateVerify: "aether:update-verify",
  windowAction: "aether:window-action",
  windowMaximizedChanged: "aether:window-maximized-changed",
  windowState: "aether:window-state",
});

const REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const TRUSTED_GESTURE_WINDOW_MS = 1_200;
let lastTrustedGestureAt = 0;

function rememberTrustedGesture(event) {
  if (event?.isTrusted === true) {
    lastTrustedGestureAt = Date.now();
  }
}

if (typeof globalThis.addEventListener === "function") {
  globalThis.addEventListener("pointerdown", rememberTrustedGesture, true);
  globalThis.addEventListener("keydown", rememberTrustedGesture, true);
}

function hasRecentTrustedUserGesture() {
  const userActivation = globalThis.navigator?.userActivation;
  if (typeof userActivation?.isActive === "boolean") {
    return userActivation.isActive;
  }
  return (
    lastTrustedGestureAt > 0 &&
    Date.now() - lastTrustedGestureAt <= TRUSTED_GESTURE_WINDOW_MS
  );
}

function subscribe(channel, callback, predicate = null) {
  if (typeof callback !== "function") {
    throw new TypeError("O callback precisa ser uma função.");
  }

  const listener = (_event, payload) => {
    if (!predicate || predicate(payload)) {
      callback(payload);
    }
  };
  ipcRenderer.on(channel, listener);
  let active = true;
  return () => {
    if (!active) {
      return;
    }
    active = false;
    ipcRenderer.removeListener(channel, listener);
  };
}

function createRequestId() {
  const webCrypto = globalThis.crypto;
  if (typeof webCrypto?.randomUUID === "function") {
    return `request_${webCrypto.randomUUID().replace(/-/g, "")}`;
  }
  if (typeof webCrypto?.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    webCrypto.getRandomValues(bytes);
    return `request_${Array.from(bytes, (value) =>
      value.toString(16).padStart(2, "0")).join("")}`;
  }
  // The identifier is used for correlation, not authentication. Main still
  // validates it and the backend is protected by a separate random token.
  return `request_${Date.now().toString(36)}${Math.random()
    .toString(36)
    .slice(2, 14)}`;
}

function normaliseStreamPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new TypeError("O conteúdo do chat precisa ser um objeto.");
  }
  const suppliedId = payload.request_id;
  const requestId =
    typeof suppliedId === "string" && REQUEST_ID_PATTERN.test(suppliedId)
      ? suppliedId
      : createRequestId();
  return {
    requestId,
    payload: {
      ...payload,
      request_id: requestId,
    },
  };
}

function normaliseBackendRequestOptions(options) {
  if (
    !options ||
    typeof options !== "object" ||
    Array.isArray(options)
  ) {
    return {};
  }
  const normalised = {};
  for (const key of [
    "method",
    "body",
    "requestId",
    "confirmed",
    "projectId",
    "timeoutMs",
  ]) {
    if (Object.prototype.hasOwnProperty.call(options, key)) {
      normalised[key] = options[key];
    }
  }
  return normalised;
}

function startChatStream(payload, onEvent) {
  if (typeof onEvent !== "function") {
    throw new TypeError("onEvent precisa ser uma função.");
  }
  const normalised = normaliseStreamPayload(payload);
  let disposed = false;
  const unsubscribe = subscribe(
    CHANNELS.chatStreamEvent,
    onEvent,
    (event) => event?.requestId === normalised.requestId,
  );
  const completion = ipcRenderer
    .invoke(CHANNELS.startChatStream, normalised.payload)
    .catch((error) => {
      const message =
        typeof error?.message === "string"
          ? error.message
          : "Falha na ponte de streaming.";
      if (!disposed) {
        onEvent({
          requestId: normalised.requestId,
          type: "transport-error",
          event: "error",
          data: {
            type: "error",
            message,
          },
          timestamp: Date.now(),
        });
      }
      return {
        ok: false,
        cancelled: false,
        requestId: normalised.requestId,
        terminalType: "transport-error",
        error: message,
      };
    })
    .finally(() => {
      disposed = true;
      unsubscribe();
    });

  return Object.freeze({
    requestId: normalised.requestId,
    completion,
    cancel: () =>
      ipcRenderer.invoke(CHANNELS.cancelRequest, normalised.requestId),
    dispose: () => {
      disposed = true;
      unsubscribe();
    },
  });
}

const windowControls = Object.freeze({
  minimize: () => ipcRenderer.send(CHANNELS.windowAction, "minimize"),
  toggleMaximize: () =>
    ipcRenderer.send(CHANNELS.windowAction, "toggle-maximize"),
  close: () => ipcRenderer.send(CHANNELS.windowAction, "close"),
  hide: () => ipcRenderer.send(CHANNELS.windowAction, "hide"),
  isMaximized: () => ipcRenderer.invoke(CHANNELS.windowState),
  onMaximizedChange: (callback) =>
    subscribe(CHANNELS.windowMaximizedChanged, callback),
});

const credentials = Object.freeze({
  status: () => ipcRenderer.invoke(CHANNELS.credentialStatus),
  set: (key, value) =>
    ipcRenderer.invoke(CHANNELS.credentialSet, { key, value }),
  delete: (key) => ipcRenderer.invoke(CHANNELS.credentialDelete, key),
  authorize: (key, options = {}) =>
    ipcRenderer.invoke(CHANNELS.credentialAuthorize, {
      key,
      integration: options.integration,
      policy: options.policy,
      expiresAt: options.expiresAt,
      ttlMs: options.ttlMs,
    }),
  revoke: (key, integration = null) =>
    ipcRenderer.invoke(CHANNELS.credentialRevoke, {
      key,
      integration,
    }),
});

const updates = Object.freeze({
  status: () => ipcRenderer.invoke(CHANNELS.updateStatus),
  setChannel: (channel) =>
    ipcRenderer.invoke(CHANNELS.updateChannel, { channel }),
  verify: (payload) => ipcRenderer.invoke(CHANNELS.updateVerify, payload),
  createSnapshot: (options = {}) =>
    ipcRenderer.invoke(CHANNELS.recoverySnapshot, options),
  listSnapshots: () => ipcRenderer.invoke(CHANNELS.recoveryList),
  rollback: (id) =>
    ipcRenderer.invoke(CHANNELS.recoveryRollback, { id }),
});

const desktop = Object.freeze({
  ready: () => ipcRenderer.invoke(CHANNELS.rendererReady),
  getCapabilities: () => ipcRenderer.invoke(CHANNELS.desktopCapabilities),
  getSettings: () => ipcRenderer.invoke(CHANNELS.desktopSettings),
  updateSettings: (patch) =>
    ipcRenderer.invoke(CHANNELS.updateDesktopSettings, patch),
  chooseFiles: (options = {}) =>
    ipcRenderer.invoke(CHANNELS.chooseFiles, options),
  readSelectedFiles: (paths) =>
    ipcRenderer.invoke(CHANNELS.readSelectedFiles, paths),
  chooseFolder: (options = {}) =>
    ipcRenderer.invoke(CHANNELS.chooseFolder, options),
  getDisplays: () => ipcRenderer.invoke(CHANNELS.displays),
  authorizeScreenshot: () => {
    if (!hasRecentTrustedUserGesture()) {
      return Promise.resolve({
        ok: false,
        blocked: true,
        code: "TRUSTED_USER_GESTURE_REQUIRED",
        error: "A captura precisa ser iniciada por um gesto explícito.",
      });
    }
    return ipcRenderer.invoke(CHANNELS.authorizeScreenshot);
  },
  captureScreenshot: (options = {}) =>
    ipcRenderer.invoke(CHANNELS.captureScreenshot, options),
  notify: (payload) => ipcRenderer.invoke(CHANNELS.notify, payload),
  onSettingsChanged: (callback) =>
    subscribe(CHANNELS.desktopSettingsChanged, callback),
  onExternalIntent: (callback) =>
    subscribe(CHANNELS.externalIntent, callback),
  onOperationProgress: (callback) =>
    subscribe(CHANNELS.operationProgress, callback),
});

const aetherApi = Object.freeze({
  request: (resourcePath, options = {}) =>
    ipcRenderer.invoke(CHANNELS.backendRequest, {
      path: resourcePath,
      options: normaliseBackendRequestOptions(options),
    }),
  createRequestId,
  startChatStream,
  cancelRequest: (requestId) =>
    ipcRenderer.invoke(CHANNELS.cancelRequest, requestId),
  chooseWorkspace: () => ipcRenderer.invoke(CHANNELS.chooseWorkspace),
  retryBackend: () => ipcRenderer.invoke(CHANNELS.backendRetry),
  restartBackend: () => ipcRenderer.invoke(CHANNELS.backendRestart),
  getBackendStatus: () => ipcRenderer.invoke(CHANNELS.getBackendStatus),
  getRuntimeInfo: () => ipcRenderer.invoke(CHANNELS.getRuntimeInfo),
  openExternal: (url) => ipcRenderer.invoke(CHANNELS.openExternal, url),
  onBackendStatus: (callback) =>
    subscribe(CHANNELS.backendStatus, callback),
  onShortcut: (callback) => subscribe(CHANNELS.shortcut, callback),
  onChatStreamEvent: (callback) =>
    subscribe(CHANNELS.chatStreamEvent, callback),
  onOperationProgress: (callback) =>
    subscribe(CHANNELS.operationProgress, callback),
  onExternalIntent: (callback) =>
    subscribe(CHANNELS.externalIntent, callback),
  desktop,
  credentials,
  updates,
  window: windowControls,
});

contextBridge.exposeInMainWorld("aether", aetherApi);
