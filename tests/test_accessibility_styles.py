"""Focused regression tests for GUI accessibility helpers."""

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gui.layout import ScrollableFrame
from gui.styles import APP_BACKGROUND, STATUS_COLORS
from gui.tooltip import ToolTip


def _relative_luminance(color):
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    channels = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return (
        0.2126 * channels[0]
        + 0.7152 * channels[1]
        + 0.0722 * channels[2]
    )


def _contrast_ratio(foreground, background):
    foreground_luminance = _relative_luminance(foreground)
    background_luminance = _relative_luminance(background)
    return (
        max(foreground_luminance, background_luminance) + 0.05
    ) / (min(foreground_luminance, background_luminance) + 0.05)


class _FakeWidget:
    def __init__(self, path=".widget", root_y=0, height=20):
        self.path = path
        self.root_y = root_y
        self.height = height
        self.bindings = {}

    def __str__(self):
        return self.path

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = (callback, add)
        return sequence

    def winfo_rootx(self):
        return 0

    def winfo_rooty(self):
        return self.root_y

    def winfo_height(self):
        return self.height


class _FakeCanvas(_FakeWidget):
    def __init__(self):
        super().__init__(path=".frame.canvas", root_y=100, height=100)
        self.scroll_calls = []
        self.move_calls = []

    def winfo_rootx(self):
        return 0

    def winfo_width(self):
        return 200

    def update_idletasks(self):
        return None

    def yview_scroll(self, amount, what):
        self.scroll_calls.append((amount, what))

    def yview_moveto(self, fraction):
        self.move_calls.append(fraction)

    def bbox(self, _tag):
        return (0, 0, 200, 1000)

    def canvasy(self, _value):
        return 0


class _FakeTipWindow:
    instances = []

    def __init__(self, _parent):
        self.destroyed = False
        self.__class__.instances.append(self)

    def winfo_exists(self):
        return not self.destroyed

    def wm_overrideredirect(self, _value):
        return None

    def wm_geometry(self, _geometry):
        return None

    def destroy(self):
        self.destroyed = True


class _FakeLabel:
    def __init__(self, *_args, **_kwargs):
        return None

    def pack(self, **_kwargs):
        return None


class AccessibilityStylesTests(unittest.TestCase):
    def test_status_colors_meet_normal_text_contrast(self):
        for style_name, color in STATUS_COLORS.items():
            with self.subTest(style=style_name):
                self.assertGreaterEqual(
                    _contrast_ratio(color, APP_BACKGROUND), 4.5
                )

    def test_status_labels_are_textual_and_not_color_only(self):
        source = Path("gui/log_panel.py").read_text(encoding="utf-8")
        # The production module keeps these literals escaped for source-file
        # portability; they become the visible labels when Python evaluates
        # the strings.
        labels = {
            "成功": r"\u6210\u529F",
            "失败": r"\u5931\u8D25",
            "跳过": r"\u8DF3\u8FC7",
            "取消": r"\u53D6\u6D88",
        }
        for label, escaped_label in labels.items():
            with self.subTest(label=label):
                self.assertIn(escaped_label, source)

    def test_tooltip_supports_focus_without_duplicate_windows(self):
        widget = _FakeWidget()
        _FakeTipWindow.instances = []
        with patch("gui.tooltip.tk.Toplevel", _FakeTipWindow), patch(
            "gui.tooltip.tk.Label", _FakeLabel
        ):
            tooltip = ToolTip(widget, "help")
            self.assertEqual(
                {"<Enter>", "<Leave>", "<FocusIn>", "<FocusOut>"},
                set(widget.bindings),
            )
            tooltip.show_tip()
            tooltip.show_tip()
            self.assertEqual(1, len(_FakeTipWindow.instances))
            tooltip.hide_tip()
            self.assertIsNone(tooltip.tip_window)

    def test_scrollable_frame_handles_wheel_keys_and_focus(self):
        frame = object.__new__(ScrollableFrame)
        frame._w = ".frame"
        frame.body = _FakeWidget(path=".frame.body")
        frame.canvas = _FakeCanvas()
        frame.scrollbar = _FakeWidget(path=".frame.scrollbar")
        child = _FakeWidget(path=".frame.body.child", root_y=250, height=20)

        self.assertEqual(
            "break",
            frame._on_mousewheel(SimpleNamespace(x_root=10, y_root=110, delta=1)),
        )
        self.assertEqual((-1, "units"), frame.canvas.scroll_calls[-1])
        frame._on_mousewheel(SimpleNamespace(x_root=10, y_root=110, delta=-1))
        self.assertEqual((1, "units"), frame.canvas.scroll_calls[-1])
        frame._on_mousewheel(
            SimpleNamespace(x_root=10, y_root=110, num=4, delta=0)
        )
        self.assertEqual((-1, "units"), frame.canvas.scroll_calls[-1])
        frame._on_mousewheel(
            SimpleNamespace(x_root=10, y_root=110, num=5, delta=0)
        )
        self.assertEqual((1, "units"), frame.canvas.scroll_calls[-1])

        frame._on_keypress(SimpleNamespace(widget=frame.body, keysym="PageUp"))
        self.assertEqual((-1, "pages"), frame.canvas.scroll_calls[-1])
        frame._on_keypress(SimpleNamespace(widget=frame.body, keysym="PageDown"))
        self.assertEqual((1, "pages"), frame.canvas.scroll_calls[-1])
        self.assertEqual(
            "break", frame._on_keypress(SimpleNamespace(widget=frame.body, keysym="Home"))
        )
        self.assertEqual(0, frame.canvas.move_calls[-1])
        frame._on_keypress(SimpleNamespace(widget=frame.body, keysym="End"))
        self.assertEqual(1, frame.canvas.move_calls[-1])

        frame._on_focus_in(SimpleNamespace(widget=child))
        self.assertTrue(frame.canvas.move_calls[-1] > 0)


if __name__ == "__main__":
    unittest.main()
