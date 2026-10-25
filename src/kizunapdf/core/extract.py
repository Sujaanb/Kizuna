from __future__ import annotations

import hashlib
import re
import statistics
from pathlib import Path

import pikepdf
import pymupdf as fitz

from kizunapdf.config import Settings

from .geometry import contained, display_box
from .models import Block, DocumentInfo, DocumentIR, Glyph, Page, Span
from .protect import japanese


class InputError(ValueError):
    pass


def extract(path: Path, settings: Settings, password: str | None = None) -> DocumentIR:
    if path.stat().st_size > settings.max_upload_bytes:
        raise InputError("PDF exceeds the configured 50 MB limit")
    if not path.read_bytes()[:1024].lstrip().startswith(b"%PDF-"):
        raise InputError("Input is not a PDF")
    try:
        doc = fitz.open(path)
    except Exception as e:
        raise InputError("Invalid or damaged PDF") from e
    with doc:
        if doc.needs_pass and not doc.authenticate(password or ""):
            raise InputError("Encrypted PDF requires the correct runtime password")
        if not 0 < len(doc) <= settings.max_pages:
            raise InputError("PDF page count must be between 1 and 100")
        if doc.is_form_pdf:
            raise InputError("Interactive PDF forms are unsupported; flatten a copy first")
        with pikepdf.open(path, password=password or "") as raw:
            pages = []
            for i, page in enumerate(doc):
                media = tuple(float(v) for v in raw.pages[i].mediabox)
                crop = tuple(float(v) for v in raw.pages[i].cropbox)
                if float(raw.pages[i].obj.get("/UserUnit", 1)) != 1:
                    raise InputError("Non-default PDF UserUnit is unsupported")
                if not contained(crop, media):
                    raise InputError("CropBox outside MediaBox is unsupported")
                offset = (crop[0] - media[0], media[3] - crop[3])
                w, h = crop[2] - crop[0], crop[3] - crop[1]
                images = page.get_image_info()
                drawings = page.get_drawings()
                obstacles = [tuple(d["rect"]) for d in drawings] + [
                    tuple(im["bbox"]) for im in images
                ]
                try:
                    cells = [tuple(c) for t in page.find_tables().tables for c in t.cells if c]
                except Exception:
                    cells = []
                raw_blocks = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
                blocks = []
                for bi, raw_block in enumerate(raw_blocks):
                    if raw_block["type"] != 0:
                        continue
                    # A source block is a paragraph; separate lines inside ruled table cells.
                    groups = []
                    for line in raw_block["lines"]:
                        cell = next(
                            (c for c in cells if contained(tuple(line["bbox"]), c, 2)), None
                        )
                        if cell or not groups or groups[-1][1] or abs(line["dir"][1]) > 0.1:
                            groups.append(([line], cell))
                        else:
                            groups[-1][0].append(line)
                    for gi, (lines, cell) in enumerate(groups):
                        spans = []
                        texts = []
                        for line in lines:
                            line_text = ""
                            for s in line["spans"]:
                                chars = s.get("chars", [])
                                text = "".join(c["c"] for c in chars)
                                line_text += text
                                spans.append(
                                    Span(
                                        text=text,
                                        bbox=tuple(s["bbox"]),
                                        font=s["font"],
                                        size=s["size"],
                                        flags=s["flags"],
                                        color=s["color"],
                                        glyphs=[
                                            Glyph(
                                                text=c["c"],
                                                bbox=tuple(c["bbox"]),
                                                origin=tuple(c["origin"]),
                                            )
                                            for c in chars
                                        ],
                                    )
                                )
                            texts.append(line_text)
                        source = "\n".join(texts).strip()
                        if not source or not spans:
                            continue
                        bounds = fitz.Rect(spans[0].bbox)
                        for s in spans[1:]:
                            bounds |= fitz.Rect(s.bbox)
                        if bounds.is_empty:
                            continue
                        size = statistics.median(s.size for s in spans)
                        is_ja = japanese(source)
                        vertical = any(
                            abs(line["dir"][1]) > 0.1 or line.get("wmode", 0) for line in lines
                        )
                        equation = any(
                            any(c in s.text for c in "∑∫√∂∞≤≥") or "math" in s.font.lower()
                            for s in spans
                        )
                        equation = equation or bool(
                            re.search(r"[A-Za-z]\s*=\s*[A-Za-z0-9]", source)
                        )
                        role = (
                            "table_cell"
                            if cell
                            else "equation"
                            if equation
                            else "heading"
                            if size >= 16
                            else "footnote"
                            if size < 9
                            else "caption"
                            if source.startswith(("図", "表", "Fig."))
                            else "paragraph"
                        )
                        warnings = []
                        if vertical:
                            warnings.append("vertical_or_rotated_text_requires_review")
                        if equation and is_ja:
                            warnings.append("mixed_equation_prose_protected")
                        if "\ufffd" in source:
                            warnings.append("garbled_text_layer")
                        mode = "translate" if is_ja and not vertical and not equation else "protect"
                        blocks.append(
                            Block(
                                id=f"p{i + 1:04d}-b{bi + 1:04d}-{gi + 1}",
                                source=source,
                                bbox_unrotated=tuple(bounds),
                                bbox_pdf_pt=display_box(tuple(bounds), w, h, page.rotation),
                                reading_order=len(blocks),
                                spans=spans,
                                table_cell=cell,
                                font_family=spans[0].font,
                                font_size_pt=size,
                                font_weight="bold" if spans[0].flags & 16 else "normal",
                                italic=bool(spans[0].flags & 2),
                                rgb=f"#{spans[0].color:06x}",
                                line_height_pt=size * 1.2,
                                role=role,
                                direction="vertical" if vertical else "horizontal",
                                protection_mode=mode,
                                translation_status="pending"
                                if mode == "translate"
                                else "protected",
                                warnings=warnings,
                            )
                        )
                # Column-major for distinct columns, retaining full-width headings first.
                midpoint = w / 2
                left = [b for b in blocks if b.bbox_unrotated[2] < midpoint + 10]
                right = [b for b in blocks if b.bbox_unrotated[0] > midpoint - 10]
                columns = len(left) >= 2 and len(right) >= 2
                blocks.sort(
                    key=lambda b: (
                        (
                            (
                                0
                                if b.bbox_unrotated[2] - b.bbox_unrotated[0] > w * 0.65
                                else 1
                                if b in left
                                else 2
                            ),
                            b.bbox_unrotated[1],
                            b.bbox_unrotated[0],
                        )
                        if columns
                        else (b.bbox_unrotated[1], b.bbox_unrotated[0])
                    )
                )
                for order, b in enumerate(blocks):
                    b.reading_order = order
                large_image = any(fitz.Rect(im["bbox"]).get_area() > w * h * 0.45 for im in images)
                kind = (
                    "mixed"
                    if blocks and large_image
                    else "native"
                    if blocks
                    else "scan"
                    if images
                    else "needs_review"
                    if drawings
                    else "empty"
                )
                warnings = []
                if page.annots() and list(page.annots()):
                    warnings.append("annotations_are_not_preserved")
                if page.get_links():
                    warnings.append("hyperlink_semantics_not_preserved")
                if kind in ("mixed", "needs_review"):
                    warnings.append("image_or_outlined_text_requires_manual_review")
                pages.append(
                    Page(
                        page_index=i,
                        width_pt=page.rect.width,
                        height_pt=page.rect.height,
                        media_box=media,
                        crop_box=crop,
                        crop_offset=offset,
                        rotation=page.rotation,
                        classification=kind,
                        blocks=blocks,
                        obstacles=obstacles,
                        warnings=warnings,
                        extraction_confidence=0.5 if any(b.warnings for b in blocks) else 1,
                    )
                )
    return DocumentIR(
        document=DocumentInfo(
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            page_count=len(pages),
            filename=path.name,
        ),
        pages=pages,
    )
