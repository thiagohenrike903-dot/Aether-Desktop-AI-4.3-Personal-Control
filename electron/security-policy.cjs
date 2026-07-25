"use strict";

const SCREENSHOT_GRANT_TTL_MS = 5_000;
const MAX_SCREENSHOT_GRANT_TTL_MS = 15_000;
const MAX_ROUTE_LENGTH = 8_192;
const MAX_PROJECT_ID_LENGTH = 128;
const PROJECT_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const SAFE_SEGMENT = "[^/]{1,256}";
const SAFE_SCOPE = `${SAFE_SEGMENT}(?:/${SAFE_SEGMENT}){0,5}`;

function route(methods, pattern) {
  return Object.freeze({
    methods: new Set(Array.isArray(methods) ? methods : [methods]),
    pattern,
  });
}

const RENDERER_BACKEND_ROUTES = Object.freeze([
  route("GET", /^\/$/),
  route("GET", /^\/(?:health|capabilities|diagnostics|system)$/),
  route("POST", /^\/(?:chat|command|context\/preview)$/),
  route("GET", /^\/llm\/provider$/),

  route("GET", /^\/operations$/),
  route("POST", /^\/(?:actions|operations)\/execute$/),
  route("GET", new RegExp(`^/operations/${SAFE_SEGMENT}(?:/events)?$`)),
  route("POST", new RegExp(
    `^/operations/${SAFE_SEGMENT}/(?:approve|cancel|retry|undo)$`,
  )),

  route("GET", /^\/safety-mode$/),
  route("PUT", /^\/safety-mode$/),
  route("POST", /^\/safety-mode\/(?:preview|emergency-suspend|resume)$/),
  route("GET", /^\/permissions(?:\/capabilities)?$/),
  route("PUT", new RegExp(`^/permissions/${SAFE_SCOPE}$`)),
  route("DELETE", new RegExp(`^/permissions/${SAFE_SCOPE}$`)),
  route("POST", /^\/permissions\/session\/reset$/),

  route(["GET", "POST"], /^\/model-profiles$/),
  route("PUT", /^\/model-profiles\/active$/),
  route(["PATCH", "DELETE"], new RegExp(`^/model-profiles/${SAFE_SEGMENT}$`)),
  route("POST", new RegExp(
    `^/model-profiles/${SAFE_SEGMENT}/(?:reset-usage|clone)$`,
  )),

  route("GET", /^\/conversations$/),
  route("POST", /^\/conversations$/),
  route(["GET", "PATCH", "DELETE"], new RegExp(
    `^/conversations/${SAFE_SEGMENT}$`,
  )),
  route(["GET", "POST"], new RegExp(
    `^/conversations/${SAFE_SEGMENT}/messages$`,
  )),
  route(["PATCH", "DELETE"], new RegExp(
    `^/conversations/${SAFE_SEGMENT}/messages/${SAFE_SEGMENT}$`,
  )),

  route(["GET", "POST"], /^\/automations$/),
  route(["GET", "PATCH", "DELETE"], new RegExp(
    `^/automations/${SAFE_SEGMENT}$`,
  )),
  route("POST", new RegExp(
    `^/automations/${SAFE_SEGMENT}/(?:simulate|run)$`,
  )),
  route("GET", new RegExp(`^/automations/${SAFE_SEGMENT}/runs$`)),
  route("POST", new RegExp(`^/automations/events/${SAFE_SEGMENT}$`)),

  route("GET", /^\/voices$/),
  route("POST", /^\/tts(?:\/stream)?$/),
  route("GET", /^\/memory\/(?:short|long|sessions|facts|preferences|overview)$/),
  route("POST", /^\/memory\/(?:facts|preferences|project|recall)$/),
  route("DELETE", new RegExp(
    `^/memory/(?:turns|sessions|facts|preferences|project)/${SAFE_SEGMENT}$`,
  )),
  route(["GET", "POST"], /^\/memories$/),
  route(["PATCH", "DELETE"], new RegExp(`^/memories/${SAFE_SEGMENT}$`)),

  route("POST", /^\/vision\/(?:analyze|enroll)$/),
  route("GET", /^\/vision\/faces$/),
  route(["GET", "POST"], /^\/workspace$/),
  route("GET", /^\/workspace\/(?:recent|tree|tasks)$/),
  route("POST", /^\/workspace\/(?:inspect|read|write|create|rename|delete|search|run)$/),
  route("POST", /^\/code\/(?:plan|apply)$/),
  route("GET", /^\/code\/history$/),
  route("POST", new RegExp(
    `^/code/checkpoints/${SAFE_SEGMENT}/undo$`,
  )),
  route("POST", /^\/tasks\/(?:code|validation)$/),
  route("GET", /^\/tasks$/),
  route("GET", new RegExp(`^/tasks/${SAFE_SEGMENT}$`)),
  route("POST", new RegExp(
    `^/tasks/${SAFE_SEGMENT}/(?:control|apply|reject)$`,
  )),

  route(["GET", "POST"], /^\/skills$/),
  route("GET", /^\/skills\/export$/),
  route("POST", /^\/skills\/import$/),
  route(["GET", "PUT", "DELETE"], new RegExp(`^/skills/${SAFE_SEGMENT}$`)),
  route("POST", new RegExp(
    `^/skills/${SAFE_SEGMENT}/(?:duplicate|test)$`,
  )),
  route("POST", new RegExp(
    `^/skills/${SAFE_SEGMENT}/restore/${SAFE_SEGMENT}$`,
  )),

  route("GET", /^\/os\/(?:apps|processes)$/),
  route("GET", /^\/os\/file\/list$/),
  route("POST", /^\/os\/(?:processes\/kill|file|volume|brightness|media|system|app\/open|path\/open|url\/open)$/),
  route("POST", /^\/files\/(?:organize|clean-temp|undo-organize)$/),
  route("POST", /^\/vlm\/analyze$/),
  route("POST", /^\/web\/(?:search|fetch)$/),
  route("POST", /^\/research$/),
  route("POST", /^\/responses\/verify$/),
  route("POST", /^\/documents\/extract$/),

  route("GET", /^\/projects(?:\/capabilities)?$/),
  route("POST", /^\/projects$/),
  route(["GET", "PATCH", "DELETE"], new RegExp(`^/projects/${SAFE_SEGMENT}$`)),
  route(["GET", "PUT", "DELETE"], new RegExp(
    `^/projects/${SAFE_SEGMENT}/safety-policy$`,
  )),
  route("GET", new RegExp(`^/projects/${SAFE_SEGMENT}/documents$`)),
  route("POST", new RegExp(
    `^/projects/${SAFE_SEGMENT}/documents/(?:import|import-folder)$`,
  )),
  route(["GET", "DELETE"], new RegExp(
    `^/projects/${SAFE_SEGMENT}/documents/${SAFE_SEGMENT}$`,
  )),
  route("POST", new RegExp(`^/projects/${SAFE_SEGMENT}/search$`)),
  route("GET", new RegExp(
    `^/projects/${SAFE_SEGMENT}/(?:index-status|duplicates|versions)$`,
  )),
  route("POST", new RegExp(
    `^/projects/${SAFE_SEGMENT}/(?:reindex|semantic-index)$`,
  )),
  route("GET", new RegExp(
    `^/projects/${SAFE_SEGMENT}/documents/${SAFE_SEGMENT}/versions$`,
  )),

  route("POST", /^\/git\/(?:status|log|diff|commit|push|pull|branches|branch\/create|branch\/checkout|merge)$/),
  route("GET", /^\/email\/list$/),
  route("POST", /^\/email\/(?:send|search)$/),
  route(["GET", "POST"], /^\/calendar\/events$/),
  route("DELETE", new RegExp(`^/calendar/events/${SAFE_SEGMENT}$`)),
  route("POST", /^\/weather\/(?:current|forecast)$/),
  route("POST", /^\/pdf\/(?:text|upload-text|tables|extract)$/),
  route("POST", /^\/crypto\/(?:encrypt|decrypt|encrypt-text|decrypt-text)$/),
  route("POST", /^\/backup\/(?:create|restore)$/),
  route("GET", /^\/backup\/list$/),
  route("GET", /^\/plugins$/),
  route("POST", /^\/plugins\/(?:install|run)$/),
  route("POST", new RegExp(
    `^/plugins/(?:load|unload|reload)/${SAFE_SEGMENT}$`,
  )),
  route("GET", /^\/browser\/status$/),
  route("POST", /^\/browser\/(?:navigate|screenshot|click|fill)$/),

  // 4.3 — personalização, governança e transparência.
  route(["GET", "POST"], /^\/experience-profiles$/),
  route("PUT", /^\/experience-profiles\/active$/),
  route(["PATCH", "DELETE"], new RegExp(
    `^/experience-profiles/${SAFE_SEGMENT}$`,
  )),
  route("GET", /^\/connections$/),
  route("POST", /^\/connections\/test$/),
  route("GET", /^\/audit\/(?:export|search|integrity|report|verify)$/),
  route(["GET", "PUT"], /^\/privacy(?:\/mode)?$/),
  route(["GET", "PUT", "DELETE"], new RegExp(
    `^/privacy/conversations/${SAFE_SEGMENT}$`,
  )),
  route("GET", new RegExp(
    `^/privacy/conversations/${SAFE_SEGMENT}/map$`,
  )),
  route("GET", /^\/privacy\/map$/),
  route(["GET", "POST"], /^\/workflows$/),
  route("POST", /^\/workflows\/from-operations$/),
  route(["GET", "PUT", "PATCH", "DELETE"], new RegExp(
    `^/workflows/${SAFE_SEGMENT}$`,
  )),
  route("POST", new RegExp(
    `^/workflows/${SAFE_SEGMENT}/(?:simulate|restore)$`,
  )),
  route("GET", new RegExp(
    `^/workflows/${SAFE_SEGMENT}/(?:revisions|runs)$`,
  )),
  route("POST", new RegExp(
    `^/workflows/${SAFE_SEGMENT}/run$`,
  )),
  route("POST", new RegExp(
    `^/workflows/${SAFE_SEGMENT}/restore/${SAFE_SEGMENT}$`,
  )),
  route(["GET", "POST"], /^\/model-lab\/presets$/),
  route("GET", /^\/model-lab\/runs$/),
  route("GET", new RegExp(`^/model-lab/runs/${SAFE_SEGMENT}$`)),
  route("POST", new RegExp(
    `^/model-lab/runs/${SAFE_SEGMENT}/(?:winner|profile)$`,
  )),
  route("POST", /^\/model-lab\/compare$/),
  route("POST", /^\/system-health\/check$/),
  route("POST", /^\/system-health\/repair$/),
  route("GET", /^\/system-health\/history$/),
  route("POST", /^\/user-backup\/(?:preview|create|restore|validate)$/),
  route("GET", /^\/user-backup$/),
  route("GET", /^\/updates\/(?:status|snapshots)$/),
  route("POST", /^\/updates\/(?:snapshot|rollback)$/),
  route(["GET", "POST"], /^\/evaluations\/cases$/),
  route("GET", /^\/evaluations\/runs$/),
  route(["GET", "POST"], /^\/evaluations\/presets$/),
  route("POST", /^\/evaluations\/(?:run|release-gate)$/),
  route(["GET", "POST"], /^\/simulations$/),
  route("GET", new RegExp(`^/simulations/${SAFE_SEGMENT}$`)),
  route("POST", new RegExp(
    `^/simulations/${SAFE_SEGMENT}/(?:approve|convert)$`,
  )),
  route("GET", /^\/agents\/governance$/),
  route("POST", /^\/agents\/candidates\/validate$/),
  route(["GET", "PUT", "DELETE"], new RegExp(
    `^/safety/projects/${SAFE_SEGMENT}$`,
  )),
  route("GET", /^\/safety\/suspensions$/),
  route("POST", /^\/safety\/(?:suspend-all|resume-all)$/),
  route("POST", new RegExp(
    `^/safety/(?:suspend|resume)/${SAFE_SEGMENT}$`,
  )),
]);

function validatedRoutePath(resourcePath) {
  if (
    typeof resourcePath !== "string" ||
    !resourcePath.startsWith("/") ||
    resourcePath.startsWith("//") ||
    resourcePath.length > MAX_ROUTE_LENGTH ||
    /[\u0000-\u001f\u007f\\]/.test(resourcePath)
  ) {
    throw new Error("Caminho de API inválido.");
  }
  const rawPath = resourcePath.split("?", 1)[0];
  if (/%(?:2e|2f|5c)/i.test(rawPath)) {
    throw new Error("Segmento codificado não permitido no caminho da API.");
  }
  let url;
  try {
    url = new URL(resourcePath, "http://127.0.0.1");
  } catch {
    throw new Error("Caminho de API inválido.");
  }
  if (
    url.origin !== "http://127.0.0.1" ||
    url.username ||
    url.password ||
    url.hash ||
    url.pathname !== rawPath
  ) {
    throw new Error("Caminho de API não permitido.");
  }
  for (const rawSegment of rawPath.split("/").slice(1)) {
    let segment;
    try {
      segment = decodeURIComponent(rawSegment);
    } catch {
      throw new Error("Codificação inválida no caminho da API.");
    }
    if (
      segment === "." ||
      segment === ".." ||
      segment.length > 256 ||
      /[/\\\u0000-\u001f\u007f]/.test(segment)
    ) {
      throw new Error("Segmento não permitido no caminho da API.");
    }
  }
  return url.pathname;
}

function rendererBackendRequestAllowed(methodValue, resourcePath) {
  const method = String(methodValue || "GET").toUpperCase();
  const pathname = validatedRoutePath(resourcePath);
  return RENDERER_BACKEND_ROUTES.some(
    (entry) => entry.methods.has(method) && entry.pattern.test(pathname),
  );
}

function assertRendererBackendRequestAllowed(methodValue, resourcePath) {
  if (!rendererBackendRequestAllowed(methodValue, resourcePath)) {
    const error = new Error(
      "A interface não possui permissão para acessar esta rota local.",
    );
    error.code = "AETHER_BACKEND_ROUTE_BLOCKED";
    throw error;
  }
  return true;
}

function backendConfirmationHeaders(confirmed) {
  return confirmed === true
    ? { "X-Aether-Confirmed": "true" }
    : {};
}

function validatedProjectId(projectId) {
  if (
    projectId === undefined ||
    projectId === null ||
    projectId === ""
  ) {
    return null;
  }
  if (
    typeof projectId !== "string" ||
    projectId.length > MAX_PROJECT_ID_LENGTH ||
    !PROJECT_ID_PATTERN.test(projectId)
  ) {
    const error = new Error("Identificador de projeto inválido.");
    error.code = "AETHER_PROJECT_ID_INVALID";
    throw error;
  }
  return projectId;
}

function backendProjectHeaders(projectId) {
  const validated = validatedProjectId(projectId);
  return validated === null
    ? {}
    : { "X-Aether-Project-Id": validated };
}

class OneShotGrantStore {
  constructor(options = {}) {
    const requestedTtl = Number(options.ttlMs);
    this.ttlMs = Number.isFinite(requestedTtl)
      ? Math.min(Math.max(requestedTtl, 250), MAX_SCREENSHOT_GRANT_TTL_MS)
      : SCREENSHOT_GRANT_TTL_MS;
    this.now = typeof options.now === "function" ? options.now : Date.now;
    this.maximumEntries = Math.min(
      Math.max(Number(options.maximumEntries) || 64, 1),
      1_024,
    );
    this.grants = new Map();
  }

  _key(subject) {
    const key = String(subject ?? "");
    if (!key || key.length > 128) {
      throw new Error("Origem da concessão inválida.");
    }
    return key;
  }

  grant(subject) {
    const key = this._key(subject);
    const grantedAt = this.now();
    this.prune();
    if (!this.grants.has(key) && this.grants.size >= this.maximumEntries) {
      const oldestKey = this.grants.keys().next().value;
      this.grants.delete(oldestKey);
    }
    const record = {
      grantedAt,
      expiresAt: grantedAt + this.ttlMs,
      oneShot: true,
    };
    this.grants.set(key, record);
    return { ok: true, ...record };
  }

  consume(subject) {
    const key = this._key(subject);
    const record = this.grants.get(key);
    this.grants.delete(key);
    if (!record) {
      return {
        ok: false,
        code: "SCREENSHOT_GRANT_REQUIRED",
        reason: "missing",
      };
    }
    if (record.expiresAt <= this.now()) {
      return {
        ok: false,
        code: "SCREENSHOT_GRANT_EXPIRED",
        reason: "expired",
      };
    }
    return { ok: true, ...record };
  }

  status(subject) {
    const key = this._key(subject);
    const record = this.grants.get(key);
    if (!record || record.expiresAt <= this.now()) {
      if (record) {
        this.grants.delete(key);
      }
      return { active: false, expiresAt: null, oneShot: true };
    }
    return {
      active: true,
      expiresAt: record.expiresAt,
      oneShot: true,
    };
  }

  revoke(subject) {
    return this.grants.delete(this._key(subject));
  }

  clear() {
    const cleared = this.grants.size;
    this.grants.clear();
    return cleared;
  }

  prune() {
    const now = this.now();
    for (const [key, record] of this.grants) {
      if (record.expiresAt <= now) {
        this.grants.delete(key);
      }
    }
  }
}

async function runWithScreenshotGrant(grantStore, subject, capture) {
  if (
    !grantStore ||
    typeof grantStore.consume !== "function" ||
    typeof capture !== "function"
  ) {
    throw new TypeError("Política de captura inválida.");
  }
  const grant = grantStore.consume(subject);
  if (!grant.ok) {
    return {
      ok: false,
      blocked: true,
      code: grant.code,
      error:
        grant.reason === "expired"
          ? "A autorização curta para captura expirou."
          : "Autorize a captura por um gesto explícito antes de continuar.",
    };
  }
  return capture();
}

module.exports = {
  MAX_PROJECT_ID_LENGTH,
  MAX_SCREENSHOT_GRANT_TTL_MS,
  OneShotGrantStore,
  PROJECT_ID_PATTERN,
  RENDERER_BACKEND_ROUTES,
  SCREENSHOT_GRANT_TTL_MS,
  assertRendererBackendRequestAllowed,
  backendConfirmationHeaders,
  backendProjectHeaders,
  rendererBackendRequestAllowed,
  runWithScreenshotGrant,
  validatedProjectId,
  validatedRoutePath,
};
