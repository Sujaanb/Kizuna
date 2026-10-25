# Third-party notices

Application source: AGPL-3.0-only. Copyright 2026 KizunaPDF contributors.
The license applies to this application, not to separately downloaded model weights,
Apple system software/fonts, or dependencies under their own terms.

| Component | License / notice |
|---|---|
| PyMuPDF / MuPDF | AGPLv3 or commercial Artifex license. [Licensing](https://pymupdf.io/licensing) |
| pikepdf / qpdf | MPL-2.0 / Apache-2.0; see installed distributions |
| pypdfium2 / PDFium | Apache-2.0 or BSD-3-Clause wrapper; PDFium BSD and bundled third-party notices |
| MLX / mlx-lm | MIT |
| TranslateGemma / MLX community quantization | Separate [Gemma Terms](https://ai.google.dev/gemma/terms); [upstream model](https://huggingface.co/google/translategemma-4b-it), [quantization](https://huggingface.co/mlx-community/translategemma-4b-it-4bit). Not AGPL, Apache or MIT weights. |
| FastAPI, Pydantic, Typer, uvicorn | MIT or BSD (see each installed distribution) |
| React, Vite, Tailwind CSS, Lucide | MIT / ISC as distributed |
| PDF.js | Apache-2.0 |
| NumPy / Pillow | BSD-3-Clause / HPND |
| XeTeX / TeX Live | Multiple free-software licenses; individual packages retain their licenses |
| Apple Vision / macOS fonts | Apple system components; not redistributed in this repository |

Design references (no implementation source copied):
[Qi et al., BabelDOC, ACL 2026](https://aclanthology.org/2026.acl-demo.25/),
[BabelDOC](https://github.com/funstory-ai/BabelDOC),
[PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate).
The IR separation and protected-content design are informed by those works.
KizunaPDF makes no scientific-novelty or comparative-quality claim.

Synthetic fixture prose and graphics are original to this project. Fonts are resolved
from the local system during generation; font files are not shipped. TeX may embed
font subsets in the user's locally generated PDF under the installed font's terms.
