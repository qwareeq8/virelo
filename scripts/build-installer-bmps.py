#!/usr/bin/env python3
"""Generate the four Inno Setup wizard bitmaps under ``branding``.

Install Pillow once with ``python -m pip install pillow``.

The script also requires the Inkscape CLI. On Windows, it probes common
installation paths and then falls back to ``PATH``.

This developer helper is not a runtime or packaging dependency and is not
called by ``scripts/build-installer.ps1``. Inno Setup consumes the committed
``branding/*.bmp`` files directly.

Run it from the repository root:

``.venv-x64\\Scripts\\python.exe scripts\\build-installer-bmps.py``

The outputs are uncompressed 24-bit RGB Windows bitmaps. Wizard images use
a white tile and slate glyph on a slate banner. Header images use a slate
tile and white glyph on the light application surface.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRANDING_DIR = PROJECT_ROOT / "branding"
ICON_SVG_PATH = BRANDING_DIR / "virelo-icon.svg"

# Shared color tokens.
SLATE = "#1C1A16"
WHITE = "#FFFFFF"
LIGHT_BG = "#FAF9F7"

# Each bitmap specifies its canvas, background, tile geometry, and colors.
BMP_SPECS = {
    "installer-wizard.bmp": {
        "canvas": (164, 314),
        "bg": SLATE,
        "tile": (100, 32, 60),
        "tile_fill": WHITE,  # Inverted treatment.
        "glyph_fill": SLATE,
    },
    "installer-wizard_2x.bmp": {
        "canvas": (328, 628),
        "bg": SLATE,
        "tile": (200, 64, 120),
        "tile_fill": WHITE,
        "glyph_fill": SLATE,
    },
    "installer-header.bmp": {
        "canvas": (55, 58),
        "bg": LIGHT_BG,
        "tile": (44, 5, 7),
        "tile_fill": SLATE,  # Direct treatment.
        "glyph_fill": WHITE,
    },
    "installer-header_2x.bmp": {
        "canvas": (110, 116),
        "bg": LIGHT_BG,
        "tile": (88, 10, 14),
        "tile_fill": SLATE,
        "glyph_fill": WHITE,
    },
}


def find_inkscape() -> str:
    """Return the Inkscape CLI executable path, probing common locations."""
    env_path = os.environ.get("INKSCAPE_PATH")
    if env_path and Path(env_path).is_file():
        return env_path

    candidates = [
        r"C:\ProgramData\chocolatey\bin\inkscape.exe",
        r"C:\Program Files\Inkscape\bin\inkscape.exe",
        r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    executable = shutil.which("inkscape")
    if executable:
        return executable
    raise FileNotFoundError(
        "Inkscape CLI not found. Install from https://inkscape.org/ or set "
        "INKSCAPE_PATH environment variable."
    )


def make_tile_svg(tile_fill: str, glyph_fill: str) -> str:
    """Recolor the shared application-icon SVG for one installer tile."""
    try:
        root = ET.fromstring(ICON_SVG_PATH.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as error:
        raise RuntimeError(f"Could not read the icon source {ICON_SVG_PATH}: {error}.") from error

    colors = {SLATE.casefold(): tile_fill, WHITE.casefold(): glyph_fill}
    replacements = 0
    for element in root.iter():
        for attribute in ("fill", "stroke"):
            value = element.get(attribute)
            replacement = colors.get(value.casefold()) if value is not None else None
            if replacement is not None:
                element.set(attribute, replacement)
                replacements += 1
    if replacements < 2:
        raise RuntimeError(
            f"The icon source {ICON_SVG_PATH} does not contain the expected brand colors."
        )

    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root,
        encoding="unicode",
    )


def rasterize_svg_to_png(inkscape: str, svg_path: Path, size: int, out_png: Path) -> None:
    """Invoke Inkscape to rasterize svg_path to out_png at size x size pixels."""
    cmd = [
        inkscape,
        str(svg_path),
        "--export-type=png",
        f"--export-filename={out_png}",
        f"--export-width={size}",
        f"--export-height={size}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Inkscape timed out while rasterizing {svg_path} at {size}x{size}."
        ) from error
    if result.returncode != 0:
        raise RuntimeError(
            f"Inkscape failed to rasterize {svg_path} at {size}x{size}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}."
        )
    if not out_png.exists():
        raise RuntimeError(f"Inkscape did not produce the expected output: {out_png}.")


def build_bmp(name: str, spec: dict, inkscape: str, tmp: Path) -> None:
    """Construct one BMP per spec and save to branding/."""
    from PIL import Image

    canvas_w, canvas_h = spec["canvas"]
    tile_size, tile_x, tile_y = spec["tile"]
    bg = spec["bg"]
    tile_fill = spec["tile_fill"]
    glyph_fill = spec["glyph_fill"]

    # Render RGBA at the exact tile size so the alpha channel preserves the
    # rounded corners during compositing.
    tile_svg = make_tile_svg(tile_fill, glyph_fill)
    tile_svg_path = tmp / f"{name}-tile.svg"
    tile_svg_path.write_text(tile_svg, encoding="utf-8")

    tile_png_path = tmp / f"{name}-tile.png"
    rasterize_svg_to_png(inkscape, tile_svg_path, tile_size, tile_png_path)

    tile_img = Image.open(tile_png_path).convert("RGBA")

    # Build a solid RGB canvas for 24-bit bitmap output.
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg)

    # Use the tile alpha channel to blend its rounded corners.
    canvas.paste(tile_img, (tile_x, tile_y), mask=tile_img.split()[-1])

    out_path = BRANDING_DIR / name
    # Pillow saves RGB bitmaps as uncompressed 24-bit Windows v3 files.
    canvas.save(out_path, format="BMP")
    print(
        f"  wrote {name} ({canvas_w}x{canvas_h}, "
        f"tile {tile_size}x{tile_size} at ({tile_x},{tile_y})) "
        f"-> {out_path.stat().st_size} bytes"
    )


def main() -> None:
    try:
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise ImportError("Pillow is required. Run `python -m pip install pillow` once.") from exc

    if not BRANDING_DIR.is_dir():
        raise FileNotFoundError(
            f"The branding directory is missing: {BRANDING_DIR}. "
            "Restore it before regenerating installer bitmaps."
        )
    if not ICON_SVG_PATH.is_file():
        raise FileNotFoundError(
            f"The shared icon source is missing: {ICON_SVG_PATH}. "
            "Restore it before regenerating installer bitmaps."
        )

    inkscape = find_inkscape()
    print(f"Using Inkscape: {inkscape}")
    print(f"Building {len(BMP_SPECS)} installer BMPs in {BRANDING_DIR}...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for name, spec in BMP_SPECS.items():
            build_bmp(name, spec, inkscape, tmp)

    print("Installer bitmap generation completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
