(function () {
  "use strict";

  if (window.aether) return;
  window.__AETHER_BROWSER__ = true;

  var API_BASE = (function () {
    var origin = window.location.origin;
    if (origin.includes("localhost") || origin.includes("127.0.0.1")) {
      return "http://127.0.0.1:8765";
    }
    return origin + "/api";
  })();

  var pendingStreams = {};

  function apiUrl(path) {
    return API_BASE + path;
  }

  function getToken() {
    try {
      return sessionStorage.getItem("aether_api_token") || "";
    } catch (_) {
      return "";
    }
  }

  async function request(method, path, opts) {
    opts = opts || {};
    var headers = {
      "Content-Type": "application/json",
      "X-Aether-Token": getToken(),
    };
    if (opts.projectId) headers["X-Aether-Project-Id"] = opts.projectId;
    if (opts.confirmed) headers["X-Aether-Confirmed"] = "1";

    var fetchOpts = {
      method: method,
      headers: headers,
    };
    if (opts.body && method !== "GET") {
      fetchOpts.body = typeof opts.body === "string" ? opts.body : JSON.stringify(opts.body);
    }
    var response = await fetch(apiUrl(path), fetchOpts);

    if (response.status === 428) {
      var body = await response.json();
      if (body.pending_confirmation) {
        var confirmed = window.confirm(
          (body.safety && body.safety.reason) || "Esta ação requer confirmação. Continuar?"
        );
        if (confirmed) {
          headers["X-Aether-Confirmed"] = "1";
          var retryResp = await fetch(apiUrl(path), { method: method, headers: headers, body: fetchOpts.body });
          return retryResp.json();
        }
        throw new Error("Ação cancelada pelo usuário.");
      }
    }

    if (!response.ok) {
      var errBody = await response.json().catch(function () { return {}; });
      var err = new Error(errBody.detail || errBody.error || "Request failed: " + response.status);
      err.status = response.status;
      err.body = errBody;
      throw err;
    }

    var contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return response.json();
    }
    return response.text();
  }

  function createRequestId() {
    return "req_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  async function chatStream(payload, onEvent) {
    var requestId = payload.request_id || createRequestId();
    payload.request_id = requestId;

    var controller = new AbortController();
    pendingStreams[requestId] = controller;

    try {
      var response = await fetch(apiUrl("/chat"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Aether-Token": getToken(),
          Accept: "text/event-stream",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok) {
        var errBody = await response.json().catch(function () { return {}; });
        onEvent({
          requestId: requestId,
          type: "transport-error",
          event: "error",
          data: { type: "error", message: errBody.detail || "Chat request failed" },
          timestamp: Date.now(),
        });
        return { ok: false, requestId: requestId };
      }

      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";

      while (true) {
        var result = await reader.read();
        if (result.done) break;
        buffer += decoder.decode(result.value, { stream: true });
        var lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (var i = 0; i < lines.length; i++) {
          var line = lines[i];
          if (line.startsWith("data: ")) {
            try {
              var data = JSON.parse(line.slice(6));
              onEvent({
                requestId: requestId,
                type: data.type || "token",
                event: data.event || data.type || "data",
                data: data,
                timestamp: Date.now(),
              });
            } catch (_) {}
          }
        }
      }

      onEvent({
        requestId: requestId,
        type: "done",
        event: "done",
        data: { type: "done" },
        timestamp: Date.now(),
      });

      return { ok: true, requestId: requestId };
    } catch (err) {
      if (err.name === "AbortError") {
        onEvent({
          requestId: requestId,
          type: "cancelled",
          event: "cancelled",
          data: { type: "cancelled" },
          timestamp: Date.now(),
        });
        return { ok: false, cancelled: true, requestId: requestId };
      }
      onEvent({
        requestId: requestId,
        type: "transport-error",
        event: "error",
        data: { type: "error", message: err.message },
        timestamp: Date.now(),
      });
      return { ok: false, requestId: requestId };
    } finally {
      delete pendingStreams[requestId];
    }
  }

  var aetherApi = {
    _apiBase: API_BASE,
    request: function (path, opts) {
      opts = opts || {};
      var method = opts.method || "GET";
      return request(method, path, opts);
    },
    createRequestId: createRequestId,
    startChatStream: chatStream,
    cancelRequest: function (requestId) {
      var controller = pendingStreams[requestId];
      if (controller) {
        controller.abort();
        delete pendingStreams[requestId];
      }
    },
    getBackendStatus: function () {
      return request("GET", "/health").then(function (data) {
        return { ok: true, status: "online", data: data };
      }).catch(function () {
        return { ok: false, status: "offline" };
      });
    },
    getRuntimeInfo: function () {
      return request("GET", "/health").then(function (data) {
        return { version: data.version, platform: "web" };
      }).catch(function () {
        return null;
      });
    },
    retryBackend: function () {
      return Promise.resolve();
    },
    restartBackend: function () {
      return Promise.resolve();
    },
    openExternal: function (url) {
      window.open(url, "_blank", "noopener,noreferrer");
      return Promise.resolve();
    },
    chooseWorkspace: function () {
      return Promise.resolve(null);
    },
    desktop: {
      ready: function () { return Promise.resolve(); },
      getCapabilities: function () {
        return Promise.resolve({
          screenshots: false,
          notifications: "html5",
          filePicking: false,
          credentials: false,
          osControl: false,
        });
      },
      getSettings: function () { return Promise.resolve(null); },
      updateSettings: function () { return Promise.resolve(); },
      chooseFiles: function () { return Promise.resolve([]); },
      readSelectedFiles: function () { return Promise.resolve([]); },
      chooseFolder: function () { return Promise.resolve(null); },
      getDisplays: function () { return Promise.resolve([]); },
      authorizeScreenshot: function () { return Promise.resolve({ ok: false, blocked: true }); },
      captureScreenshot: function () { return Promise.resolve(null); },
      notify: function (payload) {
        if ("Notification" in window && Notification.permission === "granted") {
          new Notification(payload.title || "Aether", { body: payload.message || "" });
        }
        return Promise.resolve();
      },
      onSettingsChanged: function () { return function () {}; },
      onExternalIntent: function () { return function () {}; },
      onOperationProgress: function () { return function () {}; },
    },
    credentials: {
      status: function () { return Promise.resolve({ available: false, enforced: false }); },
      set: function () { return Promise.resolve({ ok: false, error: "Cofre indisponível no navegador." }); },
      delete: function () { return Promise.resolve({ ok: false }); },
      authorize: function () { return Promise.resolve({ ok: false, error: "Cofre indisponível no navegador." }); },
      revoke: function () { return Promise.resolve({ ok: false }); },
    },
    updates: {
      status: function () { return Promise.resolve({ available: false, channel: "stable" }); },
      setChannel: function () { return Promise.resolve(); },
      verify: function () { return Promise.resolve({ ok: false }); },
      createSnapshot: function () { return Promise.resolve({ ok: false }); },
      listSnapshots: function () { return Promise.resolve([]); },
      rollback: function () { return Promise.resolve({ ok: false }); },
    },
    window: {
      minimize: function () {},
      toggleMaximize: function () {},
      close: function () {},
      hide: function () {},
      isMaximized: function () { return Promise.resolve(false); },
      onMaximizedChange: function () { return function () {}; },
    },
    onBackendStatus: function () { return function () {}; },
    onShortcut: function () { return function () {}; },
    onChatStreamEvent: function () { return function () {}; },
    onOperationProgress: function () { return function () {}; },
    onExternalIntent: function () { return function () {}; },
  };

  window.aether = Object.freeze(aetherApi);
})();
