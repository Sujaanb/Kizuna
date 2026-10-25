# Quality and its limits

The QA report is evidence about mechanical invariants, not a semantic translation score.
No fabricated model confidence is provided. Source OCR confidence comes from Vision;
segmentation confidence is a documented heuristic.

Hard gates include page count, MediaBox/CropBox/Rotate, source-removal checks, preserved
native protected text, selectable complete English in each assigned region, missing font
glyphs, compiler failure, measured height overflow, overfull words, and page bounds.
Protected literal mismatches cannot be silently accepted. If placeholder translation
fails, one raw-source retry must preserve the literal multiset; only unambiguous thousands
separator differences are normalized and the source spelling is restored.

Warnings requiring review include protected Japanese, experimental/mixed/outlined
pages, ambiguous directions, changed links/annotations, possible collisions, unusually
long translation, and a missed visual target. Explicit `ignore` requires a reason and
always appears in QA. The raw-source literal fallback is an informational warning after
successful exact verification.

At 150 DPI, original and result are compared outside source and target text rectangles
(with a 5-pixel antialiasing margin). Metrics include the fraction of pixels differing by
more than 12/255 and **masked global SSIM** using luminance/variance/covariance across all
unmasked samples. This is not the local-window SSIM benchmark used by scikit-image.
The engineering target is >=0.98 global SSIM and <=2% mismatched unmodified pixels;
this is neither a guarantee nor a translation-quality measure. The masking can hide
artwork damage inside a text region. Visual review remains necessary for overlapping art.

Scans use 250 DPI Vision OCR. A near-white global background test and local annulus test
restrict masking. These tests cannot prove every glyph pixel was removed. Therefore all
OCR output is `needs_review`, never verified scan fidelity. Complex backgrounds stop
cleanup. No learned inpainting or equation reconstruction is included.

Run `uv run pytest` for unit and local XeLaTeX integration tests. Default Linux CI skips
TeX-dependent fixtures and never fetches the model. Run `scripts/model_smoke.py` and
`scripts/real_integration.py` explicitly for local real-model acceptance. See the status
matrix for actual test results and remaining coverage gaps.
