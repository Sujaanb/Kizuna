import zipfile

import pytest

from kizunapdf.core.cache import TranslationCache
from kizunapdf.core.export import safe_extract
from kizunapdf.core.geometry import display_box, media_box, unrotate_box, vision_box
from kizunapdf.core.latex import escape_tex, layout_region
from kizunapdf.core.models import Block, Page, QAReport
from kizunapdf.core.protect import literal_errors, protect, restore
from kizunapdf.providers.mlx_translategemma import messages


@pytest.mark.parametrize(
    "rotation,expected",
    [
        (0, (10, 20, 40, 60)),
        (90, (140, 10, 180, 40)),
        (180, (60, 140, 90, 180)),
        (270, (20, 60, 60, 90)),
    ],
)
def test_geometry_roundtrip(rotation, expected):
    assert display_box((10, 20, 40, 60), 100, 200, rotation) == expected
    assert unrotate_box(expected, 100, 200, rotation) == (10, 20, 40, 60)


def test_offsets_and_vision():
    assert media_box((10, 20, 40, 60), (15, 35)) == (25, 55, 55, 95)
    assert vision_box((0.1, 0.2, 0.3, 0.4), 100, 200) == pytest.approx((10, 80, 40, 160))


def test_protection_exactness():
    source = "売上は¥1,200、利益は-25、割合は12.5%、日付は2026/10/26です。 https://example.org/a"
    masked, mapping = protect(source)
    assert restore(masked, mapping) == source
    with pytest.raises(ValueError):
        restore(masked + " KZPHAZ", mapping)
    with pytest.raises(ValueError):
        restore(masked.replace("KZPHAZ", "100"), mapping)
    assert literal_errors("100 100", "100")
    assert not literal_errors("価格1200円", "Price 1200 yen")


def test_glossary():
    text, mapping = protect("研究報告です。", {"研究報告": "Research report"})
    assert restore(text, mapping) == "Research reportです。"


def test_safe_tex():
    escaped = escape_tex(r"\input{/etc/passwd} $ % & _ # ^ ~")
    assert r"\input{" not in escaped
    assert r"\textbackslash{}input\{" in escaped
    assert "\x00" not in escape_tex("a\x00b")


def test_bad_ir_and_qa():
    with pytest.raises(ValueError):
        Block(
            id="x",
            source="a",
            bbox_pdf_pt=(1, 1, 0, 0),
            bbox_unrotated=(1, 1, 2, 2),
            reading_order=0,
        )
    q = QAReport()
    q.add("warning", "x", "x")
    assert q.status == "verified"
    q.add("needs_review", "x", "x")
    assert q.status == "needs_review"
    q.add("failed", "x", "x")
    q.add("needs_review", "x", "x")
    assert q.status == "failed"


def test_cache(tmp_path):
    cache = TranslationCache(tmp_path / "cache.sqlite")
    k = cache.key(model="m", revision="v1", source="日本語")
    cache.put(k, "Japanese")
    assert cache.get(k) == "Japanese"
    assert cache.get(cache.key(model="m", revision="v2", source="日本語")) is None


def test_template_contract():
    m = messages("研究報告")
    assert len(m) == 1 and m[0]["role"] == "user"
    assert m[0]["content"] == [
        {"type": "text", "source_lang_code": "ja", "target_lang_code": "en", "text": "研究報告"}
    ]


def test_zip_traversal(tmp_path):
    p = tmp_path / "bad.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("../escape", "bad")
    with pytest.raises(ValueError):
        safe_extract(p, tmp_path / "dest")
    assert not (tmp_path / "escape").exists()


def test_verified_literal_fallback():
    from kizunapdf.core.protect import restore_verified_literals

    assert (
        restore_verified_literals("売上は1200円です。", "Sales are 1,200 yen.")
        == "Sales are 1200 yen."
    )
    with pytest.raises(ValueError):
        restore_verified_literals("1200", "12,345")
    with pytest.raises(ValueError):
        restore_verified_literals("1200", "1200 or 1300")
    with pytest.raises(ValueError):
        restore_verified_literals("1200 1200", "1200")
    with pytest.raises(ValueError):
        restore_verified_literals("2026/10/26", "10/26/2026")


def test_japanese_detection_excludes_punctuation():
    from kizunapdf.core.protect import japanese

    assert not japanese("KizunaPDF synthetic fixture ・ 1")
    assert japanese("これは日本語です。")
    assert japanese("ﾃｽﾄ")


def test_font_failure_identifies_unicode_and_region():
    from kizunapdf.core.latex import missing_glyph_details

    log = "KZBLOCK:p0001-b0005-1\nMissing character: There is no １ (U+FF11) in font Arial\nMissing character: There is no ※ (U+203B) in font Arial\n"
    message = missing_glyph_details(log)
    assert "１ (U+FF11)" in message
    assert "※ (U+203B)" in message
    assert "p0001-b0005-1" in message
    assert missing_glyph_details("KZBLOCK:p1\nOutput written") is None


def test_table_fitting_uses_left_space_but_stops_above_preserved_text():
    cell = (40, 40, 110, 100)
    label = Block(
        id="label",
        source="見出し",
        reading_order=0,
        bbox_pdf_pt=(70, 45, 90, 55),
        bbox_unrotated=(70, 45, 90, 55),
        table_cell=cell,
    )
    preserved = Block(
        id="preserved",
        source="Existing English",
        reading_order=1,
        bbox_pdf_pt=(45, 60, 105, 70),
        bbox_unrotated=(45, 60, 105, 70),
        protection_mode="protect",
        table_cell=cell,
    )
    page = Page(
        page_index=0,
        width_pt=200,
        height_pt=200,
        media_box=(0, 0, 200, 200),
        crop_box=(0, 0, 200, 200),
        crop_offset=(0, 0),
        rotation=0,
        classification="native",
        blocks=[label, preserved],
    )
    assert layout_region(label, page) == (42, 45, 108, 60)
    preserved.bbox_unrotated = (95, 45, 105, 55)
    label_box = layout_region(label, page)
    neighbor_box = layout_region(preserved, page)
    assert label_box[2] == neighbor_box[0]
