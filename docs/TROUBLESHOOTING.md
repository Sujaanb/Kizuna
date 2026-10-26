# Troubleshooting

| Symptom | Action |
|---|---|
| `uv` / `node` / `pnpm` not found | Use `scripts/start.command` in the configured checkout. For a fresh machine install uv and Node LTS/pnpm, then rerun setup. `KIZUNA_ROOT="$PWD"; . ./scripts/env.sh` exposes available local tools. |
| `xelatex` not found | Install BasicTeX or set `KIZUNAPDF_XELATEX` to an absolute executable. Doctor also searches `/Library/TeX/texbin` and this checkout's `.tools/texlive`. |
| Missing `.sty` package | Read the page's `.log`; use the owning TeX installation's absolute `tlmgr install` command. Never use sudo for a user-local TeX tree. |
| Missing font / missing characters | Rebuild with the current version: individual missing glyphs fall back to Hiragino Sans/Noto Sans CJK JP, then Apple Symbols/DejaVu Sans. Full-width digits and symbols are preserved. If all fonts lack a glyph, the error identifies its Unicode code point and region ID; install a covering local font or correct the target text. |
| Blank or missing CJK in preview | Rebuild UI with `pnpm --dir frontend build`; this copies local PDF.js CMaps, standard fonts and wasm assets. Reload. Check `/pdfjs/cmaps/` is served locally. |
| No Metal device in Codex sandbox | Run the same command in a normal Mac Terminal. GPU access can be denied by tool isolation despite a working MLX installation. No cloud fallback is used. |
| Model not cached / partial download | `kizunapdf model status`, then explicit `model download`. Check free disk and the model path. Processing never silently downloads. |
| Hugging Face 401/403 | Accept the official model's access terms, `hf auth login`, then retry. Never paste tokens into source files or issue reports. |
| Model OOM or slow translation | Close memory-heavy apps; run only one KizunaPDF service/model process. Keep the 4-bit 4B model. Shorten a very long region. Cancellation checks occur between generated tokens. |
| Placeholder changed | The app tries once with original text and exact literal verification. If that fails, edit the translation and rebuild; no result with invented values is accepted. |
| Overflow / very long word | Open Quality report and select a text overflow issue to jump to its page and region editor. Shorten the English and Save & rebuild. All affected pages are reported together. Table fitting uses free horizontal space and stops above neighboring labels, including preserved English. No clipped PDF is released. Font shrinking is bounded to 85%, with a 7pt floor unless the original is already smaller. |
| Unknown orientation / crop | Native rotated/cropped/negative-origin fixtures are tested. Review any new unusual PDF; do not normalize page boxes manually merely to hide a failure. Non-default UserUnit is rejected. |
| Japanese Vision unavailable | `VisionOCR --languages` must report Japanese. Update compatible macOS/CLT or use native PDFs. No external OCR service is substituted. |
| Swift build / SDK failure | Confirm `xcode-select -p`; update Apple CLT through Apple's tools. Setup builds the small helper with `swiftc -O` and a project-local module cache. |
| Scan cleanup rejected | Textured/colored/photographic backgrounds, border artwork or uncertain OCR need manual review. Use a clean source PDF when possible; scan output always carries review status. |
| App interrupted | Restart, choose the recent job, and resume translation. Saved translated segments are retained. Rebuild uses saved text without model inference. |
| Port already in use | Stop the old launcher with Ctrl-C. Alternatively `kizunapdf serve --port 8788` and open that loopback URL. LAN binding is refused. |
| Finder/Gatekeeper warning | Inspect the source and use macOS's normal Open workflow. Do not disable platform security globally. |
| Encrypted PDF | Use `--password` for a hidden runtime prompt or the upload password field. The password is not stored. Forms must be flattened in a copy first. |
| Old output after editing | Edits invalidate exports; Save & rebuild updates them. If QA fails, inspect the issue rather than using an older PDF. |

Compile logs and intermediate files live only in the private job directory. A failed job
keeps useful diagnostics, but does not expose a stale PDF as its current result. Never
post those logs publicly without checking for private document text and local paths.
