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


# Task Scheduler 2.0 constants used through the late-bound COM interface.
_TASK_TRIGGER_LOGON = 9
_TASK_ACTION_EXEC = 0
_TASK_CREATE_OR_UPDATE = 6
_TASK_LOGON_INTERACTIVE_TOKEN = 3
_TASK_RUNLEVEL_HIGHEST = 1
_ERROR_TASK_NOT_FOUND = -2147024894  # HRESULT 0x80070002, "file not found".

STARTUP_TASK_NAME = "Virelo"


def _current_user_account() -> str:
    """Return the DOMAIN\\user account name that scopes the logon trigger."""
    try:
        import win32api

        return win32api.GetUserNameEx(2)  # This is the NameSamCompatible format.
    except Exception:
        domain = os.environ.get("USERDOMAIN", "")
        user = os.environ.get("USERNAME", "")
        return f"{domain}\\{user}" if domain and user else user


def _task_scheduler_root(dispatch):
    """Connect to the Task Scheduler service and return it with its root folder."""
    service = dispatch("Schedule.Service")
    service.Connect()
    return service, service.GetFolder("\\")


def register_startup_task(target, arguments, working_directory, dispatch=None) -> None:
    """Register or update the elevated logon task for the current user.

    A highest-run-level logon task starts Virelo elevated at sign-in without
    a UAC prompt, which a Startup-folder shortcut cannot do for an
    application that always self-elevates. Registration itself requires an
    elevated process.
    """
    dispatch = dispatch or ensure_dispatch
    service, root = _task_scheduler_root(dispatch)
    definition = service.NewTask(0)
    definition.RegistrationInfo.Description = "Starts Virelo, elevated, when the user signs in."
    definition.Principal.RunLevel = _TASK_RUNLEVEL_HIGHEST
    definition.Principal.LogonType = _TASK_LOGON_INTERACTIVE_TOKEN
    settings = definition.Settings
    # A resident tray utility must start on battery power, and the scheduler's
    # default execution time limit must never stop it.
    settings.DisallowStartIfOnBatteries = False
    settings.StopIfGoingOnBatteries = False
    settings.ExecutionTimeLimit = "PT0S"
    trigger = definition.Triggers.Create(_TASK_TRIGGER_LOGON)
    trigger.UserId = _current_user_account()
    action = definition.Actions.Create(_TASK_ACTION_EXEC)
    action.Path = target
    if arguments:
        action.Arguments = arguments
    if working_directory:
        action.WorkingDirectory = working_directory
    root.RegisterTaskDefinition(
        STARTUP_TASK_NAME,
        definition,
        _TASK_CREATE_OR_UPDATE,
        None,
        None,
        _TASK_LOGON_INTERACTIVE_TOKEN,
    )


def remove_startup_task(dispatch=None) -> None:
    """Delete the elevated logon task. A missing task is not an error."""
    dispatch = dispatch or ensure_dispatch
    _service, root = _task_scheduler_root(dispatch)
    try:
        root.DeleteTask(STARTUP_TASK_NAME, 0)
    except Exception as error:
        if _is_missing_task_error(error):
            return
        raise


def _is_missing_task_error(error) -> bool:
    """Return whether a COM error reports the task as absent."""
    codes = set()
    hresult = getattr(error, "hresult", None)
    if isinstance(hresult, int):
        codes.add(hresult)
    excepinfo = getattr(error, "excepinfo", None)
    if excepinfo and len(excepinfo) >= 6 and isinstance(excepinfo[5], int):
        codes.add(excepinfo[5])
    return _ERROR_TASK_NOT_FOUND in codes or (_ERROR_TASK_NOT_FOUND & 0xFFFFFFFF) in codes


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
