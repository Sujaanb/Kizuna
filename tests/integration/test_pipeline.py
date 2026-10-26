import importlib.util
import json
import platform

import pikepdf
import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

from kizunapdf.api.app import create_app
from kizunapdf.config import ROOT, Settings
from kizunapdf.core.export import rebuild
from kizunapdf.core.extract import InputError, extract
from kizunapdf.core.jobs import JobManager
from kizunapdf.providers.fake import FakeTranslator

spec = importlib.util.spec_from_file_location(
    "fixtures", ROOT / "examples/synthetic_fixtures_generator.py"
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory):
    if platform.system() != "Darwin" or not Settings().xelatex:
        pytest.skip("XeLaTeX not installed")
    out = tmp_path_factory.mktemp("synthetic")
    fixtures.generate(out)
    return out


@pytest.mark.parametrize(
    "name", ["native", "two_columns", "table", "science", "geometry", "blank", "overlap"]
)
def test_pipeline(name, fixture_dir, tmp_path):
    settings = Settings(data_dir=tmp_path / "jobs")
    manager = JobManager(settings, FakeTranslator(fixtures.REFERENCES))
    job = manager.create(fixture_dir / f"{name}.pdf")
    state = manager.process(job["id"])
    assert state["output_available"], state
    assert state["status"] in ("needs_review", "completed"), state
    work = manager.folder(job["id"])
    with fitz.open(work / "translated.pdf") as out:
        if name != "blank":
            assert "Research report" in "".join(
                p.get_text() for p in out
            ) or "Experimental results" in "".join(p.get_text() for p in out)
        assert "研究報告" not in "".join(p.get_text() for p in out)
    with (
        pikepdf.open(fixture_dir / f"{name}.pdf") as source,
        pikepdf.open(work / "translated.pdf") as out,
    ):
        assert len(source.pages) == len(out.pages)
        for a, b in zip(source.pages, out.pages, strict=True):
            assert list(a.mediabox) == list(b.mediabox)
            assert list(a.cropbox) == list(b.cropbox)
    if name == "overlap":
        with (
            fitz.open(fixture_dir / "overlap.pdf") as original,
            fitz.open(work / "assets/backgrounds/page_0001.pdf") as background,
        ):
            assert [i["digest"] for i in original[0].get_image_info(hashes=True)] == [
                i["digest"] for i in background[0].get_image_info(hashes=True)
            ]
    if name == "native":
        report = rebuild(work / "reconstruction.zip", tmp_path / "moved/rebuilt.pdf", settings)
        assert report.status != "failed"
        assert (tmp_path / "moved/rebuilt.pdf").exists()


def test_preflight(fixture_dir, tmp_path):
    settings = Settings(data_dir=tmp_path)
    with pytest.raises(InputError):
        extract(fixture_dir / "invalid.pdf", settings)
    with pytest.raises(InputError):
        extract(fixture_dir / "encrypted.pdf", settings)
    assert (
        extract(fixture_dir / "encrypted.pdf", settings, "synthetic-reader").document.page_count
        == 1
    )
    assert extract(fixture_dir / "scan_white.pdf", settings).pages[0].classification == "scan"


def test_api_boundary_and_edits(fixture_dir, tmp_path):
    settings = Settings(data_dir=tmp_path / "jobs")
    with TestClient(create_app(settings, FakeTranslator(fixtures.REFERENCES))) as client:
        assert client.get("/api/v1/health", headers={"host": "evil.example"}).status_code == 400
        assert client.post("/api/v1/documents").status_code == 403
        token = client.get("/api/v1/health").json()["session_token"]
        headers = {"X-Kizuna-Token": token}
        assert (
            client.post(
                "/api/v1/documents", headers={**headers, "Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        with (fixture_dir / "native.pdf").open("rb") as f:
            response = client.post(
                "/api/v1/documents",
                files={"file": ("native.pdf", f, "application/pdf")},
                headers=headers,
            )
        assert response.status_code == 201, response.text
        job = response.json()["id"]
        assert client.get(f"/api/v1/jobs/{job}/export/pdf").status_code == 409
        segments = client.get(f"/api/v1/jobs/{job}/segments").json()
        segment = segments[0]["id"]
        assert (
            client.patch(
                f"/api/v1/jobs/{job}/segments/{segment}",
                json={"protection_mode": "ignore"},
                headers=headers,
            ).status_code
            == 422
        )
        r = client.patch(
            f"/api/v1/jobs/{job}/segments/{segment}",
            json={"target": "Research report"},
            headers=headers,
        )
        assert r.status_code == 200
        assert client.get("/api/v1/jobs/not-a-uuid").status_code == 404


def test_overflow_and_cancellation(fixture_dir, tmp_path):
    settings = Settings(data_dir=tmp_path / "jobs")
    manager = JobManager(settings, FakeTranslator(fixtures.REFERENCES))
    j = manager.create(fixture_dir / "native.pdf")["id"]
    ir = manager.ir(j)
    b = ir.pages[0].blocks[0]
    b.target = "Unbreakable" * 1000
    b.translation_status = "edited"
    manager.save_ir(j, ir)
    state = manager.process(j)
    assert not state["output_available"]
    assert "overflow" in state["message"].lower()
    j2 = manager.create(fixture_dir / "native.pdf")["id"]
    manager.cancel(j2)
    assert manager.process(j2)["status"] == "cancelled"


def test_overflow_reports_regions_on_every_affected_page(fixture_dir, tmp_path):
    source = tmp_path / "two_pages.pdf"
    with pikepdf.open(fixture_dir / "native.pdf") as pdf:
        pdf.pages.append(pdf.pages[0])
        pdf.save(source)
    manager = JobManager(Settings(data_dir=tmp_path / "jobs"), FakeTranslator(fixtures.REFERENCES))
    job = manager.create(source)["id"]
    ir = manager.ir(job)
    expected = set()
    for page in ir.pages:
        block = page.blocks[0]
        block.target = "M" * 25
        block.translation_status = "edited"
        expected.add((page.page_index, block.id))
    manager.save_ir(job, ir)
    assert not manager.process(job)["output_available"]
    report = json.loads((manager.folder(job) / "qa_report.json").read_text())
    assert {(d["page"], d["block_id"]) for d in report["diagnostics"]} == expected
    assert all(d["check"] == "text_overflow" for d in report["diagnostics"])


def test_inference_failure_is_not_success(fixture_dir, tmp_path):
    class BrokenTranslator:
        model_id = "test-only/broken"
        revision = "1"

        def translate(self, text, cancel=None):
            raise RuntimeError("Intentional inference failure")

    manager = JobManager(Settings(data_dir=tmp_path / "jobs"), BrokenTranslator())
    job = manager.create(fixture_dir / "native.pdf")["id"]
    state = manager.process(job)
    assert state["status"] == "failed"
    assert not state["output_available"]
    assert not (manager.folder(job) / "translated.pdf").exists()


def test_redaction_and_bundle_source_exclusion(fixture_dir, tmp_path):
    import zipfile

    manager = JobManager(Settings(data_dir=tmp_path / "jobs"), FakeTranslator(fixtures.REFERENCES))
    job = manager.create(fixture_dir / "native.pdf")["id"]
    assert manager.process(job)["output_available"]
    work = manager.folder(job)
    with zipfile.ZipFile(work / "reconstruction.zip") as bundle:
        assert "original.pdf" not in bundle.namelist()
        assert "tex/pages/page_0001.tex" in bundle.namelist()
    with fitz.open(work / "assets/backgrounds/page_0001.pdf") as bg:
        text = bg[0].get_text()
        assert "研究報告" not in text
        assert "1200" not in text
        assert "E = mc²" in text
        assert len(bg[0].get_drawings()) > 0


def test_cli_manifest_option(fixture_dir, tmp_path):
    from typer.testing import CliRunner

    from kizunapdf.cli import app

    manager = JobManager(Settings(data_dir=tmp_path / "jobs"), FakeTranslator(fixtures.REFERENCES))
    job = manager.create(fixture_dir / "native.pdf")["id"]
    assert manager.process(job)["output_available"]
    work = manager.folder(job)
    result = CliRunner().invoke(
        app, ["validate", str(work / "translated.pdf"), "--manifest", str(work / "manifest.json")]
    )
    assert result.exit_code == 0, result.output
    assert "verified" in result.output


def test_unicode_fallback_preserves_fullwidth_numbers_and_marks(tmp_path):
    if platform.system() != "Darwin" or not Settings().xelatex:
        pytest.skip("Mac XeLaTeX fixture required")
    source = tmp_path / "unicode.pdf"
    fixtures.make_page(source, [(48, 48, 12, "項目１ ※")])
    manager = JobManager(
        Settings(data_dir=tmp_path / "jobs"), FakeTranslator({"項目KZPHAZ※": "Item KZPHAZ ※ ○"})
    )
    job = manager.create(source)["id"]
    state = manager.process(job)
    assert state["output_available"], state
    work = manager.folder(job)
    assert "Missing character:" not in (work / "tex/pages/page_0001.log").read_text()
    with fitz.open(work / "translated.pdf") as pdf:
        text = pdf[0].get_text()
        assert "１" in text and "※" in text and "○" in text
    rebuilt = tmp_path / "relocated.pdf"
    assert rebuild(work / "reconstruction.zip", rebuilt, manager.settings).status != "failed"
    with fitz.open(rebuilt) as pdf:
        assert "１" in pdf[0].get_text() and "※" in pdf[0].get_text()


def test_unavailable_glyph_still_blocks_export(fixture_dir, tmp_path):
    manager = JobManager(Settings(data_dir=tmp_path / "jobs"), FakeTranslator(fixtures.REFERENCES))
    job = manager.create(fixture_dir / "native.pdf")["id"]
    ir = manager.ir(job)
    block = ir.pages[0].blocks[0]
    block.target = "Unsupported \U0010ffff"
    block.translation_status = "edited"
    manager.save_ir(job, ir)
    state = manager.process(job)
    assert not state["output_available"]
    assert "U+10FFFF" in state["message"] and block.id in state["message"]
