# Synthetic examples

Run `uv run python examples/synthetic_fixtures_generator.py` on the configured Mac.
The generator uses XeLaTeX and the locally licensed Hiragino Sans system font to create
original fixture text/graphics. No user document or third-party copyrighted text is used.

Outputs in `tests/fixtures/generated/` include native prose, two columns, a ruled financial
table, preserved scientific formulas/URLs, landscape, mixed rotation/crop/nonzero-origin
pages, image/text overlap, white and complex scans, encrypted/blank/invalid PDFs.
All generated PDFs and raster assets are excluded from Git. `REFERENCES` is the explicit
human-authored fixture translator mapping used only in tests. The production CLI/UI has
no fake translator option.

The small native example is a functional acceptance sample, not a representative Japanese
translation benchmark. Inspect original and English pages plus QA output. Use your own
human-reviewed benchmark before making quality claims about specialized documents.
