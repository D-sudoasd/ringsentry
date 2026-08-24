from gui.windowing import calculate_window_bounds, fit_window_to_screen


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
