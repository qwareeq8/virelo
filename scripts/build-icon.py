#!/usr/bin/env python3
"""Rasterize branding/virelo-icon.svg into the 7-resolution icon.ico.

Run once: pip install pillow

External dep (not on PyPI): Inkscape CLI. Install from https://inkscape.org/.
On Windows this script probes common install paths and falls back to PATH.

Phase 3 one-shot developer helper. NOT a runtime or packaging dependency.
NOT wired into scripts/build-installer.ps1. End-users consume the committed
icon.ico directly; this script only regenerates it from the SVG source.

Usage (from project root):
    .venv/Scripts/python.exe scripts/build-icon.py

Output: overwrites D:/Virelo/icon.ico with a multi-image ICO containing
        7 sub-images at sizes 16, 24, 32, 48, 64, 128, 256. Each sub-image
        is a fresh Inkscape rasterization of branding/virelo-icon.svg at
        target resolution (not a bicubic downsample of the 256 master)
        so per-size rounded-corner anti-aliasing is crisp.

Per-size proportional radius (from 03-CONTEXT.md D-03 table) is achieved
automatically by the SVG's rx="48" on a 256x256 viewBox: rasterizing at
size S yields a radius of 48*S/256 pixels, matching the target table
(3 / 4.5 / 6 / 9 / 12 / 24 / 48).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = PROJECT_ROOT / "branding" / "virelo-icon.svg"
ICO_PATH = PROJECT_ROOT / "icon.ico"
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def find_inkscape() -> str:
    """Return the Inkscape CLI executable path, probing common locations."""
    env_path = os.environ.get("INKSCAPE_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    candidates = [
        r"C:\ProgramData\chocolatey\bin\inkscape.exe",
        r"C:\Program Files\Inkscape\bin\inkscape.exe",
        r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe",
        "inkscape",  # fall back to PATH
    ]
    for candidate in candidates:
        if candidate == "inkscape" or Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "Inkscape CLI not found. Install from https://inkscape.org/ or set "
        "INKSCAPE_PATH environment variable."
    )


def rasterize(inkscape: str, svg: Path, size: int, out_png: Path) -> None:
    """Invoke Inkscape to rasterize svg to out_png at size x size pixels."""
    cmd = [
        inkscape,
        str(svg),
        "--export-type=png",
        f"--export-filename={out_png}",
        f"--export-width={size}",
        f"--export-height={size}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Inkscape failed to rasterize {svg} at {size}x{size}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )
    if not out_png.exists():
        raise RuntimeError(f"Inkscape did not produce expected output: {out_png}")


def build_ico() -> None:
    """Rasterize the SVG at all 7 target sizes and assemble icon.ico."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("Pillow is required. Run once: pip install pillow") from exc

    if not SVG_PATH.exists():
        raise FileNotFoundError(f"SVG source missing: {SVG_PATH}")

    inkscape = find_inkscape()
    print(f"Using Inkscape: {inkscape}")
    print(f"Rasterizing {SVG_PATH.name} at {len(ICO_SIZES)} sizes...")

    pngs: list[Path] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for size in ICO_SIZES:
            out = tmp / f"virelo-icon-{size}.png"
            rasterize(inkscape, SVG_PATH, size, out)
            pngs.append(out)
            print(f"  rendered {size}x{size} -> {out.name} ({out.stat().st_size} bytes)")

        # Load each Inkscape-rasterized PNG. The largest (256) is the master
        # passed to save(); the other six ride along via append_images=, so
        # every sub-image in the ICO is a crisp per-size rasterization of the
        # SVG rather than a downsample of the 256 master (Pillow's ICO writer
        # matches each size tuple against the available images exactly).
        imgs = [Image.open(p).convert("RGBA") for p in pngs]
        imgs_by_size = {im.size: im for im in imgs}

        master = imgs_by_size[(256, 256)]
        appended = [im for im in imgs if im.size != (256, 256)]
        size_tuples = [(s, s) for s in ICO_SIZES]

        # bitmap_format="bmp" writes all 7 sub-images as uncompressed 32-bit
        # BGRA BMP (Windows ICO convention for Windows 10/11; all-BMP is
        # simpler than the legacy mixed "PNG for 256 + BMP for <=128" form
        # and D-04 permits it). The resulting ICO is larger than a single
        # PNG-compressed 256-only file but reads faster because the shell
        # never has to decompress a PNG stream.
        print(f"Assembling {ICO_PATH.name} with {len(size_tuples)} embedded sub-images...")
        master.save(
            ICO_PATH,
            format="ICO",
            sizes=size_tuples,
            append_images=appended,
            bitmap_format="bmp",
        )

    ico_bytes = ICO_PATH.stat().st_size
    print(f"Wrote {ICO_PATH} ({ico_bytes} bytes).")


if __name__ == "__main__":
    try:
        build_ico()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
