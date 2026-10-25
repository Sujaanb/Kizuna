from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Box = tuple[float, float, float, float]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class Glyph(StrictModel):
    text: str
    bbox: Box
    origin: tuple[float, float]


class Span(StrictModel):
    text: str
    bbox: Box
    font: str
    size: float
    flags: int = 0
    color: int = 0
    glyphs: list[Glyph] = Field(default_factory=list)


class Block(StrictModel):
    id: str
    source: str
    target: str | None = None
    bbox_pdf_pt: Box
    bbox_unrotated: Box
    layout_bbox: Box | None = None
    coordinates: str = "top_left_points_after_rotation_normalization"
    reading_order: int
    role: Literal[
        "heading", "paragraph", "caption", "footnote", "table_cell", "equation", "other"
    ] = "paragraph"
    direction: Literal["horizontal", "vertical", "rotated"] = "horizontal"
    font_family: str = "Helvetica"
    font_size_pt: float = Field(default=11, gt=0)
    font_weight: Literal["normal", "bold"] = "normal"
    italic: bool = False
    rgb: str = Field(default="#222222", pattern=r"^#[0-9a-fA-F]{6}$")
    alignment: Literal["left", "center", "right"] = "left"
    line_height_pt: float = 13
    source_confidence: float = Field(default=1, ge=0, le=1)
    segmentation_confidence: float = Field(default=0.8, ge=0, le=1)
    translation_status: Literal["pending", "translated", "edited", "protected", "failed"] = (
        "pending"
    )
    protection_mode: Literal["translate", "protect", "ignore"] = "translate"
    override_reason: str | None = None
    protected_spans: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)
    table_cell: Box | None = None
    parent_id: str | None = None
    origin: Literal["native", "ocr"] = "native"
    fitted_font_size: float | None = None

    @model_validator(mode="after")
    def valid_rect(self):
        for b in (self.bbox_pdf_pt, self.bbox_unrotated, self.layout_bbox):
            if b and (b[2] <= b[0] or b[3] <= b[1]):
                raise ValueError("Block rectangle must have positive width and height")
        return self


class Page(StrictModel):
    page_index: int
    width_pt: float
    height_pt: float
    media_box: Box
    crop_box: Box
    crop_offset: tuple[float, float]
    rotation: Literal[0, 90, 180, 270]
    classification: Literal["native", "mixed", "scan", "empty", "needs_review"]
    extraction_confidence: float = 1
    blocks: list[Block] = Field(default_factory=list)
    obstacles: list[Box] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DocumentInfo(StrictModel):
    sha256: str
    source_lang: Literal["ja"] = "ja"
    target_lang: Literal["en"] = "en"
    page_count: int
    filename: str


class DocumentIR(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    segmentation_version: str = "1.0"
    document: DocumentInfo
    pages: list[Page]

    @model_validator(mode="after")
    def coherent(self):
        if len(self.pages) != self.document.page_count:
            raise ValueError("IR page count mismatch")
        ids = [b.id for p in self.pages for b in p.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate segment IDs")
        return self


class Diagnostic(StrictModel):
    severity: Literal["pass", "warning", "needs_review", "failed"]
    check: str
    message: str
    page: int | None = None
    block_id: str | None = None


class QAReport(StrictModel):
    schema_version: str = "1.0"
    status: Literal["verified", "needs_review", "failed"] = "verified"
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)

    def add(self, severity: str, check: str, message: str, page=None, block_id=None):
        self.diagnostics.append(
            Diagnostic(
                severity=severity, check=check, message=message, page=page, block_id=block_id
            )
        )
        if severity == "failed":
            self.status = "failed"
        elif severity == "needs_review" and self.status != "failed":
            self.status = "needs_review"
        self.metrics["counts"] = {
            level: sum(d.severity == level for d in self.diagnostics)
            for level in ("pass", "warning", "needs_review", "failed")
        }
