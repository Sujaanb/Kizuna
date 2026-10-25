from pathlib import Path

import pypdfium2 as pdfium


def render_page(path: Path, page: int, dpi=150):
    with pdfium.PdfDocument(str(path)) as doc:
        p = doc[page]
        try:
            bitmap = p.render(scale=dpi / 72)
            image = bitmap.to_pil().convert("RGB")
            bitmap.close()
            return image
        finally:
            p.close()
