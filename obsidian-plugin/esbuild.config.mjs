import esbuild from "esbuild";
import builtins from "builtin-modules";
import { cpSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const prod = process.argv[2] === "production";
const __dir = dirname(fileURLToPath(import.meta.url));

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
  if (prod) {
    const src = resolve(__dir, "main.js");
    const dst = resolve(__dir, "../synthadoc/data/obsidian-plugin/main.js");
    cpSync(src, dst);
    console.log("synced main.js to synthadoc/data/obsidian-plugin/");
  }
});
