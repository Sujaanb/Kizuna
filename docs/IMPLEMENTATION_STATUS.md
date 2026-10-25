# Implementation status — 2026-10-26

A working local Phase 1 implementation exists. The native acceptance path has been
proven with **real TranslateGemma inference and real XeLaTeX**, not a fake translator.
This is an early implementation with explicit limitations; not every aspirational
capability in the original brief is complete.

## Observed environment and model

- Apple Silicon macOS 27.0.1, 16 GB unified memory; ample free disk.
- Python 3.12.14, Node 24.22.1, uv 0.13.5, pnpm 11.25.0.
- Project-local TeX Live 2026 / XeLaTeX; Swift Vision helper compiled with `swiftc -O`.
- Vision returned `ja-JP` and `en-US` as supported languages.
- Model: `mlx-community/translategemma-4b-it-4bit`, commit
  `5788ec08c047f3f2e17808101b8d9566ac930d58`.
- User explicitly accepted Gemma Terms before the download. No weights are committed.
- Tokenizer template SHA256:
  `5e85514635b80a62b64c9982810bfdfbdd482be9a59ed12c25ded2bf3aabddaf`.
- MLX-LM 0.31.3, MLX 0.32.4, PyMuPDF 1.28.2, pikepdf 10.17.0,
  pypdfium2 5.14.0. Exact dependency resolution is in the lockfiles.

## Real native acceptance evidence

Command: `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/real_integration.py`.
The script also denied Python AF_INET/AF_INET6 socket connections while processing.
Observed **zero attempted internet socket connections**, four cache misses and zero
cache hits. This is an instrumented application-level offline test, not a physical
network disconnect or OS-wide packet capture.

The synthetic native page contains a Japanese heading, three Japanese sentences, an
amount, preserved formula text, a vector rectangle and a Latin footer. Output:

| Japanese source | Actual model output |
|---|---|
| 研究報告 | Research report |
| これは日本語の文書です。 | This is a Japanese document. |
| 数式と図を保持します。 | It will preserve formulas and diagrams. |
| 売上は1200円です。 | The sales totaled 1200 yen. |

The amount used the verified literal fallback described in DECISIONS.md; the first
placeholder attempt had fabricated an amount and was rejected. Original translated
Japanese was physically absent from native background text. English was searchable.
Formula/footer/vector artwork survived. Page count was one and original boxes were
595.28 × 841.89 PDF points. Automated result: `verified`, one informational fallback
warning. The relocated exported ZIP rebuilt to another `verified` PDF without inference.

Measured one-page run: **4.664 seconds**, including lazy model load and reconstruction;
peak process RSS **1,642,561,536 bytes**, MLX peak allocation **2,381,847,088 bytes**.
These are separate memory measurements, not additive estimates of total system RAM.
This small run is not a throughput/thermal benchmark or a guarantee for other documents.
Unmodified-area mismatch was **0.0** at 150 DPI and masked global SSIM was
**0.999999894**. Source/output PNGs were visually inspected locally.

Local, ignored evidence files:
`output/acceptance/native.en.pdf`, `native.kizunapdf.zip`, `rebuilt.pdf`,
`manifest.json`, `qa_report.json`, and source/output PNGs. They contain only synthetic
material. The repository includes the generator, not generated PDFs or model artifacts.

## Tested and implemented matrix

| Area | Status | Evidence / limit |
|---|---|---|
| Typed IR, glyphs/styles, geometry | Implemented and tested | Schema export; native, crop, 90° rotation, mixed landscape and negative/nonzero origin fixtures |
| Preflight limits, bad/encrypted files | Implemented and tested | Runtime password, bad input, size limit; forms/UserUnit rejected |
| Paragraph/column/table segmentation | Implemented heuristics, partial generality | Two-column and ruled-table fixtures; unusual layouts may need manual ordering |
| Protected literals / cache | Implemented and tested | Strict markers, numeric fallback, immutable multiset, revision-aware cache |
| Real local MLX | Implemented and tested | Actual model smoke test plus uncached native integration; token cap and end-turn fix |
| Native source removal | Implemented and tested | Glyph redaction, protected text checks, vector/image overlap fixture, original excluded from ZIP |
| XeLaTeX / exact geometry merge | Implemented and tested | Editable per-page TeX, measured fitting, overflow refusal, mixed boxes and orientations |
| QA | Implemented with known blindspots | Text/geometry/collision and masked global visual metrics; semantic meaning remains human-reviewed |
| CLI | Implemented and tested | Doctor, translate, model setup/status, manifest validation, ZIP/directory rebuild, loopback serve |
| Browser workflow | Implemented and manually tested | Actual upload, PDF.js Japanese rendering, translation, region edit, no-inference rebuild, export links |
| White scans | Experimental, tested on this Mac | Vision recognized synthetic Japanese; cleanup produced `needs_review` draft; visual inspection performed |
| Textured scans | Guarded rejection tested | `unsupported_scan_style`, no output PDF |
| Queue / cancel / recovery | Implemented, partial hardening | One worker, bounded queue, cancellation regression, stale-job recovery; no cross-process coordination |
| API boundary | Implemented and tested | Host/origin/session checks, chunked body cap, upload validation, UUID routes, traversal-resistant ZIP |
| Offline operation | Application-level tested | Cached local model, socket-denial acceptance, local PDF.js assets; no OS packet-capture claim |
| Setup / launcher / docs | Implemented | Executable Mac launcher, explicit model opt-in, environment checks and repair commands |
| GitHub CI configuration | Prepared; not remotely run | Lean tests/build, no model downloads |
| GitHub publication | Blocked by missing CLI/auth setup | No gh executable/config and no GH_TOKEN/GITHUB_TOKEN; no repo URL claimed |

## Checks and browser evidence

- `.venv/bin/ruff check src tests examples scripts` — passed.
- `.venv/bin/ruff format --check src tests examples scripts` — passed.
- `.venv/bin/pytest -q` — **32 passed**; third-party SWIG and
  Starlette/httpx deprecation warnings do not affect the checks.
- `pnpm --dir frontend build` — passed TypeScript and Vite production compilation.
  Vite warns that the PDF.js application chunk is >500 kB; all assets remain local.
- `kizunapdf validate ... --manifest ...` and ZIP `rebuild --output ...` — exercised.
- Browser uploaded the native fixture, translated it, edited “Research report” to
  “Research Report”, and rebuilt to `verified`. The rebuild manifest showed zero model
  cache misses and no MLX allocations in that server process; elapsed 0.352 seconds.
- [Actual browser screenshot](screenshots/review.png) shows the synthetic edited result.
  At the current narrow app panel width, the two previews stack responsively. Desktop
  widths use two columns. No fabricated UI screenshot is included.

## Partial / deferred items

- Source styles are captured per run, but the English block uses its dominant style.
  No general mixed-style or equation-to-editable-LaTeX reconstruction.
- Native garbled/mixed/outlined content is flagged; localized OCR recovery on arbitrary
  native image regions is not implemented. Vertical Japanese is protected and reviewed.
- Simple tables/columns work heuristically; there is no learned document-layout model.
- Scans use conservative white-background masking, not general image restoration or a
  proven glyph residual detector. Every scan draft requires human review.
- The glossary protection utility is tested, but no UI/CLI glossary editor is exposed.
- Region text/protection/order can be edited. Drag-resizing layout boxes and compiling
  only affected pages are deferred; current rebuild compiles the whole document.
- No cross-process worker lock, mid-kernel Metal cancellation, or full OS-level PDF/TeX
  sandbox. Run one service per data directory; compile only trusted edited bundles.
- No full hyperlink/annotation/TOC preservation, accessibility tags, signatures, forms,
  rich scans, multilingual directions or native app packaging.
- No automated full browser suite yet; UI smoke verification was manual via browser tools.
  No broad human translation benchmark, multilingual corpus, or thermal soak measurement.

The implementation must not be described as universally pixel-perfect, semantically
certified, secure-redaction software, or as fully implementing every research proposal.

## Source audit and local commit

The staged source audit found no credential patterns, personal absolute paths, model
weights, runtime/job files or files over 5 MB. Original implementation prompts remain
local and ignored. The only tracked binary is the actual synthetic UI screenshot.
No pre-existing remote was present. Git author identity was not configured, so the
initial local commit is attributed explicitly to `Codex <codex@localhost>`, not to an
invented user identity. Configure your preferred Git identity before future commits.
No GitHub repository was created or pushed; installation/authentication is still needed.
