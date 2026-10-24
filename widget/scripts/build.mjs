import { copyFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const bundle = (entry, outfile, globalName) =>
  build({
    entryPoints: [fileURLToPath(new URL(entry, import.meta.url))],
    outfile: fileURLToPath(new URL(outfile, import.meta.url)),
    bundle: true,
    minify: true,
    format: "iife",
    globalName,
  });

await Promise.all([
  bundle("../src/index.ts", "../dist/askharbor.js", "AskHarborBundle"),
  bundle("../src/editor.ts", "../dist/editor.js", "AskHarborEditorBundle"),
  bundle("../src/admin.ts", "../dist/admin.js", "AskHarborAdminBundle"),
]);

await Promise.all([
  copyFile(
    new URL("../../examples/demo.html", import.meta.url),
    new URL("../dist/index.html", import.meta.url),
  ),
  copyFile(
    new URL("../../examples/editor.html", import.meta.url),
    new URL("../dist/editor.html", import.meta.url),
  ),
  copyFile(
    new URL("../../examples/admin.html", import.meta.url),
    new URL("../dist/admin.html", import.meta.url),
  ),
]);
