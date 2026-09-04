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

    MIN_SAMPLE_COUNT = 1
    MAX_SAMPLE_COUNT = 20
    DEFAULT_SAMPLE_COUNT = 5

    _SUPPORTED_SUGGESTION_KEYS = {
        "hot_pixel_enable",
        "hot_pixel_window",
        "hot_pixel_sigma",
        "pclip_low",
        "pclip_high",
        "formats",
    }
    _SUGGESTION_LABELS = {
        "hot_pixel_enable": "热像素抑制",
        "hot_pixel_window": "热像素窗口",
        "hot_pixel_sigma": "热像素 sigma",
        "pclip_low": "PClip 下限 (%)",
        "pclip_high": "PClip 上限 (%)",
        "formats": "输出格式",
    }

    def __init__(self, parent, app):
        super().__init__(parent, padding=0)
        self.app = app
        self.sample_count_var = tk.IntVar(value=self.DEFAULT_SAMPLE_COUNT)
        self._suggestion_plan = {"changes": [], "notes": []}
        self._create_widgets()

    def _create_widgets(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.scrollable = ScrollableFrame(self, padding=15)
        self.scrollable.grid(row=0, column=0, sticky="nsew")
        self.body = self.scrollable.body
        body = self.body
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

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
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        controls = ttk.LabelFrame(body, text="自动质控推荐", padding=10)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        controls.columnconfigure(4, weight=1)

        ttk.Label(controls, text="抽样文件数:").grid(row=0, column=0, padx=(0, 5))
        sample_spin = ttk.Spinbox(
            controls,
            from_=self.MIN_SAMPLE_COUNT,
            to=self.MAX_SAMPLE_COUNT,
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
            style="Muted.TLabel",
        ).grid(row=0, column=3, columnspan=2, sticky="w")

        suggestion_frame = ttk.LabelFrame(
            body, text="建议变更预览（确认后应用）", padding=5
        )
        suggestion_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        suggestion_frame.columnconfigure(0, weight=1)
        suggestion_frame.rowconfigure(0, weight=1)
        self.suggestion_text = tk.Text(
            suggestion_frame,
            wrap="word",
            height=9,
            font=("Microsoft YaHei UI", 9),
            state="disabled",
            takefocus=True,
            highlightthickness=1,
        )
        self.suggestion_scrollbar = ttk.Scrollbar(
            suggestion_frame,
            orient="vertical",
            command=self.suggestion_text.yview,
            takefocus=False,
        )
        self.suggestion_text.configure(
            yscrollcommand=self.suggestion_scrollbar.set,
        )
        self.suggestion_text.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.suggestion_scrollbar.grid(
            row=0, column=1, sticky="ns", padx=(0, 5)
        )
        self.apply_suggestions_btn = ttk.Button(
            suggestion_frame,
            text="确认并应用支持的建议",
            command=self.apply_suggestions,
            state="disabled",
        )
        self.apply_suggestions_btn.grid(row=0, column=2, sticky="n", padx=5)
        ToolTip(
            self.apply_suggestions_btn,
            "先查看变更前后与依据，再确认应用热像素、PClip 或输出格式建议。",
        )

        result_frame = ttk.LabelFrame(body, text="质控结果", padding=5)
        result_frame.grid(row=3, column=0, sticky="nsew")
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

    @staticmethod
    def _normalise_suggestion_value(key, value):
        if key in {"pclip_low", "pclip_high"}:
            if value in (None, ""):
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
        if key == "hot_pixel_enable":
            return bool(value)
        if key == "hot_pixel_window":
            try:
                return int(value)
            except (TypeError, ValueError):
                return value
        if key == "hot_pixel_sigma":
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
        if key == "formats":
            return [value] if isinstance(value, str) else [str(item) for item in value]
        return value

    @staticmethod
    def _format_suggestion_value(key, value):
        if value in (None, ""):
            return "（空）"
        if key == "hot_pixel_enable":
            return "启用" if value else "停用"
        if key == "formats":
            return ", ".join(value) or "（无）"
        return str(value)

    def _current_suggestion_values(self):
        geometry = self.app.geometry_tab
        def read(name, default):
            variable = getattr(geometry, name, None)
            return default if variable is None else variable.get()

        return {
            "hot_pixel_enable": read("hot_pixel_enable_var", False),
            "hot_pixel_window": read("hot_pixel_window_var", 3),
            "hot_pixel_sigma": read("hot_pixel_sigma_var", 8.0),
            "pclip_low": self._normalise_suggestion_value(
                "pclip_low", read("pclip_low_var", "")
            ),
            "pclip_high": self._normalise_suggestion_value(
                "pclip_high", read("pclip_high_var", "")
            ),
            "formats": [
                fmt for fmt, variable in self.app.output_tab.format_vars.items()
                if variable.get()
            ],
        }

    def _build_suggestion_plan(self, reports):
        """Build a non-mutating, explainable plan from report suggestions."""
        before = self._current_suggestion_values()
        observations = {key: [] for key in self._SUPPORTED_SUGGESTION_KEYS}
        notes = []
        output_keys = set(self.app.output_tab.format_vars)
        for report in reports:
            source = getattr(report, "source_name", "") or "<样本>"
            for suggestion in getattr(report, "suggestions", []) or []:
                action = str(getattr(suggestion, "action", "") or "人工判断")
                reason = str(getattr(suggestion, "reason", "") or "未提供原因")
                recognised = False
                for key, raw_value in (getattr(suggestion, "parameters", {}) or {}).items():
                    if key not in self._SUPPORTED_SUGGESTION_KEYS:
                        continue
                    value = self._normalise_suggestion_value(key, raw_value)
                    if key == "formats":
                        value = [fmt for fmt in value if fmt in output_keys]
                        if not value:
                            continue
                    observations[key].append((value, reason, source))
                    recognised = True
                if not recognised:
                    notes.append(f"人工判断：{action}；依据：{reason}（样本：{source}）")

        changes = []
        for key, entries in observations.items():
            if not entries:
                continue
            current = before[key]
            reasons = list(dict.fromkeys(item[1] for item in entries))
            sources = ", ".join(dict.fromkeys(item[2] for item in entries))
            conflict = False
            if key == "formats":
                recommended = list(dict.fromkeys(
                    fmt for item in entries for fmt in item[0]
                ))
                after = [
                    fmt for fmt in self.app.output_tab.format_vars
                    if fmt in current or fmt in recommended
                ]
                reason = "；".join(reasons)
                if len(entries) > 1:
                    reason = "多个样本建议采用并集并保留当前格式；依据：" + reason
            else:
                proposals = list(dict.fromkeys(item[0] for item in entries))
                if len(proposals) > 1:
                    conflict = True
                    after = None
                    display_after = "冲突：" + " / ".join(
                        self._format_suggestion_value(key, value) for value in proposals
                    )
                    reason = "多个样本建议冲突，保守不自动合并；依据：" + "；".join(reasons)
                else:
                    after = proposals[0]
                    display_after = self._format_suggestion_value(key, after)
            if key == "formats":
                display_after = self._format_suggestion_value(key, after)
            changes.append({
                "parameter": key,
                "before": current,
                "after": after,
                "display_after": display_after,
                "reason": reason,
                "source": sources,
                "conflict": conflict,
                "can_apply": not conflict and current != after,
            })
        return {"changes": changes, "notes": notes}

    def _render_suggestion_plan(self, plan):
        self._suggestion_plan = plan
        lines = [
            "建议变更预览：分析只读取当前配置，不会自动修改设置。",
            "支持确认应用的参数：热像素、PClip、输出格式。", "",
        ]
        if not plan["changes"] and not plan["notes"]:
            lines.append("本次分析没有可用参数建议。")
        for change in plan["changes"]:
            state = (
                "冲突，未自动应用" if change["conflict"]
                else "待确认" if change["can_apply"]
                else "当前值已满足建议"
            )
            key = change["parameter"]
            lines.extend([
                f"[{state}] {self._SUGGESTION_LABELS[key]}",
                f"  变更前：{self._format_suggestion_value(key, change['before'])}",
                f"  变更后：{change['display_after']}",
                f"  依据：{change['reason']}",
                f"  样本：{change['source']}", "",
            ])
        if plan["notes"]:
            lines.append("不直接改参数的质控建议：")
            lines.extend(f"- {note}" for note in plan["notes"])
        self.suggestion_text.config(state="normal")
        self.suggestion_text.delete("1.0", "end")
        self.suggestion_text.insert("1.0", "\n".join(lines).rstrip())
        self.suggestion_text.config(state="disabled")
        self.suggestion_text.see("1.0")
        self.apply_suggestions_btn.config(
            state="normal" if any(item["can_apply"] for item in plan["changes"])
            else "disabled"
        )

    def _update_suggestion_preview(self, reports):
        """Render suggestions without changing processing variables."""
        self._render_suggestion_plan(self._build_suggestion_plan(reports or []))

    def _set_suggestion_value(self, key, value):
        if key == "formats":
            enabled = set(value)
            for fmt, variable in self.app.output_tab.format_vars.items():
                variable.set(fmt in enabled)
            return
        if key in {"pclip_low", "pclip_high"}:
            value = "" if value is None else str(value)
        getattr(self.app.geometry_tab, f"{key}_var").set(value)

    def apply_suggestions(self):
        """Apply only confirmed, supported, non-conflicting suggestions."""
        pending = [item for item in self._suggestion_plan["changes"] if item["can_apply"]]
        if not pending:
            return
        lines = ["将应用以下已预览的参数变更：", ""]
        for item in pending:
            key = item["parameter"]
            lines.append(
                f"- {self._SUGGESTION_LABELS[key]}: "
                f"{self._format_suggestion_value(key, item['before'])} -> "
                f"{item['display_after']}"
            )
        if not messagebox.askyesno("确认质控建议", "\n".join(lines)):
            self.app.log("用户取消应用质控建议；当前参数未改变。")
            return
        current = self._current_suggestion_values()
        applied, skipped = [], []
        for item in pending:
            key = item["parameter"]
            if current[key] != item["before"]:
                skipped.append(key)
                item["conflict"] = True
                item["can_apply"] = False
                item["display_after"] = "未应用：用户已修改当前值"
                continue
            self._set_suggestion_value(key, item["after"])
            item["before"] = item["after"]
            item["can_apply"] = False
            applied.append(key)
        if applied:
            preset_var = getattr(getattr(self.app, "io_tab", None), "workflow_preset_var", None)
            if preset_var is not None and preset_var.get() != "Custom":
                preset_var.set("Custom")
            self.app.log("已确认应用质控建议: " + ", ".join(
                self._SUGGESTION_LABELS[key] for key in applied
            ))
        if skipped:
            self.app.log("质控建议未覆盖用户在预览后修改的参数: " + ", ".join(
                self._SUGGESTION_LABELS[key] for key in skipped
            ))
        self._render_suggestion_plan(self._suggestion_plan)

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

    def _normalise_sample_count(self):
        """Return a safe sample count and explain any manual correction."""
        try:
            raw_value = self.sample_count_var.get()
            sample_count = int(str(raw_value).strip())
        except (TypeError, ValueError, tk.TclError):
            sample_count = self.DEFAULT_SAMPLE_COUNT
            warning = (
                "抽样文件数必须是 1-20 的整数；"
                f"当前输入无效，已回退为 {sample_count}。"
            )
        else:
            warning = None
            if sample_count < self.MIN_SAMPLE_COUNT:
                sample_count = self.MIN_SAMPLE_COUNT
                warning = (
                    "抽样文件数不能小于 1；"
                    f"已调整为 {sample_count}（允许范围：1-20）。"
                )
            elif sample_count > self.MAX_SAMPLE_COUNT:
                sample_count = self.MAX_SAMPLE_COUNT
                warning = (
                    "抽样文件数不能超过 20；"
                    f"已调整为 {sample_count}（允许范围：1-20）。"
                )

        self.sample_count_var.set(sample_count)
        if warning:
            messagebox.showwarning("抽样文件数已调整", warning)
        return sample_count

    def run_quality_check(self):
        """Analyze multiple samples without changing user parameters."""
        self.app.count_files(show_dialog=False)
        if not self.app.filelist:
            self._update_suggestion_preview([])
            messagebox.showwarning(
                "无文件", "请先选择输入文件夹或具体文件。"
            )
            return

        sample_count = self._normalise_sample_count()

        try:
            plan = self._current_plan()
        except Exception as exc:
            self._update_suggestion_preview([])
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
        self._update_suggestion_preview(reports)
        review_count = sum(1 for report in reports if report.review_required)
        failure_count = len(samples) - len(reports)
        if failure_count and not reports:
            self.status_var.set(
                f"质控失败：读取/分析失败 {failure_count} 个样本；"
                "请检查输入文件或 HDF5 路径。"
            )
        elif failure_count:
            self.status_var.set(
                f"已分析 {len(reports)} 个样本，读取/分析失败 {failure_count} 个，"
                f"需要人工复核 {review_count} 个。"
            )
        else:
            self.status_var.set(
                f"已分析 {len(reports)} 个样本，需要人工复核 {review_count} 个。"
            )
        self._set_result_text("\n".join(blocks).strip())
        for report in reports:
            self.app.log(quality_summary_line(report))
        if failure_count:
            self.app.log(
                f"自动质控完成: 成功 {len(reports)} 个，失败 {failure_count} 个，"
                f"需要人工复核 {review_count} 个"
            )
        else:
            self.app.log(
                f"自动质控完成: 抽样 {len(reports)} 个，需要人工复核 {review_count} 个"
            )
