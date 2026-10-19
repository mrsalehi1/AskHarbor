import { copyFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

await build({
  entryPoints: [fileURLToPath(new URL("../src/index.ts", import.meta.url))],
  outfile: fileURLToPath(new URL("../dist/askharbor.js", import.meta.url)),
  bundle: true,
  minify: true,
  format: "iife",
  globalName: "AskHarborBundle",
});

await copyFile(
  new URL("../../examples/demo.html", import.meta.url),
  new URL("../dist/index.html", import.meta.url),
);
