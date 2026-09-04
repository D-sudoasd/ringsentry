from gui.windowing import (
    calculate_window_bounds,
    clamp_popup_geometry,
    fit_window_to_screen,
)


class FakeWindow:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.geometry_value = None
        self.minimum_value = None

    def winfo_screenwidth(self):
        return self.screen_width

    def winfo_screenheight(self):
        return self.screen_height

    def geometry(self, value):
        self.geometry_value = value

    def minsize(self, width, height):
        self.minimum_value = (width, height)


def test_large_screen_keeps_preferred_size_and_centers_window():
    bounds = calculate_window_bounds(
        screen_size=(1920, 1080),
        preferred_size=(1280, 900),
        minimum_size=(1100, 800),
    )

    assert bounds == (1280, 900, 320, 90, 1100, 800)


def test_small_screen_caps_both_size_and_minimum_to_visible_area():
    bounds = calculate_window_bounds(
        screen_size=(1024, 768),
        preferred_size=(1280, 900),
        minimum_size=(1100, 800),
    )

    assert bounds == (960, 704, 32, 32, 960, 704)


def test_tiny_screen_never_requests_negative_or_offscreen_bounds():
    bounds = calculate_window_bounds(
        screen_size=(40, 30),
        preferred_size=(1280, 900),
        minimum_size=(1100, 800),
        margin=32,
    )

    width, height, x, y, min_width, min_height = bounds
    assert width == 1
    assert height == 1
    assert x >= 0
    assert y >= 0
    assert x + width <= 40
    assert y + height <= 30
    assert min_width == 1
    assert min_height == 1


def test_preferred_smaller_than_minimum_keeps_preferred_and_caps_minsize():
    bounds = calculate_window_bounds(
        screen_size=(1920, 1080),
        preferred_size=(800, 600),
        minimum_size=(1100, 800),
    )

    assert bounds == (800, 600, 560, 240, 800, 600)


def test_clamp_popup_flips_above_near_bottom_and_shifts_left_near_right():
    x, y = clamp_popup_geometry(
        screen_size=(1024, 768),
        anchor_box=(900, 720, 80, 24),
        popup_size=(200, 80),
        margin=8,
        offset=(8, 6),
    )

    assert 8 <= x <= 1024 - 200 - 8
    assert 8 <= y <= 768 - 80 - 8
    assert y + 80 <= 768
    assert x + 200 <= 1024


def test_fit_window_applies_visible_geometry_and_minimum():
    window = FakeWindow(1366, 768)

    bounds = fit_window_to_screen(
        window,
        preferred_size=(1400, 700),
        minimum_size=(900, 600),
    )

    assert bounds == (1302, 700, 32, 34, 900, 600)
    assert window.geometry_value == "1302x700+32+34"
    assert window.minimum_value == (900, 600)
