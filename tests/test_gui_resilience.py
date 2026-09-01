import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import tifffile

try:
    import tkinter as tk
    import tkinter.messagebox as messagebox
except Exception:  # pragma: no cover - tkinter may be unavailable in some envs
    tk = None
    messagebox = None


class _StubVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


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

    def test_worker_ui_callback_is_dropped_after_mainloop_exit(self):
        app = self._create_app()
        try:
            def raise_after(*_args, **_kwargs):
                raise RuntimeError("main thread is not in main loop")

            app._mainloop_active = True
            app.after = raise_after

            scheduled = app._schedule_ui_callback(lambda: None)

            self.assertFalse(scheduled)
        finally:
            app.destroy()

    def test_worker_ui_callback_is_dropped_when_mainloop_is_inactive(self):
        app = self._create_app()
        try:
            scheduled = app._schedule_ui_callback(lambda: None)

            self.assertFalse(scheduled)
        finally:
            app.destroy()

    def test_pending_worker_ui_callback_is_cancelled_on_destroy(self):
        app = self._create_app()
        try:
            app._mainloop_active = True
            scheduled = app._schedule_ui_callback(lambda: None)
            self.assertTrue(scheduled)
            self.assertTrue(app._pending_ui_after_ids)

            app.destroy()

            self.assertFalse(app._pending_ui_after_ids)
        finally:
            try:
                app.destroy()
            except tk.TclError:
                pass

    def test_overexposure_poll_timer_is_cancelled_on_destroy(self):
        app = self._create_app()
        try:
            tab = app.overexposure_tab
            self.assertIsNotNone(tab._poll_after_id)

            tab.destroy()

            self.assertIsNone(tab._poll_after_id)
        finally:
            app.destroy()

    def test_conversion_ui_state_skips_overexposure_tab(self):
        app = self._create_app()
        try:
            self.assertEqual(str(app.overexposure_tab.scan_btn.cget("state")), "normal")
            app._set_ui_state(running=True)
            self.assertEqual(str(app.overexposure_tab.scan_btn.cget("state")), "normal")

            app.overexposure_tab.set_running(True)
            app._set_ui_state(running=True)
            self.assertEqual(str(app.overexposure_tab.stop_btn.cget("state")), "normal")
        finally:
            app.overexposure_tab.set_running(False)
            app.destroy()

    def test_overexposure_start_refuses_while_conversion_running(self):
        app = self._create_app()
        try:
            app.is_running = True
            app.overexposure_tab.start("scan")
            self.assertTrue(
                any("批处理" in m["message"] for m in self.messages),
                self.messages,
            )
            self.assertIsNone(app.overexposure_tab.worker)
        finally:
            app.is_running = False
            app.destroy()

    def test_run_conversion_refuses_while_overexposure_worker_is_alive(self):
        app = self._create_app()
        try:
            app.overexposure_tab.worker = type(
                "ActiveWorker", (), {"is_alive": lambda _self: True}
            )()
            app.run_conversion()
            self.assertTrue(
                any("CBF" in m["message"] or "过曝" in m["message"] for m in self.messages),
                self.messages,
            )
            self.assertFalse(app.is_running)
        finally:
            app.overexposure_tab.worker = None
            app.destroy()

    def test_update_config_value_reports_and_reraises(self):
        app = self._create_app()
        try:
            with patch("gui.app.open", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    app._update_config_value("q_calc_custom_presets", {})
            self.assertTrue(
                any(
                    m["kind"] == "error" and "config.json" in m["message"]
                    for m in self.messages
                ),
                self.messages,
            )
        finally:
            app.destroy()

    def test_close_requests_safe_stop_before_destroying_active_cbf_worker(self):
        app = self._create_app()
        try:
            tab = app.overexposure_tab
            tab.worker = type("ActiveWorker", (), {"is_alive": lambda _self: True})()
            stop_calls = []
            tab.stop = lambda: stop_calls.append(True)
            destroy_calls = []
            app.destroy = lambda: destroy_calls.append(True)
            self._orig_messagebox["askyesno"] = messagebox.askyesno
            messagebox.askyesno = lambda *_args, **_kwargs: True

            app._on_close()

            self.assertEqual(stop_calls, [True])
            self.assertEqual(destroy_calls, [])
        finally:
            app.destroy = tk.Tk.destroy.__get__(app, type(app))
            app.destroy()

    def test_overexposure_tab_destroy_sets_cancel_event_for_active_worker(self):
        app = self._create_app()
        try:
            tab = app.overexposure_tab
            tab.worker = type("ActiveWorker", (), {"is_alive": lambda _self: True})()

            tab.destroy()

            self.assertTrue(tab.cancel_event.is_set())
        finally:
            app.destroy()

    def test_output_tab_has_png_options_default_off(self):
        with tempfile.TemporaryDirectory(prefix="gui_default_config_") as tmp:
            config_path = str(Path(tmp) / "config.json")
            with patch("gui.app.CONFIG_FILE", config_path):
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

    def test_preview_applies_selected_workflow_preset_before_rendering(self):
        from gui.app import App

        app = SimpleNamespace(
            io_tab=SimpleNamespace(workflow_preset_var=_StubVar("SAXS Quick")),
            processing_tab=SimpleNamespace(
                clip_negative_var=_StubVar(True),
                mask_nonzero_is_invalid_var=_StubVar(False),
                bg_offset_var=_StubVar(17.0),
                min_intensity_var=_StubVar("5"),
                max_intensity_var=_StubVar("9"),
            ),
            geometry_tab=SimpleNamespace(
                rotate_var=_StubVar("90"),
                flip_x_var=_StubVar(True),
                flip_y_var=_StubVar(True),
                bin_factor_var=_StubVar(4),
                norm_mode_var=_StubVar("max"),
                pclip_low_var=_StubVar("1"),
                pclip_high_var=_StubVar("99"),
                intensity_transform_var=_StubVar("log1p"),
                gamma_var=_StubVar(0.5),
                hot_pixel_enable_var=_StubVar(True),
                hot_pixel_window_var=_StubVar(5),
                hot_pixel_sigma_var=_StubVar(3.0),
            ),
            output_tab=SimpleNamespace(
                format_vars={
                    name: _StubVar(name == "csv")
                    for name in ("tif", "npy", "csv", "dat", "xycsv", "xydat")
                },
                xy_skip_zeros=_StubVar(False),
                xy_zero_tol=_StubVar(2.0),
            ),
            log=lambda _message: None,
        )
        app._apply_workflow_preset = lambda: App._apply_workflow_preset(app)

        with patch("gui.app.show_preview") as render_preview:
            App.preview_image(app)

        render_preview.assert_called_once_with(app)
        self.assertEqual(app.processing_tab.bg_offset_var.get(), 0.0)
        self.assertEqual(app.processing_tab.min_intensity_var.get(), "")
        self.assertEqual(app.processing_tab.max_intensity_var.get(), "")
        self.assertEqual(app.geometry_tab.rotate_var.get(), "0")
        self.assertFalse(app.geometry_tab.flip_x_var.get())
        self.assertTrue(app.output_tab.format_vars["tif"].get())
        self.assertTrue(app.output_tab.format_vars["npy"].get())
        self.assertFalse(app.output_tab.format_vars["csv"].get())

    def test_preview_rejects_invalid_png_options_before_rendering(self):
        from gui.preview import show_preview

        app = SimpleNamespace(
            filelist=[(Path("sample.tif"), Path("sample.tif"))],
            output_tab=SimpleNamespace(
                format_vars={"png": _StubVar(True)},
                png_scale_var=_StubVar("linear"),
                png_min_var=_StubVar(""),
                png_max_var=_StubVar("100"),
                png_colormap_var=_StubVar("viridis"),
                png_dpi_var=_StubVar(300),
            ),
        )

        with patch("gui.preview._lazy_import_matplotlib") as lazy_import:
            show_preview(app)

        lazy_import.assert_not_called()
        self.assertTrue(
            any(
                m["kind"] == "error"
                and m["title"] == "设置无效"
                and "PNG I Min" in m["message"]
                for m in self.messages
            ),
            self.messages,
        )

    def test_preview_rejects_invalid_or_out_of_bounds_roi(self):
        from gui.preview import show_preview

        for roi_text in ("1,2,3", "-1,0,2,2", "8,8,3,3"):
            with self.subTest(roi=roi_text):
                self.messages.clear()
                app = SimpleNamespace(
                    filelist=[(Path("sample.tif"), Path("sample.tif"))],
                    io_tab=SimpleNamespace(h5_path_var=_StubVar("")),
                    output_tab=SimpleNamespace(
                        format_vars={"png": _StubVar(False)},
                    ),
                    processing_tab=SimpleNamespace(roi_var=_StubVar(roi_text)),
                )
                with patch(
                    "gui.preview.load_image",
                    return_value=np.zeros((10, 10), dtype=np.float32),
                ):
                    with patch(
                        "gui.preview._lazy_import_matplotlib"
                    ) as lazy_import:
                        with patch("gui.preview.apply_matplotlib_style"):
                            show_preview(app)

                lazy_import.assert_not_called()
                self.assertTrue(
                    any(
                        m["kind"] == "error"
                        and m["title"] == "设置无效"
                        and "ROI" in m["message"]
                        for m in self.messages
                    ),
                    self.messages,
                )
                self.assertFalse(
                    any(m["kind"] == "warning" for m in self.messages),
                    self.messages,
                )

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
                    app.output_tab.png_dpi_var.set(600)
                    app.output_tab.plot_export_preset_var.set("Publication")
                    app._save_config_impl()
                finally:
                    app.destroy()

                app2 = self._create_app()
                try:
                    self.assertTrue(app2.output_tab.format_vars["png"].get())
                    self.assertEqual(app2.output_tab.png_scale_var.get(), "log")
                    self.assertEqual(app2.output_tab.png_min_var.get(), "-5")
                    self.assertEqual(app2.output_tab.png_max_var.get(), "500")
                    self.assertEqual(app2.output_tab.png_dpi_var.get(), 600)
                    self.assertEqual(
                        app2.output_tab.plot_export_preset_var.get(),
                        "Publication",
                    )
                finally:
                    app2.destroy()

    def test_roi_drag_helper_uses_top_left_array_coordinates(self):
        from gui.preview import _roi_from_drag_points

        roi = _roi_from_drag_points((8.8, 2.2), (3.1, 6.9))

        self.assertEqual(roi, (3, 2, 5, 4))

    def test_preview_final_array_matches_full_batch_pipeline(self):
        from core.processing import apply_processing
        from gui.preview import _preview_processing_arrays

        arr = np.arange(1, 25, dtype=np.float32).reshape(4, 6)
        options = {
            "roi": (1, 0, 4, 4),
            "bg_offset": 2.0,
            "clip_negative": True,
            "pclip_low": 10.0,
            "pclip_high": 90.0,
            "rotate_deg": "90",
            "flip_x": True,
            "bin_factor": 2,
            "intensity_transform": "log1p",
            "gamma": 0.8,
            "norm_mode": "minmax",
        }

        coordinate, final = _preview_processing_arrays(arr, **options)
        expected = apply_processing(arr, **options)
        expected_coordinate = apply_processing(
            arr,
            bg_offset=2.0,
            clip_negative=True,
            rotate_deg="0",
            flip_x=False,
            flip_y=False,
            bin_factor=1,
        )

        self.assertEqual(coordinate.shape, arr.shape)
        self.assertNotEqual(
            arr.shape, apply_processing(arr, rotate_deg="90").shape
        )
        np.testing.assert_array_equal(coordinate, expected_coordinate)
        np.testing.assert_array_equal(final, expected)
        self.assertEqual(final.shape, (2, 2))

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
