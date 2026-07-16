import os


def _select_python_executable(executable, exists=os.path.exists):
    if executable.lower().endswith("python.exe"):
        candidate = executable[:-10] + "pythonw.exe"
        if exists(candidate):
            return candidate
    return executable


def startup_shortcut_spec(executable, argv0, frozen, exists=os.path.exists):
    if frozen:
        return executable, ""
    target = _select_python_executable(executable, exists)
    return target, f'"{argv0}"'
