import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gui.tabs.io_tab import IOTab
from gui.tabs.quality_tab import QualityTab


class _Var:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Text:
    def __init__(self):
        self.value = ""

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value += value

    def see(self, *_args):
        pass

    def config(self, **kwargs):
        self.state = kwargs.get("state", getattr(self, "state", "normal"))


class _Button:
    def __init__(self):
        self.state = "normal"

    def config(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]


class QualityWorkflowUXTests(unittest.TestCase):
    def _io_tab(self, app):
        tab = IOTab.__new__(IOTab)
        tab.app = app
        tab.dir_var = _Var("")
        tab.outdir_var = _Var("")
        tab.input_mode_var = _Var("directory")
        tab.selected_files_var = _Var("无")
        tab.workflow_preset_var = _Var("Custom")
        return tab

    def test_selecting_input_directory_shows_default_output_without_overwriting_custom(self):
        app = SimpleNamespace(log=lambda _message: None)
        tab = self._io_tab(app)
        with patch(
            "gui.tabs.io_tab.filedialog.askdirectory",
            return_value="E:/data/sample",
        ):
            tab._select_dir()

        self.assertEqual(tab.outdir_var.get().replace("\\", "/"), "E:/data/sample/_converted")

        tab.outdir_var.set("E:/my-custom-output")
        with patch(
            "gui.tabs.io_tab.filedialog.askdirectory",
            return_value="E:/data/other",
        ):
            tab._select_dir()
        self.assertEqual(tab.outdir_var.get(), "E:/my-custom-output")

    def test_selecting_workflow_preset_applies_immediately_and_logs(self):
        messages = []
        calls = []
        app = SimpleNamespace(
            log=messages.append,
            _apply_workflow_preset=lambda: calls.append("applied"),
        )
        tab = self._io_tab(app)
        tab.workflow_preset_var.set("SAXS Quick")

        tab._on_workflow_preset_selected()

        self.assertEqual(calls, ["applied"])
        self.assertTrue(any("SAXS Quick" in message for message in messages))

    def _quality_tab_stub(self, app):
        tab = QualityTab.__new__(QualityTab)
        tab.app = app
        tab.sample_count_var = _Var(5)
        tab.status_var = _Var("尚未分析样本。")
        tab.result_text = _Text()
        tab.suggestion_text = _Text()
        tab.apply_suggestions_btn = _Button()
        tab._suggestion_plan = {"changes": [], "notes": []}
        return tab

    def _quality_app(self):
        return SimpleNamespace(
            filelist=[(Path("bad-1.tif"), Path("bad-1.tif")),
                      (Path("bad-2.tif"), Path("bad-2.tif"))],
            count_files=lambda show_dialog=False: None,
            io_tab=SimpleNamespace(h5_path_var=_Var("/entry/data/data")),
            output_tab=SimpleNamespace(
                format_vars={"tif": _Var(True)},
            ),
            processing_tab=SimpleNamespace(roi_var=_Var("")),
            geometry_tab=SimpleNamespace(
                bin_factor_var=_Var(1), rotate_var=_Var("0"),
            ),
            log=lambda _message: None,
            last_quality_reports=[],
        )

    def test_all_sample_read_failures_report_failure_count_without_review_zero(self):
        app = self._quality_app()
        tab = self._quality_tab_stub(app)
        with patch(
            "gui.tabs.quality_tab.load_image_with_info",
            side_effect=OSError("corrupt input"),
        ), patch("gui.tabs.quality_tab.messagebox.showwarning"):
            tab.run_quality_check()

        self.assertIn("失败 2 个", tab.status_var.get())
        self.assertNotIn("需复核 0", tab.status_var.get())
        self.assertEqual(tab.apply_suggestions_btn.state, "disabled")

    def test_sample_count_is_capped_at_twenty_and_warns(self):
        app = self._quality_app()
        app.filelist = [
            (Path(f"sample-{index}.tif"), Path(f"sample-{index}.tif"))
            for index in range(25)
        ]
        tab = self._quality_tab_stub(app)
        tab.sample_count_var.set("999")
        with patch(
            "gui.tabs.quality_tab.load_image_with_info",
            side_effect=OSError("corrupt input"),
        ), patch(
            "gui.tabs.quality_tab.messagebox.showwarning"
        ) as showwarning:
            tab.run_quality_check()

        self.assertEqual(tab.sample_count_var.get(), 20)
        self.assertEqual(showwarning.call_count, 1)
        self.assertIn("20", showwarning.call_args.args[1])
        self.assertIn("失败 20 个", tab.status_var.get())

    def test_invalid_sample_count_falls_back_and_warns(self):
        app = self._quality_app()
        tab = self._quality_tab_stub(app)
        tab.sample_count_var.set("not-a-number")
        with patch(
            "gui.tabs.quality_tab.load_image_with_info",
            side_effect=OSError("corrupt input"),
        ), patch(
            "gui.tabs.quality_tab.messagebox.showwarning"
        ) as showwarning:
            tab.run_quality_check()

        self.assertEqual(tab.sample_count_var.get(), QualityTab.DEFAULT_SAMPLE_COUNT)
        self.assertEqual(showwarning.call_count, 1)
        self.assertIn("回退", showwarning.call_args.args[1])
        self.assertIn("失败 2 个", tab.status_var.get())

    def test_suggestion_preview_is_non_mutating_and_applies_only_after_confirmation(self):
        app = SimpleNamespace(
            geometry_tab=SimpleNamespace(
                hot_pixel_enable_var=_Var(False),
                hot_pixel_window_var=_Var(5),
                hot_pixel_sigma_var=_Var(3.0),
                pclip_low_var=_Var(""),
                pclip_high_var=_Var(""),
            ),
            output_tab=SimpleNamespace(
                format_vars={"edf": _Var(False), "tif": _Var(True), "npy": _Var(False)},
            ),
            io_tab=SimpleNamespace(workflow_preset_var=_Var("Custom")),
            log=lambda _message: None,
        )
        tab = self._quality_tab_stub(app)
        report = SimpleNamespace(
            source_name="sample.cbf",
            suggestions=[
                SimpleNamespace(
                    action="建议启用热像素抑制。",
                    reason="极端亮点超过稳健阈值。",
                    parameters={"hot_pixel_enable": True, "hot_pixel_window": 3,
                                "hot_pixel_sigma": 8.0},
                ),
                SimpleNamespace(
                    action="建议保留原始矩阵格式。",
                    reason="CBF dtype 需要保真导出。",
                    parameters={"formats": ["edf", "npy"]},
                ),
                SimpleNamespace(
                    action="建议预览百分位裁剪。",
                    reason="p99 与中位数差异较大。",
                    parameters={"pclip_low": 1.0, "pclip_high": 99.0},
                ),
            ],
        )
        before = {
            "hot": app.geometry_tab.hot_pixel_enable_var.get(),
            "window": app.geometry_tab.hot_pixel_window_var.get(),
            "formats": [key for key, var in app.output_tab.format_vars.items() if var.get()],
        }

        tab._update_suggestion_preview([report])

        self.assertEqual(app.geometry_tab.hot_pixel_enable_var.get(), before["hot"])
        self.assertEqual(app.geometry_tab.hot_pixel_window_var.get(), before["window"])
        self.assertEqual(
            [key for key, var in app.output_tab.format_vars.items() if var.get()],
            before["formats"],
        )
        self.assertIn("变更前", tab.suggestion_text.value)
        self.assertIn("依据", tab.suggestion_text.value)
        self.assertIn("PClip", tab.suggestion_text.value)
        self.assertEqual(tab.apply_suggestions_btn.state, "normal")

        with patch("gui.tabs.quality_tab.messagebox.askyesno", return_value=False):
            tab.apply_suggestions()
        self.assertFalse(app.geometry_tab.hot_pixel_enable_var.get())

        with patch("gui.tabs.quality_tab.messagebox.askyesno", return_value=True):
            tab.apply_suggestions()
        self.assertTrue(app.geometry_tab.hot_pixel_enable_var.get())
        self.assertEqual(app.geometry_tab.hot_pixel_window_var.get(), 3)
        self.assertEqual(app.geometry_tab.hot_pixel_sigma_var.get(), 8.0)
        self.assertEqual(app.geometry_tab.pclip_low_var.get(), "1.0")
        self.assertEqual(app.geometry_tab.pclip_high_var.get(), "99.0")
        self.assertTrue(app.output_tab.format_vars["edf"].get())
        self.assertTrue(app.output_tab.format_vars["npy"].get())

    def test_conflicting_scalar_suggestions_are_shown_but_not_applied(self):
        app = SimpleNamespace(
            geometry_tab=SimpleNamespace(
                hot_pixel_enable_var=_Var(False),
                hot_pixel_window_var=_Var(3),
                hot_pixel_sigma_var=_Var(8.0),
                pclip_low_var=_Var(""),
                pclip_high_var=_Var(""),
            ),
            output_tab=SimpleNamespace(format_vars={"tif": _Var(True)}),
            log=lambda _message: None,
        )
        tab = self._quality_tab_stub(app)
        reports = [
            SimpleNamespace(source_name="a.tif", suggestions=[SimpleNamespace(
                action="A", reason="first", parameters={"pclip_low": 1.0}
            )]),
            SimpleNamespace(source_name="b.tif", suggestions=[SimpleNamespace(
                action="B", reason="second", parameters={"pclip_low": 5.0}
            )]),
        ]

        tab._update_suggestion_preview(reports)

        self.assertIn("冲突", tab.suggestion_text.value)
        self.assertEqual(tab.apply_suggestions_btn.state, "disabled")
        self.assertEqual(app.geometry_tab.pclip_low_var.get(), "")


if __name__ == "__main__":
    unittest.main()
