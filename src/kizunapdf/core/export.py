from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from kizunapdf.config import Settings

from .latex import compile_tex, merge_pages
from .models import DocumentIR
from .qa import run_qa

REBUILD_README = """# Rebuild locally
This bundle contains private source/target text and sanitized page artwork. Treat it as private.
Install KizunaPDF and XeLaTeX. Extract this ZIP, then run:

    kizunapdf rebuild /path/to/extracted-directory --output rebuilt.pdf

Or use `scripts/rebuild.sh` from anywhere. Edit plain English in tex/pages/*.tex for typography.
When editing text, also update matching target in ir/document_ir.json to keep QA expectations aligned.
Rebuild compiles the saved TeX (does not regenerate it or run model inference).
Never compile TeX bundles from untrusted senders: TeX is executable input even without shell escape.
Full page MediaBox/CropBox/Rotate values are restored during merge.
The original input PDF is deliberately excluded; protected text and artwork may remain in backgrounds.
This is a translation bundle, not a security-redaction product.
"""


def write_bundle(work: Path) -> Path:
    (work / "README_REBUILD.md").write_text(REBUILD_README)
    scripts = work / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "rebuild.sh").write_text(
        '#!/bin/sh\nset -eu\nBUNDLE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\nexec kizunapdf rebuild "$BUNDLE" --output "${1:-$BUNDLE/rebuilt.pdf}"\n'
    )
    (scripts / "rebuild.sh").chmod(0o755)
    destination = work / "reconstruction.zip"
    included = [
        "README_REBUILD.md",
        "manifest.json",
        "qa_report.json",
        "ir/document_ir.json",
        "text/translation_segments.json",
        "scripts/rebuild.sh",
    ]
    included += [
        str(p.relative_to(work))
        for glob in ("tex/pages/*.tex", "assets/backgrounds/*.pdf")
        for p in work.glob(glob)
    ]
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as z:
        for name in included:
            if (work / name).is_file():
                z.write(work / name, name)
    return destination


def safe_extract(source: Path, dest: Path):
    with zipfile.ZipFile(source) as z:
        if sum(i.file_size for i in z.infolist()) > 500 * 1024 * 1024 or len(z.infolist()) > 2000:
            raise ValueError("Bundle exceeds extraction limits")
        for i in z.infolist():
            path = (dest / i.filename).resolve()
            if (
                not path.is_relative_to(dest.resolve())
                or i.filename.startswith("/")
                or (i.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("Unsafe path or symlink in bundle")
        z.extractall(dest)


def rebuild(source: Path, output: Path, settings: Settings):
    with tempfile.TemporaryDirectory(prefix="kizunapdf-rebuild-") as temporary:
        root = Path(temporary)
        if source.is_file():
            safe_extract(source, root)
        else:
            shutil.copytree(
                source,
                root,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("*.pdf", "*.zip", "*.log", "*.aux"),
            )
            shutil.copytree(source / "assets", root / "assets", dirs_exist_ok=True)
        ir = DocumentIR.model_validate_json((root / "ir/document_ir.json").read_text())
        for p in ir.pages:
            tex = root / f"tex/pages/page_{p.page_index + 1:04d}.tex"
            log = compile_tex(tex, settings)
            if "Overfull \\hbox" in log or "Overfull \\vbox" in log:
                raise ValueError("Saved TeX overflows; correct layout before exporting")
        merge_pages(ir, root, root / "rebuilt.pdf")
        report = run_qa(None, root / "rebuilt.pdf", ir)
        report.add(
            "warning",
            "rebuild_visual_comparison",
            "Original omitted from bundle; source visual comparison unavailable",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".qa.json").write_text(report.model_dump_json(indent=2))
        if report.status == "failed":
            raise ValueError("Rebuilt PDF failed QA; inspect adjacent .qa.json")
        shutil.copyfile(root / "rebuilt.pdf", output)
        return report


def export_result(work: Path, output_dir: Path, stem: str):
    output_dir.mkdir(parents=True, exist_ok=True)
    for source, name in (
        ("translated.pdf", stem + ".en.pdf"),
        ("reconstruction.zip", stem + ".kizunapdf.zip"),
        ("manifest.json", "manifest.json"),
        ("qa_report.json", "qa_report.json"),
    ):
        if (work / source).exists():
            shutil.copyfile(work / source, output_dir / name)
    return json.loads((work / "qa_report.json").read_text())
