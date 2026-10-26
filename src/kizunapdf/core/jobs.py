from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf as fitz

from kizunapdf import __version__
from kizunapdf.config import Settings
from kizunapdf.providers.mlx_translategemma import get_translator

from .cache import TranslationCache
from .export import write_bundle
from .extract import extract
from .latex import TypesettingError, build_pages
from .models import DocumentIR, QAReport
from .protect import japanese, protect, restore, restore_verified_literals
from .qa import run_qa
from .redaction import sanitize
from .scan_cleanup import recognize

BUSY = {"queued", "analyze", "ocr", "translate", "sanitize", "compile", "qa"}


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    temp.replace(path)


class JobManager:
    def __init__(self, settings: Settings, translator=None):
        self.settings = settings
        settings.prepare()
        self.translator = translator
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kizuna")
        self.cancel_flags = {}
        self.lock = threading.RLock()
        for state in settings.data_dir.glob("*/job.json"):
            data = json.loads(state.read_text())
            if data["status"] in BUSY:
                data.update(
                    status="interrupted",
                    message="Previous process stopped; resume translation or rebuild",
                )
                write_json(state, data)

    def folder(self, job_id: str):
        try:
            if str(uuid.UUID(job_id)) != job_id:
                raise ValueError()
        except ValueError as e:
            raise FileNotFoundError("Unknown job") from e
        path = self.settings.data_dir / job_id
        if not (path / "job.json").is_file():
            raise FileNotFoundError("Unknown job")
        return path

    def state(self, job_id):
        return json.loads((self.folder(job_id) / "job.json").read_text())

    def update(self, job_id, **changes):
        with self.lock:
            state = self.state(job_id)
            state.update(changes, updated_at=time.time())
            write_json(self.folder(job_id) / "job.json", state)

    def ir(self, job_id):
        return DocumentIR.model_validate_json(
            (self.folder(job_id) / "ir/document_ir.json").read_text()
        )

    def save_ir(self, job_id, ir):
        write_json(self.folder(job_id) / "ir/document_ir.json", ir.model_dump())
        write_json(
            self.folder(job_id) / "text/translation_segments.json",
            [b.model_dump() for p in ir.pages for b in p.blocks],
        )

    def create(self, source: Path, password=None, allow_scans=False):
        ir = extract(source, self.settings, password)
        job_id = str(uuid.uuid4())
        folder = self.settings.data_dir / job_id
        folder.mkdir(mode=0o700)
        # Password is never persisted; authenticated decrypted copy remains private job data.
        with fitz.open(source) as pdf:
            if pdf.needs_pass:
                pdf.authenticate(password or "")
                pdf.save(folder / "original.pdf", encryption=fitz.PDF_ENCRYPT_NONE)
            else:
                shutil.copyfile(source, folder / "original.pdf")
        write_json(
            folder / "job.json",
            {
                "id": job_id,
                "filename": source.name,
                "status": "ready",
                "message": "Ready for local translation",
                "progress": 0,
                "allow_scans": allow_scans,
                "created_at": time.time(),
                "updated_at": time.time(),
                "output_available": False,
            },
        )
        self.save_ir(job_id, ir)
        return self.state(job_id)

    def cancel(self, job_id):
        self.folder(job_id)
        self.cancel_flags.setdefault(job_id, threading.Event()).set()
        self.update(job_id, message="Cancellation requested")

    def start(self, job_id, rebuild=False):
        with self.lock:
            if self.state(job_id)["status"] in BUSY:
                raise ValueError("Job is already running")
            queued = sum(
                json.loads(p.read_text())["status"] in BUSY
                for p in self.settings.data_dir.glob("*/job.json")
            )
            if queued >= 8:
                raise ValueError("Local queue is full (8 jobs)")
            self.cancel_flags[job_id] = threading.Event()
            self.update(
                job_id, status="queued", message="Queued for local worker", output_available=False
            )
            return self.pool.submit(self.process, job_id, rebuild)

    def process(self, job_id, rebuild=False):
        start = time.monotonic()
        work = self.folder(job_id)
        flag = self.cancel_flags.setdefault(job_id, threading.Event())
        cancel = flag.is_set
        ir = self.ir(job_id)
        cache_hits = cache_misses = 0
        # Remove stale deliverables before any new attempt.
        for f in ("translated.pdf", "reconstruction.zip", "qa_report.json"):
            (work / f).unlink(missing_ok=True)
        try:
            if cancel():
                raise InterruptedError("Cancelled")
            if not rebuild:
                for p in ir.pages:
                    if p.classification == "scan" and not p.blocks:
                        if self.state(job_id)["allow_scans"]:
                            self.update(
                                job_id, status="ocr", message=f"Recognizing page {p.page_index + 1}"
                            )
                            recognize(work / "original.pdf", p, work, self.settings)
                        else:
                            p.warnings.append("scan_disabled_enable_experimental_ocr")
                blocks = [
                    b
                    for p in ir.pages
                    for b in sorted(p.blocks, key=lambda b: b.reading_order)
                    if b.protection_mode == "translate"
                ]
                translator = self.translator or (get_translator(self.settings) if blocks else None)
                cache = TranslationCache(self.settings.data_dir / "translations.sqlite3")
                for i, b in enumerate(blocks):
                    if cancel():
                        raise InterruptedError("Cancelled")
                    self.update(
                        job_id,
                        status="translate",
                        message=f"Translating {i + 1} of {len(blocks)} regions",
                        progress=i / max(1, len(blocks)) * 0.6,
                    )
                    if b.target and b.translation_status in ("edited", "translated"):
                        continue
                    protected, mapping = protect(b.source)
                    b.protected_spans = mapping
                    key = cache.key(
                        model=translator.model_id,
                        revision=translator.revision,
                        source=b.source,
                        target="en",
                        glossary="none",
                        segmentation=ir.segmentation_version,
                    )
                    target = cache.get(key)
                    if target is None:
                        cache_misses += 1
                        result = translator.translate(protected, cancel=cancel)
                        try:
                            target = restore(result, mapping)
                        except ValueError:
                            # One bounded retry using unchanged source, still the official template.
                            result = translator.translate(b.source, cancel=cancel)
                            target = restore_verified_literals(b.source, result)
                            b.warnings.append("placeholder_fallback_literals_verified")
                        if not target or japanese(target):
                            raise ValueError(
                                f"Unexpected target language or empty translation: {b.id}"
                            )
                        cache.put(key, target)
                    else:
                        cache_hits += 1
                    b.target = target
                    b.translation_status = "translated"
                    self.save_ir(job_id, ir)
                provenance = (
                    {"id": translator.model_id, "revision": translator.revision}
                    if translator
                    else {"id": "none", "revision": None}
                )
            else:
                provenance = (
                    json.loads((work / "manifest.json").read_text()).get("model", {})
                    if (work / "manifest.json").exists()
                    else {"id": "manual"}
                )
            self.save_ir(job_id, ir)
            self.update(
                job_id,
                status="sanitize",
                message="Removing source text from page artwork",
                progress=0.65,
            )
            sanitize(work / "original.pdf", ir, work, self.settings, cancel)
            self.update(
                job_id, status="compile", message="Typesetting English with XeLaTeX", progress=0.75
            )
            build_pages(ir, work, self.settings, cancel)
            self.save_ir(job_id, ir)
            self.update(
                job_id, status="qa", message="Checking content, geometry and artwork", progress=0.9
            )
            report = run_qa(work / "original.pdf", work / "translated.pdf", ir)
            if provenance.get("id", "").startswith("test-only/"):
                report.add(
                    "needs_review",
                    "test_translator",
                    "Fixture reference translator; not actual model inference",
                )
            if cancel():
                raise InterruptedError("Cancelled")
            write_json(work / "qa_report.json", report.model_dump())
            versions = {
                p: importlib.metadata.version(p)
                for p in ("pymupdf", "pikepdf", "pypdfium2", "pydantic")
            }
            import resource
            import sys

            mlx_core = sys.modules.get("mlx.core")

            write_json(
                work / "manifest.json",
                {
                    "schema_version": "1.0",
                    "app_version": __version__,
                    "input_sha256": ir.document.sha256,
                    "document": ir.document.model_dump(),
                    "pages": [p.model_dump(exclude={"blocks", "obstacles"}) for p in ir.pages],
                    "model": provenance,
                    "tools": versions,
                    "compiler": self.settings.xelatex,
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                    "peak_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    * (1 if os.uname().sysname == "Darwin" else 1024),
                    "cache_hits": cache_hits,
                    "cache_misses": cache_misses,
                    "mlx_peak_memory_bytes": mlx_core.get_peak_memory() if mlx_core else None,
                    "qa_status": report.status,
                    "original_included": False,
                },
            )
            if report.status == "failed":
                (work / "translated.pdf").unlink(missing_ok=True)
            else:
                write_bundle(work)
            self.update(
                job_id,
                status="completed" if report.status == "verified" else report.status,
                message="Quality checks passed"
                if report.status == "verified"
                else "Review diagnostics before using the output",
                progress=1,
                output_available=report.status != "failed",
                qa_status=report.status,
            )
        except InterruptedError:
            (work / "translated.pdf").unlink(missing_ok=True)
            self.update(
                job_id,
                status="cancelled",
                message="Cancelled; saved translations can be resumed",
                output_available=False,
            )
        except Exception as e:
            self.save_ir(job_id, ir)
            (work / "translated.pdf").unlink(missing_ok=True)
            report = QAReport()
            severity = "needs_review" if isinstance(e, ValueError) else "failed"
            if isinstance(e, TypesettingError):
                for diagnostic in e.diagnostics:
                    report.add(**diagnostic.model_dump())
            else:
                report.add(severity, "pipeline", str(e)[:2000])
            write_json(work / "qa_report.json", report.model_dump())
            self.update(
                job_id,
                status=severity,
                message=str(e)[:2000],
                output_available=False,
                qa_status=report.status,
            )
        return self.state(job_id)
