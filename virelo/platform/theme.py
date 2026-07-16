def normalize_theme_mode(value, default="system"):
    mode = str(value or "").strip().lower()
    if mode in ("system", "dark", "light"):
        return mode
    fallback = str(default or "").strip().lower()
    return fallback if fallback in ("system", "dark", "light") else "system"


def resolve_theme(mode, system_theme):
    normalized = normalize_theme_mode(mode)
    if normalized == "system":
        return "light" if str(system_theme).lower() == "light" else "dark"
    return normalized


def toggle_theme_mode(mode, system_theme):
    normalized = normalize_theme_mode(mode)
    if normalized == "system":
        return "dark" if resolve_theme("system", system_theme) == "light" else "light"
    return "light" if normalized == "dark" else "dark"


def get_windows_theme(read_registry=None):
    try:
        if read_registry is None:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        else:
            value = read_registry()
        return "light" if int(value) == 1 else "dark"
    except Exception:
        return "dark"
