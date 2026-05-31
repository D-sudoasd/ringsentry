"""Automatic QC tab.

This panel gives conservative, explainable recommendations. It does not
change preprocessing parameters; users still decide whether to apply them.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from core.loader import load_image_with_info
from core.quality import (
    analyze_image_quality,
    assess_processing_plan,
    format_quality_report,
    quality_summary_line,
)
from core.utils import parse_roi_text
from gui.layout import ScrollableFrame
from gui.tooltip import ToolTip


class QualityTab(ttk.Frame):
    """Automatic quality-control recommendations for input samples."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=0)
        self.app = app
        self.sample_count_var = tk.IntVar(value=5)
        self._create_widgets()

    def _create_widgets(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.scrollable = ScrollableFrame(self, padding=15)
        self.scrollable.grid(row=0, column=0, sticky="nsew")
        self.body = self.scrollable.body
        body = self.body
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        workflow = ttk.LabelFrame(body, text="新手工作流", padding=10)
        workflow.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        workflow.columnconfigure(0, weight=1)
        ttk.Label(
            workflow,
            text="检查样本 -> 预览 -> 确认参数 -> 批处理 -> 查看报告",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            workflow,
            text="本页只给出质控事实、风险解释和参数建议，不会自动修改任何设置。",
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        controls = ttk.LabelFrame(body, text="自动质控推荐", padding=10)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        controls.columnconfigure(4, weight=1)

        ttk.Label(controls, text="抽样文件数:").grid(row=0, column=0, padx=(0, 5))
        sample_spin = ttk.Spinbox(
            controls,
            from_=1,
            to=20,
            textvariable=self.sample_count_var,
            width=6,
        )
        sample_spin.grid(row=0, column=1, padx=(0, 10))
        ToolTip(
            sample_spin,
            "从当前文件列表前部抽样检查。建议先用 3-10 个样本确认尺寸、dtype 和异常值风险。",
        )

        analyze_btn = ttk.Button(
            controls,
            text="分析样本",
            command=self.run_quality_check,
        )
        analyze_btn.grid(row=0, column=2, padx=(0, 10))
        ToolTip(
            analyze_btn,
            "读取样本并报告 shape、dtype、动态范围、NaN/Inf、零值、负值、饱和和疑似热像素。",
        )

        self.status_var = tk.StringVar(value="尚未分析样本。")
        ttk.Label(
            controls,
            textvariable=self.status_var,
            foreground="#555555",
        ).grid(row=0, column=3, columnspan=2, sticky="w")

        result_frame = ttk.LabelFrame(body, text="质控结果", padding=5)
        result_frame.grid(row=2, column=0, sticky="nsew")
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)

        scroll = ttk.Scrollbar(result_frame)
        scroll.grid(row=0, column=1, sticky="ns")
        self.result_text = tk.Text(
            result_frame,
            wrap="word",
            height=18,
            font=("Microsoft YaHei UI", 9),
            yscrollcommand=scroll.set,
        )
        self.result_text.grid(row=0, column=0, sticky="nsew")
        scroll.config(command=self.result_text.yview)

    def _current_plan(self):
        formats = [
            fmt
            for fmt, var in self.app.output_tab.format_vars.items()
            if var.get()
        ]
        roi = parse_roi_text(self.app.processing_tab.roi_var.get())
        return {
            "formats": formats,
            "roi": roi,
            "bin_factor": int(self.app.geometry_tab.bin_factor_var.get() or 1),
            "rotate_deg": self.app.geometry_tab.rotate_var.get(),
        }

    def _set_result_text(self, text):
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.see("1.0")

    def run_quality_check(self):
        """Analyze multiple samples without changing user parameters."""
        self.app.count_files(show_dialog=False)
        if not self.app.filelist:
            messagebox.showwarning(
                "无文件", "请先选择输入文件夹或具体文件。"
            )
            return

        try:
            sample_count = max(1, int(self.sample_count_var.get()))
        except Exception:
            sample_count = 5
            self.sample_count_var.set(sample_count)

        try:
            plan = self._current_plan()
        except Exception as exc:
            messagebox.showerror("参数读取失败", f"当前参数无法解析: {exc}")
            return

        samples = self.app.filelist[:sample_count]
        reports = []
        blocks = [
            "自动质控只给建议，不会自动修改参数。\n",
            f"抽样文件: {len(samples)} / {len(self.app.filelist)}\n",
        ]

        shape_to_files = {}
        for file_path, _ in samples:
            try:
                loaded = load_image_with_info(
                    file_path,
                    self.app.io_tab.h5_path_var.get(),
                )
                report = analyze_image_quality(
                    loaded["data"],
                    metadata=loaded["metadata"],
                    source_name=file_path.name,
                )
                report.findings.extend(assess_processing_plan(report, **plan))
                report.review_required = any(
                    item.level in {"WARNING", "ERROR"}
                    for item in report.findings
                )
                reports.append(report)
                shape_to_files.setdefault(report.shape, []).append(file_path.name)
                blocks.append(format_quality_report(report))
                blocks.append("")
            except Exception as exc:
                blocks.append(f"文件: {file_path.name}")
                blocks.append(f"[ERROR] 无法读取或分析: {exc}")
                blocks.append("")

        if len(shape_to_files) > 1:
            blocks.append("跨样本尺寸检查")
            blocks.append(
                "- [WARNING] 抽样文件尺寸不一致。批处理仍可逐文件运行，"
                "但 dark/flat/mask 和 ROI 必须逐尺寸确认。"
            )
            for shape, names in sorted(shape_to_files.items()):
                preview = ", ".join(names[:3])
                suffix = "" if len(names) <= 3 else f" ... (+{len(names) - 3})"
                blocks.append(f"  shape={shape}: {preview}{suffix}")

        self.app.last_quality_reports = reports
        review_count = sum(1 for report in reports if report.review_required)
        self.status_var.set(
            f"已分析 {len(reports)} 个样本，需要人工复核 {review_count} 个。"
        )
        self._set_result_text("\n".join(blocks).strip())
        for report in reports:
            self.app.log(quality_summary_line(report))
        self.app.log(
            f"自动质控完成: 抽样 {len(reports)} 个，需要人工复核 {review_count} 个"
        )
