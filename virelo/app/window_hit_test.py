"""Pure WM_NCHITTEST classification for the frameless Virelo window."""

RESIZE_BORDER = 4
TITLE_BAR_HEIGHT = 34
TITLE_BAR_INTERACTIVE_WIDTH = 320
TITLE_BAR_CONTROLS_WIDTH = 72

HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17


def classify_window_hit(x: int, y: int, width: int, height: int) -> int:
    """Return the Win32 non-client hit code for a client-relative point.

    The frontend reserves the first 320 CSS pixels for the logo, title, and
    search button, and the final 72 pixels for the window controls. Only the
    empty spacer between those regions behaves as a title-bar drag handle.
    """
    if x < RESIZE_BORDER:
        if y < RESIZE_BORDER:
            return HTTOPLEFT
        if y >= height - RESIZE_BORDER:
            return HTBOTTOMLEFT
        return HTLEFT
    if x >= width - RESIZE_BORDER:
        if y < RESIZE_BORDER:
            return HTTOPRIGHT
        if y >= height - RESIZE_BORDER:
            return HTBOTTOMRIGHT
        return HTRIGHT
    if y < RESIZE_BORDER:
        return HTTOP
    if y >= height - RESIZE_BORDER:
        return HTBOTTOM

    if (
        y < TITLE_BAR_HEIGHT
        and x >= TITLE_BAR_INTERACTIVE_WIDTH
        and x < width - TITLE_BAR_CONTROLS_WIDTH
    ):
        return HTCAPTION
    return 0
