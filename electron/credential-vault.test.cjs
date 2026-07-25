"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const {
  CredentialVaultStore,
  VAULT_VERSION,
  secureOnlyCredentialEnvironment,
  withoutManagedCredentialEnvironment,
} = require("./credential-vault.cjs");

const ENVIRONMENT_KEYS = Object.freeze({
  gemini: "GEMINI_API_KEY",
  weather: "WEATHER_API_KEY",
  GMAIL_OAUTH_TOKEN_JSON: "GMAIL_OAUTH_TOKEN_JSON",
});
const RESTRICTED_INTEGRATIONS = Object.freeze({
  GMAIL_OAUTH_TOKEN_JSON: Object.freeze(["gmail"]),
});

function fakeSafeStorage() {
  const transform = (value) => Buffer.from(value)
    .map((byte) => byte ^ 0xa5);
  return {
    isEncryptionAvailable: () => true,
    getSelectedStorageBackend: () => "kwallet",
    encryptString: (value) => transform(Buffer.from(value, "utf8")),
    decryptString: (value) =>
      transform(Buffer.from(value)).toString("utf8"),
  };
}

function fixture(t, options = {}) {
  const directory = fs.mkdtempSync(
    path.join(os.tmpdir(), "aether-vault-test-"),
  );
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const clock = { value: options.now ?? Date.parse("2026-07-24T10:00:00Z") };
  const filePath = path.join(directory, "credentials.safe");
  const storage = fakeSafeStorage();
  const create = () => new CredentialVaultStore({
    filePath,
    environmentKeys: ENVIRONMENT_KEYS,
    restrictedIntegrations: RESTRICTED_INTEGRATIONS,
    safeStorage: storage,
    platform: "linux",
    now: () => clock.value,
    logger: { warn: () => {} },
  });
  return { clock, create, directory, filePath, storage };
}

function readEncryptedDocument(filePath, storage) {
  return JSON.parse(
    storage.decryptString(fs.readFileSync(filePath)),
  );
}

test("legacy flat vault migrates to secrets and per-integration grants", (t) => {
  const current = fixture(t);
  fs.writeFileSync(
    current.filePath,
    current.storage.encryptString(JSON.stringify({
      gemini: "legacy-secret-value",
      unsupported: "must-not-survive",
    })),
  );

  const vault = current.create();
  const status = vault.status();
  const migrated = readEncryptedDocument(
    current.filePath,
    current.storage,
  );

  assert.equal(migrated.version, VAULT_VERSION);
  assert.equal(migrated.secrets.gemini.value, "legacy-secret-value");
  assert.equal("unsupported" in migrated.secrets, false);
  assert.equal(migrated.grants["gemini:gemini"].policy, "always");
  assert.equal(
    fs.readFileSync(current.filePath).includes("legacy-secret-value"),
    false,
  );
  assert.equal(status.configured.gemini, true);
  assert.equal(status.grants[0].effective, true);
  assert.equal(JSON.stringify(status).includes("legacy-secret-value"), false);
  assert.deepEqual(vault.environment(), {
    GEMINI_API_KEY: "legacy-secret-value",
    AETHER_SECURE_GEMINI_API_KEY: "legacy-secret-value",
  });
});

test("a future vault version fails closed instead of being overwritten", (t) => {
  const current = fixture(t);
  const futureDocument = current.storage.encryptString(JSON.stringify({
    version: VAULT_VERSION + 1,
    secrets: {
      gemini: {
        value: "future-secret-value",
      },
    },
  }));
  fs.writeFileSync(current.filePath, futureDocument);
  const before = fs.readFileSync(current.filePath);
  const vault = current.create();

  assert.equal(vault.status().readable, false);
  assert.deepEqual(vault.environment(), {});
  assert.throws(
    () => vault.setSecret("gemini", "replacement-secret-value"),
    /descriptografado/i,
  );
  assert.deepEqual(fs.readFileSync(current.filePath), before);
});

test("invalid persisted grant timestamps are normalised to the current time", (t) => {
  const current = fixture(t);
  fs.writeFileSync(
    current.filePath,
    current.storage.encryptString(JSON.stringify({
      version: VAULT_VERSION,
      secrets: {
        gemini: {
          value: "timestamp-secret-value",
          updatedAt: "invalid",
        },
      },
      grants: {
        "gemini:gemini": {
          secretKey: "gemini",
          integration: "gemini",
          policy: "always",
          grantedAt: "invalid",
          updatedAt: "invalid",
          expiresAt: null,
        },
      },
    })),
  );
  const status = current.create().status();

  assert.equal(
    status.grants[0].grantedAt,
    new Date(current.clock.value).toISOString(),
  );
  assert.equal(
    status.grants[0].updatedAt,
    new Date(current.clock.value).toISOString(),
  );
});

test("session grants stay in memory and temporary grants expire", (t) => {
  const current = fixture(t);
  const vault = current.create();
  vault.setSecret("gemini", "session-secret-value");
  vault.revoke({ key: "gemini" });

  const session = vault.authorize({
    key: "gemini",
    integration: "model-lab",
    policy: "session",
  });
  assert.equal(session.persisted, false);
  assert.equal(session.effective, true);
  assert.equal(vault.environment().GEMINI_API_KEY, "session-secret-value");

  const freshProcess = current.create();
  assert.deepEqual(freshProcess.environment(), {});

  vault.revoke({ key: "gemini" });
  const temporary = vault.authorize({
    key: "gemini",
    integration: "research",
    policy: "temporary",
    ttlMs: 2_000,
  });
  assert.equal(temporary.effective, true);
  current.clock.value += 1_999;
  assert.equal(vault.environment().GEMINI_API_KEY, "session-secret-value");
  current.clock.value += 1;
  assert.deepEqual(vault.environment(), {});
  assert.equal(
    vault.status().grants.find(
      (grant) => grant.integration === "research",
    ).effective,
    false,
  );
});

test("blocked grants do not inject secrets and revocation removes policies", (t) => {
  const current = fixture(t);
  const vault = current.create();
  vault.setSecret("weather", "weather-secret-value");
  vault.authorize({
    key: "weather",
    integration: "weather",
    policy: "blocked",
  });

  assert.deepEqual(vault.environment(), {});
  assert.equal(vault.status().grants[0].policy, "blocked");

  vault.authorize({
    key: "weather",
    integration: "dashboard",
    policy: "always",
  });
  assert.equal(vault.environment().WEATHER_API_KEY, "weather-secret-value");

  const revoked = vault.revoke({ key: "weather" });
  assert.equal(revoked.revoked, 2);
  assert.deepEqual(vault.environment(), {});
  assert.equal(vault.status().configured.weather, true);
  assert.deepEqual(vault.status().grants, []);
});

test("deleting a secret also deletes every grant without exposing values", (t) => {
  const current = fixture(t);
  const vault = current.create();
  vault.setSecret("gemini", "delete-secret-value");
  vault.authorize({
    key: "gemini",
    integration: "research",
    policy: "session",
  });

  const result = vault.deleteSecret("gemini");
  assert.equal(result.removed, true);
  assert.equal(vault.status().configured.gemini, false);
  assert.deepEqual(vault.status().grants, []);
  assert.equal(fs.existsSync(current.filePath), false);
});

test("Linux basic_text storage is rejected as an encrypted vault", (t) => {
  const current = fixture(t);
  const vault = new CredentialVaultStore({
    filePath: current.filePath,
    environmentKeys: ENVIRONMENT_KEYS,
    safeStorage: {
      ...current.storage,
      getSelectedStorageBackend: () => "basic_text",
    },
    platform: "linux",
  });
  assert.equal(vault.available(), false);
  assert.throws(
    () => vault.setSecret("gemini", "unavailable-secret"),
    /criptografia segura/i,
  );
});

test("OAuth JSON reaches Python only through its secure granted variable", (t) => {
  const current = fixture(t);
  const vault = current.create();
  vault.setSecret(
    "GMAIL_OAUTH_TOKEN_JSON",
    "{\"access_token\":\"token-value\"}",
    { authorizeDefault: false },
  );
  assert.deepEqual(vault.environment(), {});
  vault.authorize({
    key: "GMAIL_OAUTH_TOKEN_JSON",
    integration: "gmail",
    policy: "always",
  });
  const environment = secureOnlyCredentialEnvironment(
    vault.environment(),
    ["GMAIL_OAUTH_TOKEN_JSON"],
  );

  assert.equal("GMAIL_OAUTH_TOKEN_JSON" in environment, false);
  assert.equal(
    environment.AETHER_SECURE_GMAIL_OAUTH_TOKEN_JSON,
    "{\"access_token\":\"token-value\"}",
  );
  assert.equal(
    JSON.stringify(vault.status()).includes("token-value"),
    false,
  );
});

test("OAuth grants are enforced by the vault while loading persisted state", (t) => {
  const current = fixture(t);
  fs.writeFileSync(
    current.filePath,
    current.storage.encryptString(JSON.stringify({
      version: VAULT_VERSION,
      secrets: {
        GMAIL_OAUTH_TOKEN_JSON: {
          value: "{\"access_token\":\"token-value\"}",
          updatedAt: "2026-07-24T10:00:00.000Z",
        },
      },
      grants: {
        "GMAIL_OAUTH_TOKEN_JSON:calendar": {
          secretKey: "GMAIL_OAUTH_TOKEN_JSON",
          integration: "calendar",
          policy: "always",
          grantedAt: "2026-07-24T10:00:00.000Z",
          updatedAt: "2026-07-24T10:00:00.000Z",
          expiresAt: null,
        },
      },
    })),
  );
  const vault = current.create();

  assert.deepEqual(vault.environment(), {});
  assert.deepEqual(vault.status().grants, []);
  assert.throws(
    () => vault.authorize({
      key: "GMAIL_OAUTH_TOKEN_JSON",
      integration: "calendar",
      policy: "always",
    }),
    /não pode autorizar/i,
  );
  assert.equal(
    vault.authorize({
      key: "GMAIL_OAUTH_TOKEN_JSON",
      integration: "gmail",
      policy: "session",
    }).effective,
    true,
  );
});

test("ungranted managed secrets are removed from inherited backend env", () => {
  const inherited = withoutManagedCredentialEnvironment(
    {
      PATH: "/safe/bin",
      gemini_api_key: "legacy-lowercase-secret",
      AETHER_SECURE_GEMINI_API_KEY: "forged-secure-secret",
      AETHER_UPDATE_PUBLIC_KEY: "public-but-main-only",
    },
    ["GEMINI_API_KEY"],
    ["AETHER_UPDATE_PUBLIC_KEY"],
  );

  assert.deepEqual(inherited, { PATH: "/safe/bin" });
});

test("vault refuses to read credentials through a symbolic link", (t) => {
  const current = fixture(t);
  const outside = path.join(current.directory, "outside.safe");
  fs.writeFileSync(
    outside,
    current.storage.encryptString(JSON.stringify({
      gemini: "linked-secret-value",
    })),
  );
  try {
    fs.symlinkSync(outside, current.filePath);
  } catch (error) {
    if (process.platform === "win32" && error?.code === "EPERM") {
      t.skip("O ambiente Windows não permite criar symlink sem privilégio.");
      return;
    }
    throw error;
  }

  const vault = current.create();
  assert.equal(vault.status().readable, false);
  assert.deepEqual(vault.environment(), {});
  assert.throws(
    () => vault.setSecret("gemini", "replacement-secret-value"),
    /descriptografado/i,
  );
});
