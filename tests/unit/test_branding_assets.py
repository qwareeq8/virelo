"""Verify the committed Windows branding assets without optional image libraries."""

from __future__ import annotations

import importlib.util
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SVG_PATH = PROJECT_ROOT / "branding" / "virelo-icon.svg"
ICO_PATH = PROJECT_ROOT / "icon.ico"
EXPECTED_ICO_SIZES = {16, 24, 32, 48, 64, 128, 256}
EXPECTED_BMPS = {
    "installer-wizard.bmp": (164, 314),
    "installer-wizard_2x.bmp": (328, 628),
    "installer-header.bmp": (55, 58),
    "installer-header_2x.bmp": (110, 116),
}


def _load_bmp_generator() -> ModuleType:
    """Load the hyphenated developer helper as a testable Python module."""
    script = PROJECT_ROOT / "scripts" / "build-installer-bmps.py"
    spec = importlib.util.spec_from_file_location("build_installer_bmps", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snap_mark_svg_is_the_vector_source_of_truth() -> None:
    """The shared source has the expected canvas and simple snap-mark geometry."""
    root = ET.parse(SVG_PATH).getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}

    assert root.get("viewBox") == "0 0 256 256"
    assert root.get("width") == "256"
    assert root.get("height") == "256"
    assert len(root.findall(".//svg:path", namespace)) == 4
    assert len(root.findall(".//svg:rect", namespace)) == 2


def test_installer_generator_recolors_the_shared_snap_mark() -> None:
    """Installer artwork reuses the icon SVG instead of duplicating its geometry."""
    generator = _load_bmp_generator()

    recolored = generator.make_tile_svg("#FFFFFF", "#1C1A16")

    assert 'd="M 48 96 V 62 Q 48 48 62 48 H 96"' in recolored
    assert recolored.count("#FFFFFF") == 1
    assert recolored.count("#1C1A16") == 2


def test_icon_contains_all_uncompressed_bgra_resolutions() -> None:
    """The Windows icon contains every documented directly rendered size."""
    payload = ICO_PATH.read_bytes()
    reserved, image_type, count = struct.unpack_from("<HHH", payload)

    assert (reserved, image_type, count) == (0, 1, len(EXPECTED_ICO_SIZES))
    sizes: set[int] = set()
    for index in range(count):
        (
            width_byte,
            height_byte,
            _color_count,
            _reserved,
            _planes,
            bits_per_pixel,
            image_size,
            image_offset,
        ) = struct.unpack_from("<BBBBHHII", payload, 6 + 16 * index)
        width = width_byte or 256
        height = height_byte or 256
        sizes.add(width)
        assert height == width
        assert bits_per_pixel == 32
        assert image_offset + image_size <= len(payload)
        assert struct.unpack_from("<I", payload, image_offset)[0] == 40

    assert sizes == EXPECTED_ICO_SIZES


def test_installer_bitmaps_are_uncompressed_24_bit_windows_assets() -> None:
    """Each committed Inno bitmap has its required canvas and pixel format."""
    for filename, expected_dimensions in EXPECTED_BMPS.items():
        payload = (PROJECT_ROOT / "branding" / filename).read_bytes()
        signature, declared_size, _reserved, pixel_offset = struct.unpack_from(
            "<2sI4sI",
            payload,
        )
        dib_size = struct.unpack_from("<I", payload, 14)[0]
        width, height, planes, bits_per_pixel, compression = struct.unpack_from(
            "<iiHHI",
            payload,
            18,
        )

        assert signature == b"BM"
        assert declared_size == len(payload)
        assert pixel_offset == 54
        assert dib_size == 40
        assert (width, height) == expected_dimensions
        assert planes == 1
        assert bits_per_pixel == 24
        assert compression == 0
