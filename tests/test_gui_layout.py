import unittest
from pathlib import Path

try:
    import tkinter as tk
except Exception:  # pragma: no cover - tkinter may be unavailable in some envs
    tk = None


class GuiLayoutTests(unittest.TestCase):
    def setUp(self):
        if tk is None:
            self.skipTest("tkinter is not available")

    def test_scrollable_frame_exposes_body_and_canvas(self):
        from gui.layout import ScrollableFrame

        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            self.skipTest(f"Tk display is unavailable: {exc}")

        try:
            frame = ScrollableFrame(root, padding=12)
            frame.pack(fill="both", expand=True)
            tk.Label(frame.body, text="inside").pack()
            root.update_idletasks()

            self.assertIsNotNone(frame.body)
            self.assertGreaterEqual(frame.canvas.winfo_reqwidth(), 1)
        finally:
            root.destroy()

    def _create_app(self):
        from gui.app import App

        try:
            app = App()
            app.withdraw()
            app.update_idletasks()
            return app
        except tk.TclError as exc:
            self.skipTest(f"Tk display is unavailable: {exc}")

    def _button_texts(self, widget):
        labels = []
        for child in widget.winfo_children():
            if child.winfo_class() == "TButton":
                labels.append(str(child.cget("text")))
            labels.extend(self._button_texts(child))
        return labels

    def _labelframe_texts(self, widget):
        labels = []
        for child in widget.winfo_children():
            if child.winfo_class() == "TLabelframe":
                labels.append(str(child.cget("text")))
            labels.extend(self._labelframe_texts(child))
        return labels

    def _label_texts(self, widget):
        labels = []
        for child in widget.winfo_children():
            if child.winfo_class() == "TLabel":
                labels.append(str(child.cget("text")))
            labels.extend(self._label_texts(child))
        return labels

    def test_main_window_layout_contract(self):
        app = self._create_app()
        try:
            tabs = [
                app.io_tab,
                app.processing_tab,
                app.output_tab,
                app.geometry_tab,
                app.quality_tab,
            ]
            for tab in tabs:
                self.assertTrue(hasattr(tab, "scrollable"))
                self.assertTrue(hasattr(tab, "body"))

            self.assertTrue(hasattr(app.processing_tab, "roi_var"))
            self.assertTrue(hasattr(app.io_tab, "files_entry"))
            self.assertEqual(str(app.io_tab.files_entry.cget("state")), "readonly")
            self.assertTrue(hasattr(app.output_tab, "format_vars"))
            self.assertTrue(hasattr(app.geometry_tab, "bin_factor_var"))
            self.assertTrue(hasattr(app.quality_tab, "result_text"))
            self.assertTrue(hasattr(app.q_calc_tab, "scrollable"))
            self.assertTrue(hasattr(app.q_calc_tab, "body"))
            self.assertTrue(hasattr(app.overexposure_tab, "tab_basic_scroll"))
            self.assertEqual(
                [
                    "文件与输出",
                    "修复规则",
                    "安全与复现",
                    "项目元数据",
                    "日志",
                ],
                [
                    app.overexposure_tab.repair_notebook.tab(i, "text")
                    for i in range(app.overexposure_tab.repair_notebook.index("end"))
                ],
            )

            self.assertLessEqual(int(app.log_panel.log_txt.cget("height")), 5)
            self.assertTrue(hasattr(app.output_tab, "png_controls"))
            self.assertTrue(hasattr(app.output_tab, "lossless_matrix_cb"))

            app.output_tab.format_vars["png"].set(False)
            app.output_tab._sync_png_controls()
            for control in app.output_tab.png_controls:
                self.assertEqual(str(control.cget("state")), "disabled")

            app.output_tab.format_vars["png"].set(True)
            app.output_tab._sync_png_controls()
            for control in app.output_tab.png_controls:
                self.assertNotEqual(str(control.cget("state")), "disabled")

            self.assertLessEqual(
                len(str(app.output_tab.lossless_matrix_cb.cget("text"))),
                32,
            )

            button_texts = set(self._button_texts(app))
            expected_contextual_buttons = {
                "选择输入文件夹",
                "选择输入文件",
                "清空文件列表",
                "选择输出目录",
                "选择暗帧",
                "清空暗帧",
                "管理暗帧",
                "选择平场",
                "清空平场",
                "管理平场",
                "选择掩膜",
                "清空掩膜",
                "单图预览",
                "批量预览",
                "清空 ROI",
                "保存配置",
                "加载配置",
                "只扫描",
                "模拟修复 Dry-run",
                "开始安全修复",
                "停止后续任务",
                "打开输出目录",
                "打开 QC 报告",
                "选择输入文件夹",
                "选择输出文件夹",
            }
            self.assertTrue(
                expected_contextual_buttons.issubset(button_texts),
                expected_contextual_buttons - button_texts,
            )

            section_texts = set(self._labelframe_texts(app.overexposure_tab))
            expected_repair_sections = {
                "输入/输出",
                "批处理行为",
                "像素替换规则",
                "安全与可追溯",
                "项目元数据（写入配置和 QC 报告，不改 CBF 数据）",
            }
            self.assertTrue(
                expected_repair_sections.issubset(section_texts),
                expected_repair_sections - section_texts,
            )

            label_texts = set(self._label_texts(app.overexposure_tab))
            expected_repair_labels = {
                "输入文件夹",
                "输出文件夹",
                "输出后缀",
                "异常值",
                "替换为",
                "强峰阈值",
                "邻域半径/像素",
                "并行 worker 数",
                "项目名称",
                "操作者",
                "样品",
                "线站",
                "探测器",
                "实验日期",
                "备注",
            }
            self.assertTrue(
                expected_repair_labels.issubset(label_texts),
                expected_repair_labels - label_texts,
            )
        finally:
            app.destroy()

    def test_scroll_regions_avoid_global_mousewheel_binding(self):
        checked_files = [
            Path("gui/layout.py"),
            Path("gui/gallery.py"),
            Path("gui/tabs/q_calculator_tab.py"),
        ]
        offenders = {}
        for path in checked_files:
            text = path.read_text(encoding="utf-8")
            if 'bind_all("<MouseWheel>"' in text or 'unbind_all("<MouseWheel>"' in text:
                offenders[str(path)] = "uses global mouse-wheel binding"
            if 'winfo_toplevel().bind("<MouseWheel>"' in text:
                offenders[str(path)] = "binds MouseWheel on the application toplevel"

        self.assertEqual({}, offenders)


if __name__ == "__main__":
    unittest.main()
