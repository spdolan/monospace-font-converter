import os

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from monospace_font_converter import Options, convert_font
from monospace_font_converter.cli import main
from monospace_font_converter.convert import convert_file, list_faces

UPEM = 1000
# name -> (advance, ink xmin, ink xmax)
GLYPHS = {
    ".notdef": (500, 50, 450),
    "space": (250, None, None),
    "i": (240, 80, 160),      # narrow: should be centered
    "o": (600, 40, 560),      # reference glyph: fits exactly
    "m": (850, 40, 810),      # wide: should be squeezed
}
CMAP = {0x20: "space", ord("i"): "i", ord("o"): "o", ord("m"): "m"}


def _rect(pen, x0, x1):
    pen.moveTo((x0, 0)); pen.lineTo((x1, 0)); pen.lineTo((x1, 500)); pen.lineTo((x0, 500)); pen.closePath()


def build_font(cff: bool) -> TTFont:
    fb = FontBuilder(UPEM, isTTF=not cff)
    fb.setupGlyphOrder(list(GLYPHS))
    fb.setupCharacterMap(CMAP)
    metrics = {}
    if cff:
        charstrings = {}
        for name, (adv, x0, x1) in GLYPHS.items():
            pen = T2CharStringPen(adv, None)
            if x0 is not None:
                _rect(pen, x0, x1)
            charstrings[name] = pen.getCharString()
            metrics[name] = (adv, x0 or 0)
        fb.setupCFF("Test-Regular", {"FamilyName": "Test"}, charstrings, {})
    else:
        glyphs = {}
        for name, (adv, x0, x1) in GLYPHS.items():
            pen = TTGlyphPen(None)
            if x0 is not None:
                _rect(pen, x0, x1)
            glyphs[name] = pen.glyph()
            metrics[name] = (adv, x0 or 0)
        fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    return fb.font


def ink_extent(font: TTFont, name: str):
    from fontTools.pens.boundsPen import BoundsPen
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    return None if pen.bounds is None else (pen.bounds[0], pen.bounds[2])


def roundtrip(font: TTFont, tmp_path) -> TTFont:
    p = os.path.join(tmp_path, "out.ttf")
    font.save(p)
    return TTFont(p)


@pytest.mark.parametrize("cff", [False, True], ids=["glyf", "cff"])
def test_all_advances_equal_reference_glyph(tmp_path, cff):
    font = build_font(cff)
    result = convert_font(font, Options())
    font = roundtrip(font, tmp_path)
    assert result.cell == 600
    assert {adv for adv, _ in font["hmtx"].metrics.values()} == {600}
    assert font["post"].isFixedPitch == 1
    assert font["OS/2"].panose.bProportion == 9


@pytest.mark.parametrize("cff", [False, True], ids=["glyf", "cff"])
def test_narrow_glyph_is_centered_and_wide_glyph_is_squeezed(tmp_path, cff):
    font = build_font(cff)
    result = convert_font(font, Options(margin=15))
    font = roundtrip(font, tmp_path)
    x0, x1 = ink_extent(font, "i")
    assert (x0, x1) == (260, 340)  # 80 wide, centered in 600
    assert font["hmtx"]["i"] == (600, 260)  # bearing matches the outline
    x0, x1 = ink_extent(font, "m")
    assert x0 == 15 and x1 == 585  # squeezed into cell minus margins
    assert result.squeezed == 1
    assert ink_extent(font, "space") is None


def test_overflow_mode_keeps_wide_glyph_width(tmp_path):
    font = build_font(False)
    result = convert_font(font, Options(wide="overflow"))
    font = roundtrip(font, tmp_path)
    x0, x1 = ink_extent(font, "m")
    assert x1 - x0 == 770
    assert result.overflowed == 1 and result.squeezed == 0


def test_explicit_cell_and_renaming(tmp_path):
    font = build_font(False)
    result = convert_font(font, Options(cell=500, family="Testy Mono"))
    font = roundtrip(font, tmp_path)
    assert {adv for adv, _ in font["hmtx"].metrics.values()} == {500}
    assert result.family == "Testy Mono"
    assert font["name"].getDebugName(6) == "TestyMono-Regular"
    assert font["name"].getDebugName(16) == "Testy Mono"


def test_default_family_gets_mono_suffix_and_layout_stripped(tmp_path):
    font = build_font(False)
    convert_font(font, Options())
    assert font["name"].getDebugName(16) == "Test Mono"
    assert "GPOS" not in font and "kern" not in font


def test_rejects_conflicting_cell_options():
    with pytest.raises(ValueError):
        Options(cell=500, cell_em=0.5)


def test_cli_list_and_convert(tmp_path, capsys):
    src = os.path.join(tmp_path, "Test.ttf")
    build_font(False).save(src)
    assert main(["list", src]) == 0
    assert "Test-Regular" in capsys.readouterr().out
    out = os.path.join(tmp_path, "out")
    assert main(["convert", src, "-o", out, "--cell-em", "0.5"]) == 0
    produced = os.listdir(out)
    assert produced == ["TestMono-Regular.ttf"]
    assert {adv for adv, _ in TTFont(os.path.join(out, produced[0]))["hmtx"].metrics.values()} == {500}
    assert list_faces(os.path.join(out, produced[0]))[0]["family"] == "Test Mono"


def test_convert_file_rejects_bad_face_index(tmp_path):
    src = os.path.join(tmp_path, "Test.ttf")
    build_font(False).save(src)
    with pytest.raises(IndexError):
        convert_file(src, str(tmp_path), Options(), faces=[3])
