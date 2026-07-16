"""Tests for path canonicalization utility."""

from virelo.platform.paths import canonicalize_path


def test_empty_string():
    """Empty string should return empty string."""
    assert canonicalize_path("") == ""


def test_forward_slashes_normalized():
    """Forward slashes should be converted to backslashes."""
    assert canonicalize_path("C:/Users/test") == "c:\\users\\test"


def test_trailing_separator_stripped():
    """Trailing backslash should be stripped (unless root drive)."""
    assert canonicalize_path("C:\\Users\\test\\") == "c:\\users\\test"


def test_root_drive_preserved():
    """Root drive path should keep its trailing backslash."""
    assert canonicalize_path("C:\\") == "c:\\"


def test_file_url_decoded():
    """file:/// URLs should be decoded and normalized."""
    assert canonicalize_path("file:///C:/Users/test%20dir") == "c:\\users\\test dir"


def test_case_normalized():
    """Path should be lowercased for case-insensitive comparison."""
    assert canonicalize_path("C:\\USERS\\TEST") == "c:\\users\\test"


def test_multiple_trailing_separators():
    """Multiple trailing backslashes should all be stripped."""
    assert canonicalize_path("C:\\Users\\test\\\\") == "c:\\users\\test"
