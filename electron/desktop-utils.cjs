"use strict";

const path = require("node:path");
const { StringDecoder } = require("node:string_decoder");

const REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const MAX_SSE_EVENT_BYTES = 1024 * 1024;
const MAX_SSE_STREAM_BYTES = 32 * 1024 * 1024;
const REDACTED_TEXT = "[redigido]";
const SENSITIVE_EXACT_KEYS = new Set([
  "access_key",
  "access_token",
  "api_key",
  "apikey",
  "app_id",
  "appid",
  "auth",
  "auth_token",
  "authorization",
  "client_secret",
  "code",
  "cookie",
  "credential",
  "credentials",
  "id_token",
  "key",
  "oauth_token",
  "password",
  "passwd",
  "private_key",
  "proxy_authorization",
  "refresh_token",
  "security_token",
  "secret",
  "set_cookie",
  "sig",
  "signature",
  "token",
  "x_api_key",
  "x_goog_api_key",
]);
const SENSITIVE_KEY_PARTS = [
  "access_key",
  "api_key",
  "apikey",
  "authorization",
  "cookie",
  "credential",
  "password",
  "passwd",
  "private_key",
  "secret",
  "signature",
  "token",
];
const EMBEDDED_HTTP_URL_PATTERN = /https?:\/\/[^\s<>"']+/gi;
const TRAILING_URL_PUNCTUATION = ".,;:!?)]}";

function isValidRequestId(value) {
  return typeof value === "string" && REQUEST_ID_PATTERN.test(value);
}

function cleanText(value, maximumLength, fallback = "") {
  if (typeof value !== "string") {
    return fallback;
  }
  const cleaned = value
    .replace(/\0/g, "")
    .replace(/\r\n?/g, "\n")
    .trim();
  return cleaned.slice(0, maximumLength) || fallback;
}

function normaliseSecretKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function isSensitiveKey(value) {
  const normalised = normaliseSecretKey(value);
  return (
    SENSITIVE_EXACT_KEYS.has(normalised) ||
    SENSITIVE_KEY_PARTS.some((part) => normalised.includes(part)) ||
    normalised.endsWith("_key")
  );
}

function redactEmbeddedHttpUrl(value) {
  let candidate = value;
  let trailing = "";
  while (
    candidate &&
    TRAILING_URL_PUNCTUATION.includes(candidate[candidate.length - 1])
  ) {
    const closing = candidate[candidate.length - 1];
    const opening = { ")": "(", "]": "[", "}": "{" }[closing];
    if (
      opening &&
      candidate.split(opening).length >= candidate.split(closing).length
    ) {
      break;
    }
    trailing = closing + trailing;
    candidate = candidate.slice(0, -1);
  }

  let url;
  try {
    url = new URL(candidate);
  } catch {
    return value;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return value;
  }
  url.username = "";
  url.password = "";
  for (const key of [...new Set(url.searchParams.keys())]) {
    if (isSensitiveKey(key)) {
      url.searchParams.set(key, REDACTED_TEXT);
    }
  }
  const serialised = url.toString().replace(
    /%5Bredigido%5D/gi,
    REDACTED_TEXT,
  );
  return `${serialised}${trailing}`;
}

function redactSensitiveText(value) {
  let text = String(value ?? "").replace(
    /(https?:\/\/)[^/\s?#]+@/gi,
    "$1",
  );
  text = text.replace(
    /([?&;#])([^=&;\s]+)=([^&;\s<>"'#]+)/g,
    (match, separator, rawKey) => {
      let decodedKey = rawKey;
      try {
        decodedKey = decodeURIComponent(rawKey.replace(/\+/g, " "));
      } catch {
        // A malformed key is compared in its raw form.
      }
      return isSensitiveKey(decodedKey)
        ? `${separator}${rawKey}=${REDACTED_TEXT}`
        : match;
    },
  );
  text = text.replace(
    EMBEDDED_HTTP_URL_PATTERN,
    redactEmbeddedHttpUrl,
  );
  text = text.replace(
    /\b(authorization|proxy[_-]?authorization)\b(["']?\s*[:=]\s*)(?:"[^\r\n"]*"|'[^\r\n']*'|[^\r\n,;]+)/gi,
    `$1$2${REDACTED_TEXT}`,
  );
  text = text.replace(
    /\b(cookie|set[_-]?cookie)\b(["']?\s*[:=]\s*)(?:"[^\r\n"]*"|'[^\r\n']*'|[^\r\n,]+)/gi,
    `$1$2${REDACTED_TEXT}`,
  );
  text = text.replace(
    /(--(?:api[_-]?key|app[_-]?id|appid|authorization|client[_-]?secret|cookie|key|password|passwd|private[_-]?key|secret|token)\b(?:\s*=\s*|\s+))(?:(?:bearer|basic)\s+)?(?:"[^\r\n"]*"|'[^\r\n']*'|[^\s,;]+)/gi,
    `$1${REDACTED_TEXT}`,
  );
  text = text.replace(
    /\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{4,}/gi,
    `$1 ${REDACTED_TEXT}`,
  );
  text = text.replace(
    /\b(client[_ -]?secret|refresh[_ -]?token|access[_ -]?token|id[_ -]?token|security[_ -]?token|api[_ -]?key|x[_ -]?api[_ -]?key|x[_ -]?goog[_ -]?api[_ -]?key|private[_ -]?key|access[_ -]?key|app[_ -]?id|appid|password|passwd|secret|token|signature|credential|auth|key)\b(["']?\s*[:=]\s*)(?!\[redigido\])("[^\r\n"]*"|'[^\r\n']*'|[^\s,;&]+)/gi,
    `$1$2${REDACTED_TEXT}`,
  );
  return text.replace(
    /\b(sk-[A-Za-z0-9_-]{4,}|ghp_[A-Za-z0-9_]{4,}|github_pat_[A-Za-z0-9_]{4,}|AIza[A-Za-z0-9_-]{4,})\b/g,
    REDACTED_TEXT,
  );
}

function createRedactingLineBuffer(onRecord, options = {}) {
  if (typeof onRecord !== "function") {
    throw new TypeError("onRecord precisa ser uma função.");
  }
  const maximumPendingChars = Number.isFinite(options.maximumPendingChars)
    ? Math.max(1_024, options.maximumPendingChars)
    : 1024 * 1024;
  const decoder = new StringDecoder("utf8");
  let pending = "";
  let discardingOversizedLine = false;
  let finished = false;

  function emit(record) {
    if (record) {
      onRecord(redactSensitiveText(record));
    }
  }

  function drainCompleteLines() {
    let boundary = pending.indexOf("\n");
    while (boundary !== -1) {
      emit(pending.slice(0, boundary + 1));
      pending = pending.slice(boundary + 1);
      boundary = pending.indexOf("\n");
    }
    if (pending.length > maximumPendingChars) {
      emit("[linha de log omitida por exceder o limite seguro]\n");
      pending = "";
      discardingOversizedLine = true;
    }
  }

  function accept(text) {
    if (discardingOversizedLine) {
      const boundary = text.indexOf("\n");
      if (boundary === -1) {
        return;
      }
      discardingOversizedLine = false;
      text = text.slice(boundary + 1);
    }
    pending += text;
    drainCompleteLines();
  }

  return Object.freeze({
    push(chunk) {
      if (finished) {
        throw new Error("O buffer de log já foi encerrado.");
      }
      const text = typeof chunk === "string"
        ? chunk
        : decoder.write(Buffer.from(chunk));
      accept(text);
    },
    finish() {
      if (finished) {
        return;
      }
      finished = true;
      accept(decoder.end());
      if (!discardingOversizedLine) {
        emit(pending);
      }
      pending = "";
    },
    get pendingLength() {
      return pending.length;
    },
  });
}

function normaliseAccelerator(value) {
  if (value === null || value === false || value === "") {
    return null;
  }
  if (typeof value !== "string") {
    throw new TypeError("O atalho precisa ser uma combinação de teclas.");
  }

  const accelerator = value.trim();
  if (
    accelerator.length < 3 ||
    accelerator.length > 96 ||
    /[\0\r\n\t]/.test(accelerator)
  ) {
    throw new Error("Atalho global inválido.");
  }
  return accelerator;
}

function normaliseProgressValue(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  const scaled = numeric > 1 ? numeric / 100 : numeric;
  return Math.min(1, Math.max(0, scaled));
}

function selectDesktopActivityState(backendState, activeRequestCount = 0) {
  const active = Number.isFinite(Number(activeRequestCount))
    ? Math.max(0, Number(activeRequestCount))
    : 0;
  if (backendState === "starting" || active > 0) {
    return "working";
  }
  return backendState === "ready" ? "online" : "offline";
}

function constrainWindowState(value, workAreas, options = {}) {
  const source =
    value && typeof value === "object" && !Array.isArray(value)
      ? value
      : {};
  const areas = (Array.isArray(workAreas) ? workAreas : [])
    .map((item) => item?.workArea || item)
    .filter((item) => (
      item &&
      Number.isFinite(Number(item.x)) &&
      Number.isFinite(Number(item.y)) &&
      Number.isFinite(Number(item.width)) &&
      Number.isFinite(Number(item.height)) &&
      Number(item.width) > 0 &&
      Number(item.height) > 0
    ))
    .map((item) => ({
      x: Math.round(Number(item.x)),
      y: Math.round(Number(item.y)),
      width: Math.round(Number(item.width)),
      height: Math.round(Number(item.height)),
    }));
  if (areas.length === 0) {
    return null;
  }

  const defaultWidth = Math.max(320, Number(options.defaultWidth) || 1_440);
  const defaultHeight = Math.max(240, Number(options.defaultHeight) || 920);
  const minimumWidth = Math.max(320, Number(options.minimumWidth) || 900);
  const minimumHeight = Math.max(240, Number(options.minimumHeight) || 640);
  const rawWidth = Number.isFinite(Number(source.width))
    ? Number(source.width)
    : defaultWidth;
  const rawHeight = Number.isFinite(Number(source.height))
    ? Number(source.height)
    : defaultHeight;
  const hasPosition =
    Number.isFinite(Number(source.x)) &&
    Number.isFinite(Number(source.y));
  const rawBounds = {
    x: hasPosition ? Number(source.x) : 0,
    y: hasPosition ? Number(source.y) : 0,
    width: Math.max(1, rawWidth),
    height: Math.max(1, rawHeight),
  };

  function overlapArea(first, second) {
    const width = Math.max(
      0,
      Math.min(first.x + first.width, second.x + second.width) -
        Math.max(first.x, second.x),
    );
    const height = Math.max(
      0,
      Math.min(first.y + first.height, second.y + second.height) -
        Math.max(first.y, second.y),
    );
    return width * height;
  }

  let target = areas[0];
  let visibleArea = 0;
  if (hasPosition) {
    for (const area of areas) {
      const overlap = overlapArea(rawBounds, area);
      if (overlap > visibleArea) {
        visibleArea = overlap;
        target = area;
      }
    }
  }
  if (visibleArea < 64 * 64) {
    target = areas[0];
  }

  const lowerWidth = Math.min(minimumWidth, target.width);
  const lowerHeight = Math.min(minimumHeight, target.height);
  const width = Math.round(
    Math.min(target.width, Math.max(lowerWidth, rawWidth)),
  );
  const height = Math.round(
    Math.min(target.height, Math.max(lowerHeight, rawHeight)),
  );
  const fallbackX = target.x + Math.round((target.width - width) / 2);
  const fallbackY = target.y + Math.round((target.height - height) / 2);
  const requestedX =
    hasPosition && visibleArea >= 64 * 64 ? Number(source.x) : fallbackX;
  const requestedY =
    hasPosition && visibleArea >= 64 * 64 ? Number(source.y) : fallbackY;
  const x = Math.round(
    Math.min(
      target.x + target.width - width,
      Math.max(target.x, requestedX),
    ),
  );
  const y = Math.round(
    Math.min(
      target.y + target.height - height,
      Math.max(target.y, requestedY),
    ),
  );

  return {
    x,
    y,
    width,
    height,
    maximized: source.maximized === true,
  };
}

function sanitiseDialogFilters(filters) {
  if (!Array.isArray(filters)) {
    return [];
  }

  return filters.slice(0, 12).flatMap((filter) => {
    if (!filter || typeof filter !== "object") {
      return [];
    }
    const name = cleanText(filter.name, 80);
    const extensions = Array.isArray(filter.extensions)
      ? filter.extensions
        .slice(0, 32)
        .map((extension) => String(extension || "").trim().toLowerCase())
        .filter((extension) => (
          extension === "*" ||
          /^[a-z0-9][a-z0-9_-]{0,15}$/.test(extension)
        ))
      : [];
    if (!name || extensions.length === 0) {
      return [];
    }
    return [{ name, extensions: [...new Set(extensions)] }];
  });
}

function sanitiseDeepLink(urlValue) {
  if (typeof urlValue !== "string" || urlValue.length > 12_000) {
    return null;
  }

  let url;
  try {
    url = new URL(urlValue);
  } catch {
    return null;
  }
  if (url.protocol !== "aether:" || url.username || url.password) {
    return null;
  }

  const action = (url.hostname || url.pathname.split("/").filter(Boolean)[0] || "")
    .toLowerCase();
  if (action === "new" || action === "new-chat") {
    return { type: "new-chat", source: "deep-link" };
  }
  if (action === "settings") {
    return { type: "open-settings", source: "deep-link" };
  }
  if (action === "ask" || action === "open") {
    const text = cleanText(url.searchParams.get("text"), 8_192);
    if (!text) {
      return null;
    }
    return { type: "ask-text", text, source: "deep-link" };
  }
  return null;
}

function extractExternalIntents(argv, options = {}) {
  if (!Array.isArray(argv)) {
    return [];
  }

  const intents = [];
  const existingFile = typeof options.existingFile === "function"
    ? options.existingFile
    : () => false;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = String(argv[index] || "");
    if (argument.startsWith("aether:")) {
      const intent = sanitiseDeepLink(argument);
      if (intent) {
        intents.push(intent);
      }
      continue;
    }

    let candidate = null;
    if (argument === "--ask-file") {
      candidate = argv[index + 1];
      index += 1;
    } else if (argument.startsWith("--ask-file=")) {
      candidate = argument.slice("--ask-file=".length);
    }
    if (!candidate || typeof candidate !== "string") {
      continue;
    }

    const absolutePath = path.resolve(candidate);
    if (existingFile(absolutePath)) {
      intents.push({
        type: "ask-file",
        paths: [absolutePath],
        source: "command-line",
      });
    }
  }
  return intents.slice(0, 8);
}

function createSseParser(onEvent, options = {}) {
  if (typeof onEvent !== "function") {
    throw new TypeError("onEvent precisa ser uma função.");
  }

  const maximumEventBytes = Number.isFinite(options.maximumEventBytes)
    ? options.maximumEventBytes
    : MAX_SSE_EVENT_BYTES;
  const maximumStreamBytes = Number.isFinite(options.maximumStreamBytes)
    ? options.maximumStreamBytes
    : MAX_SSE_STREAM_BYTES;
  let buffer = "";
  let streamBytes = 0;
  const decoder = new StringDecoder("utf8");

  function dispatch(frame) {
    if (!frame || frame.startsWith(":")) {
      return;
    }
    if (Buffer.byteLength(frame, "utf8") > maximumEventBytes) {
      throw new Error("Um evento de streaming excedeu o limite permitido.");
    }

    let eventName = "message";
    let eventId = null;
    const dataLines = [];
    for (const rawLine of frame.split("\n")) {
      const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
      if (!line || line.startsWith(":")) {
        continue;
      }
      const separator = line.indexOf(":");
      const field = separator === -1 ? line : line.slice(0, separator);
      let value = separator === -1 ? "" : line.slice(separator + 1);
      if (value.startsWith(" ")) {
        value = value.slice(1);
      }
      if (field === "event") {
        eventName = cleanText(value, 80, "message");
      } else if (field === "id" && !value.includes("\0")) {
        eventId = cleanText(value, 256) || null;
      } else if (field === "data") {
        dataLines.push(value);
      }
    }
    if (dataLines.length === 0) {
      return;
    }

    const dataText = dataLines.join("\n");
    let data = dataText;
    try {
      data = JSON.parse(dataText);
    } catch {
      // SSE permits plain text. The renderer receives it as text without eval.
    }
    onEvent({ event: eventName, id: eventId, data });
  }

  return Object.freeze({
    push(chunk) {
      const text = typeof chunk === "string"
        ? chunk
        : decoder.write(Buffer.from(chunk));
      streamBytes += typeof chunk === "string"
        ? Buffer.byteLength(chunk, "utf8")
        : Buffer.byteLength(Buffer.from(chunk));
      if (streamBytes > maximumStreamBytes) {
        throw new Error("O streaming excedeu o limite total permitido.");
      }
      buffer += text.replace(/\r\n|\r/g, "\n");

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        dispatch(frame);
        boundary = buffer.indexOf("\n\n");
      }
      if (Buffer.byteLength(buffer, "utf8") > maximumEventBytes) {
        throw new Error("Um evento de streaming excedeu o limite permitido.");
      }
    },
    finish() {
      buffer += decoder.end();
      if (buffer.trim()) {
        dispatch(buffer);
      }
      buffer = "";
    },
    get bytesRead() {
      return streamBytes;
    },
  });
}

module.exports = Object.freeze({
  MAX_SSE_EVENT_BYTES,
  MAX_SSE_STREAM_BYTES,
  cleanText,
  constrainWindowState,
  createRedactingLineBuffer,
  createSseParser,
  extractExternalIntents,
  isValidRequestId,
  normaliseAccelerator,
  normaliseProgressValue,
  redactSensitiveText,
  sanitiseDeepLink,
  sanitiseDialogFilters,
  selectDesktopActivityState,
});
