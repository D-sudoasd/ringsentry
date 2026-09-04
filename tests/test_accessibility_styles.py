"""Focused regression tests for GUI accessibility helpers."""

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gui.layout import ScrollableFrame
from gui.styles import APP_BACKGROUND, INVALID_ROW_FOREGROUND, STATUS_COLORS
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
    def __init__(
        self,
        path=".widget",
        root_x=0,
        root_y=0,
        width=80,
        height=20,
        screen_width=1024,
        screen_height=768,
    ):
        self.path = path
        self.root_x = root_x
        self.root_y = root_y
        self.width = width
        self.height = height
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.bindings = {}
        self._ringsentry_tooltip_escape = False

    def __str__(self):
        return self.path

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = (callback, add)
        return sequence

    def winfo_rootx(self):
        return self.root_x

    def winfo_rooty(self):
        return self.root_y

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def winfo_screenwidth(self):
        return self.screen_width

    def winfo_screenheight(self):
        return self.screen_height

    def winfo_toplevel(self):
        return self

    def winfo_viewable(self):
        return True

    def winfo_class(self):
        return "TFrame"


class _FakeCanvas(_FakeWidget):
    def __init__(self):
        super().__init__(path=".frame.canvas", root_y=100, height=100, width=200)
        self.scroll_calls = []
        self.move_calls = []
        self.viewable = True

    def winfo_viewable(self):
        return self.viewable

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
        self.geometry = None
        self.__class__.instances.append(self)

    def winfo_exists(self):
        return not self.destroyed

    def winfo_reqwidth(self):
        return 200

    def winfo_reqheight(self):
        return 80

    def update_idletasks(self):
        return None

    def wm_overrideredirect(self, _value):
        return None

    def wm_attributes(self, *_args, **_kwargs):
        return None

    def wm_geometry(self, geometry):
        self.geometry = geometry

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
        self.assertGreaterEqual(
            _contrast_ratio(INVALID_ROW_FOREGROUND, "#ffffff"), 4.5
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
                {
                    "<Enter>",
                    "<Leave>",
                    "<FocusIn>",
                    "<FocusOut>",
                    "<Escape>",
                    "<Unmap>",
                    "<Destroy>",
                },
                set(widget.bindings),
            )
            tooltip.show_tip()
            tooltip.show_tip()
            self.assertEqual(1, len(_FakeTipWindow.instances))
            tooltip.hide_tip()
            self.assertIsNone(tooltip.tip_window)
            tooltip.show_tip()
            widget.bindings["<Escape>"][0]()
            self.assertIsNone(tooltip.tip_window)

    def test_tooltip_stays_on_screen_near_bottom_right_edge(self):
        widget = _FakeWidget(root_x=900, root_y=720, width=80, height=24)
        _FakeTipWindow.instances = []
        with patch("gui.tooltip.tk.Toplevel", _FakeTipWindow), patch(
            "gui.tooltip.tk.Label", _FakeLabel
        ):
            tooltip = ToolTip(widget, "help that would otherwise overflow")
            tooltip.show_tip()
            geometry = _FakeTipWindow.instances[-1].geometry
            self.assertIsNotNone(geometry)
            _, xy = geometry.split("+", 1)
            x_text, y_text = xy.split("+", 1)
            x, y = int(x_text), int(y_text)
            self.assertGreaterEqual(x, 8)
            self.assertGreaterEqual(y, 8)
            self.assertLessEqual(x + 200, 1024)
            self.assertLessEqual(y + 80, 768)

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

        entry = _FakeWidget(path=".frame.body.entry")
        entry.winfo_class = lambda: "TEntry"
        before = len(frame.canvas.scroll_calls)
        self.assertIsNone(
            frame._on_keypress(SimpleNamespace(widget=entry, keysym="PageDown"))
        )
        self.assertEqual(len(frame.canvas.scroll_calls), before)

        before_outside = len(frame.canvas.scroll_calls)
        frame._on_mousewheel(SimpleNamespace(x_root=10, y_root=50, delta=120))
        self.assertEqual(len(frame.canvas.scroll_calls), before_outside)
        nested = _FakeWidget(path=".frame.body.text", root_y=110, height=20)
        nested.winfo_class = lambda: "Text"
        before_nested = len(frame.canvas.scroll_calls)
        self.assertIsNone(
            frame._on_mousewheel(
                SimpleNamespace(widget=nested, x_root=10, y_root=110, delta=120)
            )
        )
        self.assertEqual(len(frame.canvas.scroll_calls), before_nested)
        frame.canvas.viewable = False
        self.assertIsNone(
            frame._on_mousewheel(SimpleNamespace(x_root=10, y_root=110, delta=120))
        )
        frame.canvas.viewable = True

        frame._on_focus_in(SimpleNamespace(widget=child))
        self.assertTrue(frame.canvas.move_calls[-1] > 0)
        visible = _FakeWidget(path=".frame.body.visible", root_y=120, height=20)
        before_move = len(frame.canvas.move_calls)
        frame._on_focus_in(SimpleNamespace(widget=visible))
        self.assertEqual(len(frame.canvas.move_calls), before_move)

    def test_accent_button_keeps_theme_label_when_sv_ttk_applied(self):
        import tkinter as tk
        from tkinter import ttk
        from gui.styles import configure_styles

        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            self.skipTest(f"Tk display is unavailable: {exc}")

        try:
            root._ringsentry_sv_ttk = True
            configure_styles(root)
            accent = ttk.Style(root).configure("Accent.TButton") or {}
            self.assertNotEqual(accent.get("foreground"), "#1769aa")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
