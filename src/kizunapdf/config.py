from __future__ import annotations

import os
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "mlx-community/translategemma-4b-it-4bit"
TERMS_URL = "https://ai.google.dev/gemma/terms"


class Settings(BaseModel):
    data_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "KIZUNAPDF_DATA_DIR", str(Path.home() / "Library/Application Support/KizunaPDF")
            )
        ).expanduser()
    )
    model_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("KIZUNAPDF_MODEL_DIR", str(ROOT / ".tools/models/translategemma"))
        ).expanduser()
    )
    max_upload_bytes: int = 50 * 1024 * 1024
    max_pages: int = 100
    max_input_tokens: int = 1800
    max_output_tokens: int = 1024
    compile_timeout: int = 90
    inference_timeout: int = 180
    min_font_ratio: float = 0.85
    ocr_dpi: int = 250

    @property
    def xelatex(self) -> str | None:
        candidates = [
            os.environ.get("KIZUNAPDF_XELATEX"),
            shutil.which("xelatex"),
            "/Library/TeX/texbin/xelatex",
            str(ROOT / ".tools/texlive/bin/universal-darwin/xelatex"),
        ]
        return next((p for p in candidates if p and Path(p).is_file()), None)

    @property
    def ocr(self) -> Path:
        return Path(
            os.environ.get("KIZUNAPDF_OCR", str(ROOT / "macos/VisionOCR/.build/release/VisionOCR"))
        )

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
