"""Pure WM_NCHITTEST classification for the frameless Virelo window."""

import math

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


def normalize_hit_test_regions(
    interactive_width: int,
    controls_width: int,
    title_bar_height: int,
) -> tuple[int, int, int]:
    """Validate frontend-measured hit-test regions expressed in CSS pixels."""
    values = (
        ("interactive_width", interactive_width, 0, 4096),
        ("controls_width", controls_width, 1, 512),
        ("title_bar_height", title_bar_height, 1, 256),
    )
    normalized = []
    for name, value, minimum, maximum in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer.")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be from {minimum} to {maximum} pixels.")
        normalized.append(value)
    return normalized[0], normalized[1], normalized[2]


def classify_window_hit(
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    resize_border: int = RESIZE_BORDER,
    title_bar_height: int = TITLE_BAR_HEIGHT,
    interactive_width: int = TITLE_BAR_INTERACTIVE_WIDTH,
    controls_width: int = TITLE_BAR_CONTROLS_WIDTH,
) -> int:
    """Return the Win32 non-client hit code for a client-relative point.

    The frontend reserves the first 320 CSS pixels for the logo, title, and
    search button, and the final 72 pixels for the window controls. Only the
    empty spacer between those regions behaves as a title-bar drag handle.
    """
    if width <= 0 or height <= 0:
        return 0

    # Caption controls take priority over the top and right resize strips so a
    # flick to the upper-right corner still reaches the close button.
    controls_start = max(0, width - controls_width)
    if x >= controls_start and 0 <= y < title_bar_height:
        return 0

    if x < resize_border:
        if y < resize_border:
            return HTTOPLEFT
        if y >= height - resize_border:
            return HTBOTTOMLEFT
        return HTLEFT
    if x >= width - resize_border:
        if y < resize_border:
            return HTTOPRIGHT
        if y >= height - resize_border:
            return HTBOTTOMRIGHT
        return HTRIGHT
    if y < resize_border:
        return HTTOP
    if y >= height - resize_border:
        return HTBOTTOM

    if y < title_bar_height and x >= interactive_width and x < width - controls_width:
        return HTCAPTION
    return 0


def classify_physical_window_hit(
    screen_x: int,
    screen_y: int,
    window_rect: tuple[int, int, int, int],
    scale: float,
    *,
    interactive_width: int = TITLE_BAR_INTERACTIVE_WIDTH,
    controls_width: int = TITLE_BAR_CONTROLS_WIDTH,
    title_bar_height: int = TITLE_BAR_HEIGHT,
) -> int:
    """Classify a native screen point without mixing physical and Qt coordinates."""
    if not math.isfinite(scale) or scale <= 0:
        scale = 1.0
    left, top, right, bottom = window_rect

    def scaled(value: int) -> int:
        return max(1, math.ceil(value * scale))

    return classify_window_hit(
        screen_x - left,
        screen_y - top,
        right - left,
        bottom - top,
        resize_border=scaled(RESIZE_BORDER),
        title_bar_height=scaled(title_bar_height),
        interactive_width=scaled(interactive_width),
        controls_width=scaled(controls_width),
    )
