"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const {
  UpdateRecoveryManager,
  canonicalJson,
  normaliseUpdateManifest,
} = require("./update-recovery.cjs");

function fixture(t, options = {}) {
  const directory = fs.mkdtempSync(
    path.join(os.tmpdir(), "aether-recovery-test-"),
  );
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  let randomValue = 0;
  const clock = {
    value: options.now ?? Date.parse("2026-07-24T10:00:00.123Z"),
  };
  const manager = new UpdateRecoveryManager({
    userDataPath: directory,
    appVersion: "4.3.0",
    platform: "linux",
    arch: "x64",
    publicKey: options.publicKey || null,
    now: () => clock.value,
    randomBytes: (size) => {
      const value = Buffer.alloc(size, randomValue);
      randomValue = (randomValue + 1) % 256;
      return value;
    },
  });
  return { clock, directory, manager };
}

function signedUpdate(managerFixture, privateKey, contents = "release-data") {
  const updates = path.join(managerFixture.directory, "updates");
  fs.mkdirSync(updates, { recursive: true });
  const artifact = Buffer.from(contents, "utf8");
  const fileName = "Aether-4.3.1.bin";
  fs.writeFileSync(path.join(updates, fileName), artifact);
  const manifest = normaliseUpdateManifest({
    schemaVersion: 1,
    channel: "stable",
    version: "4.3.1",
    publishedAt: "2026-07-24T10:00:00.000Z",
    platform: "linux",
    arch: "x64",
    artifact: {
      fileName,
      size: artifact.length,
      sha256: crypto.createHash("sha256").update(artifact).digest("hex"),
    },
  });
  const signature = crypto.sign(
    null,
    Buffer.from(canonicalJson(manifest), "utf8"),
    privateKey,
  ).toString("base64");
  return { artifact, fileName, manifest, signature };
}

test("update verification requires a configured Ed25519 key", (t) => {
  const current = fixture(t);
  const status = current.manager.status();
  assert.equal(status.verification.available, false);
  assert.equal(status.installationAvailable, false);

  const result = current.manager.verifyUpdate({
    manifest: {},
    signature: "AA==",
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "UPDATE_PUBLIC_KEY_UNAVAILABLE");
});

test("update trust configuration refuses private signing material", (t) => {
  const { privateKey } = crypto.generateKeyPairSync("ed25519");
  const current = fixture(t, {
    publicKey: privateKey.export({ type: "pkcs8", format: "pem" }),
  });
  const status = current.manager.status();

  assert.equal(status.verification.available, false);
  assert.match(status.verification.error, /somente a chave pública/i);
  assert.throws(
    () => current.manager.verifyUpdate({}),
    /somente a chave pública/i,
  );
});

test("signed manifest and artifact SHA-256 are both verified", (t) => {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  const current = fixture(t, {
    publicKey: publicKey.export({ type: "spki", format: "pem" }),
  });
  const update = signedUpdate(current, privateKey);

  const verified = current.manager.verifyUpdate(update);
  assert.equal(verified.ok, true);
  assert.equal(verified.verified, true);
  assert.equal(verified.installationAvailable, false);
  assert.equal(
    current.manager.status().lastVerified.sha256,
    update.manifest.artifact.sha256,
  );

  fs.writeFileSync(
    path.join(current.directory, "updates", update.fileName),
    Buffer.from("tampered-data", "utf8"),
  );
  const tampered = current.manager.verifyUpdate(update);
  assert.equal(tampered.ok, false);
  assert.match(tampered.code, /^UPDATE_(?:SIZE|DIGEST)_MISMATCH$/);
});

test("wrong signatures and channels never become verified updates", (t) => {
  const first = crypto.generateKeyPairSync("ed25519");
  const second = crypto.generateKeyPairSync("ed25519");
  const current = fixture(t, { publicKey: first.publicKey });
  const update = signedUpdate(current, second.privateKey);

  assert.equal(
    current.manager.verifyUpdate(update).code,
    "UPDATE_SIGNATURE_INVALID",
  );
  current.manager.setChannel("beta");
  assert.equal(
    current.manager.verifyUpdate(update).code,
    "UPDATE_CHANNEL_MISMATCH",
  );
});

test("stable and beta channel selection persists without enabling install", (t) => {
  const current = fixture(t);
  assert.equal(current.manager.status().channel, "stable");
  const changed = current.manager.setChannel("beta");
  assert.equal(changed.channel, "beta");
  assert.equal(changed.installationAvailable, false);

  const reloaded = new UpdateRecoveryManager({
    userDataPath: current.directory,
    appVersion: "4.3.0",
    platform: "linux",
    arch: "x64",
  });
  assert.equal(reloaded.status().channel, "beta");
  assert.throws(
    () => reloaded.setChannel("nightly"),
    /não permitido/i,
  );
});

test("update verification refuses artifacts reached through symlink parents", (t) => {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  const current = fixture(t, { publicKey });
  const outside = fs.mkdtempSync(
    path.join(os.tmpdir(), "aether-update-outside-"),
  );
  t.after(() => fs.rmSync(outside, { recursive: true, force: true }));
  try {
    fs.symlinkSync(outside, path.join(current.directory, "updates"), "dir");
  } catch (error) {
    if (process.platform === "win32" && error?.code === "EPERM") {
      t.skip("O ambiente Windows não permite criar symlink sem privilégio.");
      return;
    }
    throw error;
  }
  const update = signedUpdate(current, privateKey);

  assert.throws(
    () => current.manager.verifyUpdate(update),
    /links simbólicos/i,
  );
});

test("snapshot restore is verified and removes roots absent at capture time", (t) => {
  const current = fixture(t);
  const dataDirectory = path.join(current.directory, "data");
  fs.mkdirSync(dataDirectory, { recursive: true });
  fs.writeFileSync(path.join(dataDirectory, "aether.db"), "original");
  fs.writeFileSync(
    path.join(current.directory, "desktop-settings.json"),
    "{\"theme\":\"mono\"}",
  );
  fs.writeFileSync(
    path.join(current.directory, ".env"),
    "LEGACY_API_KEY=must-not-enter-snapshot",
  );

  const snapshot = current.manager.createSnapshot({ reason: "before update" });
  assert.equal(snapshot.ok, true);
  assert.equal(current.manager.listSnapshots()[0].ok, true);
  assert.equal(
    fs.existsSync(path.join(
      current.directory,
      "recovery",
      "snapshots",
      snapshot.id,
      "contents",
      ".env",
    )),
    false,
  );

  fs.writeFileSync(path.join(dataDirectory, "aether.db"), "changed");
  fs.writeFileSync(path.join(current.directory, ".env"), "UNCHANGED=1");
  fs.writeFileSync(path.join(current.directory, "window-state.json"), "{}");
  const restored = current.manager.rollback(snapshot.id);

  assert.equal(restored.ok, true);
  assert.equal(restored.restartRequired, true);
  assert.match(restored.safetySnapshotId, /^snapshot-/);
  assert.equal(current.manager.listSnapshots().length, 2);
  assert.equal(
    fs.readFileSync(path.join(dataDirectory, "aether.db"), "utf8"),
    "original",
  );
  assert.equal(
    fs.existsSync(path.join(current.directory, "window-state.json")),
    false,
  );
  assert.equal(
    fs.readFileSync(path.join(current.directory, ".env"), "utf8"),
    "UNCHANGED=1",
  );
});

test("snapshot integrity detects modified files before rollback", (t) => {
  const current = fixture(t);
  fs.mkdirSync(path.join(current.directory, "data"), { recursive: true });
  fs.writeFileSync(path.join(current.directory, "data", "state.db"), "state");
  const snapshot = current.manager.createSnapshot();
  fs.writeFileSync(
    path.join(
      current.directory,
      "recovery",
      "snapshots",
      snapshot.id,
      "contents",
      "data",
      "state.db",
    ),
    "modified",
  );

  assert.throws(
    () => current.manager.verifySnapshot(snapshot.id),
    /integridade/i,
  );
  assert.equal(current.manager.listSnapshots()[0].ok, false);
});

test("snapshot integrity rejects files absent from its manifest", (t) => {
  const current = fixture(t);
  fs.mkdirSync(path.join(current.directory, "data"), { recursive: true });
  fs.writeFileSync(path.join(current.directory, "data", "state.db"), "state");
  const snapshot = current.manager.createSnapshot();
  fs.writeFileSync(
    path.join(
      current.directory,
      "recovery",
      "snapshots",
      snapshot.id,
      "contents",
      "data",
      "injected.txt",
    ),
    "not declared",
  );

  assert.throws(
    () => current.manager.rollback(snapshot.id, {
      createSafetySnapshot: false,
    }),
    /conjunto de arquivos/i,
  );
});

test("failed rollback restores every live root already replaced", (t) => {
  const current = fixture(t);
  const dataDirectory = path.join(current.directory, "data");
  fs.mkdirSync(dataDirectory, { recursive: true });
  fs.writeFileSync(path.join(dataDirectory, "state.db"), "snapshot-state");
  fs.writeFileSync(
    path.join(current.directory, "credentials.safe"),
    "snapshot-vault",
  );
  const snapshot = current.manager.createSnapshot();

  fs.writeFileSync(path.join(dataDirectory, "state.db"), "live-state");
  fs.rmSync(path.join(current.directory, "credentials.safe"));
  const outside = path.join(current.directory, "outside.safe");
  fs.writeFileSync(outside, "outside-must-not-change");
  try {
    fs.symlinkSync(
      outside,
      path.join(current.directory, "credentials.safe"),
    );
  } catch (error) {
    if (process.platform === "win32" && error?.code === "EPERM") {
      t.skip("O ambiente Windows não permite criar symlink sem privilégio.");
      return;
    }
    throw error;
  }

  assert.throws(
    () => current.manager.rollback(snapshot.id, {
      createSafetySnapshot: false,
    }),
    /link simbólico/i,
  );
  assert.equal(
    fs.readFileSync(path.join(dataDirectory, "state.db"), "utf8"),
    "live-state",
  );
  assert.equal(fs.readFileSync(outside, "utf8"), "outside-must-not-change");
  assert.equal(
    fs.lstatSync(path.join(current.directory, "credentials.safe"))
      .isSymbolicLink(),
    true,
  );
});
