from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pikepdf
import pymupdf as fitz

from .geometry import contained, display_box, intersects
from .models import DocumentIR, QAReport
from .protect import japanese, literal_errors
from .render import render_page


def normalized(text):
    return re.sub(r"[\s\u00ad]+", "", text).replace("ﬀ", "ff").replace("ﬁ", "fi").replace("ﬂ", "fl")


def validate_structure(output: Path, ir: DocumentIR, report: QAReport):
    with pikepdf.open(output) as pdf:
        if len(pdf.pages) != len(ir.pages):
            report.add("failed", "page_count", "Output page count differs")
            return
        for page, expected in zip(pdf.pages, ir.pages, strict=True):
            for name, a, b in (
                ("MediaBox", page.mediabox, expected.media_box),
                ("CropBox", page.cropbox, expected.crop_box),
            ):
                if any(abs(float(x) - y) > 0.1 for x, y in zip(a, b, strict=True)):
                    report.add("failed", "geometry", f"{name} changed", expected.page_index)
            if int(page.obj.get("/Rotate", 0)) % 360 != expected.rotation:
                report.add("failed", "rotation", "Page rotation changed", expected.page_index)
    report.add("pass", "structural_check_completed", "Page count, boxes, and rotation inspected")


def run_qa(source: Path | None, output: Path, ir: DocumentIR) -> QAReport:
    report = QAReport()
    validate_structure(output, ir, report)
    with fitz.open(output) as pdf:
        for page in ir.pages:
            i = page.page_index
            if i >= len(pdf):
                break
            crop = (0, 0, page.crop_box[2] - page.crop_box[0], page.crop_box[3] - page.crop_box[1])
            text = normalized(pdf[i].get_text())
            for warning in page.warnings:
                report.add("needs_review", "page_warning", warning, i)
            for b in page.blocks:
                for warning in b.warnings:
                    report.add(
                        "warning"
                        if warning == "placeholder_fallback_literals_verified"
                        else "needs_review",
                        "region_warning",
                        warning,
                        i,
                        b.id,
                    )
                if b.protection_mode == "ignore":
                    report.add(
                        "needs_review",
                        "ignored_region",
                        b.override_reason or "Region ignored",
                        i,
                        b.id,
                    )
                    continue
                if b.protection_mode == "protect":
                    if b.origin == "native" and normalized(b.source) not in text:
                        report.add(
                            "failed", "protected_content", "Protected source text missing", i, b.id
                        )
                    if japanese(b.source):
                        report.add(
                            "needs_review",
                            "untranslated_region",
                            "Japanese region remains protected",
                            i,
                            b.id,
                        )
                    continue
                if not b.target:
                    report.add(
                        "failed", "missing_translation", "No target for translation region", i, b.id
                    )
                    continue
                target = normalized(b.target)
                region = fitz.Rect(b.layout_bbox or b.bbox_unrotated)
                found = normalized(pdf[i].get_text("text", clip=region + (-1, -1, 1, 1)))
                if target not in found:
                    report.add(
                        "failed",
                        "searchable_text",
                        "Complete target is not selectable inside its region",
                        i,
                        b.id,
                    )
                if normalized(b.source) in text and japanese(b.source) and b.origin == "native":
                    report.add(
                        "needs_review",
                        "source_residue",
                        "Source string still appears in output; inspect protected duplicates",
                        i,
                        b.id,
                    )
                for error in literal_errors(b.source, b.target):
                    report.add("needs_review", "literal_preservation", error, i, b.id)
                if japanese(b.target):
                    report.add(
                        "needs_review",
                        "target_language",
                        "Japanese remains in translated region",
                        i,
                        b.id,
                    )
                if len(b.target) > max(100, len(b.source) * 8):
                    report.add(
                        "needs_review", "length_ratio", "Unusually long translation", i, b.id
                    )
                crop = (
                    0,
                    0,
                    page.crop_box[2] - page.crop_box[0],
                    page.crop_box[3] - page.crop_box[1],
                )
                if not contained(tuple(region), crop):
                    report.add(
                        "failed", "out_of_bounds", "Target region extends beyond page", i, b.id
                    )
                for other in page.blocks:
                    if other.id != b.id and intersects(
                        tuple(region), other.layout_bbox or other.bbox_unrotated
                    ):
                        report.add(
                            "needs_review", "collision", f"Region intersects {other.id}", i, b.id
                        )
            if page.classification in ("scan", "mixed", "needs_review"):
                report.add(
                    "needs_review",
                    "experimental_page",
                    "OCR / image-based or ambiguous content needs visual review",
                    i,
                )
            if source:
                before = np.asarray(render_page(source, i, 150)).astype(float)
                after = np.asarray(render_page(output, i, 150)).astype(float)
                if before.shape != after.shape:
                    report.add("failed", "render_dimensions", "Rendered dimensions differ", i)
                    continue
                mask = np.ones(before.shape[:2], dtype=bool)
                scale = 150 / 72
                cw, ch = (
                    crop[2:]
                    if page.blocks
                    else (page.crop_box[2] - page.crop_box[0], page.crop_box[3] - page.crop_box[1])
                )
                for b in page.blocks:
                    if b.protection_mode == "translate":
                        for rect in (
                            b.bbox_pdf_pt,
                            display_box(b.layout_bbox or b.bbox_unrotated, cw, ch, page.rotation),
                        ):
                            x0, y0, x1, y1 = [int(v * scale) for v in rect]
                            mask[max(0, y0 - 5) : y1 + 6, max(0, x0 - 5) : x1 + 6] = False
                a, z = before[mask], after[mask]
                if len(a):
                    mismatch = float(np.mean(np.max(np.abs(a - z), axis=1) > 12))
                    # Masked global SSIM: explicitly not the local-window reference SSIM implementation.
                    av, zv = a.mean(), z.mean()
                    variance_a, variance_z = a.var(), z.var()
                    covariance = ((a - av) * (z - zv)).mean()
                    ssim = float(
                        ((2 * av * zv + 6.5025) * (2 * covariance + 58.5225))
                        / ((av * av + zv * zv + 6.5025) * (variance_a + variance_z + 58.5225))
                    )
                    report.metrics[f"page_{i + 1}"] = {
                        "unmodified_pixel_mismatch": mismatch,
                        "masked_global_ssim": ssim,
                        "dpi": 150,
                    }
                    if ssim < 0.98 or mismatch > 0.02:
                        report.add(
                            "needs_review",
                            "visual_fidelity",
                            "Unmodified-area comparison missed engineering target",
                            i,
                        )
    report.metrics["counts"] = {
        s: sum(d.severity == s for d in report.diagnostics)
        for s in ("pass", "warning", "needs_review", "failed")
    }
    return report
