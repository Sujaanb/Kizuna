import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kizunapdf.api.app import create_app
from kizunapdf.config import Settings
from kizunapdf.core.extract import InputError, extract
from kizunapdf.core.models import Block, Page
from kizunapdf.core.scan_cleanup import clean_scan


def test_api_without_tex(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/health", headers={"host": "attacker.test"}).status_code == 400
        assert (
            client.post("/api/v1/models/download", json={"accepted_terms": True}).status_code == 403
        )
        token = client.get("/api/v1/health").json()["session_token"]
        headers = {"X-Kizuna-Token": token}
        assert (
            client.post(
                "/api/v1/models/download", json={"accepted_terms": False}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/documents",
                headers=headers,
                files={"file": ("bad.pdf", io.BytesIO(b"bad"), "application/pdf")},
            ).status_code
            == 422
        )
        assert client.get("/api/v1/jobs/../../etc/passwd").status_code == 404


def test_size_limit(tmp_path):
    source = tmp_path / "huge.pdf"
    source.write_bytes(b"%PDF-" + b"x" * 100)
    with pytest.raises(InputError):
        extract(source, Settings(max_upload_bytes=10))


def test_complex_scan_mask_rejected(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(
        "kizunapdf.core.scan_cleanup.render_page",
        lambda *args: Image.new("RGB", (200, 200), (80, 100, 120)),
    )
    page = Page(
        page_index=0,
        width_pt=100,
        height_pt=100,
        media_box=(0, 0, 100, 100),
        crop_box=(0, 0, 100, 100),
        crop_offset=(0, 0),
        rotation=0,
        classification="scan",
    )
    with pytest.raises(ValueError, match="unsupported_scan_style"):
        clean_scan(Path("unused"), page, tmp_path / "out.pdf", Settings())


def test_white_scan_local_artwork_rejected(tmp_path, monkeypatch):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (200, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((17, 17, 42, 42), fill="navy")
    monkeypatch.setattr("kizunapdf.core.scan_cleanup.render_page", lambda *args: image)
    page = Page(
        page_index=0,
        width_pt=100,
        height_pt=100,
        media_box=(0, 0, 100, 100),
        crop_box=(0, 0, 100, 100),
        crop_offset=(0, 0),
        rotation=0,
        classification="scan",
        blocks=[
            Block(
                id="p1",
                source="文字",
                target="Text",
                bbox_pdf_pt=(10, 10, 20, 20),
                bbox_unrotated=(10, 10, 20, 20),
                reading_order=0,
            )
        ],
    )
    with pytest.raises(ValueError, match="artwork touches"):
        clean_scan(Path("unused"), page, tmp_path / "out.pdf", Settings(ocr_dpi=144))


def test_chunked_body_limit(tmp_path):
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from kizunapdf.api.limits import UploadLimitMiddleware

    async def endpoint(request):
        return PlainTextResponse(str(len(await request.body())))

    app = UploadLimitMiddleware(
        Starlette(routes=[Route("/api/v1/documents", endpoint, methods=["POST"])]), max_bytes=5
    )
    with TestClient(app) as client:
        assert client.post("/api/v1/documents", content=iter([b"abc", b"def"])).status_code == 413
        assert client.post("/api/v1/documents", content=iter([b"ab", b"cd"])).status_code == 200
