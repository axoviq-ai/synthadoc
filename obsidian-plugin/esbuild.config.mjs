import esbuild from "esbuild";
import builtins from "builtin-modules";
import { cpSync, readFileSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const prod = process.argv[2] === "production";
const __dir = dirname(fileURLToPath(import.meta.url));

// Bundled third-party libraries (moment, cytoscape) use Function("return this")()
// as a UMD global-scope accessor.  Obsidian runs on Electron/Chromium where
// globalThis is always available, so the pattern is dead code.  Replacing it
// removes a false-positive eval/exec finding from static security scanners.
const PATCHES = [
  ['Function("return this")()', "globalThis"],
];

function patchBundle(path) {
  let text = readFileSync(path, "utf8");
  let patched = text;
  for (const [from, to] of PATCHES) {
    patched = patched.replaceAll(from, to);
  }
  if (patched !== text) {
    writeFileSync(path, patched, "utf8");
    console.log(`patched main.js (Function("return this") → globalThis)`);
  }
}

esbuild.build({
  entryPoints: ["src/main.ts"],
  bundle: true,
  external: ["obsidian", "electron", ...builtins],
  format: "cjs",
  target: "es2018",
  logLevel: "info",
  sourcemap: prod ? false : "inline",
  minify: prod,
  outfile: "main.js",
}).then(() => {
  const src = resolve(__dir, "main.js");
  patchBundle(src);
  if (prod) {
    const dst = resolve(__dir, "../synthadoc/data/obsidian-plugin/main.js");
    cpSync(src, dst);
    console.log("synced main.js to synthadoc/data/obsidian-plugin/");
  }
});
