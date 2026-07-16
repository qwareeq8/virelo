import urllib.parse


def canonicalize_path(path: str) -> str:
    """Normalize a filesystem path for comparison (lowercase, backslash, no trailing sep)."""
    if not path:
        return ""
    path = path.strip()
    if path.lower().startswith("file:///"):
        path = urllib.parse.unquote(path[8:])
    path = path.replace("/", "\\")
    while len(path) > 3 and path.endswith("\\"):
        path = path[:-1]
    path = path.lower()
    return path
