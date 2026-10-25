# Engineering decisions

2026-10-26, inspected on the user's Mac. Native arm64 macOS 27.0.1, 16 GB RAM.
Python 3.12.14 and Node 24.22.1 were available through Codex's local runtime; no normal
uv, Node, pnpm, gh or XeLaTeX command was initially on PATH. Apple CLT was present.
uv 0.13.5 and dependencies were installed into project-local `.tools` / `.venv`.
TeX Live 2026 scheme-basic plus XeTeX/fontspec/eso-pic and companion packages was
installed under `.tools/texlive`, with no sudo/system package changes. The installer
used the CTAN-selected JAIST HTTPS mirror; GPG was unavailable, which TeX Live reported.
The Swift package compiled, but sandboxed dSYM generation failed; `swiftc -O` without
debug symbols built the same helper successfully. Japanese Vision support was queried,
not assumed. Lockfiles capture the installed Python and UI dependencies.

## Core choices

- Preserve native vector PDF objects using transparent glyph-level redaction. Keep
  equations and already-English regions as original artwork/text. Re-typeset translated
  mixed-language paragraphs completely, restoring protected literals in the overlay.
- Use the full, unrotated MediaBox for XeLaTeX, translate its content stream for nonzero
  media origins, and restore raw CropBox/Rotate values during pikepdf merge. Display
  coordinates are separately normalized to the rotated visible crop.
- Use measured TeX vbox heights and overfull diagnostics, bounded whitespace expansion,
  and 100/92.5/85 percent font trials. Never silently clip or drop words.
- Use one in-process MLX provider and one inference worker. No local model HTTP server.
- Use only the official structured TranslateGemma template; no system message.
- The downloaded snapshot's default EOS set omitted `<end_of_turn>`. Live generation
  emitted that token repeatedly after the correct answer. Registering the token through
  the tokenizer's `add_eos_token` fixes stopping without a hardcoded token ID.
- A live test changed `KZPHAZ` to `12,345`. Placeholder output is always validated. One
  fallback retries the original source, verifies the exact multiset of literals (allowing
  thousands-separator equivalence), then restores original literal spellings. If that
  fails, no PDF is exported. The fallback is recorded in region warnings.
- Scans are experimental: local Vision, whole-page near-white test, per-region border
  test, masking only eligible text. OCR results always require human review. Rotated/
  cropped scans and textured backgrounds are refused by cleanup.
- UI and CLI share the same job service. The browser loads its scripts, worker and fonts
  locally. Native PDF previews use PDF.js, not remote viewers.

## References inspected

Only designs/API guidance were consulted; no implementation source was copied.

- [BabelDOC paper, Qi et al., ACL 2026](https://aclanthology.org/2026.acl-demo.25/): separation of geometry and semantics.
- [BabelDOC repository](https://github.com/funstory-ai/BabelDOC), [PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate): baseline scope and protected-content pitfalls.
- [Google TranslateGemma](https://huggingface.co/google/translategemma-4b-it): structured language-aware message contract.
- [MLX quantization](https://huggingface.co/mlx-community/translategemma-4b-it-4bit), [mlx-lm](https://github.com/ml-explore/mlx-lm): local model/runtime.
- [PyMuPDF Page API](https://pymupdf.readthedocs.io/en/latest/page.html): unrotated extraction coordinates and redaction arguments. Installed signature and behavior tested.
- [PyMuPDF licensing](https://pymupdf.io/licensing): application licensed AGPL-3.0-only.
- [pikepdf composition](https://pikepdf.readthedocs.io/en/stable/topics/overlays.html).
- [Apple Vision](https://developer.apple.com/documentation/vision/vnrecognizetextrequest): recognition language discovery and local helper.
- [MacTeX](https://www.tug.org/mactex/) (browser fetch returned 403; official TeX Live installer downloaded successfully), [textpos](https://ctan.org/pkg/textpos). This implementation uses eso-pic absolute placement.

No claim of superiority to the referenced systems, universal fidelity, or scientific novelty.
