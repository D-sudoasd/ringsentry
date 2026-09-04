"""Screen-aware sizing helpers for application and preview windows."""


def calculate_window_bounds(
    screen_size,
    preferred_size,
    minimum_size=(640, 480),
    margin=32,
):
    """Return visible, centred window and minimum bounds.

    The returned tuple is ``(width, height, x, y, min_width, min_height)``.
    Minimum dimensions are capped as well so small displays are never forced
    to place part of a window outside the usable screen area.
    """
    screen_width, screen_height = (max(1, int(v)) for v in screen_size)
    preferred_width, preferred_height = (
        max(1, int(v)) for v in preferred_size
    )
    minimum_width, minimum_height = (max(1, int(v)) for v in minimum_size)
    margin = max(0, int(margin))

    usable_width = max(1, screen_width - 2 * margin)
    usable_height = max(1, screen_height - 2 * margin)
    width = min(preferred_width, usable_width)
    height = min(preferred_height, usable_height)
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    min_width = min(minimum_width, width)
    min_height = min(minimum_height, height)
    return width, height, x, y, min_width, min_height


def clamp_popup_geometry(
    screen_size,
    anchor_box,
    popup_size,
    margin=8,
    offset=(8, 6),
):
    """Return ``(x, y)`` for a popup that stays fully on-screen.

    ``anchor_box`` is ``(x, y, width, height)`` in screen coordinates.
    The popup is placed below the anchor when it fits, otherwise above.
    Horizontal overflow is shifted left rather than clipped.
    """
    screen_width, screen_height = (max(1, int(value)) for value in screen_size)
    anchor_x, anchor_y, _anchor_width, anchor_height = (
        int(value) for value in anchor_box
    )
    popup_width, popup_height = (max(1, int(value)) for value in popup_size)
    margin = max(0, int(margin))
    offset_x, offset_y = (int(value) for value in offset)

    x = anchor_x + offset_x
    y = anchor_y + anchor_height + offset_y
    if y + popup_height + margin > screen_height:
        y = anchor_y - popup_height - offset_y

    max_x = max(margin, screen_width - popup_width - margin)
    max_y = max(margin, screen_height - popup_height - margin)
    x = min(max(margin, x), max_x)
    y = min(max(margin, y), max_y)
    return x, y


def fit_window_to_screen(
    window,
    preferred_size,
    minimum_size=(640, 480),
    margin=32,
):
    """Apply a centred geometry that remains fully visible on the screen."""
    bounds = calculate_window_bounds(
        (window.winfo_screenwidth(), window.winfo_screenheight()),
        preferred_size,
        minimum_size,
        margin,
    )
    width, height, x, y, min_width, min_height = bounds
    window.geometry(f"{width}x{height}+{x}+{y}")
    window.minsize(min_width, min_height)
    return bounds
