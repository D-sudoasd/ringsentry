import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class PreviewGalleryRegressionTests(unittest.TestCase):
    def test_gallery_wheel_units_cover_trackpads_and_linux_buttons(self):
        from gui.gallery import _wheel_scroll_units

        self.assertEqual(_wheel_scroll_units(SimpleNamespace(delta=1)), -1)
        self.assertEqual(_wheel_scroll_units(SimpleNamespace(delta=-1)), 1)
        self.assertEqual(
            _wheel_scroll_units(SimpleNamespace(delta=0, num=4)), -1
        )
        self.assertEqual(
            _wheel_scroll_units(SimpleNamespace(delta=0, num=5)), 1
        )

    def test_gallery_thumbnail_is_keyboard_focusable_and_opens_same_file(self):
        from gui.gallery import _bind_preview_activation

        class FakeWidget:
            def __init__(self):
                self.options = {}
                self.bindings = {}

            def configure(self, **kwargs):
                self.options.update(kwargs)

            def bind(self, sequence, callback, add=None):
                self.bindings[sequence] = (callback, add)

        app = object()
        file_path = Path("sample.tif")
        widget = FakeWidget()

        with patch("gui.gallery._open_full_preview") as open_preview:
            _bind_preview_activation(widget, app, file_path)
            result = widget.bindings["<Return>"][0](None)

        self.assertTrue(widget.options["takefocus"])
        self.assertIn("<Button-1>", widget.bindings)
        self.assertIn("<space>", widget.bindings)
        self.assertEqual(result, "break")
        open_preview.assert_called_once_with(app, file_path)

    def test_line_profile_axes_are_replaced_after_redraw(self):
        from gui.preview import _register_line_profile_axes

        old_raw = object()
        old_processed = object()
        new_raw = object()
        new_processed = object()
        axes = [old_raw, old_processed]

        _register_line_profile_axes(axes, new_raw, new_processed)

        self.assertEqual(axes, [new_raw, new_processed])

    def test_explicit_preview_target_wins_over_filelist(self):
        from gui.preview import _resolve_preview_target

        first = Path("first.tif")
        second = Path("second.tif")
        app = SimpleNamespace(filelist=[(first, first)])

        self.assertEqual(_resolve_preview_target(app, second), second)

    def test_public_preview_loads_explicit_target(self):
        from gui.preview import show_preview

        first = Path("first.tif")
        second = Path("second.tif")
        app = SimpleNamespace(
            filelist=[(first, first)],
            io_tab=SimpleNamespace(h5_path_var=_Var("/entry/data/data")),
            output_tab=SimpleNamespace(format_vars={"png": _Var(False)}),
            processing_tab=SimpleNamespace(roi_var=_Var("99,99,2,2")),
        )

        with patch(
            "gui.preview.load_image",
            return_value=np.zeros((10, 10), dtype=np.float32),
        ) as load_image:
            with patch("gui.preview.messagebox.showerror"):
                show_preview(app, target_file=second)

        load_image.assert_called_once_with(second, "/entry/data/data")

    def test_gallery_open_full_preview_passes_target_without_mutating_filelist(self):
        from gui.gallery import _open_full_preview

        first = Path("first.tif")
        second = Path("second.tif")
        app = SimpleNamespace(filelist=[(first, first)])

        with patch("gui.preview.show_preview") as show_preview:
            _open_full_preview(app, second)

        show_preview.assert_called_once_with(app, target_file=second)
        self.assertEqual(app.filelist, [(first, first)])

    def test_thumbnail_dimensions_preserve_aspect_ratio(self):
        from gui.gallery import _thumbnail_dimensions

        self.assertEqual(_thumbnail_dimensions((100, 200), 64), (64, 32))
        self.assertEqual(_thumbnail_dimensions((200, 100), 64), (32, 64))
        self.assertEqual(_thumbnail_dimensions((64, 64), 64), (64, 64))

    def test_gallery_refresh_uses_each_generation_queue_without_losing_results(self):
        """A stale poll must not consume the next refresh's result."""
        import gui.gallery as gallery

        windows = []
        buttons = []
        labels = []
        threads = []

        class FakeVar:
            def __init__(self, value=None):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class FakeWidget:
            def __init__(self, master=None, **kwargs):
                self.master = master
                self.children = []
                self.options = dict(kwargs)
                self.bindings = {}
                if hasattr(master, "children"):
                    master.children.append(self)

            def bind(self, sequence, callback, add=None):
                self.bindings[sequence] = (callback, add)

            def configure(self, **kwargs):
                self.options.update(kwargs)

            config = configure

            def create_window(self, *args, **kwargs):
                return 1

            def destroy(self):
                if self.master is not None and hasattr(self.master, "children"):
                    if self in self.master.children:
                        self.master.children.remove(self)

            def grid(self, **kwargs):
                return None

            def pack(self, **kwargs):
                return None

            def winfo_children(self):
                return list(self.children)

            def itemconfig(self, *args, **kwargs):
                return None

            def yview(self, *args, **kwargs):
                return None

            def yview_scroll(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return None

            def winfo_rootx(self):
                return 0

            def winfo_rooty(self):
                return 0

            def winfo_width(self):
                return 1000

            def winfo_height(self):
                return 800

        class FakeWindow(FakeWidget):
            def __init__(self, master=None, **kwargs):
                super().__init__(master, **kwargs)
                self.after_calls = []
                self.protocols = {}
                self.exists = True
                windows.append(self)

            def title(self, value):
                self.window_title = value

            def protocol(self, name, callback):
                self.protocols[name] = callback

            def after(self, delay, callback):
                self.after_calls.append((delay, callback))
                return callback

            def winfo_exists(self):
                return int(self.exists)

        class FakeLabel(FakeWidget):
            def __init__(self, master=None, **kwargs):
                super().__init__(master, **kwargs)
                self.text = kwargs.get("text")
                labels.append(self)

        class FakeButton(FakeWidget):
            def __init__(self, master=None, **kwargs):
                super().__init__(master, **kwargs)
                self.command = kwargs.get("command")
                buttons.append(self)

        class FakeThread:
            def __init__(self, target, daemon=None):
                self.target = target
                self.alive = True
                threads.append(self)

            def start(self):
                return None

            def is_alive(self):
                return self.alive

        app = SimpleNamespace(
            filelist=[(Path("old.cbf"), Path("old.cbf"))],
            io_tab=SimpleNamespace(h5_path_var=FakeVar("/entry/data/data")),
        )

        fake_canvas = type("FakeCanvas", (FakeWidget,), {})
        fake_tk = {
            "Toplevel": FakeWindow,
            "IntVar": FakeVar,
            "StringVar": FakeVar,
            "Canvas": fake_canvas,
        }
        fake_ttk = {
            "Frame": FakeWidget,
            "Label": FakeLabel,
            "Spinbox": FakeWidget,
            "Button": FakeButton,
            "Scrollbar": FakeWidget,
        }

        with patch.object(gallery.tk, "Toplevel", fake_tk["Toplevel"]), \
                patch.object(gallery.tk, "IntVar", fake_tk["IntVar"]), \
                patch.object(gallery.tk, "StringVar", fake_tk["StringVar"]), \
                patch.object(gallery.tk, "Canvas", fake_tk["Canvas"]), \
                patch.object(gallery.ttk, "Frame", fake_ttk["Frame"]), \
                patch.object(gallery.ttk, "Label", fake_ttk["Label"]), \
                patch.object(gallery.ttk, "Spinbox", fake_ttk["Spinbox"]), \
                patch.object(gallery.ttk, "Button", fake_ttk["Button"]), \
                patch.object(gallery.ttk, "Scrollbar", fake_ttk["Scrollbar"]), \
                patch.object(gallery, "fit_window_to_screen"), \
                patch.object(gallery, "apply_matplotlib_style"), \
                patch.object(gallery, "load_image", side_effect=RuntimeError("load")), \
                patch.object(gallery.threading, "Thread", FakeThread), \
                patch.object(gallery, "_lazy_import_matplotlib", return_value=(object, object)):
            gallery.show_gallery(app)

            self.assertEqual(len(threads), 1)
            first_poll = windows[0].after_calls[0][1]
            buttons[0].command()
            self.assertEqual(len(threads), 2)
            second_poll = windows[0].after_calls[-1][1]

            # Finish only the new worker.  Run the old callback first, exactly
            # the ordering that used to drain and discard the new result.
            threads[1].target()
            threads[1].alive = False
            first_poll()
            second_poll()

        self.assertEqual([label.text for label in labels].count("加载失败"), 1)


if __name__ == "__main__":
    unittest.main()
