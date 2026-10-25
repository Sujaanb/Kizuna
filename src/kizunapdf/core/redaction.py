from pathlib import Path

import pikepdf
import pymupdf as fitz

from kizunapdf.config import Settings

from .geometry import intersects
from .models import DocumentIR
from .qa import normalized
from .scan_cleanup import clean_scan


def sanitize(source: Path, ir: DocumentIR, work: Path, settings: Settings, cancel=lambda: False):
    destination = work / "assets/backgrounds"
    destination.mkdir(parents=True, exist_ok=True)
    for page_ir in ir.pages:
        if cancel():
            raise InterruptedError("Cancelled")
        out = destination / f"page_{page_ir.page_index + 1:04d}.pdf"
        if page_ir.classification == "scan" and any(b.target for b in page_ir.blocks):
            clean_scan(source, page_ir, out, settings)
            continue
        with fitz.open(source) as original:
            clean = fitz.open()
            clean.insert_pdf(
                original,
                from_page=page_ir.page_index,
                to_page=page_ir.page_index,
                links=False,
                annots=False,
                widgets=False,
            )
            page = clean[0]
            translated = [
                b for b in page_ir.blocks if b.protection_mode == "translate" and b.target
            ]
            kept = [
                g for b in page_ir.blocks if b not in translated for s in b.spans for g in s.glyphs
            ]
            for block in translated:
                for span in block.spans:
                    for glyph in span.glyphs:
                        if glyph.text.isspace():
                            continue
                        rect = fitz.Rect(glyph.bbox)
                        # A small inset avoids adjacent edge contacts without missing glyph intersections.
                        rect = fitz.Rect(
                            rect.x0 + 0.15, rect.y0 + 0.15, rect.x1 - 0.15, rect.y1 - 0.15
                        )
                        if rect.is_empty:
                            continue
                        if any(intersects(tuple(rect), g.bbox) for g in kept):
                            raise ValueError(
                                f"Unsafe redaction overlaps protected text: {block.id}"
                            )
                        page.add_redact_annot(rect, fill=False, cross_out=False)
            if translated:
                page.apply_redactions(
                    images=fitz.PDF_REDACT_IMAGE_NONE,
                    graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                    text=fitz.PDF_REDACT_TEXT_REMOVE,
                )
            for block in translated:
                if page.get_text("text", clip=fitz.Rect(block.bbox_unrotated)).strip():
                    raise ValueError(f"Source text remains after redaction: {block.id}")
            for b in page_ir.blocks:
                if b not in translated and b.origin == "native":
                    if normalized(b.source) not in normalized(page.get_text()):
                        raise ValueError(f"Protected text changed during redaction: {b.id}")
            page.set_rotation(0)
            clean.save(out, garbage=4, deflate=True, clean=True)
            clean.close()
        # Background includes full original MediaBox, not the cropped display window.
        with pikepdf.open(out, allow_overwriting_input=True) as pdf:
            pdf.pages[0].cropbox = pikepdf.Array(page_ir.media_box)
            pdf.save(out)
