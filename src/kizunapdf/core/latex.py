from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pikepdf

from kizunapdf.config import Settings

from .geometry import intersects, media_box
from .models import Block, Diagnostic, DocumentIR, Page

ESCAPE = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "^": r"\textasciicircum{}",
    "~": r"\textasciitilde{}",
}

# Check the font actually selected for each character. Do not normalize protected
# full-width numbers or replace source symbols merely to fit a Latin font.
FONT_FALLBACKS = r"""
\newcommand{\kzcjk}{}
\newcommand{\kzsymbols}{}
\IfFontExistsTF{Hiragino Sans}{\newfontfamily\kzcjkfont{Hiragino Sans}\renewcommand{\kzcjk}{\kzcjkfont}}{%
  \IfFontExistsTF{Noto Sans CJK JP}{\newfontfamily\kzcjkfont{Noto Sans CJK JP}\renewcommand{\kzcjk}{\kzcjkfont}}{}%
}
\IfFontExistsTF{Apple Symbols}{\newfontfamily\kzsymbolsfont{Apple Symbols}\renewcommand{\kzsymbols}{\kzsymbolsfont}}{%
  \IfFontExistsTF{DejaVu Sans}{\newfontfamily\kzsymbolsfont{DejaVu Sans}\renewcommand{\kzsymbols}{\kzsymbolsfont}}{}%
}
\newcommand{\kzchar}[2]{%
  \iffontchar\font#1\relax#2%
  \else{\mdseries\upshape\kzcjk%
    \iffontchar\font#1\relax#2%
    \else{\kzsymbols#2}\fi}%
  \fi%
}
"""


def escape_tex(text: str) -> str:
    return "".join(
        ESCAPE.get(c, " " if c in "\r\n\t" else c) for c in text if ord(c) >= 32 or c in "\r\n\t"
    )


def text_with_fallbacks(text: str) -> str:
    return "".join(
        rf"\kzchar{{{ord(char)}}}{{{escape_tex(char)}}}" if ord(char) > 127 else escape_tex(char)
        for char in text
    )


def missing_glyph_details(log: str) -> str | None:
    current_block = None
    missing: dict[str, set[str]] = {}
    for line in log.splitlines():
        if line.startswith("KZBLOCK:"):
            current_block = line.removeprefix("KZBLOCK:").strip()
        match = re.search(r"Missing character: There is no (.*?) \(U\+([0-9A-Fa-f]+)\)", line)
        if match:
            label = f"{match[1]} (U+{match[2]})"
            missing.setdefault(label, set())
            if current_block:
                missing[label].add(current_block)
    if not missing:
        return "unidentified character" if "Missing character:" in log else None
    return "; ".join(
        label + (" in " + ", ".join(sorted(blocks)) if blocks else "")
        for label, blocks in missing.items()
    )


def layout_region(block: Block, page: Page):
    if block.table_cell:
        c = block.table_cell
        x0, y0, x1, y1 = block.bbox_unrotated
        left, right = min(x0, c[0] + 2), max(x1, c[2] - 2)
        obstacles = [b.bbox_unrotated for b in page.blocks if b.id != block.id] + page.obstacles
        # Share vacant horizontal space between same-row labels. A centered source
        # label may use space to its left, but cannot cross another label or artwork.
        for other in obstacles:
            if min(y1, other[3]) - max(y0, other[1]) > 0.2:
                if other[2] <= x0:
                    left = max(left, (other[2] + x0) / 2)
                elif other[0] >= x1:
                    right = min(right, (x1 + other[0]) / 2)
        bottom = max(y1, c[3] - 2)
        # A cell can contain multiple translated lines and preserved English.
        # Giving every line the whole remaining cell height would hide collisions.
        for other in obstacles:
            if min(right, other[2]) - max(left, other[0]) > 0.2 and other[1] >= y1:
                bottom = min(bottom, other[1])
        return (left, y0, right, bottom)
    box = list(block.bbox_unrotated)
    width = page.crop_box[2] - page.crop_box[0]
    height = page.crop_box[3] - page.crop_box[1]
    obstacles = [b.bbox_unrotated for b in page.blocks if b.id != block.id] + page.obstacles
    # Only grow into measured vacant strips, preserving gutters and graphics.
    for axis, limit in ((2, min(width - 18, box[2] + 160)), (3, min(height - 18, box[3] + 36))):
        for edge in range(int(box[axis]) + 1, int(limit) + 1):
            trial = box.copy()
            trial[axis] = edge
            if any(
                intersects(tuple(trial), o) and not intersects(block.bbox_unrotated, o)
                for o in obstacles
            ):
                break
            box = trial
    return tuple(box)


def page_tex(page: Page, ratio=1.0) -> str:
    mw, mh = page.media_box[2] - page.media_box[0], page.media_box[3] - page.media_box[1]
    header = rf"""% KizunaPDF: editable translation text; compile from tex/pages.
\documentclass{{article}}
\usepackage{{fontspec,graphicx,xcolor,eso-pic}}
\usepackage[paperwidth={mw:.5f}bp,paperheight={mh:.5f}bp,margin=0bp]{{geometry}}
\IfFontExistsTF{{Arial}}{{\setmainfont{{Arial}}}}{{\setmainfont{{Latin Modern Sans}}}}
{FONT_FALLBACKS}
\pagestyle{{empty}}
\setlength{{\unitlength}}{{1bp}}
\setlength{{\parindent}}{{0pt}}
\newbox\kzbox
\begin{{document}}
\AddToShipoutPictureBG*{{\AtPageLowerLeft{{\includegraphics[pagebox=mediabox,width={mw:.5f}bp,height={mh:.5f}bp]{{../../assets/backgrounds/page_{page.page_index + 1:04d}.pdf}}}}}}
"""
    parts = [header]
    for block in sorted(page.blocks, key=lambda b: b.reading_order):
        if block.protection_mode != "translate" or not block.target:
            continue
        block.layout_bbox = layout_region(block, page)
        x0, y0, x1, y1 = media_box(block.layout_bbox, page.crop_offset)
        fs = max(min(block.font_size_pt, 7), block.font_size_pt * ratio)
        block.fitted_font_size = fs
        style = (r"\bfseries " if block.font_weight == "bold" else "") + (
            r"\itshape " if block.italic else ""
        )
        align = {"left": r"\raggedright", "center": r"\centering", "right": r"\raggedleft"}[
            block.alignment
        ]
        parts.append(rf"""% Segment {block.id}
\typeout{{KZBLOCK:{block.id}}}
\setbox\kzbox=\vbox{{\hsize={x1 - x0:.5f}bp\linewidth=\hsize
\fontsize{{{fs:.4f}bp}}{{{fs * 1.16:.4f}bp}}\selectfont {align}
\color[HTML]{{{block.rgb[1:]}}}{style}
{text_with_fallbacks(block.target)}\par}}
\typeout{{KZHEIGHT:{block.id}:\the\dimexpr\ht\kzbox+\dp\kzbox\relax}}
\AddToShipoutPictureFG*{{\AtPageUpperLeft{{\put({x0:.5f},-{y0:.5f}){{\makebox(0,0)[lt]{{\copy\kzbox}}}}}}}}
""")
        # Each shipout hook captures a separate TeX box register.
        n = len(parts) - 2
        parts[-1] = parts[-1].replace(r"\copy\kzbox", rf"\copy\csname kzbox{n}\endcsname")
        parts[-1] = parts[-1].replace(
            r"\AddToShipoutPictureFG*",
            rf"\expandafter\newbox\csname kzbox{n}\endcsname"
            + "\n"
            + rf"\expandafter\setbox\csname kzbox{n}\endcsname=\copy\kzbox"
            + "\n"
            + r"\AddToShipoutPictureFG*",
        )
    parts.append("\\null\\thispagestyle{empty}\\newpage\n\\end{document}\n")
    return "\n".join(parts)


def compile_tex(tex: Path, settings: Settings):
    if not settings.xelatex:
        raise RuntimeError(
            "XeLaTeX is missing. Install BasicTeX/TeX Live; see docs/SETUP_AND_RUN.md"
        )
    env = {**os.environ, "openin_any": "p", "openout_any": "p", "shell_escape": "f"}
    # TeX needs relative ../../assets paths; use 'r' for reads, bounded generated filenames only.
    env["openin_any"] = "r"
    result = subprocess.run(
        [
            settings.xelatex,
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            tex.name,
        ],
        cwd=tex.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=settings.compile_timeout,
    )
    log = (
        tex.with_suffix(".log").read_text(errors="replace")
        if tex.with_suffix(".log").exists()
        else result.stdout
    )
    if result.returncode or not tex.with_suffix(".pdf").is_file():
        raise RuntimeError(
            f"XeLaTeX failed for {tex.name}. See {tex.with_suffix('.log')}: {log[-1500:]}"
        )
    missing = missing_glyph_details(log)
    if missing:
        raise ValueError(
            f"No available local font can render {missing} in {tex.name}. "
            "Install a font covering these characters or edit the affected region. "
            "No PDF was exported."
        )
    return log


class TypesettingError(ValueError):
    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        pages = ", ".join(str(i + 1) for i in sorted({d.page for d in diagnostics}))
        super().__init__(
            f"Text overflow in {len(diagnostics)} region(s) on page(s) {pages}. "
            "Select a text overflow issue in Quality report, shorten the English text, "
            "then Save & rebuild. No PDF was exported."
        )


def horizontal_overflows(log: str) -> set[str]:
    current_block = "unknown"
    blocks = set()
    for line in log.splitlines():
        if line.startswith("KZBLOCK:"):
            current_block = line.removeprefix("KZBLOCK:").strip()
        elif "Overfull \\hbox" in line:
            blocks.add(current_block)
    return blocks


def build_pages(ir: DocumentIR, work: Path, settings: Settings, cancel=lambda: False):
    pages_dir = work / "tex/pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    diagnostics = []
    for page in ir.pages:
        if cancel():
            raise InterruptedError("Cancelled")
        tex = pages_dir / f"page_{page.page_index + 1:04d}.tex"
        errors = {}
        for ratio in (1.0, 0.925, settings.min_font_ratio):
            tex.write_text(page_tex(page, ratio))
            log = compile_tex(tex, settings)
            measured = dict(re.findall(r"KZHEIGHT:([^:]+):([\d.]+)pt", log))
            errors = {}
            for b in page.blocks:
                if b.protection_mode == "translate" and b.target:
                    # TeX pt -> PDF bp.
                    actual = float(measured.get(b.id, "inf")) * 72 / 72.27
                    if actual > b.layout_bbox[3] - b.layout_bbox[1] + 0.3:
                        errors[b.id] = "The translation is too tall for the available space."
            for block_id in sorted(horizontal_overflows(log)):
                errors[block_id] = "A word is too wide for the available space."
            if not errors:
                break
        if errors:
            tex.with_suffix(".pdf").unlink(missing_ok=True)
            diagnostics.extend(
                Diagnostic(
                    severity="needs_review",
                    check="text_overflow",
                    message=message + " Shorten this region's English text, then Save & rebuild.",
                    page=page.page_index,
                    block_id=block_id if block_id != "unknown" else None,
                )
                for block_id, message in errors.items()
            )
    if diagnostics:
        raise TypesettingError(diagnostics)
    merge_pages(ir, work, work / "translated.pdf")


def merge_pages(ir: DocumentIR, work: Path, output: Path):
    with pikepdf.Pdf.new() as merged:
        for page in ir.pages:
            with pikepdf.open(work / f"tex/pages/page_{page.page_index + 1:04d}.pdf") as src:
                if len(src.pages) != 1:
                    raise ValueError("Page-level XeLaTeX produced an unexpected page count")
                merged.pages.append(src.pages[0])
                p = merged.pages[-1]
                x, y = page.media_box[:2]
                if x or y:
                    p.contents_add(f"q 1 0 0 1 {x} {y} cm\n".encode(), prepend=True)
                    p.contents_add(b"\nQ\n")
                p.mediabox = pikepdf.Array(page.media_box)
                p.cropbox = pikepdf.Array(page.crop_box)
                p.obj["/Rotate"] = page.rotation
        merged.docinfo["/Producer"] = "KizunaPDF / XeLaTeX"
        merged.save(output)
