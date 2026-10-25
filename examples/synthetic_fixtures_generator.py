"""Generate only original, synthetic, non-confidential fixtures using XeLaTeX.
Run: uv run python examples/synthetic_fixtures_generator.py --output tests/fixtures/generated
All resulting PDFs and raster files are ignored by Git.
"""

import argparse
import io
from pathlib import Path

import pikepdf
import pymupdf as fitz
from PIL import ImageDraw

from kizunapdf.config import Settings
from kizunapdf.core.latex import compile_tex, escape_tex
from kizunapdf.core.render import render_page

REFERENCES = {
    "研究報告": "Research report",
    "これは日本語の文書です。": "This is a Japanese document.",
    "数式と図を保持します。": "Equations and figures are preserved.",
    "売上はKZPHAZ円です。": "Sales are KZPHAZ yen.",
    "左の列です。": "This is the left column.",
    "右の列です。": "This is the right column.",
    "図の説明です。": "This is the figure caption.",
    "実験結果": "Experimental results",
    "売上": "Revenue",
    "利益": "Profit",
    "日付": "Date",
    "変化率": "Change",
    "注記": "Note",
    "合計": "Total",
    "数式は変更しません。": "The equation is unchanged.",
}


def make_page(path, entries, width=595.276, height=841.89, art=""):
    body = []
    for x, y, size, text in entries:
        body.append(
            rf"\put({x},-{y}){{\makebox(0,0)[lt]{{\fontsize{{{size}bp}}{{{size * 1.3}bp}}\selectfont {escape_tex(text)}}}}}"
        )
    tex = rf"""\documentclass{{article}}
\usepackage{{fontspec,geometry,xcolor,eso-pic,graphicx}}
\geometry{{paperwidth={width}bp,paperheight={height}bp,margin=0bp}}
\setmainfont{{Hiragino Sans}}
\pagestyle{{empty}}
\setlength{{\unitlength}}{{1bp}}
\begin{{document}}
\AddToShipoutPictureFG*{{\AtPageUpperLeft{{
{chr(10).join(body)}
{art}
}}}}
\null\newpage
\end{{document}}
"""
    path.with_suffix(".tex").write_text(tex)
    compile_tex(path.with_suffix(".tex"), Settings())


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    native = output / "native.pdf"
    make_page(
        native,
        [
            (48, 48, 20, "研究報告"),
            (48, 115, 12, "これは日本語の文書です。"),
            (48, 148, 12, "数式と図を保持します。"),
            (48, 185, 12, "売上は1200円です。"),
            (48, 270, 12, "E = mc²"),
            (48, 790, 8, "KizunaPDF synthetic fixture · 1"),
        ],
        art=r"\put(48,-330){\color[rgb]{0.15,0.42,0.33}\rule{180bp}{36bp}}",
    )
    make_page(
        output / "two_columns.pdf",
        [
            (45, 40, 19, "実験結果"),
            (45, 110, 12, "左の列です。"),
            (45, 150, 12, "これは日本語の文書です。"),
            (325, 110, 12, "右の列です。"),
            (325, 150, 12, "図の説明です。"),
            (325, 200, 10, "[1] Synthetic reference"),
        ],
    )
    table = [(52, 45, 20, "研究報告")]
    for r, row in enumerate(
        [
            ["売上", "利益", "日付", "変化率"],
            ["1200", "-250", "2026/10/26", "12.5%"],
            ["合計", "注記", "100", "-2%"],
        ]
    ):
        for c, t in enumerate(row):
            table.append((55 + c * 120, 110 + r * 40, 11, t))
    art = "\n".join(rf"\put(48,-{100 + y * 40}){{\rule{{480bp}}{{0.4bp}}}}" for y in range(4))
    art += "\n" + "\n".join(
        rf"\put({48 + x * 120},-220){{\rule{{0.4bp}}{{120bp}}}}" for x in range(5)
    )
    make_page(output / "table.pdf", table, art=art)
    make_page(
        output / "science.pdf",
        [
            (48, 48, 19, "研究報告"),
            (48, 115, 12, "数式は変更しません。"),
            (48, 170, 14, "E = mc²"),
            (48, 230, 10, "https://example.org/report"),
            (48, 260, 10, "10.1234/example"),
        ],
    )
    make_page(
        output / "landscape.pdf",
        [(50, 50, 20, "研究報告"), (50, 120, 12, "これは日本語の文書です。")],
        841.89,
        595.276,
    )
    with pikepdf.Pdf.new() as geo:
        for file in (native, output / "landscape.pdf", native, native, native):
            with pikepdf.open(file) as src:
                geo.pages.append(src.pages[0])
        geo.pages[2].obj["/Rotate"] = 90
        geo.pages[3].cropbox = pikepdf.Array([20, 20, 575.276, 821.89])
        origin_page = geo.pages[4]
        origin_page.contents_add(b"q 1 0 0 1 -30 -40 cm\n", prepend=True)
        origin_page.contents_add(b"\nQ\n")
        origin_page.mediabox = pikepdf.Array([-30, -40, 565.28, 801.89])
        origin_page.cropbox = pikepdf.Array([-10, -20, 545.28, 781.89])
        geo.save(output / "geometry.pdf")
    from PIL import Image

    with fitz.open(native) as overlap:
        pixels = Image.new("RGB", (100, 50), (243, 234, 220))
        buffer = io.BytesIO()
        pixels.save(buffer, format="PNG")
        overlap[0].insert_image(fitz.Rect(40, 40, 290, 95), stream=buffer.getvalue(), overlay=False)
        overlap.save(output / "overlap.pdf")
    image = render_page(native, 0, 250)
    for name, hard in [("scan_white.pdf", False), ("scan_complex.pdf", True)]:
        img = image.copy()
        if hard:
            overlay = ImageDraw.Draw(img)
            for y in range(0, img.height, 15):
                overlay.line((0, y, img.width, y), fill=(190, 205, 225), width=8)
        data = io.BytesIO()
        img.save(data, format="PNG")
        with fitz.open() as pdf:
            p = pdf.new_page(width=595.276, height=841.89)
            p.insert_image(p.rect, stream=data.getvalue())
            pdf.save(output / name)
    with fitz.open(native) as pdf:
        pdf.save(
            output / "encrypted.pdf",
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="synthetic-owner",
            user_pw="synthetic-reader",
        )
    with fitz.open() as pdf:
        pdf.new_page()
        pdf.save(output / "blank.pdf")
    (output / "invalid.pdf").write_bytes(b"not a PDF")
    return native


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=Path("tests/fixtures/generated"))
    print(generate(p.parse_args().output))
