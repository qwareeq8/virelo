#!/usr/bin/env python3
"""Generate the 4 Inno Setup wizard BMPs under branding/.

Run once: pip install pillow

External dep (not on PyPI): Inkscape CLI. Install from https://inkscape.org/.
On Windows this script probes common install paths and falls back to PATH.

Phase 3 one-shot developer helper. NOT a runtime or packaging dependency.
NOT wired into scripts/build-installer.ps1. Inno Setup consumes the
committed branding/*.bmp files at ISCC compile time; this script only
regenerates them.

Usage (from project root):
    .venv/Scripts/python.exe scripts/build-installer-bmps.py

Outputs (all 24-bit RGB Windows v3 BMP, no alpha, uncompressed):
    branding/installer-wizard.bmp        164x314
    branding/installer-wizard_2x.bmp     328x628
    branding/installer-header.bmp        55x58
    branding/installer-header_2x.bmp     110x116

Pixel layouts from 03-UI-SPEC.md (Color section) and 03-CONTEXT.md D-10, D-11.
Wizard BMPs use INVERTED glyph/tile (white tile + Slate V on solid Slate
banner for contrast). Header BMPs use DIRECT (Slate tile + white V on
#FAF9F7 surface - matches the app icon color direction).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRANDING_DIR = PROJECT_ROOT / "branding"

# Color tokens (Phase 1-locked):
SLATE = "#1C1A16"
WHITE = "#FFFFFF"
LIGHT_BG = "#FAF9F7"

# V glyph path data (flattened Inter 700 V on a 256x256 viewBox - same glyph
# geometry as branding/virelo-icon.svg). Encoded once so both wizard and
# header BMPs share the identical shape via SVG string templating.
V_GLYPH_PATH = "M 48 48 L 128 208 L 208 48 L 172 48 L 128 148 L 84 48 Z"


# Per-BMP pixel layout. Each entry specifies:
#   canvas: (width, height)
#   bg: background RGB hex
#   tile: (tile_size, tile_x, tile_y, tile_radius)
#   tile_fill: tile background hex
#   glyph_fill: V glyph color hex
BMP_SPECS = {
    "installer-wizard.bmp": {
        "canvas": (164, 314),
        "bg": SLATE,
        "tile": (100, 32, 60, 18),
        "tile_fill": WHITE,  # INVERTED
        "glyph_fill": SLATE,
    },
    "installer-wizard_2x.bmp": {
        "canvas": (328, 628),
        "bg": SLATE,
        "tile": (200, 64, 120, 36),
        "tile_fill": WHITE,
        "glyph_fill": SLATE,
    },
    "installer-header.bmp": {
        "canvas": (55, 58),
        "bg": LIGHT_BG,
        "tile": (44, 5, 7, 8),
        "tile_fill": SLATE,  # DIRECT
        "glyph_fill": WHITE,
    },
    "installer-header_2x.bmp": {
        "canvas": (110, 116),
        "bg": LIGHT_BG,
        "tile": (88, 10, 14, 16),
        "tile_fill": SLATE,
        "glyph_fill": WHITE,
    },
}


def find_inkscape() -> str:
    """Return the Inkscape CLI executable path, probing common locations."""
    env_path = os.environ.get("INKSCAPE_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    candidates = [
        r"C:\ProgramData\chocolatey\bin\inkscape.exe",
        r"C:\Program Files\Inkscape\bin\inkscape.exe",
        r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe",
        "inkscape",
    ]
    for candidate in candidates:
        if candidate == "inkscape" or Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "Inkscape CLI not found. Install from https://inkscape.org/ or set "
        "INKSCAPE_PATH environment variable."
    )


def make_tile_svg(tile_size: int, tile_fill: str, glyph_fill: str) -> str:
    """Build an SVG for a single rounded tile + V glyph at tile_size px.

    The tile fills the full viewBox; its rx is proportional to the radius of
    the parent icon (48/256 = 18.75% baseline, applied per the spec's tile
    radius table). We encode the SVG at 256x256 viewBox so the glyph path
    coordinates match branding/virelo-icon.svg, then rasterize at tile_size.
    """
    # Proportional radius at 256-viewBox units. The actual radius per
    # BMP-spec ("tile_radius" arg) is applied at rasterization via the
    # viewBox scaling: radius_at_render = (radius_at_256 / 256) * tile_size.
    # Since our source SVG uses rx=48 on 256, that yields 18.75% radius,
    # which at rasterization to 100px becomes 18.75 (~=18 per spec D-10
    # "radius ~18% of 100"). Close enough - spec allows proportional choice.
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" '
        f'width="256" height="256">'
        f'<rect x="0" y="0" width="256" height="256" rx="48" ry="48" '
        f'fill="{tile_fill}"/>'
        f'<path d="{V_GLYPH_PATH}" fill="{glyph_fill}"/>'
        f"</svg>"
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
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Inkscape failed to rasterize {svg_path} at {size}x{size}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )
    if not out_png.exists():
        raise RuntimeError(f"Inkscape did not produce expected output: {out_png}")


def build_bmp(name: str, spec: dict, inkscape: str, tmp: Path) -> None:
    """Construct one BMP per spec and save to branding/."""
    from PIL import Image

    canvas_w, canvas_h = spec["canvas"]
    tile_size, tile_x, tile_y, _tile_radius = spec["tile"]
    bg = spec["bg"]
    tile_fill = spec["tile_fill"]
    glyph_fill = spec["glyph_fill"]

    # Render the tile SVG at the exact tile pixel size (RGBA so we can
    # composite on the solid background using the tile's alpha channel,
    # which encodes the rounded-corner cutout).
    tile_svg = make_tile_svg(tile_size, tile_fill, glyph_fill)
    tile_svg_path = tmp / f"{name}-tile.svg"
    tile_svg_path.write_text(tile_svg, encoding="utf-8")

    tile_png_path = tmp / f"{name}-tile.png"
    rasterize_svg_to_png(inkscape, tile_svg_path, tile_size, tile_png_path)

    tile_img = Image.open(tile_png_path).convert("RGBA")

    # Build canvas as solid RGB (no alpha; 24-bit BMP output).
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg)

    # Paste the tile using its alpha as mask so the rounded corners blend
    # cleanly onto the background fill.
    canvas.paste(tile_img, (tile_x, tile_y), mask=tile_img.split()[-1])

    out_path = BRANDING_DIR / name
    # Pillow saves "RGB" mode .bmp as uncompressed 24-bit BGR Windows v3
    # BMP by default - matches the D-12 format contract.
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
        raise ImportError("Pillow is required. Run once: pip install pillow") from exc

    if not BRANDING_DIR.exists():
        raise FileNotFoundError(
            f"branding/ directory missing: {BRANDING_DIR}. "
            "Run scripts/build-icon.py first to create it."
        )

    inkscape = find_inkscape()
    print(f"Using Inkscape: {inkscape}")
    print(f"Building {len(BMP_SPECS)} installer BMPs in {BRANDING_DIR}...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for name, spec in BMP_SPECS.items():
            build_bmp(name, spec, inkscape, tmp)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
