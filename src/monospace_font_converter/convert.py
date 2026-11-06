"""Core conversion: give every glyph in a font the same advance width.

Glyphs whose ink is narrower than the cell are centered in it. Glyphs whose ink
is wider are either squeezed horizontally to fit (default) or left to overflow.
Outlines are rebuilt from scratch, so hinting is dropped. Kerning and OpenType
layout tables are removed by default because they are meaningless (or harmful)
in a fixed-pitch grid.

Works on TrueType (``glyf``) and CFF (``CFF ``) outlines. Variable fonts and
CFF2 are not supported.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

WIDE_MODES = ("squeeze", "overflow")

# Tables that only make sense for the original proportional outlines.
HINTING_TABLES = ("fpgm", "prep", "cvt ", "hdmx", "LTSH", "DSIG")
LAYOUT_TABLES = ("kern", "kerx", "GPOS", "GSUB", "GDEF", "BASE", "JSTF", "MATH", "morx", "feat", "ankr")
UNSUPPORTED_TABLES = ("fvar", "gvar", "CFF2")


@dataclass
class Options:
    """Conversion settings. ``cell`` and ``cell_em`` are alternatives; when both
    are ``None`` the advance width of ``reference_glyph`` is used."""

    cell: Optional[int] = None
    cell_em: Optional[float] = None
    reference_glyph: str = "o"
    margin: int = 15
    wide: str = "squeeze"
    family: Optional[str] = None
    strip_layout: bool = True

    def __post_init__(self) -> None:
        if self.wide not in WIDE_MODES:
            raise ValueError(f"wide must be one of {WIDE_MODES}, got {self.wide!r}")
        if self.cell is not None and self.cell_em is not None:
            raise ValueError("give either cell or cell_em, not both")
        if self.margin < 0:
            raise ValueError("margin must be >= 0")


@dataclass
class ConversionResult:
    postscript_name: str
    family: str
    style: str
    cell: int
    glyph_count: int
    squeezed: int = 0
    overflowed: int = 0
    path: Optional[str] = None
    notes: List[str] = field(default_factory=list)


def load_faces(path: str) -> List[TTFont]:
    """Open a font file. A TrueType Collection yields one TTFont per face."""
    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic == b"ttcf":
        return list(TTCollection(path).fonts)
    return [TTFont(path)]


def list_faces(path: str) -> List[dict]:
    out = []
    for idx, font in enumerate(load_faces(path)):
        name = font["name"]
        family = name.getDebugName(16) or name.getDebugName(1) or "Unknown"
        style = name.getDebugName(17) or name.getDebugName(2) or "Regular"
        out.append(
            {
                "index": idx,
                "postscript_name": name.getDebugName(6) or f"{family}-{style}".replace(" ", ""),
                "family": family,
                "style": style,
                "outlines": "CFF" if "CFF " in font else "TrueType" if "glyf" in font else "unknown",
            }
        )
    return out


def resolve_cell(font: TTFont, options: Options) -> int:
    upem = font["head"].unitsPerEm
    if options.cell is not None:
        return int(options.cell)
    if options.cell_em is not None:
        return int(round(options.cell_em * upem))
    cmap = font.getBestCmap() or {}
    gname = cmap.get(ord(options.reference_glyph)) if len(options.reference_glyph) == 1 else None
    if gname and gname in font["hmtx"].metrics:
        return int(font["hmtx"][gname][0])
    return int(round(0.6 * upem))


def _check_supported(font: TTFont) -> None:
    for t in UNSUPPORTED_TABLES:
        if t in font:
            raise ValueError(f"font has a {t.strip()!r} table; variable and CFF2 fonts are not supported")
    if "glyf" not in font and "CFF " not in font:
        raise ValueError("font has neither TrueType nor CFF outlines")


def _ink_bounds(rec: DecomposingRecordingPen):
    """x-extent of a recorded outline (control points; good enough for cell fitting)."""
    xs = []
    for op, args in rec.value:
        for pt in args:
            if isinstance(pt, tuple) and len(pt) == 2 and isinstance(pt[0], (int, float)):
                xs.append(pt[0])
    if not xs:
        return None
    return min(xs), max(xs)


def _cff_private(font: TTFont, glyph_name: str):
    top = font["CFF "].cff.topDictIndex[0]
    if hasattr(top, "FDArray"):
        gid = font.getGlyphID(glyph_name)
        return top.FDArray[top.FDSelect[gid]].Private
    return top.Private


def convert_font(font: TTFont, options: Options) -> ConversionResult:
    """Convert ``font`` in place and return a summary. Call ``font.save`` afterwards."""
    _check_supported(font)
    cell = resolve_cell(font, options)
    avail = cell - 2 * options.margin
    if avail <= 0:
        raise ValueError(f"margin {options.margin} leaves no room in a {cell}-unit cell")

    is_cff = "CFF " in font
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"]
    glyf = font["glyf"] if not is_cff else None
    charstrings = font["CFF "].cff.topDictIndex[0].CharStrings if is_cff else None
    global_subrs = font["CFF "].cff.GlobalSubrs if is_cff else None

    squeezed = overflowed = 0
    for name in font.getGlyphOrder():
        rec = DecomposingRecordingPen(glyph_set)
        glyph_set[name].draw(rec)
        bounds = _ink_bounds(rec)
        sx, dx = 1.0, 0.0
        if bounds is not None:
            xmin, xmax = bounds
            ink_w = xmax - xmin
            if ink_w > avail:
                if options.wide == "squeeze":
                    sx = avail / ink_w
                    squeezed += 1
                else:
                    overflowed += 1
            dx = (cell - ink_w * sx) / 2 - xmin * sx

        # The left side bearing must match the outline's xMin: TrueType renderers
        # shift the outline to the bearing, so a wrong value un-centers the glyph.
        lsb = 0
        if is_cff:
            pen = T2CharStringPen(cell, None)
            rec.replay(TransformPen(pen, (sx, 0, 0, 1, dx, 0)))
            charstrings[name] = pen.getCharString(private=_cff_private(font, name), globalSubrs=global_subrs)
            if bounds is not None:
                lsb = int(round(bounds[0] * sx + dx))
        else:
            pen = TTGlyphPen(None)
            rec.replay(TransformPen(pen, (sx, 0, 0, 1, dx, 0)))
            new_glyph = pen.glyph()
            glyf[name] = new_glyph
            if new_glyph.numberOfContours:
                new_glyph.recalcBounds(glyf)
                lsb = new_glyph.xMin
        hmtx[name] = (cell, lsb)

    for t in HINTING_TABLES + (LAYOUT_TABLES if options.strip_layout else ()):
        if t in font:
            del font[t]
    if is_cff:
        # Rebuilt charstrings carry no hints; drop stale hint-related private values.
        for key in ("BlueValues", "OtherBlues", "FamilyBlues", "FamilyOtherBlues", "StemSnapH", "StemSnapV", "StdHW", "StdVW"):
            top = font["CFF "].cff.topDictIndex[0]
            privates = [fd.Private for fd in top.FDArray] if hasattr(top, "FDArray") else [top.Private]
            for p in privates:
                if hasattr(p, key):
                    delattr(p, key)

    os2 = font["OS/2"]
    os2.panose.bProportion = 9  # monospaced
    os2.xAvgCharWidth = cell
    font["post"].isFixedPitch = 1
    font["hhea"].advanceWidthMax = cell

    family, style, ps_name = _rename(font, options.family)
    notes = []
    if options.wide == "overflow" and overflowed:
        notes.append(f"{overflowed} glyphs are wider than the cell and will overlap neighbours")
    return ConversionResult(ps_name, family, style, cell, len(font.getGlyphOrder()), squeezed, overflowed, None, notes)


def _rename(font: TTFont, new_family: Optional[str]):
    nm = font["name"]
    old_family = nm.getDebugName(16) or nm.getDebugName(1) or "Font"
    style = nm.getDebugName(17) or nm.getDebugName(2) or "Regular"
    family = new_family or f"{old_family} Mono"
    legacy_style = "Regular"
    lower = style.lower()
    if "bold" in lower and ("italic" in lower or "oblique" in lower):
        legacy_style = "Bold Italic"
    elif "bold" in lower:
        legacy_style = "Bold"
    elif "italic" in lower or "oblique" in lower:
        legacy_style = "Italic"
    legacy_family = family if style in ("Regular", "Bold", "Italic", "Bold Italic") else f"{family} {style.replace(' Italic', '').replace(' Oblique', '')}"
    full = f"{family} {style}".strip() if style != "Regular" else family
    ps_name = "".join(ch for ch in family if ch.isalnum()) + "-" + "".join(ch for ch in style if ch.isalnum())
    ps_name = ps_name[:63]
    for rec in list(nm.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17):
            nm.removeNames(rec.nameID, rec.platformID, rec.platEncID, rec.langID)
    nm.setName(legacy_family, 1, 3, 1, 0x409)
    nm.setName(legacy_style, 2, 3, 1, 0x409)
    nm.setName(f"{full} (fixed-pitch derivative)", 3, 3, 1, 0x409)
    nm.setName(full, 4, 3, 1, 0x409)
    nm.setName(ps_name, 6, 3, 1, 0x409)
    nm.setName(family, 16, 3, 1, 0x409)
    nm.setName(style, 17, 3, 1, 0x409)
    return family, style, ps_name


def output_path(font: TTFont, result: ConversionResult, out_dir: str) -> str:
    ext = ".otf" if "CFF " in font else ".ttf"
    return os.path.join(out_dir, result.postscript_name + ext)


def convert_file(path: str, out_dir: str, options: Options, faces: Optional[Sequence[int]] = None) -> List[ConversionResult]:
    all_faces = load_faces(path)
    indices = list(range(len(all_faces))) if faces is None else list(faces)
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for idx in indices:
        if idx < 0 or idx >= len(all_faces):
            raise IndexError(f"face index {idx} out of range (file has {len(all_faces)} faces)")
        font = all_faces[idx]
        result = convert_font(font, options)
        result.path = output_path(font, result, out_dir)
        font.save(result.path)
        results.append(result)
    return results
