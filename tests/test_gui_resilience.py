import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import tifffile

try:
    import tkinter as tk
    import tkinter.messagebox as messagebox
except Exception:  # pragma: no cover - tkinter may be unavailable in some envs
    tk = None
    messagebox = None


class GuiResilienceTests(unittest.TestCase):
    def setUp(self):
        if tk is None:
            self.skipTest("tkinter is not available")
        self.messages = []
        self._orig_messagebox = {
            "showwarning": messagebox.showwarning,
            "showerror": messagebox.showerror,
            "showinfo": messagebox.showinfo,
            "askyesno": messagebox.askyesno,
        }

        def record(kind):
            def _inner(title, message, *args, **kwargs):
                self.messages.append(
                    {
                        "kind": kind,
                        "title": str(title),
                        "message": str(message),
                    }
                )
                return False if kind == "askyesno" else None

            return _inner

        messagebox.showwarning = record("warning")
        messagebox.showerror = record("error")
        messagebox.showinfo = record("info")
        messagebox.askyesno = record("askyesno")

    def tearDown(self):
        if messagebox is not None and hasattr(self, "_orig_messagebox"):
            for name, func in self._orig_messagebox.items():
                setattr(messagebox, name, func)

    def _create_app(self):
        from gui.app import App

        try:
            app = App()
            app.withdraw()
            app.update()
            return app
        except tk.TclError as exc:
            self.skipTest(f"Tk display is unavailable: {exc}")

    @staticmethod
    def _write_sample_tiff(root: Path):
        src_dir = root / "输入 数据"
        out_dir = root / "输出 结果"
        src_dir.mkdir()
        source = src_dir / "样品 01.tif"
        arr = np.arange(1, 101, dtype=np.float32).reshape(10, 10)
        tifffile.imwrite(source, arr)
        return source, out_dir, arr

    def _configure_single_file_run(self, app, source: Path, out_dir: Path):
        app.io_tab.input_mode_var.set("files")
        app.selected_files = [str(source)]
        app.io_tab._update_selected_files_summary()
        app.io_tab.outdir_var.set(str(out_dir))
        for var in app.output_tab.format_vars.values():
            var.set(False)
        app.output_tab.format_vars["npy"].set(True)
        app.output_tab.format_vars["xycsv"].set(True)
        app.output_tab.xy_skip_zeros.set(False)
        app.processing_tab.roi_var.set("")

    def _run_mainloop_until_conversion_finishes(self, app, timeout_s=8.0):
        deadline = time.time() + timeout_s
        state = {"timeout": False}

        def poll():
            if app.start_time and app.thread_pool is None and app.done_count >= len(app.filelist):
                app.quit()
                return
            if time.time() > deadline:
                state["timeout"] = True
                app.quit()
                return
            app.after(50, poll)

        app.after(100, app.run_conversion)
        app.after(150, poll)
        app.mainloop()
        return state["timeout"]

    def test_conversion_worker_uses_thread_count_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="gui_snapshot_") as tmp:
            source, out_dir, arr = self._write_sample_tiff(Path(tmp))
            app = self._create_app()
            try:
                self._configure_single_file_run(app, source, out_dir)
                calls = {"n": 0}

                def get_once():
                    calls["n"] += 1
                    if calls["n"] > 1:
                        raise RuntimeError("worker read Tk variable instead of snapshot")
                    return 1

                app.log_panel.max_thr_var.get = get_once
                timed_out = self._run_mainloop_until_conversion_finishes(app)

                self.assertFalse(timed_out)
                self.assertEqual(app.done_count, 1)
                self.assertEqual(calls["n"], 1)
                npy = out_dir / "npy" / "样品 01.npy"
                self.assertTrue(npy.exists())
                self.assertTrue(np.array_equal(np.load(npy), arr))
            finally:
                app.destroy()

    def test_invalid_xy_zero_tolerance_is_reported_without_callback_crash(self):
        with tempfile.TemporaryDirectory(prefix="gui_bad_xy_tol_") as tmp:
            source, out_dir, _arr = self._write_sample_tiff(Path(tmp))
            app = self._create_app()
            try:
                self._configure_single_file_run(app, source, out_dir)
                app.output_tab.xy_zero_tol.set("not-a-number")

                app.run_conversion()

                self.assertTrue(
                    any(m["kind"] == "error" and "零值容差" in m["message"] for m in self.messages),
                    self.messages,
                )
                self.assertEqual(app.done_count, 0)
            finally:
                app.destroy()

    def test_output_tab_has_png_options_default_off(self):
        app = self._create_app()
        try:
            self.assertIn("png", app.output_tab.format_vars)
            self.assertFalse(app.output_tab.format_vars["png"].get())
            self.assertEqual(app.output_tab.png_scale_var.get(), "linear")
            self.assertEqual(app.output_tab.png_min_var.get(), "")
            self.assertEqual(app.output_tab.png_max_var.get(), "")
        finally:
            app.destroy()

    def test_png_requires_fixed_display_range_before_conversion(self):
        with tempfile.TemporaryDirectory(prefix="gui_bad_png_range_") as tmp:
            source, out_dir, _arr = self._write_sample_tiff(Path(tmp))
            app = self._create_app()
            try:
                self._configure_single_file_run(app, source, out_dir)
                for var in app.output_tab.format_vars.values():
                    var.set(False)
                app.output_tab.format_vars["png"].set(True)
                app.output_tab.png_min_var.set("")
                app.output_tab.png_max_var.set("100")

                app.run_conversion()

                self.assertTrue(
                    any(m["kind"] == "error" and "PNG I Min" in m["message"] for m in self.messages),
                    self.messages,
                )
                self.assertEqual(app.done_count, 0)
                self.assertFalse(app.is_running)
            finally:
                app.destroy()

    def test_png_options_are_saved_and_loaded_from_config(self):
        with tempfile.TemporaryDirectory(prefix="gui_png_config_") as tmp:
            config_path = str(Path(tmp) / "config.json")
            with patch("gui.app.CONFIG_FILE", config_path):
                app = self._create_app()
                try:
                    app.output_tab.format_vars["png"].set(True)
                    app.output_tab.png_scale_var.set("log")
                    app.output_tab.png_min_var.set("-5")
                    app.output_tab.png_max_var.set("500")
                    app._save_config_impl()
                finally:
                    app.destroy()

                app2 = self._create_app()
                try:
                    self.assertTrue(app2.output_tab.format_vars["png"].get())
                    self.assertEqual(app2.output_tab.png_scale_var.get(), "log")
                    self.assertEqual(app2.output_tab.png_min_var.get(), "-5")
                    self.assertEqual(app2.output_tab.png_max_var.get(), "500")
                finally:
                    app2.destroy()

    def test_roi_drag_helper_uses_top_left_array_coordinates(self):
        from gui.preview import _roi_from_drag_points

        roi = _roi_from_drag_points((8.8, 2.2), (3.1, 6.9))

        self.assertEqual(roi, (3, 2, 5, 4))

    def test_overexposure_numeric_validation_uses_field_labels(self):
        with tempfile.TemporaryDirectory(prefix="gui_zero2sat_bad_input_") as tmp:
            root = Path(tmp)
            (root / "input").mkdir()
            app = self._create_app()
            try:
                tab = app.overexposure_tab
                tab.input_dir.set(str(root / "input"))
                tab.output_dir.set(str(root / "out"))
                tab.zero_value.set("abc")

                with self.assertRaises(ValueError) as cm:
                    tab.build_config()

                text = str(cm.exception)
                self.assertIn("异常值", text)
                self.assertIn("整数", text)
                self.assertNotIn("invalid literal", text)
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
