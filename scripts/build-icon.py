#!/usr/bin/env python3
"""Rasterize ``branding/virelo-icon.svg`` into a seven-resolution icon file.

Install Pillow once with ``python -m pip install pillow``.

The script also requires the Inkscape CLI. On Windows, it probes common
installation paths and then falls back to ``PATH``.

This developer helper is not a runtime or packaging dependency and is not
called by ``scripts/build-installer.ps1``. Users consume the committed
``icon.ico`` directly.

Run it from the repository root:

``.venv-x64\\Scripts\\python.exe scripts\\build-icon.py``

The script overwrites ``icon.ico`` with 16, 24, 32, 48, 64, 128, and 256
pixel images. Each image is rasterized directly from the SVG so its rounded
corners remain crisp at the target size.
"""

from __future__ import annotations

import os
import shutil
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


def rasterize(inkscape: str, svg: Path, size: int, out_png: Path) -> None:
    """Invoke Inkscape to rasterize an SVG at the requested pixel size."""
    cmd = [
        inkscape,
        str(svg),
        "--export-type=png",
        f"--export-filename={out_png}",
        f"--export-width={size}",
        f"--export-height={size}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Inkscape timed out while rasterizing {svg} at {size}x{size}."
        ) from error
    if result.returncode != 0:
        raise RuntimeError(
            f"Inkscape failed to rasterize {svg} at {size}x{size}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}."
        )
    if not out_png.exists():
        raise RuntimeError(f"Inkscape did not produce the expected output: {out_png}.")


def build_ico() -> None:
    """Rasterize the SVG at all 7 target sizes and assemble icon.ico."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("Pillow is required. Run `python -m pip install pillow` once.") from exc

    if not SVG_PATH.is_file():
        raise FileNotFoundError(f"The SVG source is missing: {SVG_PATH}.")

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
            print(f"  Rendered {size}x{size} -> {out.name} ({out.stat().st_size} bytes).")

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

        # ``bitmap_format="bmp"`` writes every image as uncompressed 32-bit
        # BGRA data, which Windows can read without decompressing a PNG stream.
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
