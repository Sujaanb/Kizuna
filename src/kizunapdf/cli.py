from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from .config import Settings

app = typer.Typer(no_args_is_help=True, help="Local Japanese → English PDF translation")
model = typer.Typer(no_args_is_help=True)
app.add_typer(model, name="model")


def emit(data):
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@app.command()
def doctor():
    from .core.doctor import doctor as check

    result = check(Settings())
    emit(result)
    if not result["ready"]:
        raise typer.Exit(1)


@model.command("status")
def model_status():
    from .providers.mlx_translategemma import model_status as status

    emit(status(Settings()))


@model.command("download")
def model_download(
    accept_gemma_terms: bool = typer.Option(
        False, help="Use only after reviewing https://ai.google.dev/gemma/terms"
    ),
):
    from .providers.mlx_translategemma import download_model

    if not accept_gemma_terms:
        typer.echo(
            "Review https://ai.google.dev/gemma/terms. Weights retain the separate Gemma license."
        )
        accept_gemma_terms = typer.confirm(
            "Have you accepted these terms and wish to download ~2.2 GB?"
        )
    try:
        emit(download_model(Settings(), accept_gemma_terms))
    except Exception as e:
        typer.echo(
            f"Model download failed: {e}\nFor gated access: accept terms at https://huggingface.co/google/translategemma-4b-it then run hf auth login",
            err=True,
        )
        raise typer.Exit(1) from e


@app.command()
def translate(
    source: Path,
    output_dir: Path = Path("./out"),
    experimental_scans: bool = False,
    password: bool = typer.Option(False, help="Prompt for encrypted PDF password; never stored"),
):
    from .core.export import export_result
    from .core.jobs import JobManager

    manager = JobManager(Settings())
    try:
        state = manager.create(
            source,
            typer.prompt("PDF password", hide_input=True) if password else None,
            experimental_scans,
        )
        typer.echo(f"Local job: {state['id']}")
        state = manager.process(state["id"])
        report = export_result(manager.folder(state["id"]), output_dir, source.stem)
        emit(state)
        if report["status"] != "verified":
            raise typer.Exit(2 if report["status"] == "needs_review" else 1)
    except (ValueError, RuntimeError, OSError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e
    finally:
        manager.pool.shutdown(wait=False)


@app.command()
def rebuild(bundle: Path, output: Path = Path("rebuilt.pdf")):
    from .core.export import rebuild as build_bundle

    try:
        report = build_bundle(bundle, output, Settings())
        emit(report.model_dump())
        if report.status != "verified":
            raise typer.Exit(2)
    except (ValueError, RuntimeError, OSError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e


@app.command("build")
def build_alias(bundle: Path, output: Path = Path("rebuilt.pdf")):
    rebuild(bundle, output)


@app.command()
def validate(pdf: Path, manifest: Annotated[Path, typer.Option("--manifest")]):
    from .core.models import DocumentIR, QAReport
    from .core.qa import validate_structure

    data = json.loads(manifest.read_text())
    ir = DocumentIR(document=data["document"], pages=data["pages"])
    report = QAReport()
    validate_structure(pdf, ir, report)
    report.add(
        "warning",
        "validation_scope",
        "Manifest validation checks geometry only; use rebuild or original job for region and visual QA",
    )
    emit(report.model_dump())
    if report.status == "failed":
        raise typer.Exit(1)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8787):
    if host != "127.0.0.1":
        raise typer.BadParameter("Only 127.0.0.1 is allowed")
    import uvicorn

    from .api.app import create_app

    os.umask(0o077)
    uvicorn.run(create_app(), host=host, port=port, access_log=False)


if __name__ == "__main__":
    app()
