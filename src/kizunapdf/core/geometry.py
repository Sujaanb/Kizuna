"""All extraction coordinates are crop-relative, unrotated top-left PDF points.
Display boxes rotate around the CropBox. TeX uses full MediaBox top-left points.
Raw PDF boxes retain the PDF bottom-left coordinate convention.
"""

import pymupdf as fitz

from .models import Box


def display_box(box: Box, width: float, height: float, rotation: int) -> Box:
    matrices = {
        0: fitz.Matrix(1, 0, 0, 1, 0, 0),
        90: fitz.Matrix(0, 1, -1, 0, height, 0),
        180: fitz.Matrix(-1, 0, 0, -1, width, height),
        270: fitz.Matrix(0, -1, 1, 0, 0, width),
    }
    return tuple(fitz.Rect(box) * matrices[rotation])


def unrotate_box(box: Box, width: float, height: float, rotation: int) -> Box:
    w, h = (height, width) if rotation in (90, 270) else (width, height)
    return display_box(box, w, h, (360 - rotation) % 360)


def media_box(box: Box, offset: tuple[float, float]) -> Box:
    x, y = offset
    return box[0] + x, box[1] + y, box[2] + x, box[3] + y


def intersects(a: Box, b: Box, epsilon=0.2) -> bool:
    return (
        min(a[2], b[2]) - max(a[0], b[0]) > epsilon and min(a[3], b[3]) - max(a[1], b[1]) > epsilon
    )


def contained(a: Box, b: Box, tolerance=0.5) -> bool:
    return (
        a[0] >= b[0] - tolerance
        and a[1] >= b[1] - tolerance
        and a[2] <= b[2] + tolerance
        and a[3] <= b[3] + tolerance
    )


def vision_box(normalized: Box, width: float, height: float) -> Box:
    x, y, w, h = normalized
    return x * width, (1 - y - h) * height, (x + w) * width, (1 - y) * height
