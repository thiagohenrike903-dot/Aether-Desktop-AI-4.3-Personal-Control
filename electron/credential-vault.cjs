"use strict";

const fs = require("node:fs");
const path = require("node:path");

const VAULT_VERSION = 2;
const MAX_SECRET_BYTES = 16_384;
const DEFAULT_TEMPORARY_TTL_MS = 15 * 60 * 1000;
const MAX_TEMPORARY_TTL_MS = 24 * 60 * 60 * 1000;
const PERSISTED_POLICIES = new Set(["always", "temporary", "blocked"]);
const ALL_POLICIES = new Set([...PERSISTED_POLICIES, "session"]);
const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

function isPlainObject(value) {
  return Boolean(
    value &&
    typeof value === "object" &&
    !Array.isArray(value),
  );
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function isoTimestamp(value) {
  if (value === null || value === undefined || typeof value === "boolean") {
    return null;
  }
  const timestamp = Number(value);
  if (!Number.isFinite(timestamp)) {
    return null;
  }
  return new Date(timestamp).toISOString();
}

function parseTimestamp(value) {
  if (typeof value !== "string" || value.length > 64) {
    return null;
  }
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : null;
}

function normaliseIdentifier(value, label) {
  const identifier = String(value || "").trim();
  if (!IDENTIFIER_PATTERN.test(identifier)) {
    throw new Error(`${label} inválido.`);
  }
  return identifier;
}

function grantId(secretKey, integration) {
  return `${secretKey}:${integration}`;
}

function emptyDocument() {
  return {
    version: VAULT_VERSION,
    secrets: {},
    grants: {},
  };
}

function atomicWritePrivateFile(destination, data) {
  const directory = path.dirname(destination);
  const temporary = path.join(
    directory,
    `.${path.basename(destination)}.${process.pid}.${Math.random()
      .toString(16)
      .slice(2)}.tmp`,
  );
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  try {
    fs.writeFileSync(temporary, data, { flag: "wx", mode: 0o600 });
    fs.renameSync(temporary, destination);
    try {
      fs.chmodSync(destination, 0o600);
    } catch {
      // Windows applies ACLs independently from POSIX mode bits.
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

function assertVaultPathSafe(filePath) {
  const directory = path.dirname(filePath);
  for (const [filename, expectedType] of [
    [directory, "directory"],
    [filePath, "file"],
  ]) {
    let stat;
    try {
      stat = fs.lstatSync(filename);
    } catch (error) {
      if (error?.code === "ENOENT") {
        continue;
      }
      throw error;
    }
    if (
      stat.isSymbolicLink() ||
      (expectedType === "directory" && !stat.isDirectory()) ||
      (expectedType === "file" && !stat.isFile())
    ) {
      throw new Error("O caminho do cofre seguro não é um arquivo regular.");
    }
  }
}

function secureOnlyCredentialEnvironment(
  environmentValue,
  secureOnlyKeys = [],
) {
  const environment = { ...(environmentValue || {}) };
  for (const environmentKey of secureOnlyKeys) {
    delete environment[String(environmentKey)];
  }
  return environment;
}

function withoutManagedCredentialEnvironment(
  environmentValue,
  managedEnvironmentKeys = [],
  additionalBlockedKeys = [],
) {
  const environment = { ...(environmentValue || {}) };
  const blockedKeys = new Set([
    ...managedEnvironmentKeys,
    ...managedEnvironmentKeys.map(
      (environmentKey) => `AETHER_SECURE_${environmentKey}`,
    ),
    ...additionalBlockedKeys,
  ].map((environmentKey) => String(environmentKey).toUpperCase()));
  for (const environmentKey of Object.keys(environment)) {
    if (blockedKeys.has(environmentKey.toUpperCase())) {
      delete environment[environmentKey];
    }
  }
  return environment;
}

class CredentialVaultStore {
  constructor(options = {}) {
    if (!options.filePath || typeof options.filePath !== "string") {
      throw new TypeError("filePath é obrigatório para o cofre.");
    }
    if (!isPlainObject(options.environmentKeys)) {
      throw new TypeError("environmentKeys é obrigatório para o cofre.");
    }
    this.filePath = options.filePath;
    this.environmentKeys = Object.freeze({ ...options.environmentKeys });
    this.restrictedIntegrations = new Map(
      Object.entries(options.restrictedIntegrations || {})
        .filter(([key]) => Object.hasOwn(this.environmentKeys, key))
        .map(([key, integrations]) => [
          key,
          new Set(
            (Array.isArray(integrations) ? integrations : [])
              .map((integration) =>
                normaliseIdentifier(integration, "Integração")),
          ),
        ]),
    );
    this.safeStorage = options.safeStorage;
    this.now = typeof options.now === "function" ? options.now : Date.now;
    this.writeFile =
      typeof options.writeFile === "function"
        ? options.writeFile
        : atomicWritePrivateFile;
    this.logger = options.logger || console;
    this.platform = options.platform || process.platform;
    this.sessionGrants = new Map();
  }

  storageBackend() {
    try {
      return this.safeStorage?.getSelectedStorageBackend?.() || null;
    } catch {
      return null;
    }
  }

  available() {
    try {
      if (!this.safeStorage?.isEncryptionAvailable?.()) {
        return false;
      }
      return !(
        this.platform === "linux" &&
        this.storageBackend() === "basic_text"
      );
    } catch {
      return false;
    }
  }

  _assertSecretKey(value) {
    const key = normaliseIdentifier(value, "Tipo de credencial");
    if (!Object.hasOwn(this.environmentKeys, key)) {
      throw new Error("Tipo de credencial não permitido.");
    }
    return key;
  }

  _assertIntegration(secretKey, value) {
    const integration = normaliseIdentifier(value, "Integração");
    const allowed = this.restrictedIntegrations.get(secretKey);
    if (allowed && !allowed.has(integration)) {
      throw new Error("Esta credencial não pode autorizar essa integração.");
    }
    return integration;
  }

  _normaliseDocument(parsed) {
    const document = emptyDocument();
    let migrated = false;

    if (!isPlainObject(parsed)) {
      return { document, migrated };
    }

    if (parsed.version !== VAULT_VERSION) {
      if (
        parsed.version !== undefined &&
        parsed.version !== 1
      ) {
        throw new Error("Versão do cofre de credenciais não suportada.");
      }
      const migratedAt = isoTimestamp(this.now());
      for (const [key, value] of Object.entries(parsed)) {
        if (
          Object.hasOwn(this.environmentKeys, key) &&
          typeof value === "string" &&
          value.length > 0 &&
          Buffer.byteLength(value, "utf8") <= MAX_SECRET_BYTES
        ) {
          document.secrets[key] = {
            value,
            updatedAt: migratedAt,
          };
          if (!this.restrictedIntegrations.has(key)) {
            const integration = key;
            document.grants[grantId(key, integration)] = {
              secretKey: key,
              integration,
              policy: "always",
              grantedAt: migratedAt,
              updatedAt: migratedAt,
              expiresAt: null,
            };
          }
          migrated = true;
        }
      }
      return { document, migrated };
    }

    if (isPlainObject(parsed.secrets)) {
      for (const [key, record] of Object.entries(parsed.secrets)) {
        const value = isPlainObject(record) ? record.value : null;
        if (
          Object.hasOwn(this.environmentKeys, key) &&
          typeof value === "string" &&
          value.length > 0 &&
          Buffer.byteLength(value, "utf8") <= MAX_SECRET_BYTES
        ) {
          document.secrets[key] = {
            value,
            updatedAt:
              isoTimestamp(parseTimestamp(record.updatedAt)) ||
              isoTimestamp(this.now()),
          };
        }
      }
    }

    if (isPlainObject(parsed.grants)) {
      for (const record of Object.values(parsed.grants)) {
        if (!isPlainObject(record)) {
          continue;
        }
        let secretKey;
        let integration;
        try {
          secretKey = this._assertSecretKey(record.secretKey);
          integration = this._assertIntegration(
            secretKey,
            record.integration,
          );
        } catch {
          continue;
        }
        const policy = String(record.policy || "");
        if (!PERSISTED_POLICIES.has(policy)) {
          continue;
        }
        const expiresAt = policy === "temporary"
          ? parseTimestamp(record.expiresAt)
          : null;
        if (policy === "temporary" && expiresAt === null) {
          continue;
        }
        const grantedAt =
          isoTimestamp(parseTimestamp(record.grantedAt)) ||
          isoTimestamp(this.now());
        document.grants[grantId(secretKey, integration)] = {
          secretKey,
          integration,
          policy,
          grantedAt,
          updatedAt:
            isoTimestamp(parseTimestamp(record.updatedAt)) || grantedAt,
          expiresAt: expiresAt === null ? null : isoTimestamp(expiresAt),
        };
      }
    }
    return { document, migrated };
  }

  _read(options = {}) {
    if (!this.available()) {
      if (options.strict) {
        throw new Error("A criptografia segura do sistema não está disponível.");
      }
      return emptyDocument();
    }

    try {
      assertVaultPathSafe(this.filePath);
      const encrypted = fs.readFileSync(this.filePath);
      const clearText = this.safeStorage.decryptString(encrypted);
      const { document, migrated } = this._normaliseDocument(
        JSON.parse(clearText),
      );
      if (migrated) {
        this._write(document);
      }
      return document;
    } catch (error) {
      if (error?.code === "ENOENT") {
        return emptyDocument();
      }
      this.logger?.warn?.(
        "[credentials] O cofre não pôde ser aberto.",
      );
      if (options.strict) {
        throw new Error(
          "O cofre de credenciais existente não pôde ser descriptografado.",
        );
      }
      return emptyDocument();
    }
  }

  _write(document) {
    if (!this.available()) {
      throw new Error("A criptografia segura do sistema não está disponível.");
    }
    const normalised = this._normaliseDocument(document).document;
    const encrypted = this.safeStorage.encryptString(
      JSON.stringify(normalised),
    );
    assertVaultPathSafe(this.filePath);
    this.writeFile(this.filePath, encrypted);
  }

  _writeOrRemove(document) {
    if (
      Object.keys(document.secrets).length > 0 ||
      Object.keys(document.grants).length > 0
    ) {
      this._write(document);
      return;
    }
    try {
      fs.unlinkSync(this.filePath);
    } catch (error) {
      if (error?.code !== "ENOENT") {
        throw error;
      }
    }
  }

  _effective(record) {
    if (!record || record.policy === "blocked") {
      return false;
    }
    if (record.policy === "temporary") {
      const expiresAt = parseTimestamp(record.expiresAt);
      return expiresAt !== null && expiresAt > this.now();
    }
    return record.policy === "always" || record.policy === "session";
  }

  setSecret(keyValue, secretValue, options = {}) {
    const key = this._assertSecretKey(keyValue);
    const value = String(secretValue || "").trim();
    if (
      value.length < 8 ||
      Buffer.byteLength(value, "utf8") > MAX_SECRET_BYTES
    ) {
      throw new Error("A credencial parece incompleta ou excede o limite.");
    }

    const document = this._read({ strict: true });
    const timestamp = isoTimestamp(this.now());
    document.secrets[key] = { value, updatedAt: timestamp };
    const defaultId = grantId(key, key);
    if (
      options.authorizeDefault !== false &&
      !this.restrictedIntegrations.has(key) &&
      !document.grants[defaultId] &&
      !this.sessionGrants.has(defaultId)
    ) {
      document.grants[defaultId] = {
        secretKey: key,
        integration: key,
        policy: "always",
        grantedAt: timestamp,
        updatedAt: timestamp,
        expiresAt: null,
      };
    }
    this._write(document);
    return {
      ok: true,
      key,
      configured: true,
      valueReturned: false,
    };
  }

  deleteSecret(keyValue) {
    const key = this._assertSecretKey(keyValue);
    const document = this._read({ strict: true });
    const removed = Object.hasOwn(document.secrets, key);
    delete document.secrets[key];
    for (const [id, record] of Object.entries(document.grants)) {
      if (record.secretKey === key) {
        delete document.grants[id];
      }
    }
    for (const [id, record] of this.sessionGrants) {
      if (record.secretKey === key) {
        this.sessionGrants.delete(id);
      }
    }
    this._writeOrRemove(document);
    return { ok: true, key, removed };
  }

  authorize(payload = {}) {
    const key = this._assertSecretKey(payload.key);
    const integration = this._assertIntegration(
      key,
      payload.integration || key,
    );
    const policy = String(payload.policy || "session").toLowerCase();
    if (!ALL_POLICIES.has(policy)) {
      throw new Error("Política de credencial não permitida.");
    }

    const document = this._read({ strict: true });
    if (policy !== "blocked" && !document.secrets[key]) {
      throw new Error("Configure a credencial antes de autorizá-la.");
    }
    const id = grantId(key, integration);
    const timestamp = this.now();
    const grantedAt = isoTimestamp(timestamp);
    let expiresAt = null;
    if (policy === "temporary") {
      const explicitExpiry = parseTimestamp(payload.expiresAt);
      const requestedTtl = Number(payload.ttlMs);
      const ttlMs = Number.isFinite(requestedTtl)
        ? Math.min(Math.max(requestedTtl, 1_000), MAX_TEMPORARY_TTL_MS)
        : DEFAULT_TEMPORARY_TTL_MS;
      const candidate = explicitExpiry ?? timestamp + ttlMs;
      expiresAt = Math.min(
        Math.max(candidate, timestamp + 1_000),
        timestamp + MAX_TEMPORARY_TTL_MS,
      );
    }
    const record = {
      secretKey: key,
      integration,
      policy,
      grantedAt,
      updatedAt: grantedAt,
      expiresAt: expiresAt === null ? null : isoTimestamp(expiresAt),
    };

    delete document.grants[id];
    this.sessionGrants.delete(id);
    if (policy === "session") {
      this._write(document);
      this.sessionGrants.set(id, record);
    } else {
      document.grants[id] = record;
      this._write(document);
    }
    return {
      ok: true,
      ...record,
      effective: this._effective(record),
      persisted: policy !== "session",
      valueReturned: false,
    };
  }

  revoke(payload = {}) {
    const key = this._assertSecretKey(payload.key);
    const integration = payload.integration == null
      ? null
      : normaliseIdentifier(payload.integration, "Integração");
    const document = this._read({ strict: true });
    let revoked = 0;
    for (const [id, record] of Object.entries(document.grants)) {
      if (
        record.secretKey === key &&
        (integration === null || record.integration === integration)
      ) {
        delete document.grants[id];
        revoked += 1;
      }
    }
    for (const [id, record] of this.sessionGrants) {
      if (
        record.secretKey === key &&
        (integration === null || record.integration === integration)
      ) {
        this.sessionGrants.delete(id);
        revoked += 1;
      }
    }
    this._writeOrRemove(document);
    return {
      ok: true,
      key,
      integration,
      revoked,
      valueReturned: false,
    };
  }

  clearSessionGrants() {
    const cleared = this.sessionGrants.size;
    this.sessionGrants.clear();
    return cleared;
  }

  effectiveSecrets() {
    const document = this._read();
    const allGrants = new Map(Object.entries(document.grants));
    for (const [id, record] of this.sessionGrants) {
      allGrants.set(id, record);
    }
    const effectiveKeys = new Set();
    for (const record of allGrants.values()) {
      if (this._effective(record)) {
        effectiveKeys.add(record.secretKey);
      }
    }
    const secrets = {};
    for (const key of effectiveKeys) {
      const record = document.secrets[key];
      if (record?.value) {
        secrets[key] = record.value;
      }
    }
    return secrets;
  }

  environment() {
    const environment = {};
    for (const [key, value] of Object.entries(this.effectiveSecrets())) {
      const environmentKey = this.environmentKeys[key];
      if (!environmentKey) {
        continue;
      }
      environment[environmentKey] = value;
      environment[`AETHER_SECURE_${environmentKey}`] = value;
    }
    return environment;
  }

  status() {
    let document = emptyDocument();
    let readable = true;
    try {
      document = this._read({ strict: true });
    } catch {
      readable = false;
    }
    const persisted = Object.values(document.grants).map((record) => ({
      ...record,
      source: "vault",
    }));
    const session = [...this.sessionGrants.values()].map((record) => ({
      ...record,
      source: "session",
    }));
    const grants = [...persisted, ...session]
      .map((record) => ({
        secretKey: record.secretKey,
        integration: record.integration,
        policy: record.policy,
        grantedAt: record.grantedAt,
        updatedAt: record.updatedAt,
        expiresAt: record.expiresAt,
        source: record.source,
        configured: Boolean(document.secrets[record.secretKey]),
        effective:
          Boolean(document.secrets[record.secretKey]) &&
          this._effective(record),
      }))
      .sort((first, second) => (
        `${first.secretKey}:${first.integration}`.localeCompare(
          `${second.secretKey}:${second.integration}`,
        )
      ));

    return {
      available: this.available(),
      encrypted: this.available(),
      readable,
      storageBackend: this.storageBackend(),
      version: VAULT_VERSION,
      configured: Object.fromEntries(
        Object.keys(this.environmentKeys)
          .map((key) => [key, Boolean(document.secrets[key])]),
      ),
      grants: cloneJson(grants),
      valuesExposed: false,
    };
  }
}

module.exports = {
  ALL_POLICIES,
  CredentialVaultStore,
  DEFAULT_TEMPORARY_TTL_MS,
  MAX_TEMPORARY_TTL_MS,
  VAULT_VERSION,
  assertVaultPathSafe,
  atomicWritePrivateFile,
  secureOnlyCredentialEnvironment,
  withoutManagedCredentialEnvironment,
};
