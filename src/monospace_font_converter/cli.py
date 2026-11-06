"""Command line interface."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .convert import DEFAULT_DONOR_GLYPHS, Options, convert_file, list_faces


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="monospace-font-converter",
        description="Turn a proportional font you are licensed to modify into a fixed-pitch derivative.",
        epilog="You are responsible for checking that the font's license permits modification. "
        "Generated fonts are for your own machines; do not redistribute them.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    ls = sub.add_parser("list", help="list the faces in a font file or collection")
    ls.add_argument("font")

    cv = sub.add_parser("convert", help="write fixed-pitch derivatives of one or more faces")
    cv.add_argument("font", help="path to a .ttf, .otf or .ttc file")
    cv.add_argument("-o", "--out-dir", default=".", help="directory for generated files (default: current directory)")
    cv.add_argument("--face", type=int, action="append", help="face index within a collection; repeatable (default: all faces)")
    width = cv.add_mutually_exclusive_group()
    width.add_argument("--cell", type=int, help="advance width for every glyph, in font units")
    width.add_argument("--cell-em", type=float, help="advance width as a fraction of the em, e.g. 0.6")
    width.add_argument("--reference-glyph", default="o", metavar="CHAR", help="use this character's original advance as the cell (default: o)")
    cv.add_argument("--margin", type=int, default=15, help="minimum side bearing, in font units, when a glyph must be squeezed (default: 15)")
    cv.add_argument("--wide", choices=("squeeze", "overflow"), default="squeeze", help="what to do with glyphs wider than the cell (default: squeeze)")
    cv.add_argument("--family", help="family name for the derivative (default: '<original family> Mono')")
    cv.add_argument("--keep-layout", action="store_true", help="keep kerning and OpenType layout tables (dropped by default)")
    donor = cv.add_argument_group(
        "donor glyphs",
        "Borrow a few glyphs from a monospaced font you are also licensed to modify, scaled to the "
        "converted font's x-height and cap height and slanted to its italic angle. Use it for "
        "narrow letters that otherwise float in their cell.",
    )
    donor.add_argument("--donor", metavar="FONT", help="monospaced font file to borrow glyphs from")
    donor.add_argument("--donor-face", type=int, default=0, help="face index within the donor collection (default: 0)")
    donor.add_argument("--donor-glyphs", default=DEFAULT_DONOR_GLYPHS, metavar="CHARS", help=f"characters to take from the donor (default: {DEFAULT_DONOR_GLYPHS})")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        for f in list_faces(args.font):
            print(f"{f['index']:>3}  {f['postscript_name']:<40} {f['family']} / {f['style']}  [{f['outlines']}]")
        return 0

    options = Options(
        cell=args.cell,
        cell_em=args.cell_em,
        reference_glyph=args.reference_glyph,
        margin=args.margin,
        wide=args.wide,
        family=args.family,
        strip_layout=not args.keep_layout,
        donor=args.donor,
        donor_face=args.donor_face,
        donor_glyphs=args.donor_glyphs,
    )
    try:
        results = convert_file(args.font, args.out_dir, options, faces=args.face)
    except (ValueError, IndexError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for r in results:
        line = f"{r.postscript_name}: cell {r.cell}, {r.glyph_count} glyphs, {r.squeezed} squeezed"
        if r.overflowed:
            line += f", {r.overflowed} overflowing"
        if r.donated:
            line += f", {r.donated} from donor"
        print(f"{line} -> {r.path}")
        for note in r.notes:
            print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
