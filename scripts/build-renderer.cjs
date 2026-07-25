"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const projectRoot = path.resolve(__dirname, "..");
const sourceDir = path.join(projectRoot, "renderer");
const outputDir = path.join(projectRoot, "dist");
const requiredFiles = ["index.html", "styles.css", "app.js"];
const missingFiles = requiredFiles.filter(
  (fileName) => !fs.existsSync(path.join(sourceDir, fileName)),
);

if (missingFiles.length > 0) {
  console.error(
    `[renderer] Arquivos obrigatórios ausentes: ${missingFiles.join(", ")}.`,
  );
  process.exitCode = 1;
} else {
  try {
    const appScript = path.join(sourceDir, "app.js");
    new vm.Script(fs.readFileSync(appScript, "utf8"), {
      filename: appScript,
    });
  } catch (error) {
    console.error(`[renderer] JavaScript inválido: ${error.message}`);
    process.exit(1);
  }

  fs.rmSync(outputDir, { recursive: true, force: true });
  fs.mkdirSync(outputDir, { recursive: true });
  fs.cpSync(sourceDir, outputDir, {
    recursive: true,
    force: true,
    filter(source) {
      const relative = path.relative(sourceDir, source);
      return !relative.split(path.sep).includes("node_modules");
    },
  });
  console.log(`[renderer] Arquivos copiados para ${path.relative(projectRoot, outputDir)}.`);
}
