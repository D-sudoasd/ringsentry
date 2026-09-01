"""RingSentry tab for the CBF Zero2Sat overexposure-repair component."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Optional, Union

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.constants import APP_VERSION as RINGSENTRY_APP_VERSION
from gui.tooltip import ToolTip

try:
    import fabio  # noqa: F401
    import numpy as np  # noqa: F401

    from core.overexposure_repair import (
        COMPONENT_NAME,
        SOFTWARE_NAME,
        SOFTWARE_VERSION,
        ProcessConfig,
        ProjectMetadata,
        config_to_dict,
        load_config_json,
        run_batch,
    )
except Exception as exc:
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


APP_TITLE = (
    f"{SOFTWARE_NAME} v{SOFTWARE_VERSION} — {COMPONENT_NAME}"
    if IMPORT_ERROR is None
    else f"RingSentry {RINGSENTRY_APP_VERSION} — CBF Zero2Sat 过曝修复"
)


class OverexposureRepairTab(ttk.Frame):
    """Notebook tab for guarded CBF exceptional-value replacement."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self.queue = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.cancel_requested = False
        self.cancel_event = threading.Event()
        self.last_output_dir: Optional[Path] = None
        self.last_html_report: Optional[str] = None
        self.last_csv: Optional[str] = None
        self._poll_after_id = None
        self._vars()
        self._layout()
        self._check_imports()
        self._poll_after_id = self.after(100, self._poll)

    def _vars(self):
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()

        self.recursive = tk.BooleanVar(value=True)
        self.skip_output_dir = tk.BooleanVar(value=True)
        self.preserve_subfolders = tk.BooleanVar(value=True)
        self.overwrite_output = tk.BooleanVar(value=True)
        self.copy_unmodified = tk.BooleanVar(value=False)

        self.mode = tk.StringVar(value="all_zero")
        self.zero_value = tk.StringVar(value="0")
        self.replacement_value = tk.StringVar(value="32766")
        self.bright_threshold = tk.StringVar(value="20000")
        self.radius = tk.StringVar(value="3")
        self.suffix = tk.StringVar(value="_zero2sat")

        self.verify_after_write = tk.BooleanVar(value=True)
        self.compute_sha256 = tk.BooleanVar(value=True)
        self.generate_html_report = tk.BooleanVar(value=True)
        self.dry_run = tk.BooleanVar(value=True)
        self.workers = tk.StringVar(value="1")

        self.project_name = tk.StringVar()
        self.operator = tk.StringVar()
        self.sample = tk.StringVar()
        self.beamline = tk.StringVar()
        self.detector = tk.StringVar()
        self.experiment_date = tk.StringVar()
        self.notes_text: Optional[tk.Text] = None

        self.status = tk.StringVar(
            value="请选择输入/输出文件夹；建议先运行“只扫描”。"
        )
        self.summary = tk.StringVar(value="未运行。")

    def _layout(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text=APP_TITLE, font=("TkDefaultFont", 13, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.save_config_btn = ttk.Button(top, text="保存配置", command=self.save_config)
        self.save_config_btn.grid(row=0, column=1, padx=4)
        self.load_config_btn = ttk.Button(top, text="加载配置", command=self.load_config)
        self.load_config_btn.grid(row=0, column=2, padx=4)

        nb = ttk.Notebook(self)
        self.repair_notebook = nb
        nb.grid(row=1, column=0, sticky="nsew", pady=(10, 8))

        self.tab_basic = ttk.Frame(nb, padding=10)
        self.tab_rules = ttk.Frame(nb, padding=10)
        self.tab_safety = ttk.Frame(nb, padding=10)
        self.tab_meta = ttk.Frame(nb, padding=10)
        self.tab_log = ttk.Frame(nb, padding=10)
        nb.add(self.tab_basic, text="文件与输出")
        nb.add(self.tab_rules, text="修复规则")
        nb.add(self.tab_safety, text="安全与复现")
        nb.add(self.tab_meta, text="项目元数据")
        nb.add(self.tab_log, text="日志")

        self._layout_basic()
        self._layout_rules()
        self._layout_safety()
        self._layout_meta()
        self._layout_log()

        action = ttk.Frame(self)
        action.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        action.columnconfigure(6, weight=1)
        self.scan_btn = ttk.Button(
            action, text="只扫描", command=lambda: self.start("scan")
        )
        self.scan_btn.grid(row=0, column=0, padx=4)
        self.dry_btn = ttk.Button(
            action, text="模拟修复 Dry-run", command=self.start_dry_run
        )
        self.dry_btn.grid(row=0, column=1, padx=4)
        self.run_btn = ttk.Button(
            action, text="开始安全修复", command=lambda: self.start("repair")
        )
        self.run_btn.grid(row=0, column=2, padx=4)
        self.stop_btn = ttk.Button(
            action, text="停止后续任务", command=self.stop, state="disabled"
        )
        self.stop_btn.grid(row=0, column=3, padx=4)
        self.open_out_btn = ttk.Button(
            action, text="打开输出目录", command=self.open_output, state="disabled"
        )
        self.open_out_btn.grid(row=0, column=4, padx=4)
        self.open_report_btn = ttk.Button(
            action, text="打开 QC 报告", command=self.open_report, state="disabled"
        )
        self.open_report_btn.grid(row=0, column=5, padx=4)
        self.progress = ttk.Progressbar(action, orient="horizontal", mode="determinate")
        self.progress.grid(row=0, column=6, sticky="ew", padx=8)

        ttk.Label(self, textvariable=self.status).grid(row=3, column=0, sticky="ew")
        ttk.Label(self, textvariable=self.summary, foreground="#444").grid(
            row=4, column=0, sticky="ew"
        )

    def _layout_basic(self):
        f = self.tab_basic
        f.columnconfigure(0, weight=1)
        self.basic_io_frame = ttk.LabelFrame(f, text="输入/输出")
        box = self.basic_io_frame
        box.grid(row=0, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)

        self.input_dir_label = ttk.Label(box, text="输入文件夹")
        self.input_dir_label.grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(box, textvariable=self.input_dir).grid(
            row=0, column=1, sticky="ew", padx=8, pady=8
        )
        self.choose_input_btn = ttk.Button(
            box, text="选择输入文件夹", command=self.choose_input
        )
        self.choose_input_btn.grid(row=0, column=2, padx=8)
        self.output_dir_label = ttk.Label(box, text="输出文件夹")
        self.output_dir_label.grid(row=1, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(box, textvariable=self.output_dir).grid(
            row=1, column=1, sticky="ew", padx=8, pady=8
        )
        self.choose_output_btn = ttk.Button(
            box, text="选择输出文件夹", command=self.choose_output
        )
        self.choose_output_btn.grid(row=1, column=2, padx=8)

        self.behavior_frame = ttk.LabelFrame(f, text="批处理行为")
        opt = self.behavior_frame
        opt.grid(row=1, column=0, sticky="ew", pady=10)
        checks = [
            ("递归处理子文件夹", self.recursive, "处理输入目录下所有子目录中的 CBF。"),
            ("跳过输出目录", self.skip_output_dir, "防止递归时重复处理已修复文件。"),
            ("保留子目录结构", self.preserve_subfolders, "在输出目录中复制原始相对路径。"),
            ("覆盖已存在输出", self.overwrite_output, "同名输出存在时覆盖；不勾选则跳过。"),
            ("未修改文件也复制", self.copy_unmodified, "没有 0 像素的文件也复制到输出目录。"),
        ]
        check_attrs = [
            "recursive_cb",
            "skip_output_dir_cb",
            "preserve_subfolders_cb",
            "overwrite_output_cb",
            "copy_unmodified_cb",
        ]
        for i, (text, var, tip) in enumerate(checks):
            w = ttk.Checkbutton(opt, text=text, variable=var)
            setattr(self, check_attrs[i], w)
            w.grid(row=i // 2, column=i % 2, sticky="w", padx=8, pady=6)
            ToolTip(w, tip)

        suffix_box = ttk.Frame(opt)
        suffix_box.grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=6)
        self.suffix_label = ttk.Label(suffix_box, text="输出后缀")
        self.suffix_label.pack(side="left")
        ttk.Entry(suffix_box, textvariable=self.suffix, width=18).pack(side="left", padx=8)
        self.suffix_hint_label = ttk.Label(suffix_box, text="例如 sample.cbf -> sample_zero2sat.cbf")
        self.suffix_hint_label.pack(
            side="left"
        )

    def _layout_rules(self):
        f = self.tab_rules
        f.columnconfigure(0, weight=1)
        box = ttk.LabelFrame(f, text="像素替换规则")
        box.grid(row=0, column=0, sticky="ew")

        ttk.Label(box, text="异常值").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(box, textvariable=self.zero_value, width=12).grid(
            row=0, column=1, sticky="w", padx=8
        )
        ttk.Label(box, text="替换为").grid(row=0, column=2, sticky="w", padx=8)
        ttk.Entry(box, textvariable=self.replacement_value, width=12).grid(
            row=0, column=3, sticky="w", padx=8
        )
        ttk.Label(
            box,
            text="示例值：只有采集链证据确认后，才可将 0 替换为 32766。",
        ).grid(row=0, column=4, sticky="w", padx=8)

        ttk.Radiobutton(
            box,
            text="所有匹配值都替换（需仪器/采集软件证据）",
            variable=self.mode,
            value="all_zero",
        ).grid(row=1, column=0, columnspan=5, sticky="w", padx=8, pady=6)
        ttk.Radiobutton(
            box,
            text="只替换强峰附近异常值（保守，避免真实背景 0 被替换）",
            variable=self.mode,
            value="near_bright",
        ).grid(row=2, column=0, columnspan=5, sticky="w", padx=8, pady=6)

        ttk.Label(box, text="强峰阈值").grid(row=3, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(box, textvariable=self.bright_threshold, width=12).grid(
            row=3, column=1, sticky="w", padx=8
        )
        ttk.Label(box, text="邻域半径/像素").grid(row=3, column=2, sticky="w", padx=8)
        ttk.Entry(box, textvariable=self.radius, width=12).grid(
            row=3, column=3, sticky="w", padx=8
        )

        info = (
            "建议流程：先用“只扫描”确认 0 像素数量和分布，"
            "再用 Dry-run 检查预计替换数量，最后正式修复。\n"
            "零值也可能来自 beamstop、模块间隙、掩膜或真实低计数；未经确认不应修改。\n"
            "本工具不能恢复真实过曝强度；它只执行用户已确认的存储值替换规则。"
        )
        ttk.Label(f, text=info, foreground="#555", justify="left").grid(
            row=1, column=0, sticky="ew", pady=12
        )

    def _layout_safety(self):
        f = self.tab_safety
        f.columnconfigure(0, weight=1)
        box = ttk.LabelFrame(f, text="安全与可追溯")
        box.grid(row=0, column=0, sticky="ew")
        checks = [
            (
                "写出后重新读回逐像素校验",
                self.verify_after_write,
                "强烈建议勾选。重新读取输出 CBF 并确认矩阵与预期完全一致。",
            ),
            ("计算 SHA256 哈希", self.compute_sha256, "记录原始/输出文件哈希，便于归档追溯。"),
            ("生成 HTML QC 报告", self.generate_html_report, "生成可打开的质控报告。"),
        ]
        for i, (text, var, tip) in enumerate(checks):
            w = ttk.Checkbutton(box, text=text, variable=var)
            w.grid(row=i, column=0, sticky="w", padx=8, pady=7)
            ToolTip(w, tip)
        ttk.Label(box, text="并行 worker 数").grid(row=3, column=0, sticky="w", padx=8, pady=7)
        spin = ttk.Spinbox(box, from_=1, to=32, textvariable=self.workers, width=8)
        spin.grid(row=3, column=1, sticky="w", padx=8)
        ToolTip(spin, "机械硬盘建议 1-2；SSD 可尝试 2-4。并行过高会增加 IO 压力。")

        criteria = (
            "安全通过判据：\n"
            "  status = repaired_verified\n"
            "  nontarget_changed_before_write = 0\n"
            "  target_not_replaced_before_write = 0\n"
            "  readback_different_pixels = 0\n"
            "  readback_nontarget_different_pixels = 0"
        )
        ttk.Label(
            f,
            text=criteria,
            font=("TkFixedFont", 10),
            foreground="#115511",
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=14)

    def _layout_meta(self):
        f = self.tab_meta
        f.columnconfigure(0, weight=1)
        box = ttk.LabelFrame(f, text="项目元数据（写入配置和 QC 报告，不改 CBF 数据）")
        box.grid(row=0, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)
        fields = [
            ("项目名称", self.project_name),
            ("操作者", self.operator),
            ("样品", self.sample),
            ("线站", self.beamline),
            ("探测器", self.detector),
            ("实验日期", self.experiment_date),
        ]
        for i, (label, var) in enumerate(fields):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=6)
            ttk.Entry(box, textvariable=var).grid(
                row=i, column=1, sticky="ew", padx=8, pady=6
            )
        ttk.Label(box, text="备注").grid(
            row=len(fields), column=0, sticky="nw", padx=8, pady=6
        )
        self.notes_text = tk.Text(box, height=7, wrap="word")
        self.notes_text.grid(row=len(fields), column=1, sticky="ew", padx=8, pady=6)

    def _layout_log(self):
        f = self.tab_log
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        self.log_text = tk.Text(f, wrap="none", height=24)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        y = ttk.Scrollbar(f, orient="vertical", command=self.log_text.yview)
        y.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=y.set)

    def _check_imports(self):
        if IMPORT_ERROR is None:
            return
        messagebox.showerror(
            "依赖缺失",
            "缺少过曝修复依赖 fabio 或 numpy。请运行：\n\n"
            "python -m pip install -r requirements.txt\n\n"
            f"错误信息：{IMPORT_ERROR}",
        )
        for button in (self.scan_btn, self.run_btn, self.dry_btn):
            button.configure(state="disabled")

    def choose_input(self):
        path = filedialog.askdirectory(title="选择 CBF 输入文件夹")
        if path:
            self.input_dir.set(path)
            if not self.output_dir.get().strip():
                self.output_dir.set(str(Path(path) / "cbf_zero2sat_output"))

    def choose_output(self):
        path = filedialog.askdirectory(title="选择输出文件夹")
        if path:
            self.output_dir.set(path)

    @staticmethod
    def _parse_int_field(
        raw_value: str,
        label: str,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
    ) -> int:
        text = str(raw_value).strip()
        if text == "":
            raise ValueError(f"{label} 不能为空，必须输入整数。")
        try:
            value = int(text)
        except Exception as exc:
            raise ValueError(f"{label} 必须是整数，当前输入: {text!r}") from exc
        if minimum is not None and value < minimum:
            raise ValueError(f"{label} 必须 >= {minimum}，当前输入: {value}")
        if maximum is not None and value > maximum:
            raise ValueError(f"{label} 必须 <= {maximum}，当前输入: {value}")
        return value

    def build_config(self):
        if IMPORT_ERROR is not None:
            raise RuntimeError(f"过曝修复依赖不可用: {IMPORT_ERROR}")
        input_text = self.input_dir.get().strip()
        output_text = self.output_dir.get().strip()
        if not input_text:
            raise ValueError("请指定输入文件夹。")
        if not output_text:
            raise ValueError("请指定输出文件夹。")
        notes = self.notes_text.get("1.0", "end").strip() if self.notes_text else ""
        meta = ProjectMetadata(
            project_name=self.project_name.get().strip(),
            operator=self.operator.get().strip(),
            sample=self.sample.get().strip(),
            beamline=self.beamline.get().strip(),
            detector=self.detector.get().strip(),
            experiment_date=self.experiment_date.get().strip(),
            notes=notes,
        )
        cfg = ProcessConfig(
            input_dir=Path(input_text),
            output_dir=Path(output_text),
            recursive=self.recursive.get(),
            skip_output_dir=self.skip_output_dir.get(),
            preserve_subfolders=self.preserve_subfolders.get(),
            suffix=self.suffix.get(),
            overwrite_output=self.overwrite_output.get(),
            overwrite_original=False,
            backup_before_overwrite=True,
            copy_unmodified=self.copy_unmodified.get(),
            mode=self.mode.get(),
            zero_value=self._parse_int_field(self.zero_value.get(), "异常值"),
            replacement_value=self._parse_int_field(
                self.replacement_value.get(), "替换值"
            ),
            bright_threshold=self._parse_int_field(
                self.bright_threshold.get(), "强峰阈值"
            ),
            radius=self._parse_int_field(self.radius.get(), "邻域半径/像素", minimum=1),
            verify_after_write=self.verify_after_write.get(),
            compute_sha256=self.compute_sha256.get(),
            generate_html_report=self.generate_html_report.get(),
            workers=self._parse_int_field(
                self.workers.get(), "并行 worker 数", minimum=1, maximum=32
            ),
            dry_run=self.dry_run.get(),
            metadata=meta,
        ).normalized()

        if not cfg.input_dir.exists() or not cfg.input_dir.is_dir():
            raise ValueError("输入文件夹不存在。")
        if cfg.input_dir == cfg.output_dir and not cfg.suffix:
            raise ValueError("输入和输出文件夹相同时必须设置输出后缀。")
        return cfg

    def apply_config(self, cfg):
        self.input_dir.set(str(cfg.input_dir))
        self.output_dir.set(str(cfg.output_dir))
        self.recursive.set(cfg.recursive)
        self.skip_output_dir.set(cfg.skip_output_dir)
        self.preserve_subfolders.set(cfg.preserve_subfolders)
        self.suffix.set(cfg.suffix)
        self.overwrite_output.set(cfg.overwrite_output)
        self.copy_unmodified.set(cfg.copy_unmodified)
        self.mode.set(cfg.mode)
        self.zero_value.set(str(cfg.zero_value))
        self.replacement_value.set(str(cfg.replacement_value))
        self.bright_threshold.set(str(cfg.bright_threshold))
        self.radius.set(str(cfg.radius))
        self.verify_after_write.set(cfg.verify_after_write)
        self.compute_sha256.set(cfg.compute_sha256)
        self.generate_html_report.set(cfg.generate_html_report)
        self.workers.set(str(cfg.workers))
        self.dry_run.set(cfg.dry_run)
        self.project_name.set(cfg.metadata.project_name)
        self.operator.set(cfg.metadata.operator)
        self.sample.set(cfg.metadata.sample)
        self.beamline.set(cfg.metadata.beamline)
        self.detector.set(cfg.metadata.detector)
        self.experiment_date.set(cfg.metadata.experiment_date)
        if self.notes_text:
            self.notes_text.delete("1.0", "end")
            self.notes_text.insert("1.0", cfg.metadata.notes)

    def save_config(self):
        try:
            cfg = self.build_config()
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="保存配置",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config_to_dict(cfg), f, indent=2, ensure_ascii=False)
            self.log(f"配置已保存: {path}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def load_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], title="加载配置")
        if not path:
            return
        try:
            cfg = load_config_json(Path(path))
            self.apply_config(cfg)
            self.log(f"配置已加载: {path}")
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))

    def set_running(self, running: bool):
        state = "disabled" if running else "normal"
        for button in (self.scan_btn, self.dry_btn, self.run_btn):
            button.configure(state=state)
        self.stop_btn.configure(state="normal" if running else "disabled")
        if not running and self.last_output_dir:
            self.open_out_btn.configure(state="normal")
        if not running and self.last_html_report:
            self.open_report_btn.configure(state="normal")

    def start_dry_run(self):
        self.dry_run.set(True)
        self.start("repair")

    def _conversion_is_active(self):
        """Return whether the main conversion batch currently owns the GUI."""
        app = getattr(self, "app", None)
        if app is None:
            return False
        conversion_check = getattr(app, "_conversion_is_active", None)
        if callable(conversion_check):
            try:
                return bool(conversion_check())
            except Exception:
                pass
        if getattr(app, "is_running", False):
            return True
        if getattr(app, "thread_pool", None) is not None:
            return True
        coordinator = getattr(app, "_conversion_thread", None)
        is_alive = getattr(coordinator, "is_alive", None) if coordinator is not None else None
        return bool(callable(is_alive) and is_alive())

    def start(self, action: str):
        if self.worker and self.worker.is_alive():
            return
        if self._conversion_is_active():
            messagebox.showwarning(
                "正在运行",
                "当前批处理尚未结束，请等待完成或先取消当前任务。",
            )
            return
        try:
            cfg = self.build_config()
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        if action == "repair" and not cfg.dry_run:
            if not str(cfg.metadata.notes).strip():
                messagebox.showerror(
                    "缺少规则证据",
                    "正式修复前，请在“项目元数据”的备注中说明：匹配值为何代表需替换的异常码，"
                    "替换值来自哪份探测器、线站或采集软件证据。",
                )
                return
            if not cfg.verify_after_write:
                messagebox.showerror(
                    "必须启用读回校验",
                    "正式修复必须勾选“写出后重新读回逐像素校验”。"
                    "如只需评估规则，请使用 Dry-run。",
                )
                return
            ok = messagebox.askyesno(
                "确认开始修复",
                "程序将写出新的 CBF 文件，并执行逐像素校验。\n\n"
                "建议先运行“只扫描”和“Dry-run”。是否继续？",
            )
            if not ok:
                return
        self.cancel_requested = False
        self.cancel_event.clear()
        self.last_output_dir = cfg.output_dir
        self.last_html_report = None
        self.last_csv = None
        self.progress.configure(value=0, maximum=1)
        self.status.set("运行中。")
        self.summary.set("正在处理...")
        self.set_running(True)
        self.log(
            f"开始: action={action}, dry_run={cfg.dry_run}, "
            f"input={cfg.input_dir}, output={cfg.output_dir}"
        )
        self.worker = threading.Thread(
            target=self.worker_main, args=(cfg, action), daemon=True
        )
        self.worker.start()

    def stop(self):
        self.cancel_requested = True
        self.cancel_event.set()
        self.status.set("已请求停止。当前批处理会等待正在运行的文件写入安全结束。")
        self.log("停止请求已记录：为避免写坏 CBF，正在运行的文件写入不会被强制中断。")

    def worker_main(self, cfg, action: str):
        try:
            def progress(i, total, result):
                self.queue.put(("progress", (i, total, result)))

            results, summary = run_batch(
                cfg,
                action=action,
                progress_callback=progress,
                cancel_event=self.cancel_event,
            )
            self.queue.put(("done", (results, summary)))
        except Exception as exc:
            self.queue.put(("error", f"{exc}\n{traceback.format_exc()}"))

    def _poll(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "progress":
                    i, total, result = payload
                    self.progress.configure(maximum=max(1, total), value=i)
                    self.status.set(f"处理中: {i}/{total}")
                    self.log(self.format_result(i, total, result))
                elif kind == "done":
                    _results, summary = payload
                    self.last_csv = summary.csv_path
                    self.last_html_report = summary.html_path
                    self.summary.set(
                        f"完成: 文件 {summary.total_files}, 修复 {summary.repaired}, "
                        f"校验通过 {summary.verified}, 替换像素 "
                        f"{summary.total_replaced_pixels}, 错误 {summary.errors}. "
                        f"CSV: {summary.csv_path}"
                    )
                    self.status.set("完成。")
                    self.log(self.summary.get())
                    if summary.html_path:
                        self.log(f"QC 报告: {summary.html_path}")
                    needs_review = (
                        summary.errors
                        or summary.readback_nontarget_different_pixels
                        or summary.nontarget_changed_before_write
                    )
                    if needs_review:
                        messagebox.showwarning(
                            "存在需要检查的文件",
                            "有文件未通过处理或校验。请查看 CSV 和 QC 报告。",
                        )
                    self.set_running(False)
                    self.dry_run.set(False)
                elif kind == "error":
                    self.log(str(payload))
                    messagebox.showerror("运行错误", str(payload))
                    self.status.set("错误。")
                    self.set_running(False)
                    self.dry_run.set(False)
        except queue.Empty:
            pass
        self._poll_after_id = self.after(100, self._poll)

    def destroy(self):
        if self.worker is not None and self.worker.is_alive():
            self.cancel_event.set()
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None
        super().destroy()

    @staticmethod
    def format_result(i: int, total: int, result) -> str:
        name = result.relative_path or Path(result.input_file).name
        if result.status == "repaired_verified":
            return (
                f"{i}/{total} PASS {name} | replaced={result.replaced_pixels}, "
                f"non_target_change={result.nontarget_changed_before_write}, "
                f"readback_diff={result.readback_different_pixels}"
            )
        if result.status == "dry_run":
            return (
                f"{i}/{total} DRY {name} | target={result.target_pixels}, "
                f"would replace={result.replaced_pixels}"
            )
        if result.status == "scan":
            return (
                f"{i}/{total} SCAN {name} | dtype={result.dtype_before}, "
                f"shape={result.shape_before}, zero={result.zero_pixels}, "
                f"target={result.target_pixels}, max={result.max_before}"
            )
        if result.status == "error":
            first = result.error.splitlines()[0] if result.error else "unknown error"
            return f"{i}/{total} ERROR {name} | {first}"
        return f"{i}/{total} {result.status.upper()} {name} | target={result.target_pixels}"

    def log(self, msg: str):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def open_path(self, path: Union[str, Path]):
        path = str(path)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def open_output(self):
        if self.last_output_dir:
            self.open_path(self.last_output_dir)

    def open_report(self):
        if self.last_html_report:
            self.open_path(self.last_html_report)
