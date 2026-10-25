import { cpSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
const require = createRequire(import.meta.url);
const root = dirname(require.resolve("pdfjs-dist/package.json"));
for (const asset of ["cmaps", "standard_fonts", "wasm"]) {
  mkdirSync("public/pdfjs", { recursive: true });
  cpSync(join(root, asset), join("public/pdfjs", asset), { recursive: true });
}
