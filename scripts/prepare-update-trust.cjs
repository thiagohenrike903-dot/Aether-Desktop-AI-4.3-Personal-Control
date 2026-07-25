"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const destination = path.join(root, "build", "update-public-key.pem");
const requestedSource =
  process.argv[2] ||
  process.env.AETHER_UPDATE_PUBLIC_KEY_FILE ||
  destination;
const source = path.resolve(root, requestedSource);

function fail(message) {
  console.error(`[update-trust] ${message}`);
  process.exitCode = 1;
}

function readRegularPublicKey(filename) {
  let stat;
  try {
    stat = fs.lstatSync(filename);
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new Error(
        "Chave pública ausente. Informe AETHER_UPDATE_PUBLIC_KEY_FILE ou passe o caminho como argumento.",
      );
    }
    throw error;
  }
  if (
    stat.isSymbolicLink() ||
    !stat.isFile() ||
    stat.size < 32 ||
    stat.size > 16_384
  ) {
    throw new Error("A raiz de confiança precisa ser um arquivo regular e limitado.");
  }
  const contents = fs.readFileSync(filename, "utf8");
  if (/-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(contents)) {
    throw new Error("Nunca forneça uma chave privada ao pacote do aplicativo.");
  }
  let key;
  try {
    key = crypto.createPublicKey(contents);
  } catch {
    throw new Error("O arquivo não contém uma chave pública válida.");
  }
  if (key.asymmetricKeyType !== "ed25519") {
    throw new Error("A raiz de confiança precisa ser uma chave pública Ed25519.");
  }
  return key;
}

function writePublicKey(filename, contents) {
  const temporary = path.join(
    path.dirname(filename),
    `.${path.basename(filename)}.${process.pid}.${crypto
      .randomBytes(5)
      .toString("hex")}.tmp`,
  );
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  try {
    fs.writeFileSync(temporary, contents, {
      flag: "wx",
      mode: 0o644,
    });
    fs.renameSync(temporary, filename);
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

try {
  const key = readRegularPublicKey(source);
  const pem = key.export({ type: "spki", format: "pem" });
  if (source !== destination || fs.readFileSync(source, "utf8") !== pem) {
    writePublicKey(destination, pem);
  }
  const fingerprint = crypto
    .createHash("sha256")
    .update(key.export({ type: "spki", format: "der" }))
    .digest("hex");
  console.log(
    `[update-trust] Chave pública Ed25519 preparada (SHA-256 ${fingerprint}).`,
  );
} catch (error) {
  fail(error?.message || "Não foi possível preparar a raiz de confiança.");
}
