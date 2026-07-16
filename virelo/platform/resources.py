import os
import sys


def resource_path(relative_path: str) -> str:
    """Return absolute path to resource, works for dev and PyInstaller."""
    base_path = getattr(
        sys,
        "_MEIPASS",
        os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    )
    return os.path.join(base_path, relative_path)
