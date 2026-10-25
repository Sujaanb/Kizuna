from __future__ import annotations

import io
import json
import secrets
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from kizunapdf import __version__
from kizunapdf.api.limits import UploadLimitMiddleware
from kizunapdf.config import ROOT, Settings
from kizunapdf.core.doctor import doctor
from kizunapdf.core.jobs import BUSY, JobManager
from kizunapdf.core.render import render_page
from kizunapdf.providers.mlx_translategemma import download_model, model_status


class Edit(BaseModel):
    target: str | None = Field(default=None, max_length=20000)
    protection_mode: str | None = None
    reading_order: int | None = Field(default=None, ge=0, le=100000)
    reason: str | None = Field(default=None, max_length=1000)


class Download(BaseModel):
    accepted_terms: bool = False


def create_app(settings: Settings | None = None, translator=None):
    settings = settings or Settings()
    manager = JobManager(settings, translator)
    download_pool = ThreadPoolExecutor(max_workers=1)
    download_state = {"status": "idle", "error": None}
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        yield
        for flag in manager.cancel_flags.values():
            flag.set()
        manager.pool.shutdown(wait=False, cancel_futures=True)
        download_pool.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(
        title="KizunaPDF", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.state.manager = manager
    app.add_middleware(UploadLimitMiddleware, max_bytes=settings.max_upload_bytes + 1024 * 1024)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("X-Kizuna-Token") != token:
                return JSONResponse(
                    {"detail": "Missing local session token; reload the app"}, status_code=403
                )
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin write refused"}, status_code=403)
        length = request.headers.get("content-length")
        if length and (
            not length.isdecimal() or int(length) > settings.max_upload_bytes + 1024 * 1024
        ):
            return JSONResponse({"detail": "Request exceeds upload limit"}, status_code=413)
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; font-src 'self' blob: data:; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'",
            }
        )
        return response

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ValueError)
    async def bad(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "version": __version__, "local_only": True, "session_token": token}

    @app.get("/api/v1/doctor")
    def checks():
        return doctor(settings)

    @app.post("/api/v1/documents", status_code=201)
    async def upload(
        file: Annotated[UploadFile, File()],
        password: str | None = Form(default=None),
        allow_scans: bool = Form(default=False),
    ):
        with tempfile.TemporaryDirectory(prefix="kizuna-upload-") as tmp:
            name = Path(file.filename or "document.pdf").name
            if not name.lower().endswith(".pdf"):
                raise HTTPException(415, "Choose a PDF file")
            path = Path(tmp) / name
            size = 0
            with path.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise HTTPException(413, "PDF exceeds 50 MB")
                    out.write(chunk)
            # Run extraction off the event loop.
            from starlette.concurrency import run_in_threadpool

            state = await run_in_threadpool(manager.create, path, password, allow_scans)
        return state

    @app.get("/api/v1/documents/{job_id}")
    def document(job_id: str):
        return manager.ir(job_id).model_dump()

    @app.get("/api/v1/documents/{job_id}/pdf")
    def original(job_id: str):
        return FileResponse(manager.folder(job_id) / "original.pdf", media_type="application/pdf")

    @app.get("/api/v1/documents/{job_id}/pages/{page}/preview")
    def preview(job_id: str, page: int):
        ir = manager.ir(job_id)
        if not 0 <= page < len(ir.pages):
            raise HTTPException(404, "Unknown page")
        image = render_page(manager.folder(job_id) / "original.pdf", page, 100)
        data = io.BytesIO()
        image.save(data, format="PNG")
        return Response(data.getvalue(), media_type="image/png")

    @app.get("/api/v1/jobs")
    def jobs():
        return sorted(
            [json.loads(p.read_text()) for p in settings.data_dir.glob("*/job.json")],
            key=lambda j: j["created_at"],
            reverse=True,
        )[:50]

    @app.get("/api/v1/jobs/{job_id}")
    def job(job_id: str):
        return manager.state(job_id)

    @app.post("/api/v1/jobs/{job_id}/translate", status_code=202)
    def translate(job_id: str):
        manager.start(job_id)
        return manager.state(job_id)

    @app.post("/api/v1/jobs/{job_id}/rebuild", status_code=202)
    def rebuild(job_id: str):
        manager.start(job_id, rebuild=True)
        return manager.state(job_id)

    @app.post("/api/v1/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        manager.cancel(job_id)
        return manager.state(job_id)

    @app.get("/api/v1/jobs/{job_id}/segments")
    def segments(job_id: str):
        return [b.model_dump() for p in manager.ir(job_id).pages for b in p.blocks]

    @app.patch("/api/v1/jobs/{job_id}/segments/{segment_id}")
    def edit(job_id: str, segment_id: str, patch: Edit):
        with manager.lock:
            if manager.state(job_id)["status"] in BUSY:
                raise HTTPException(409, "Wait for or cancel the active job before editing")
            ir = manager.ir(job_id)
            block = next((b for p in ir.pages for b in p.blocks if b.id == segment_id), None)
            if block is None:
                raise HTTPException(404, "Unknown region")
            if patch.protection_mode is not None:
                if patch.protection_mode not in ("translate", "protect", "ignore"):
                    raise HTTPException(422, "Invalid protection mode")
                if patch.protection_mode != block.protection_mode and not patch.reason:
                    raise HTTPException(422, "Explain the region override")
                block.protection_mode = patch.protection_mode
                block.override_reason = patch.reason
            if patch.target is not None:
                block.target = patch.target.strip()
                block.translation_status = "edited"
            if patch.reading_order is not None:
                block.reading_order = patch.reading_order
            manager.save_ir(job_id, ir)
            manager.update(
                job_id,
                status="edited",
                message="Edits saved; rebuild to update output",
                output_available=False,
            )
            return block.model_dump()

    @app.get("/api/v1/jobs/{job_id}/export/{kind}")
    def export(job_id: str, kind: str):
        names = {"pdf": "translated.pdf", "latex": "reconstruction.zip", "qa": "qa_report.json"}
        if kind not in names:
            raise HTTPException(404, "Unknown export format")
        state = manager.state(job_id)
        if kind != "qa" and not state["output_available"]:
            raise HTTPException(409, "No current output passed minimum QA gates")
        path = manager.folder(job_id) / names[kind]
        if not path.exists():
            raise HTTPException(404, "Artifact is not ready")
        return FileResponse(
            path,
            filename=names[kind],
            media_type="application/pdf"
            if kind == "pdf"
            else "application/zip"
            if kind == "latex"
            else "application/json",
        )

    @app.get("/api/v1/models/status")
    def status():
        size = (
            sum(p.stat().st_size for p in settings.model_dir.rglob("*") if p.is_file())
            if settings.model_dir.exists()
            else 0
        )
        return {**model_status(settings), **download_state, "bytes_on_disk": size}

    @app.post("/api/v1/models/download", status_code=202)
    def download(request: Download):
        if not request.accepted_terms:
            raise HTTPException(422, "Accept Gemma Terms before downloading")
        if download_state["status"] == "downloading":
            raise HTTPException(409, "Download already running")
        download_state.update(status="downloading", error=None)

        def run():
            try:
                download_model(settings, True)
                download_state.update(status="ready")
            except Exception as e:
                download_state.update(status="failed", error=str(e)[:1000])

        download_pool.submit(run)
        return download_state

    dist = ROOT / "frontend/dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    else:

        @app.get("/")
        def no_ui():
            return {"message": "Frontend build missing. Run scripts/setup_mac.sh"}

    return app
