"use strict";

// Regenerates all committed desktop branding assets.
// Requires Inkscape plus ImageMagick (`magick` on Windows, `convert` elsewhere).

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const buildDirectory = __dirname;
const assetsDirectory = path.join(buildDirectory, "assets");
const trayDirectory = path.join(buildDirectory, "tray");
const iconSource = path.join(buildDirectory, "icon.svg");
const iconPng = path.join(buildDirectory, "icon.png");
const iconIco = path.join(buildDirectory, "icon.ico");
const wordmarkSource = path.join(assetsDirectory, "aether-wordmark.png");
const wordmarkTransparent = path.join(
  assetsDirectory,
  "aether-wordmark-transparent.png",
);
const portableSplash = path.join(buildDirectory, "portable-splash.bmp");
const installerHeader = path.join(buildDirectory, "installerHeader.bmp");
const installerSidebar = path.join(buildDirectory, "installerSidebar.bmp");
const uninstallerSidebar = path.join(buildDirectory, "uninstallerSidebar.bmp");
const trayStates = ["online", "working", "offline"];
const trayRepresentations = [
  { suffix: "", size: 16 },
  { suffix: "@1.25x", size: 20 },
  { suffix: "@1.5x", size: 24 },
  { suffix: "@2x", size: 32 },
];
const iconSizes = "256,128,64,48,40,32,24,20,16";
const toolProfileDirectory = path.join(
  os.tmpdir(),
  "aether-branding-tools",
);
fs.mkdirSync(toolProfileDirectory, { recursive: true });
const toolEnvironment = {
  ...process.env,
  XDG_CACHE_HOME: path.join(toolProfileDirectory, "cache"),
  XDG_CONFIG_HOME: path.join(toolProfileDirectory, "config"),
  XDG_DATA_HOME: path.join(toolProfileDirectory, "data"),
};

function commandWorks(command, args = ["--version"]) {
  const result = spawnSync(command, args, {
    cwd: buildDirectory,
    encoding: "utf8",
    env: toolEnvironment,
    shell: false,
    stdio: "ignore",
  });
  return !result.error && result.status === 0;
}

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: buildDirectory,
    encoding: "utf8",
    env: toolEnvironment,
    shell: false,
    stdio: ["ignore", "inherit", "pipe"],
  });
  if (result.error || result.status !== 0) {
    if (result.stderr) {
      process.stderr.write(result.stderr);
    }
    throw result.error ||
      new Error(`${command} terminou com código ${result.status}.`);
  }
}

function renderSvg(source, destination, size) {
  run("inkscape", [
    source,
    `--export-filename=${destination}`,
    `--export-width=${size}`,
    `--export-height=${size}`,
  ]);
}

function bitmapDestination(destination) {
  return `BMP3:${destination}`;
}

if (!fs.existsSync(iconSource)) {
  console.error("[branding] build/icon.svg não encontrado.");
  process.exitCode = 1;
} else if (!fs.existsSync(wordmarkSource)) {
  console.error("[branding] build/assets/aether-wordmark.png não encontrado.");
  process.exitCode = 1;
} else if (
  trayStates.some(
    (state) => !fs.existsSync(path.join(trayDirectory, `${state}.svg`)),
  )
) {
  console.error("[branding] Fontes SVG da bandeja estão incompletas.");
  process.exitCode = 1;
} else if (!commandWorks("inkscape")) {
  console.error("[branding] Instale o Inkscape para renderizar SVG.");
  process.exitCode = 1;
} else {
  const imageMagick = commandWorks("magick")
    ? "magick"
    : (commandWorks("convert") ? "convert" : null);

  if (!imageMagick) {
    console.error("[branding] Instale o ImageMagick para gerar PNG, ICO e BMP.");
    process.exitCode = 1;
  } else {
    try {
      fs.mkdirSync(assetsDirectory, { recursive: true });
      fs.mkdirSync(trayDirectory, { recursive: true });

      renderSvg(iconSource, iconPng, 1024);
      run(imageMagick, [
        iconPng,
        "-define",
        `icon:auto-resize=${iconSizes}`,
        iconIco,
      ]);

      run(imageMagick, [
        wordmarkSource,
        "-colorspace",
        "Gray",
        "-alpha",
        "copy",
        "-fill",
        "#FFFFFF",
        "-colorize",
        "100",
        "-trim",
        "+repage",
        "-bordercolor",
        "none",
        "-border",
        "36x28",
        wordmarkTransparent,
      ]);

      for (const state of trayStates) {
        const source = path.join(trayDirectory, `${state}.svg`);
        for (const representation of trayRepresentations) {
          const light = path.join(
            trayDirectory,
            `tray-light-${state}${representation.suffix}.png`,
          );
          const dark = path.join(
            trayDirectory,
            `tray-dark-${state}${representation.suffix}.png`,
          );
          renderSvg(source, light, representation.size);
          run(imageMagick, [
            light,
            "-channel",
            "RGB",
            "-negate",
            "+channel",
            dark,
          ]);
        }

        const templateName =
          `Aether${state[0].toUpperCase()}${state.slice(1)}Template`;
        renderSvg(
          source,
          path.join(trayDirectory, `${templateName}.png`),
          18,
        );
        renderSvg(
          source,
          path.join(trayDirectory, `${templateName}@2x.png`),
          36,
        );
      }

      run(imageMagick, [
        "-size",
        "420x240",
        "xc:#000000",
        "(",
        wordmarkTransparent,
        "-resize",
        "282x120",
        ")",
        "-gravity",
        "center",
        "-composite",
        "-alpha",
        "off",
        "-type",
        "TrueColor",
        bitmapDestination(portableSplash),
      ]);

      run(imageMagick, [
        "-size",
        "150x57",
        "xc:#000000",
        "(",
        wordmarkTransparent,
        "-resize",
        "122x45",
        ")",
        "-gravity",
        "center",
        "-composite",
        "-alpha",
        "off",
        "-type",
        "TrueColor",
        bitmapDestination(installerHeader),
      ]);

      run(imageMagick, [
        "-size",
        "164x314",
        "xc:#000000",
        "(",
        iconPng,
        "-resize",
        "104x104",
        ")",
        "-gravity",
        "north",
        "-geometry",
        "+0+48",
        "-composite",
        "(",
        wordmarkTransparent,
        "-resize",
        "132x64",
        ")",
        "-gravity",
        "north",
        "-geometry",
        "+0+174",
        "-composite",
        "-alpha",
        "off",
        "-type",
        "TrueColor",
        bitmapDestination(installerSidebar),
      ]);
      fs.copyFileSync(installerSidebar, uninstallerSidebar);

      console.log(
        "[branding] Ícone, wordmark, bandeja e imagens do instalador atualizados.",
      );
    } catch (error) {
      console.error(`[branding] Falha: ${error.message}`);
      process.exitCode = 1;
    }
  }
}
