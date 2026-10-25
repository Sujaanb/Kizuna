# Document IR 1.0

The authoritative machine schema is [document_ir.schema.json](document_ir.schema.json),
generated from `kizunapdf.core.models.DocumentIR.model_json_schema()`.

Each document contains its input SHA256, source/target languages, page count and safe
filename. Pages retain raw PDF bottom-left MediaBox/CropBox coordinates and `/Rotate`,
along with visible width/height and crop offset from the unrotated full MediaBox.

`bbox_unrotated` and glyph/span rectangles are crop-relative top-left points, matching
PyMuPDF extraction. `bbox_pdf_pt` is the rotated visible-page top-left rectangle used by
the UI. `layout_bbox` is the allocated English rectangle in unrotated crop coordinates.
TeX uses `layout_bbox + crop_offset` on a full-MediaBox canvas. `geometry.py` implements
these conversions. No A4 dimensions are hardcoded into processing.

Stable region IDs use source page/block/group indices. OCR uses separate stable IDs.
Source style runs and glyph origins are retained. The dominant run supplies overlay
style. Table cell rectangles constrain placement. Roles and segmentation confidence are
heuristic. Region protection is `translate`, `protect`, or `ignore`; a manual protection
change requires a recorded reason. Translation status distinguishes generated and manual
text. Exported IR is human-readable JSON; editing it changes QA expectations on rebuild.

IR uses strict extra-field checks, finite numbers, positive block rectangles and unique
region IDs. Additional language/provider fields can be versioned in a future schema.
