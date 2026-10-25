import importlib.util
import platform
import shutil
import subprocess
from pathlib import Path

import psutil

from kizunapdf.config import Settings
from kizunapdf.providers.mlx_translategemma import model_status


def doctor(settings: Settings):
    checks = []

    def add(name, ready, detail, fix=""):
        checks.append({"name": name, "ready": bool(ready), "detail": detail, "fix": fix})

    add(
        "Apple Silicon",
        platform.system() == "Darwin" and platform.machine() == "arm64",
        f"{platform.system()} / {platform.machine()}",
    )
    add(
        "Memory",
        psutil.virtual_memory().total >= 12 * 1024**3,
        f"{psutil.virtual_memory().total / 1024**3:.1f} GB",
    )
    add(
        "Disk",
        shutil.disk_usage(Path.cwd()).free > 4 * 1024**3,
        f"{shutil.disk_usage(Path.cwd()).free / 1024**3:.1f} GB free",
    )
    add(
        "XeLaTeX",
        settings.xelatex,
        settings.xelatex or "Not found",
        "Install BasicTeX from https://www.tug.org/mactex/ or set KIZUNAPDF_XELATEX",
    )
    if settings.xelatex:
        kpse = str(Path(settings.xelatex).parent / "kpsewhich")
        missing = []
        for p in ("fontspec", "graphicx", "geometry", "xcolor", "eso-pic"):
            r = subprocess.run([kpse, p + ".sty"], capture_output=True, text=True, timeout=10)
            if r.returncode:
                missing.append(p)
        add(
            "TeX packages",
            not missing,
            ", ".join(missing) or "All required packages found",
            "tlmgr install fontspec xcolor eso-pic geometry",
        )
    add(
        "MLX runtime",
        importlib.util.find_spec("mlx_lm") is not None,
        "Local in-process inference",
        "uv sync --extra mlx",
    )
    status = model_status(settings)
    add(
        "TranslateGemma",
        status["ready"],
        "Cached" if status["ready"] else "Model setup needed",
        "kizunapdf model download",
    )
    languages = {}
    if settings.ocr.is_file():
        try:
            import json

            p = subprocess.run(
                [str(settings.ocr), "--languages"], capture_output=True, text=True, timeout=20
            )
            languages = json.loads(p.stdout) if p.returncode == 0 else {}
        except (ValueError, subprocess.TimeoutExpired):
            pass
    add(
        "Apple Vision OCR",
        languages.get("japaneseSupported", False),
        str(languages.get("languages", [])),
        "Run scripts/setup_mac.sh; OCR is optional for native PDFs",
    )
    return {
        "checks": checks,
        "ready": all(c["ready"] for c in checks if c["name"] != "Apple Vision OCR"),
        "model": status,
    }
