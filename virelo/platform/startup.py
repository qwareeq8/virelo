import os
import re
import shutil
import sys


def ensure_dispatch(app_name: str):
    """Create a COM dispatch and rebuild a corrupt ``gen_py`` cache once."""
    from win32com.client import Dispatch

    try:
        return Dispatch(app_name)
    except AttributeError:
        import logging

        logging.getLogger("Virelo").warning("win32com gen_py cache appears corrupted. Rebuilding.")
        module_names = [
            module.__name__ for module in sys.modules.values() if getattr(module, "__name__", None)
        ]
        for module_name in module_names:
            if re.match(r"win32com\.gen_py\..+", module_name):
                sys.modules.pop(module_name, None)

        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            gen_py_path = os.path.join(localappdata, "Temp", "gen_py")
            if os.path.exists(gen_py_path):
                shutil.rmtree(gen_py_path, ignore_errors=True)

        from win32com import client

        return client.gencache.EnsureDispatch(app_name)


def select_pythonw_executable(executable, exists=os.path.exists):
    """Select a sibling ``pythonw.exe`` without assuming path-name casing."""
    if executable.lower().endswith("python.exe"):
        candidate = executable[:-10] + "pythonw.exe"
        if exists(candidate):
            return candidate
    return executable


def startup_shortcut_spec(executable, argv0, frozen, exists=os.path.exists):
    """Return the executable and arguments for a startup shortcut."""
    if frozen:
        return executable, ""
    target = select_pythonw_executable(executable, exists)
    return target, f'"{argv0}"'
