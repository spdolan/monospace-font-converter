# monospace-font-converter

Turn a proportional font you are licensed to modify into a fixed-pitch derivative, so you can use a typeface you like in a terminal or code editor that needs every character to be the same width.

It is a small command line tool built on [fontTools](https://github.com/fonttools/fonttools). It ships no fonts. You supply a font you have the right to modify, and it writes new font files to a directory you choose.

## What it does

For every glyph in the font:

- the advance width is set to one fixed cell width, chosen automatically from the width of the letter `o` or given explicitly;
- glyphs narrower than the cell are centered in it;
- glyphs wider than the cell are squeezed horizontally to fit, leaving a small margin on each side (or left to overflow, if you ask for that);
- the outline is rebuilt, so hinting instructions are dropped;
- kerning and OpenType layout tables are removed by default, since they have no meaning in a fixed grid.

The result is renamed, by default to `<original family> Mono`, with new PostScript names, so it never masquerades as the original and can be installed alongside it. The font is flagged as fixed pitch in its metadata so terminals and editors list it as a monospaced option.

Both TrueType (`glyf`) and CFF (`OTF`) outlines are supported, including TrueType Collections. Variable fonts and CFF2 are not.

## What to expect

Be realistic about the output. Real monospaced typefaces are drawn for the grid: narrow letters like `i`, `l` and `t` get serifs or tails to fill their cell, and wide letters like `m` and `w` are redrawn narrower. A mechanical conversion does neither. You will see more air around narrow letters and horizontally condensed capitals, and letters that were very wide to begin with will look compressed. Pick a smaller cell width (`--cell-em 0.5`) to tighten running text at the cost of more squeezing, or a larger one for the opposite trade-off.

Converted fonts usually lack box-drawing and powerline glyphs. Most terminals let you set a fallback font for non-ASCII characters. Point that at a real monospaced font such as SF Mono, Menlo or JetBrains Mono so borders and symbols still line up.

## Install

Requires Python 3.10 or later.

```sh
pipx install git+https://github.com/spdolan/monospace-font-converter
# or, inside a virtual environment
pip install git+https://github.com/spdolan/monospace-font-converter
```

## Usage

List the faces in a file or collection:

```sh
monospace-font-converter list /path/to/Family.ttc
```

Convert every face in a file, writing `<Family>Mono-<Style>.ttf` files to an output directory:

```sh
monospace-font-converter convert /path/to/Family.ttc -o ~/fonts/family-mono
```

Convert selected faces from a collection with a chosen cell width and family name:

```sh
monospace-font-converter convert /path/to/Family.ttc -o out \
    --face 0 --face 2 --cell 600 --family "Family Code"
```

Options for `convert`:

| Option | Meaning |
| --- | --- |
| `-o`, `--out-dir DIR` | Where to write the generated files. Default: current directory. |
| `--face N` | Face index within a collection, repeatable. Default: all faces. |
| `--cell N` | Advance width for every glyph, in font units. |
| `--cell-em F` | Advance width as a fraction of the em, for example `0.6`. |
| `--reference-glyph CHAR` | Use this character's original advance as the cell. Default: `o`. |
| `--margin N` | Minimum side bearing, in font units, when a glyph must be squeezed. Default: 15. |
| `--wide squeeze\|overflow` | What to do with glyphs wider than the cell. Default: squeeze. |
| `--family NAME` | Family name for the derivative. Default: `<original family> Mono`. |
| `--keep-layout` | Keep kerning and OpenType layout tables. |

Install the generated files the way you would any font, for example by copying them into `~/Library/Fonts` on macOS or `~/.local/share/fonts` on Linux, then select the new family in your terminal's settings.

## Licensing and intended use

Please read this section before using the tool.

**This tool does not include, download or unlock any fonts.** It only transforms font files you already have, and its output is only ever as legitimate as your right to modify the input.

**Check the license of the font you want to convert.** Font software is licensed, not sold, and licenses differ widely on modification:

- Fonts under the [SIL Open Font License](https://openfontlicense.org/) explicitly allow modification. Derivatives must not use the font's Reserved Font Names, so pass `--family` with a name of your own if the original declares any.
- Fonts under permissive licenses such as Apache 2.0 or Ubuntu Font Licence generally allow modification, with their own naming or attribution conditions.
- Most commercial font licenses, and the licenses covering fonts bundled with operating systems such as macOS and Windows, do **not** permit creating modified versions, or permit it only for your own use on licensed machines. Many prohibit redistribution of any derivative outright. The fact that a font is installed on your computer does not mean you may modify it.

**Keep derivatives of restricted fonts to yourself.** If a license allows personal modification but not redistribution, treat the output as private: install it on your own machines only, and do not commit it to a repository, attach it to a bug report, bundle it with an application or share it with colleagues. The repository's `.gitignore` excludes font files for this reason.

**Do not pass derivatives off as the original.** The tool renames every output by default. Keep that behaviour, and avoid names that suggest the output is an official release of the original typeface or an official product of its foundry. Typeface names are often trademarks.

**This is a personal convenience tool,** written so one person could use a typeface they like in their terminal. It is not a way around licensing, and it is not legal advice. If you are unsure whether a license permits what you want to do, ask the font's publisher before converting it.

## Development

```sh
git clone https://github.com/spdolan/monospace-font-converter
cd monospace-font-converter
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

The tests build tiny synthetic fonts with fontTools, so they need no font files and run anywhere. Commits follow [Conventional Commits](https://www.conventionalcommits.org/); releases are cut by release-please.

## License

The tool is released under the [MIT License](LICENSE). That license covers this software only, not any font you process with it.
