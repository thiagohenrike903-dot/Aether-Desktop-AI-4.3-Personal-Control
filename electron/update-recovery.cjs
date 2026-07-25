"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const UPDATE_CHANNELS = Object.freeze(["stable", "beta"]);
const UPDATE_STATE_FILE = "update-recovery.json";
const UPDATE_DIRECTORY = "updates";
const RECOVERY_DIRECTORY = "recovery";
const SNAPSHOT_SCHEMA_VERSION = 1;
const UPDATE_MANIFEST_SCHEMA_VERSION = 1;
const MAX_SNAPSHOT_FILES = 25_000;
const MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024 * 1024;
const MAX_SNAPSHOT_MANIFEST_BYTES = 16 * 1024 * 1024;
const MAX_UPDATE_ARTIFACT_BYTES = 4 * 1024 * 1024 * 1024;
const SNAPSHOT_ID_PATTERN =
  /^snapshot-\d{8}T\d{9}Z-[a-f0-9]{8}$/;
const DEFAULT_MANAGED_ENTRIES = Object.freeze([
  "data",
  "credentials.safe",
  "desktop-settings.json",
  "window-state.json",
]);

function isPlainObject(value) {
  return Boolean(
    value &&
    typeof value === "object" &&
    !Array.isArray(value),
  );
}

function canonicalJson(value) {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
    .join(",")}}`;
}

function sha256File(filename) {
  const hash = crypto.createHash("sha256");
  const descriptor = fs.openSync(filename, "r");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    let bytesRead;
    do {
      bytesRead = fs.readSync(descriptor, buffer, 0, buffer.length, null);
      if (bytesRead > 0) {
        hash.update(buffer.subarray(0, bytesRead));
      }
    } while (bytesRead > 0);
  } finally {
    fs.closeSync(descriptor);
  }
  return hash.digest("hex");
}

function atomicWritePrivateFile(destination, data) {
  const directory = path.dirname(destination);
  const temporary = path.join(
    directory,
    `.${path.basename(destination)}.${process.pid}.${crypto
      .randomBytes(6)
      .toString("hex")}.tmp`,
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

function safeChild(root, ...segments) {
  const absoluteRoot = path.resolve(root);
  const destination = path.resolve(absoluteRoot, ...segments);
  if (
    destination !== absoluteRoot &&
    !destination.startsWith(`${absoluteRoot}${path.sep}`)
  ) {
    throw new Error("Caminho de recuperação fora da área permitida.");
  }
  return destination;
}

function assertNoSymlinkComponents(root, destination) {
  const absoluteRoot = path.resolve(root);
  const absoluteDestination = safeChild(absoluteRoot, destination);
  const relative = path.relative(absoluteRoot, absoluteDestination);
  const components = relative ? relative.split(path.sep) : [];
  let current = absoluteRoot;
  const inspect = (filename, requiresDirectory) => {
    let stat;
    try {
      stat = fs.lstatSync(filename);
    } catch (error) {
      if (error?.code === "ENOENT") {
        return false;
      }
      throw error;
    }
    if (stat.isSymbolicLink()) {
      throw new Error("Links simbólicos não são permitidos na área de recuperação.");
    }
    if (requiresDirectory && !stat.isDirectory()) {
      throw new Error("Componente inválido na área de recuperação.");
    }
    return true;
  };
  if (!inspect(current, true)) {
    return false;
  }
  for (let index = 0; index < components.length; index += 1) {
    current = path.join(current, components[index]);
    if (!inspect(current, index < components.length - 1)) {
      return false;
    }
  }
  return true;
}

function safeRelativePath(value) {
  if (
    typeof value !== "string" ||
    !value ||
    value.length > 1_024 ||
    path.isAbsolute(value) ||
    /[\u0000-\u001f\u007f\\]/.test(value)
  ) {
    throw new Error("Caminho relativo inválido no snapshot.");
  }
  const segments = value.split("/");
  if (
    segments.some(
      (segment) => !segment || segment === "." || segment === "..",
    )
  ) {
    throw new Error("Caminho relativo inseguro no snapshot.");
  }
  return segments.join("/");
}

function validateManagedEntry(value) {
  const entry = safeRelativePath(value);
  if (entry.includes("/")) {
    throw new Error("Entradas gerenciadas precisam estar na raiz do userData.");
  }
  if (
    entry === UPDATE_DIRECTORY ||
    entry === RECOVERY_DIRECTORY ||
    entry === "logs"
  ) {
    throw new Error("Diretório interno não pode entrar no snapshot.");
  }
  return entry;
}

function decodeBase64(value) {
  if (
    typeof value !== "string" ||
    !value ||
    value.length > 4_096 ||
    !/^[A-Za-z0-9+/]+={0,2}$/.test(value)
  ) {
    throw new Error("Assinatura da atualização inválida.");
  }
  const buffer = Buffer.from(value, "base64");
  if (
    !buffer.length ||
    buffer.toString("base64").replace(/=+$/, "") !== value.replace(/=+$/, "")
  ) {
    throw new Error("Assinatura da atualização inválida.");
  }
  return buffer;
}

function loadEd25519PublicKey(value) {
  if (!value) {
    return null;
  }
  if (
    (typeof value === "object" && value?.type === "private") ||
    (
      typeof value === "string" &&
      /-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(value)
    )
  ) {
    throw new Error("Somente a chave pública de atualização é permitida.");
  }
  let key;
  try {
    if (
      typeof value === "object" &&
      value?.type === "public" &&
      typeof value?.asymmetricKeyType === "string"
    ) {
      key = value;
    } else if (
      typeof value === "string" &&
      value.includes("BEGIN PUBLIC KEY")
    ) {
      key = crypto.createPublicKey(value);
    } else if (typeof value === "string") {
      key = crypto.createPublicKey({
        key: Buffer.from(value, "base64"),
        format: "der",
        type: "spki",
      });
    } else {
      key = crypto.createPublicKey(value);
    }
  } catch {
    throw new Error("A chave pública de atualização é inválida.");
  }
  if (key.asymmetricKeyType !== "ed25519") {
    throw new Error("A chave de atualização precisa ser Ed25519.");
  }
  return key;
}

function normaliseUpdateManifest(value) {
  if (!isPlainObject(value)) {
    throw new Error("Manifesto de atualização inválido.");
  }
  if (value.schemaVersion !== UPDATE_MANIFEST_SCHEMA_VERSION) {
    throw new Error("Versão do manifesto de atualização não suportada.");
  }
  const channel = String(value.channel || "");
  if (!UPDATE_CHANNELS.includes(channel)) {
    throw new Error("Canal de atualização inválido.");
  }
  const version = String(value.version || "");
  if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(version)) {
    throw new Error("Versão da atualização inválida.");
  }
  const publishedAt = String(value.publishedAt || "");
  if (!Number.isFinite(Date.parse(publishedAt))) {
    throw new Error("Data do manifesto de atualização inválida.");
  }
  if (!isPlainObject(value.artifact)) {
    throw new Error("Artefato ausente no manifesto de atualização.");
  }
  const fileName = String(value.artifact.fileName || "");
  if (
    !/^[A-Za-z0-9][A-Za-z0-9._-]{0,180}$/.test(fileName) ||
    fileName === "." ||
    fileName === ".."
  ) {
    throw new Error("Nome do artefato de atualização inválido.");
  }
  const digest = String(value.artifact.sha256 || "").toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(digest)) {
    throw new Error("SHA-256 do artefato inválido.");
  }
  const size = Number(value.artifact.size);
  if (
    !Number.isSafeInteger(size) ||
    size < 1 ||
    size > MAX_UPDATE_ARTIFACT_BYTES
  ) {
    throw new Error("Tamanho do artefato de atualização inválido.");
  }

  const manifest = {
    schemaVersion: UPDATE_MANIFEST_SCHEMA_VERSION,
    channel,
    version,
    publishedAt: new Date(publishedAt).toISOString(),
    artifact: {
      fileName,
      sha256: digest,
      size,
    },
  };
  for (const key of ["platform", "arch"]) {
    if (value[key] !== undefined) {
      const identifier = String(value[key] || "");
      if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(identifier)) {
        throw new Error(`Campo ${key} inválido no manifesto.`);
      }
      manifest[key] = identifier;
    }
  }
  if (value.minimumVersion !== undefined) {
    const minimumVersion = String(value.minimumVersion || "");
    if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(minimumVersion)) {
      throw new Error("Versão mínima inválida no manifesto.");
    }
    manifest.minimumVersion = minimumVersion;
  }
  if (value.releaseNotesUrl !== undefined) {
    let releaseNotesUrl;
    try {
      releaseNotesUrl = new URL(String(value.releaseNotesUrl || ""));
    } catch {
      throw new Error("URL de notas da versão inválida.");
    }
    if (
      releaseNotesUrl.protocol !== "https:" ||
      releaseNotesUrl.username ||
      releaseNotesUrl.password ||
      releaseNotesUrl.hash ||
      releaseNotesUrl.href.length > 512
    ) {
      throw new Error("URL de notas da versão não permitida.");
    }
    manifest.releaseNotesUrl = releaseNotesUrl.href;
  }
  return manifest;
}

function copyFileIntoSnapshot(
  source,
  destination,
  relativePath,
  tracker,
) {
  const stat = fs.lstatSync(source);
  if (stat.isSymbolicLink()) {
    throw new Error(`Links simbólicos não entram no snapshot: ${relativePath}`);
  }
  if (!stat.isFile()) {
    throw new Error(`Tipo de arquivo não suportado no snapshot: ${relativePath}`);
  }
  tracker.files += 1;
  tracker.bytes += stat.size;
  if (
    tracker.files > tracker.maximumFiles ||
    tracker.bytes > tracker.maximumBytes
  ) {
    throw new Error("O snapshot excede os limites seguros configurados.");
  }
  fs.mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
  fs.copyFileSync(source, destination, fs.constants.COPYFILE_EXCL);
  try {
    fs.chmodSync(destination, 0o600);
  } catch {
    // Windows applies ACLs independently from POSIX mode bits.
  }
  const copiedStat = fs.lstatSync(destination);
  if (!copiedStat.isFile() || copiedStat.size !== stat.size) {
    throw new Error(`Cópia incompleta durante o snapshot: ${relativePath}`);
  }
  tracker.entries.push({
    path: relativePath,
    size: copiedStat.size,
    sha256: sha256File(destination),
  });
}

function copyTreeIntoSnapshot(
  source,
  destination,
  relativePath,
  tracker,
) {
  const stat = fs.lstatSync(source);
  if (stat.isSymbolicLink()) {
    throw new Error(`Links simbólicos não entram no snapshot: ${relativePath}`);
  }
  if (stat.isFile()) {
    copyFileIntoSnapshot(source, destination, relativePath, tracker);
    return "file";
  }
  if (!stat.isDirectory()) {
    throw new Error(`Tipo não suportado no snapshot: ${relativePath}`);
  }
  fs.mkdirSync(destination, { recursive: true, mode: 0o700 });
  const children = fs.readdirSync(source, { withFileTypes: true })
    .sort((first, second) => first.name.localeCompare(second.name));
  for (const child of children) {
    const childRelative = `${relativePath}/${child.name}`;
    safeRelativePath(childRelative);
    copyTreeIntoSnapshot(
      path.join(source, child.name),
      path.join(destination, child.name),
      childRelative,
      tracker,
    );
  }
  return "directory";
}

function inspectSnapshotTree(filename, relativePath, tracker) {
  const stat = fs.lstatSync(filename);
  if (stat.isSymbolicLink()) {
    throw new Error(`Link simbólico detectado no snapshot: ${relativePath}`);
  }
  if (stat.isFile()) {
    tracker.files += 1;
    tracker.bytes += stat.size;
    if (
      tracker.files > tracker.maximumFiles ||
      tracker.bytes > tracker.maximumBytes
    ) {
      throw new Error("O snapshot excede os limites seguros configurados.");
    }
    tracker.entries.push({
      path: relativePath,
      size: stat.size,
      sha256: sha256File(filename),
    });
    return "file";
  }
  if (!stat.isDirectory()) {
    throw new Error(`Tipo não suportado no snapshot: ${relativePath}`);
  }
  const children = fs.readdirSync(filename, { withFileTypes: true })
    .sort((first, second) => first.name.localeCompare(second.name));
  for (const child of children) {
    const childRelative = safeRelativePath(
      `${relativePath}/${child.name}`,
    );
    inspectSnapshotTree(
      path.join(filename, child.name),
      childRelative,
      tracker,
    );
  }
  return "directory";
}

class UpdateRecoveryManager {
  constructor(options = {}) {
    if (!options.userDataPath || typeof options.userDataPath !== "string") {
      throw new TypeError("userDataPath é obrigatório.");
    }
    this.userDataPath = path.resolve(options.userDataPath);
    this.appVersion = String(options.appVersion || "0.0.0");
    this.platform = options.platform || process.platform;
    this.arch = options.arch || process.arch;
    this.now = typeof options.now === "function" ? options.now : Date.now;
    this.randomBytes =
      typeof options.randomBytes === "function"
        ? options.randomBytes
        : crypto.randomBytes;
    this.writeFile =
      typeof options.writeFile === "function"
        ? options.writeFile
        : atomicWritePrivateFile;
    this.maximumFiles = Math.min(
      Math.max(Number(options.maximumFiles) || MAX_SNAPSHOT_FILES, 1),
      MAX_SNAPSHOT_FILES,
    );
    this.maximumBytes = Math.min(
      Math.max(Number(options.maximumBytes) || MAX_SNAPSHOT_BYTES, 1),
      MAX_SNAPSHOT_BYTES,
    );
    this.managedEntries = Object.freeze(
      (options.managedEntries || DEFAULT_MANAGED_ENTRIES)
        .map(validateManagedEntry),
    );
    this.explicitPublicKey = options.publicKey || null;
    this.publicKeyPath = options.publicKeyPath || null;
    this.publicKeyEnvironment = options.publicKeyEnvironment || null;
  }

  statePath() {
    return safeChild(this.userDataPath, UPDATE_STATE_FILE);
  }

  updatesPath() {
    return safeChild(this.userDataPath, UPDATE_DIRECTORY);
  }

  recoveryPath() {
    return safeChild(this.userDataPath, RECOVERY_DIRECTORY);
  }

  snapshotsPath() {
    return safeChild(this.recoveryPath(), "snapshots");
  }

  _readState() {
    try {
      assertNoSymlinkComponents(this.userDataPath, this.statePath());
      const value = JSON.parse(fs.readFileSync(this.statePath(), "utf8"));
      return {
        schemaVersion: 1,
        channel: UPDATE_CHANNELS.includes(value?.channel)
          ? value.channel
          : "stable",
        lastVerified:
          isPlainObject(value?.lastVerified)
            ? value.lastVerified
            : null,
      };
    } catch (error) {
      if (
        error?.code !== "ENOENT" &&
        !(error instanceof SyntaxError)
      ) {
        throw error;
      }
      return {
        schemaVersion: 1,
        channel: "stable",
        lastVerified: null,
      };
    }
  }

  _writeState(state) {
    assertNoSymlinkComponents(this.userDataPath, this.statePath());
    this.writeFile(
      this.statePath(),
      `${JSON.stringify(state, null, 2)}\n`,
    );
  }

  _publicKey() {
    let candidate = this.explicitPublicKey || this.publicKeyEnvironment;
    if (!candidate && this.publicKeyPath) {
      try {
        candidate = fs.readFileSync(this.publicKeyPath, "utf8");
      } catch (error) {
        if (error?.code !== "ENOENT") {
          throw error;
        }
      }
    }
    return loadEd25519PublicKey(candidate);
  }

  status() {
    let state;
    let stateError = null;
    try {
      state = this._readState();
    } catch {
      state = {
        schemaVersion: 1,
        channel: "stable",
        lastVerified: null,
      };
      stateError = "As configurações locais de atualização não são seguras ou legíveis.";
    }
    let publicKeyConfigured = false;
    let verificationError = null;
    try {
      publicKeyConfigured = Boolean(this._publicKey());
    } catch (error) {
      verificationError = error.message;
    }
    const reason = stateError || verificationError ||
      (!publicKeyConfigured
        ? "Nenhuma chave pública Ed25519 foi configurada."
        : "A instalação automática não é disponibilizada nesta versão.");
    return {
      channel: state.channel,
      supportedChannels: [...UPDATE_CHANNELS],
      currentVersion: this.appVersion,
      verification: {
        available:
          publicKeyConfigured &&
          !verificationError &&
          !stateError,
        algorithm: "Ed25519",
        digest: "SHA-256",
        publicKeyConfigured,
        error: stateError || verificationError,
      },
      installationAvailable: false,
      installationReason: reason,
      lastVerified: state.lastVerified || null,
      recovery: {
        snapshotsAvailable: true,
        atomicReplacement: true,
        atomicPerManagedRoot: true,
        crossRootAtomic: false,
        rollbackOnFailure: true,
        managedEntries: [...this.managedEntries],
      },
    };
  }

  setChannel(channelValue) {
    const channel = String(channelValue || "");
    if (!UPDATE_CHANNELS.includes(channel)) {
      throw new Error("Canal de atualização não permitido.");
    }
    const state = this._readState();
    state.channel = channel;
    state.lastVerified = null;
    this._writeState(state);
    return this.status();
  }

  verifyUpdate(payload = {}) {
    const state = this._readState();
    const key = this._publicKey();
    if (!key) {
      return {
        ok: false,
        available: false,
        code: "UPDATE_PUBLIC_KEY_UNAVAILABLE",
        error: "Nenhuma chave pública Ed25519 foi configurada.",
      };
    }
    const manifest = normaliseUpdateManifest(payload.manifest);
    if (manifest.channel !== state.channel) {
      return {
        ok: false,
        available: true,
        code: "UPDATE_CHANNEL_MISMATCH",
        error: "O manifesto não pertence ao canal selecionado.",
      };
    }
    if (manifest.platform && manifest.platform !== this.platform) {
      throw new Error("O manifesto pertence a outra plataforma.");
    }
    if (manifest.arch && manifest.arch !== this.arch) {
      throw new Error("O manifesto pertence a outra arquitetura.");
    }
    const signature = decodeBase64(payload.signature);
    const signatureValid = crypto.verify(
      null,
      Buffer.from(canonicalJson(manifest), "utf8"),
      key,
      signature,
    );
    if (!signatureValid) {
      return {
        ok: false,
        available: true,
        code: "UPDATE_SIGNATURE_INVALID",
        error: "A assinatura Ed25519 do manifesto é inválida.",
      };
    }

    const artifactPath = safeChild(
      this.updatesPath(),
      manifest.artifact.fileName,
    );
    assertNoSymlinkComponents(this.userDataPath, artifactPath);
    let stat;
    try {
      stat = fs.lstatSync(artifactPath);
    } catch (error) {
      if (error?.code === "ENOENT") {
        return {
          ok: false,
          available: true,
          code: "UPDATE_ARTIFACT_MISSING",
          error: "O artefato assinado ainda não está no diretório de atualizações.",
        };
      }
      throw error;
    }
    if (stat.isSymbolicLink() || !stat.isFile()) {
      throw new Error("O artefato de atualização precisa ser um arquivo regular.");
    }
    if (stat.size !== manifest.artifact.size) {
      return {
        ok: false,
        available: true,
        code: "UPDATE_SIZE_MISMATCH",
        error: "O tamanho do artefato não corresponde ao manifesto.",
      };
    }
    const digest = sha256File(artifactPath);
    if (digest !== manifest.artifact.sha256) {
      return {
        ok: false,
        available: true,
        code: "UPDATE_DIGEST_MISMATCH",
        error: "O SHA-256 do artefato não corresponde ao manifesto.",
      };
    }
    state.lastVerified = {
      version: manifest.version,
      channel: manifest.channel,
      fileName: manifest.artifact.fileName,
      sha256: digest,
      verifiedAt: new Date(this.now()).toISOString(),
    };
    this._writeState(state);
    return {
      ok: true,
      available: true,
      verified: true,
      installationAvailable: false,
      manifest,
      artifact: {
        fileName: manifest.artifact.fileName,
        size: stat.size,
        sha256: digest,
      },
    };
  }

  _snapshotId() {
    const timestamp = new Date(this.now())
      .toISOString()
      .replace(/[-:.]/g, "");
    return `snapshot-${timestamp}-${this.randomBytes(4).toString("hex")}`;
  }

  createSnapshot(options = {}) {
    const id = this._snapshotId();
    if (!SNAPSHOT_ID_PATTERN.test(id)) {
      throw new Error("Não foi possível gerar um identificador de snapshot.");
    }
    const snapshotsRoot = this.snapshotsPath();
    assertNoSymlinkComponents(this.userDataPath, snapshotsRoot);
    fs.mkdirSync(snapshotsRoot, { recursive: true, mode: 0o700 });
    assertNoSymlinkComponents(this.userDataPath, snapshotsRoot);
    const staging = safeChild(
      snapshotsRoot,
      `.staging-${id}-${this.randomBytes(3).toString("hex")}`,
    );
    const destination = safeChild(snapshotsRoot, id);
    const contentsRoot = safeChild(staging, "contents");
    fs.mkdirSync(contentsRoot, { recursive: true, mode: 0o700 });
    const tracker = {
      files: 0,
      bytes: 0,
      maximumFiles: this.maximumFiles,
      maximumBytes: this.maximumBytes,
      entries: [],
    };
    const roots = [];
    try {
      for (const entry of this.managedEntries) {
        const source = safeChild(this.userDataPath, entry);
        const target = safeChild(contentsRoot, entry);
        let stat;
        try {
          stat = fs.lstatSync(source);
        } catch (error) {
          if (error?.code === "ENOENT") {
            roots.push({ path: entry, present: false, type: null });
            continue;
          }
          throw error;
        }
        if (stat.isSymbolicLink()) {
          throw new Error(`Link simbólico não permitido em userData: ${entry}`);
        }
        const type = copyTreeIntoSnapshot(
          source,
          target,
          entry,
          tracker,
        );
        roots.push({ path: entry, present: true, type });
      }
      tracker.entries.sort((first, second) =>
        first.path.localeCompare(second.path));
      const reason = typeof options.reason === "string"
        ? options.reason.replace(/\s+/g, " ").trim().slice(0, 160)
        : "";
      const manifest = {
        schemaVersion: SNAPSHOT_SCHEMA_VERSION,
        id,
        createdAt: new Date(this.now()).toISOString(),
        appVersion: this.appVersion,
        reason: reason || "manual",
        roots,
        files: tracker.entries,
        totals: {
          files: tracker.files,
          bytes: tracker.bytes,
        },
      };
      this.writeFile(
        safeChild(staging, "manifest.json"),
        `${JSON.stringify(manifest, null, 2)}\n`,
      );
      fs.renameSync(staging, destination);
      return {
        ok: true,
        id,
        createdAt: manifest.createdAt,
        reason: manifest.reason,
        totals: { ...manifest.totals },
      };
    } catch (error) {
      fs.rmSync(staging, { recursive: true, force: true });
      throw error;
    }
  }

  _snapshotPath(idValue) {
    const id = String(idValue || "");
    if (!SNAPSHOT_ID_PATTERN.test(id)) {
      throw new Error("Identificador de snapshot inválido.");
    }
    const snapshotPath = safeChild(this.snapshotsPath(), id);
    assertNoSymlinkComponents(this.userDataPath, snapshotPath);
    return snapshotPath;
  }

  _readSnapshotManifest(idValue) {
    const snapshotPath = this._snapshotPath(idValue);
    const manifestPath = safeChild(snapshotPath, "manifest.json");
    const manifestStat = fs.lstatSync(manifestPath);
    if (
      manifestStat.isSymbolicLink() ||
      !manifestStat.isFile() ||
      manifestStat.size > MAX_SNAPSHOT_MANIFEST_BYTES
    ) {
      throw new Error("Manifesto de snapshot inválido.");
    }
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    if (
      !isPlainObject(manifest) ||
      manifest.schemaVersion !== SNAPSHOT_SCHEMA_VERSION ||
      manifest.id !== idValue ||
      !Array.isArray(manifest.roots) ||
      !Array.isArray(manifest.files) ||
      manifest.files.length > this.maximumFiles ||
      typeof manifest.createdAt !== "string" ||
      !Number.isFinite(Date.parse(manifest.createdAt)) ||
      typeof manifest.appVersion !== "string" ||
      manifest.appVersion.length > 64 ||
      typeof manifest.reason !== "string" ||
      manifest.reason.length > 160
    ) {
      throw new Error("Manifesto de snapshot incompatível.");
    }
    const roots = manifest.roots.map((record) => {
      if (!isPlainObject(record)) {
        throw new Error("Raiz inválida no snapshot.");
      }
      const entry = validateManagedEntry(record.path);
      if (!this.managedEntries.includes(entry)) {
        throw new Error("O snapshot contém uma raiz não gerenciada.");
      }
      const present = record.present === true;
      const type = present ? record.type : null;
      if (present && !["file", "directory"].includes(type)) {
        throw new Error("Tipo de raiz inválido no snapshot.");
      }
      return { path: entry, present, type };
    });
    if (
      roots.length !== this.managedEntries.length ||
      new Set(roots.map((record) => record.path)).size !== roots.length
    ) {
      throw new Error("Conjunto de raízes incompleto no snapshot.");
    }
    const files = manifest.files.map((record) => {
      if (!isPlainObject(record)) {
        throw new Error("Arquivo inválido no snapshot.");
      }
      const relativePath = safeRelativePath(record.path);
      const size = Number(record.size);
      const digest = String(record.sha256 || "").toLowerCase();
      if (
        !Number.isSafeInteger(size) ||
        size < 0 ||
        !/^[a-f0-9]{64}$/.test(digest)
      ) {
        throw new Error("Metadados de arquivo inválidos no snapshot.");
      }
      if (
        !roots.some(
          (root) =>
            root.present &&
            (
              relativePath === root.path ||
              relativePath.startsWith(`${root.path}/`)
            ),
        )
      ) {
        throw new Error("Arquivo fora das raízes declaradas no snapshot.");
      }
      return { path: relativePath, size, sha256: digest };
    });
    if (new Set(files.map((record) => record.path)).size !== files.length) {
      throw new Error("O snapshot contém arquivos duplicados.");
    }
    return {
      snapshotPath,
      manifest: {
        schemaVersion: SNAPSHOT_SCHEMA_VERSION,
        id: manifest.id,
        createdAt: new Date(manifest.createdAt).toISOString(),
        appVersion: manifest.appVersion,
        reason: manifest.reason,
        totals: manifest.totals,
        roots,
        files,
      },
    };
  }

  verifySnapshot(idValue) {
    const { snapshotPath, manifest } = this._readSnapshotManifest(idValue);
    const contentsRoot = safeChild(snapshotPath, "contents");
    const contentsStat = fs.lstatSync(contentsRoot);
    if (contentsStat.isSymbolicLink() || !contentsStat.isDirectory()) {
      throw new Error("Diretório de conteúdo inválido no snapshot.");
    }
    const presentRoots = new Set(
      manifest.roots
        .filter((root) => root.present)
        .map((root) => root.path),
    );
    for (const child of fs.readdirSync(contentsRoot, { withFileTypes: true })) {
      if (!presentRoots.has(child.name)) {
        throw new Error(`Conteúdo não declarado no snapshot: ${child.name}`);
      }
    }
    const tracker = {
      files: 0,
      bytes: 0,
      maximumFiles: this.maximumFiles,
      maximumBytes: this.maximumBytes,
      entries: [],
    };
    for (const root of manifest.roots) {
      const filename = safeChild(
        contentsRoot,
        ...root.path.split("/"),
      );
      if (!root.present) {
        try {
          fs.lstatSync(filename);
          throw new Error(`Raiz ausente contém dados no snapshot: ${root.path}`);
        } catch (error) {
          if (error?.code !== "ENOENT") {
            throw error;
          }
        }
        continue;
      }
      const actualType = inspectSnapshotTree(
        filename,
        root.path,
        tracker,
      );
      if (actualType !== root.type) {
        throw new Error(`Raiz inválida no snapshot: ${root.path}`);
      }
    }
    tracker.entries.sort((first, second) =>
      first.path.localeCompare(second.path));
    const declaredFiles = new Map(
      manifest.files.map((file) => [file.path, file]),
    );
    if (tracker.entries.length !== declaredFiles.size) {
      throw new Error("O conjunto de arquivos do snapshot não confere.");
    }
    for (const actual of tracker.entries) {
      const expected = declaredFiles.get(actual.path);
      if (
        !expected ||
        expected.size !== actual.size ||
        expected.sha256 !== actual.sha256
      ) {
        throw new Error(`Falha de integridade no snapshot: ${actual.path}`);
      }
    }
    if (
      manifest.totals?.files !== tracker.files ||
      manifest.totals?.bytes !== tracker.bytes
    ) {
      throw new Error("Totais do snapshot não conferem.");
    }
    return {
      ok: true,
      id: manifest.id,
      createdAt: manifest.createdAt,
      appVersion: manifest.appVersion,
      reason: manifest.reason,
      totals: {
        files: tracker.files,
        bytes: tracker.bytes,
      },
    };
  }

  listSnapshots() {
    let entries = [];
    try {
      assertNoSymlinkComponents(this.userDataPath, this.snapshotsPath());
      entries = fs.readdirSync(this.snapshotsPath(), { withFileTypes: true });
    } catch (error) {
      if (error?.code === "ENOENT") {
        return [];
      }
      throw error;
    }
    const snapshots = [];
    for (const entry of entries) {
      if (!entry.isDirectory() || !SNAPSHOT_ID_PATTERN.test(entry.name)) {
        continue;
      }
      try {
        snapshots.push(this.verifySnapshot(entry.name));
      } catch (error) {
        snapshots.push({
          ok: false,
          id: entry.name,
          error: String(error?.message || "Snapshot inválido.").slice(0, 200),
        });
      }
    }
    return snapshots.sort((first, second) =>
      String(second.id).localeCompare(String(first.id)));
  }

  rollback(idValue, options = {}) {
    const verification = this.verifySnapshot(idValue);
    const { snapshotPath, manifest } = this._readSnapshotManifest(idValue);
    const safetySnapshot = options.createSafetySnapshot === false
      ? null
      : this.createSnapshot({ reason: `antes de restaurar ${idValue}` });
    const transactionId = `rollback-${this.now()}-${this.randomBytes(4)
      .toString("hex")}`;
    const transactionRoot = safeChild(this.recoveryPath(), transactionId);
    assertNoSymlinkComponents(this.userDataPath, transactionRoot);
    const incomingRoot = safeChild(transactionRoot, "incoming");
    const backupRoot = safeChild(transactionRoot, "backup");
    fs.mkdirSync(incomingRoot, { recursive: true, mode: 0o700 });
    fs.mkdirSync(backupRoot, { recursive: true, mode: 0o700 });

    const applied = [];
    const backedUp = [];
    const incomingTracker = {
      files: 0,
      bytes: 0,
      maximumFiles: this.maximumFiles,
      maximumBytes: this.maximumBytes,
      entries: [],
    };
    try {
      for (const root of manifest.roots) {
        if (!root.present) {
          continue;
        }
        const source = safeChild(
          snapshotPath,
          "contents",
          ...root.path.split("/"),
        );
        const destination = safeChild(incomingRoot, root.path);
        copyTreeIntoSnapshot(
          source,
          destination,
          root.path,
          incomingTracker,
        );
      }
      incomingTracker.entries.sort((first, second) =>
        first.path.localeCompare(second.path));
      const expectedFiles = new Map(
        manifest.files.map((file) => [file.path, file]),
      );
      if (incomingTracker.entries.length !== expectedFiles.size) {
        throw new Error("A cópia preparada para rollback não confere.");
      }
      for (const copied of incomingTracker.entries) {
        const expected = expectedFiles.get(copied.path);
        if (
          !expected ||
          expected.size !== copied.size ||
          expected.sha256 !== copied.sha256
        ) {
          throw new Error(
            `Falha ao preparar rollback com integridade: ${copied.path}`,
          );
        }
      }

      for (const root of manifest.roots) {
        const live = safeChild(this.userDataPath, root.path);
        const backup = safeChild(backupRoot, root.path);
        try {
          const stat = fs.lstatSync(live);
          if (stat.isSymbolicLink()) {
            throw new Error(`Link simbólico não permitido em userData: ${root.path}`);
          }
          fs.mkdirSync(path.dirname(backup), { recursive: true, mode: 0o700 });
          fs.renameSync(live, backup);
          backedUp.push({ live, backup });
        } catch (error) {
          if (error?.code !== "ENOENT") {
            throw error;
          }
        }
        if (root.present) {
          const incoming = safeChild(incomingRoot, root.path);
          fs.renameSync(incoming, live);
          applied.push(live);
        }
      }
      fs.rmSync(transactionRoot, { recursive: true, force: true });
      return {
        ok: true,
        id: verification.id,
        restoredAt: new Date(this.now()).toISOString(),
        safetySnapshotId: safetySnapshot?.id || null,
        restartRequired: true,
      };
    } catch (error) {
      for (const live of applied.reverse()) {
        fs.rmSync(live, { recursive: true, force: true });
      }
      for (const record of backedUp.reverse()) {
        if (fs.existsSync(record.backup)) {
          fs.renameSync(record.backup, record.live);
        }
      }
      fs.rmSync(transactionRoot, { recursive: true, force: true });
      throw error;
    }
  }
}

module.exports = {
  DEFAULT_MANAGED_ENTRIES,
  MAX_SNAPSHOT_BYTES,
  MAX_SNAPSHOT_FILES,
  SNAPSHOT_ID_PATTERN,
  UPDATE_CHANNELS,
  UPDATE_MANIFEST_SCHEMA_VERSION,
  UpdateRecoveryManager,
  atomicWritePrivateFile,
  canonicalJson,
  loadEd25519PublicKey,
  normaliseUpdateManifest,
  sha256File,
};
