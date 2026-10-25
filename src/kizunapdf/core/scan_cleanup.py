"""Experimental white-paper scans only. Every OCR output requires human review."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pymupdf as fitz
from PIL import ImageDraw

from kizunapdf.config import Settings

from .geometry import unrotate_box, vision_box
from .models import Block, Page
from .protect import japanese
from .render import render_page


def recognize(source: Path, page: Page, work: Path, settings: Settings):
    if not settings.ocr.is_file():
        raise RuntimeError("VisionOCR helper missing; run scripts/setup_mac.sh")
    image = render_page(source, page.page_index, settings.ocr_dpi)
    if np.mean(np.all(np.asarray(image) > 235, axis=2)) < 0.85:
        raise ValueError("unsupported_scan_style: background is colored, textured or photographic")
    path = work / f"ocr_{page.page_index:04d}.png"
    image.save(path)
    proc = subprocess.run(
        [str(settings.ocr), str(path)], capture_output=True, text=True, timeout=90
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr[:1000])
    result = json.loads(proc.stdout)
    if not result["japaneseSupported"]:
        raise RuntimeError("Apple Vision does not support Japanese on this Mac")
    cw, ch = page.crop_box[2] - page.crop_box[0], page.crop_box[3] - page.crop_box[1]
    for i, o in enumerate(result["observations"]):
        box = vision_box(tuple(o["bbox"]), page.width_pt, page.height_pt)
        unrotated = unrotate_box(box, cw, ch, page.rotation)
        if not japanese(o["text"]):
            continue
        mode = "translate" if o["confidence"] >= 0.7 else "protect"
        page.blocks.append(
            Block(
                id=f"p{page.page_index + 1:04d}-ocr{i + 1:04d}",
                source=o["text"],
                bbox_pdf_pt=box,
                bbox_unrotated=unrotated,
                reading_order=i,
                font_size_pt=max(7, (unrotated[3] - unrotated[1]) * 0.85),
                origin="ocr",
                source_confidence=o["confidence"],
                segmentation_confidence=0.5,
                protection_mode=mode,
                warnings=["experimental_ocr_requires_human_review"],
                translation_status="pending" if mode == "translate" else "protected",
            )
        )
    page.warnings.append("experimental_scan_cleanup_requires_human_review")
    if not page.blocks:
        raise ValueError("No reliable Japanese OCR text; scan requires manual review")
    (work / f"ocr_{page.page_index:04d}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )


def clean_scan(source: Path, page: Page, destination: Path, settings: Settings):
    if page.rotation or page.crop_offset != (0, 0):
        raise ValueError("unsupported_scan_style: rotated/cropped scans require manual review")
    image = render_page(source, page.page_index, settings.ocr_dpi)
    pixels = np.asarray(image)
    # Broad background test AND local annulus around every removal box.
    near_white = np.all(pixels > 235, axis=2)
    if near_white.mean() < 0.85:
        raise ValueError("unsupported_scan_style: background is colored, textured or photographic")
    draw = ImageDraw.Draw(image)
    scale = settings.ocr_dpi / 72
    for block in page.blocks:
        if block.protection_mode != "translate":
            continue
        x0, y0, x1, y1 = [int(v * scale) for v in block.bbox_unrotated]
        pad = 4
        ax, ay = max(0, x0 - pad), max(0, y0 - pad)
        bx, by = min(image.width, x1 + pad), min(image.height, y1 + pad)
        ring = pixels[ay:by, ax:bx].copy()
        mask = np.ones(ring.shape[:2], bool)
        mask[max(0, y0 - ay) : y1 - ay, max(0, x0 - ax) : x1 - ax] = False
        samples = ring[mask]
        if not len(samples) or np.mean(np.all(samples > 230, axis=1)) < 0.97:
            raise ValueError("unsupported_scan_style: artwork touches an OCR region")
        draw.rectangle((x0, y0, x1, y1), fill=tuple(int(v) for v in np.median(samples, axis=0)))
    temp = destination.with_suffix(".png")
    image.save(temp)
    with fitz.open() as clean:
        p = clean.new_page(width=page.width_pt, height=page.height_pt)
        p.insert_image(p.rect, filename=str(temp))
        clean.save(destination)
    temp.unlink()
