"""Main application with Notebook (tab) layout."""

import os
import sys
import json
import math
import threading
import concurrent.futures
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox

from gui.styles import apply_theme, configure_styles
from gui.tabs.io_tab import IOTab
from gui.tabs.processing_tab import ProcessingTab
from gui.tabs.output_tab import OutputTab
from gui.tabs.geometry_tab import GeometryTab
from gui.tabs.quality_tab import QualityTab
from gui.tabs.overexposure_tab import OverexposureRepairTab
from gui.tabs.q_calculator_tab import QCalculatorTab
from gui.log_panel import LogPanel
from gui.preview import show_preview
from core.constants import APP_TITLE, APP_VERSION, CONFIG_FILE, DEFAULT_H5_PATH
from core.utils import get_output_base_name, parse_roi_text, parse_optional_float
from core.loader import (
    load_image,
    load_image_with_info,
    sniff_file_kind,
    find_files_recursive,
    build_filelist_from_selected_paths,
)
from core.quality import (
    analyze_image_quality,
    assess_processing_plan,
    quality_summary_line,
)
from core.worker import process_one_file
from core.png_export import validate_png_options


class App(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1280x900")
        self.minsize(1100, 800)

        apply_theme(self)
        configure_styles(self)

        # State
        self.filelist = []
        self.selected_files = []
        self.selected_common_root = None
        self.dark_frame = None
        self.flat_frame = None
        self.mask_frame = None
        self.cancellation_event = threading.Event()
        self.thread_pool = None
        self.is_running = False
        self.done_count = 0
        self.count_lock = threading.Lock()
        self.stats = {
            "success": 0, "failed": 0,
            "skipped": 0, "cancelled": 0,
        }
        self.start_time = None
        self.last_quality_reports = []

        self._create_widgets()
        self._load_config()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_widgets(self):
        """Build the UI with Notebook tabs and bottom log panel."""
        # Top area: Notebook with tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        # Tab 1: Input/Output
        self.io_tab = IOTab(self.notebook, self)
        self.notebook.add(self.io_tab, text="  \u8F93\u5165/\u8F93\u51FA  ")

        # Tab 2: Processing
        self.processing_tab = ProcessingTab(self.notebook, self)
        self.notebook.add(self.processing_tab, text="  \u9884\u5904\u7406  ")

        # Tab 3: Automatic QC
        self.quality_tab = QualityTab(self.notebook, self)
        self.notebook.add(self.quality_tab, text="  \u81EA\u52A8\u8D28\u63A7  ")

        # Tab 4: CBF overexposure repair
        self.overexposure_tab = OverexposureRepairTab(self.notebook, self)
        self.notebook.add(self.overexposure_tab, text="  \u8FC7\u66DD\u4FEE\u590D  ")

        # Tab 5: Output Formats
        self.output_tab = OutputTab(self.notebook, self)
        self.notebook.add(self.output_tab, text="  \u8F93\u51FA\u683C\u5F0F  ")

        # Tab 6: Geometry
        self.geometry_tab = GeometryTab(self.notebook, self)
        self.notebook.add(self.geometry_tab, text="  \u51E0\u4F55\u53D8\u6362  ")

        # Tab 7: Q Calculator
        self.q_calc_tab = QCalculatorTab(self.notebook, self)
        self.notebook.add(self.q_calc_tab, text="  Q \u8BA1\u7B97\u5668  ")

        # Bottom area: Log panel (always visible)
        self.log_panel = LogPanel(self, self)
        self.log_panel.pack(fill="both", expand=False, padx=8, pady=8)

    # --- Convenience properties for log ---
    def log(self, msg):
        self.log_panel.log(msg)

    # --- File list management ---
    def _get_active_input_filelist(self):
        mode = self.io_tab.input_mode_var.get()
        if mode == "files":
            if not self.selected_files:
                return [], None, []
            filelist, common_root, skipped = build_filelist_from_selected_paths(
                self.selected_files
            )
            self.selected_common_root = common_root
            return filelist, common_root, skipped

        root = self.io_tab.dir_var.get().strip()
        if not root or not os.path.isdir(root):
            return [], None, []
        outroot = self.io_tab.outdir_var.get().strip()
        filelist = [
            (fp, rp)
            for fp, rp in find_files_recursive(
                root, exclude_dirs=[outroot] if outroot else []
            )
        ]
        return filelist, Path(root).resolve(), []

    def _get_default_output_root(self):
        if self.io_tab.input_mode_var.get() == "files":
            if self.selected_common_root and Path(self.selected_common_root).exists():
                return str(Path(self.selected_common_root) / "_converted")
            if self.selected_files:
                return str(
                    Path(self.selected_files[0]).resolve().parent / "_converted"
                )
            return ""
        root = self.io_tab.dir_var.get().strip()
        return os.path.join(root, "_converted") if root else ""

    # --- Preview ---
    def preview_image(self):
        show_preview(self)

    def show_gallery(self):
        from gui.gallery import show_gallery
        show_gallery(self)

    # --- Count Files ---
    def count_files(self, show_dialog=True):
        mode = self.io_tab.input_mode_var.get()
        if mode == "directory":
            root = self.io_tab.dir_var.get().strip()
            if not root or not os.path.isdir(root):
                messagebox.showwarning(
                    "\u76EE\u5F55\u65E0\u6548", "\u8BF7\u9009\u62E9\u6709\u6548\u7684\u8F93\u5165\u76EE\u5F55\u3002"
                )
                return
        else:
            if not self.selected_files:
                messagebox.showwarning(
                    "\u65E0\u6587\u4EF6", "\u8BF7\u9009\u62E9\u4E00\u4E2A\u6216\u591A\u4E2A\u5177\u4F53\u6587\u4EF6\u3002"
                )
                return

        self.filelist, active_root, skipped = self._get_active_input_filelist()
        total_files = len(self.filelist)

        if skipped:
            self.log(f"\u8DF3\u8FC7 {len(skipped)} \u4E2A\u65E0\u6548/\u4E0D\u652F\u6301\u7684\u9009\u5B9A\u9879")

        groups = {}
        for file_path, rel_path in self.filelist:
            if mode == "directory":
                parent_dir = (
                    str(rel_path.parent)
                    if rel_path.parent != Path('.')
                    else "root"
                )
            else:
                parent_dir = str(file_path.parent)
            groups[parent_dir] = groups.get(parent_dir, 0) + 1

        if groups:
            dir_info = "\n".join(
                [f"  {d}: {n} \u4E2A\u6587\u4EF6" for d, n in sorted(groups.items())]
            )
            source_label = (
                self.io_tab.dir_var.get().strip()
                if mode == "directory"
                else "\u5DF2\u9009\u6587\u4EF6"
            )
            self.log(f"\u5728 '{source_label}' \u4E2D\u627E\u5230 {total_files} \u4E2A\u6587\u4EF6:\n{dir_info}")
        else:
            self.log("\u627E\u5230 0 \u4E2A\u652F\u6301\u7684\u6587\u4EF6\u3002")

        if show_dialog:
            messagebox.showinfo(
                "\u6587\u4EF6\u7EDF\u8BA1",
                f"\u627E\u5230 {total_files} \u4E2A\u652F\u6301\u683C\u5F0F\u7684\u6587\u4EF6\u3002",
            )

    # --- Workflow Preset ---
    def _apply_workflow_preset(self):
        preset = self.io_tab.workflow_preset_var.get()
        if preset == "Custom":
            return

        for fmt_var in self.output_tab.format_vars.values():
            fmt_var.set(False)

        p = self.processing_tab
        g = self.geometry_tab
        p.clip_negative_var.set(False)
        p.mask_nonzero_is_invalid_var.set(True)
        self.output_tab.xy_skip_zeros.set(True)
        self.output_tab.xy_zero_tol.set(0.0)
        g.rotate_var.set("0")
        g.flip_x_var.set(False)
        g.flip_y_var.set(False)
        g.bin_factor_var.set(1)
        g.norm_mode_var.set("none")
        g.pclip_low_var.set("")
        g.pclip_high_var.set("")
        g.intensity_transform_var.set("none")
        g.gamma_var.set(1.0)
        g.hot_pixel_enable_var.set(False)
        g.hot_pixel_window_var.set(3)
        g.hot_pixel_sigma_var.set(8.0)

        if preset == "SAXS Quick":
            self.output_tab.format_vars['tif'].set(True)
            self.output_tab.format_vars['npy'].set(True)
            p.bg_offset_var.set(0.0)
            p.min_intensity_var.set("")
            p.max_intensity_var.set("")
        elif preset == "SXRD Quick":
            self.output_tab.format_vars['tif'].set(True)
            self.output_tab.format_vars['dat'].set(True)
            self.output_tab.format_vars['xycsv'].set(True)
            self.output_tab.format_vars['xydat'].set(True)
            p.bg_offset_var.set(0.0)
            p.min_intensity_var.set("")
            p.max_intensity_var.set("")
        elif preset == "GIWAXS Quick":
            self.output_tab.format_vars['tif'].set(True)
            self.output_tab.format_vars['csv'].set(True)
            self.output_tab.format_vars['xycsv'].set(True)
            self.output_tab.format_vars['xydat'].set(True)
            p.bg_offset_var.set(0.0)
            p.min_intensity_var.set("")
            p.max_intensity_var.set("")

        self.log(f"\u5DF2\u5E94\u7528\u5DE5\u4F5C\u6D41\u9884\u8BBE: {preset}")

    # --- Preflight Checks ---
    def _run_preflight_checks(
        self, outroot, formats, roi, bin_factor, min_intensity, max_intensity
    ):
        errors = []
        warnings = []
        self.last_quality_reports = []

        if (
            min_intensity is not None
            and max_intensity is not None
            and max_intensity < min_intensity
        ):
            errors.append("I Max \u5FC5\u987B >= I Min\u3002")

        # Output write check
        try:
            Path(outroot).mkdir(parents=True, exist_ok=True)
            probe = Path(outroot) / ".__write_test__.tmp"
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            if probe.exists():
                probe.unlink()
        except Exception as e:
            errors.append(f"\u8F93\u51FA\u76EE\u5F55\u4E0D\u53EF\u5199: {outroot} ({e})")

        if not self.output_tab.overwrite_var.get():
            existing_outputs = 0
            for fp, rel_path in self.filelist:
                base_name = get_output_base_name(fp)
                for fmt in formats:
                    ext = {"xycsv": "csv", "xydat": "dat"}.get(fmt, fmt)
                    out_path = Path(outroot) / rel_path.parent / fmt / f"{base_name}.{ext}"
                    if out_path.exists():
                        existing_outputs += 1
                if existing_outputs > 20:
                    break
            if existing_outputs:
                warnings.append(
                    "\u68C0\u6D4B\u5230\u5DF2\u5B58\u5728\u7684\u8F93\u51FA\u6587\u4EF6\u3002"
                    "\u672A\u52FE\u9009\u8986\u76D6\u65F6\u8FD9\u4E9B\u6587\u4EF6\u4F1A\u88AB\u8DF3\u8FC7\uFF0C"
                    f"\u62BD\u67E5\u8BA1\u6570={existing_outputs}\u3002"
                )

        sample_infos = []
        shape_to_files = {}
        sample_entries = self.filelist[:min(5, len(self.filelist))]
        for sample_file, _ in sample_entries:
            try:
                loaded = load_image_with_info(
                    sample_file, self.io_tab.h5_path_var.get()
                )
                sample_img = loaded["data"]
                report = analyze_image_quality(
                    sample_img,
                    metadata=loaded["metadata"],
                    source_name=sample_file.name,
                )
                report.findings.extend(
                    assess_processing_plan(
                        report,
                        formats=formats,
                        roi=roi,
                        bin_factor=bin_factor,
                        rotate_deg=self.geometry_tab.rotate_var.get(),
                    )
                )
                report.review_required = any(
                    item.level in {"WARNING", "ERROR"}
                    for item in report.findings
                )
                self.last_quality_reports.append(report)
                sample_infos.append((sample_file, sample_img, report))
                shape_to_files.setdefault(sample_img.shape, []).append(
                    sample_file.name
                )
                for finding in report.findings:
                    text = (
                        f"{sample_file.name}: {finding.message} "
                        f"({finding.basis})"
                    )
                    if finding.level == "ERROR":
                        errors.append(text)
                    elif finding.level == "WARNING":
                        warnings.append(text)
            except Exception as e:
                errors.append(
                    f"\u65E0\u6CD5\u8BFB\u53D6\u62BD\u6837\u6587\u4EF6 {sample_file.name}: {e}"
                )

        # HDF5 check
        h5_files = []
        for fp, _ in self.filelist:
            try:
                if sniff_file_kind(fp) == "hdf5":
                    h5_files.append(fp)
            except Exception:
                continue
        for h5_file in h5_files[:5]:
            try:
                _ = load_image_with_info(h5_file, self.io_tab.h5_path_var.get())
            except Exception as e:
                errors.append(
                    f"HDF5 \u8DEF\u5F84\u68C0\u67E5\u5931\u8D25 {h5_file.name}: {e}"
                )

        if len(shape_to_files) > 1:
            shape_text = ", ".join(
                f"{shape}: {len(names)}\u4E2A" for shape, names in shape_to_files.items()
            )
            warnings.append(
                "\u62BD\u6837\u6587\u4EF6\u5C3A\u5BF8\u4E0D\u4E00\u81F4\u3002"
                "\u5982\u679C\u4F7F\u7528 dark/flat/mask \u6216 ROI\uFF0C"
                f"\u8BF7\u9010\u5C3A\u5BF8\u590D\u6838\u3002{shape_text}"
            )

        def effective_shape(shape):
            h0, w0 = shape
            if roi is not None:
                _, _, roi_w, roi_h = roi
                h0, w0 = roi_h, roi_w
            if self.geometry_tab.rotate_var.get() in ("90", "270"):
                h0, w0 = w0, h0
            return h0, w0

        for sample_file, sample_img, _ in sample_infos:
            if self.dark_frame is not None and self.dark_frame.shape != sample_img.shape:
                errors.append(
                    f"{sample_file.name}: \u6697\u5E27\u5C3A\u5BF8\u4E0D\u5339\u914D\u3002"
                    f"\u6697\u5E27={self.dark_frame.shape}, \u6837\u672C={sample_img.shape}"
                )
            if self.mask_frame is not None and self.mask_frame.shape != sample_img.shape:
                errors.append(
                    f"{sample_file.name}: \u63A9\u819C\u5C3A\u5BF8\u4E0D\u5339\u914D\u3002"
                    f"\u63A9\u819C={self.mask_frame.shape}, \u6837\u672C={sample_img.shape}"
                )
            if self.flat_frame is not None and self.flat_frame.shape != sample_img.shape:
                errors.append(
                    f"{sample_file.name}: \u5E73\u573A\u5C3A\u5BF8\u4E0D\u5339\u914D\u3002"
                    f"\u5E73\u573A={self.flat_frame.shape}, \u6837\u672C={sample_img.shape}"
                )

            eff_h, eff_w = effective_shape(sample_img.shape)
            geo = self.geometry_tab
            if (
                geo.hot_pixel_enable_var.get()
                and geo.hot_pixel_window_var.get() > min(eff_h, eff_w)
            ):
                warnings.append(
                    f"{sample_file.name}: \u70ED\u50CF\u7D20\u7A97\u53E3 "
                    f"({geo.hot_pixel_window_var.get()}) \u5BF9\u56FE\u50CF\u5C3A\u5BF8 "
                    f"{(eff_h, eff_w)} \u8FC7\u5927"
                )

        if sample_infos and any(fmt in ("xycsv", "xydat") for fmt in formats):
            max_h, max_w = max(
                (effective_shape(img.shape) for _, img, _ in sample_infos),
                key=lambda shape: shape[0] * shape[1],
            )
            est_points = max_h * max_w * len(self.filelist)
            if est_points > 5e7:
                warnings.append(
                    f"\u4F30\u8BA1 XY \u70B9\u6570 ~{int(est_points):,}\uFF1B"
                    "\u8FD0\u884C\u53EF\u80FD\u8F83\u6162\u4E14\u8F93\u51FA\u6587\u4EF6\u5F88\u5927"
                )

        if errors:
            text = "Preflight \u68C0\u67E5\u5931\u8D25:\n\n- " + "\n- ".join(errors)
            self.log(text.replace("\n", " | "))
            messagebox.showerror("Preflight \u5931\u8D25", text)
            return False

        if warnings:
            text = (
                "Preflight \u8B66\u544A:\n\n- "
                + "\n- ".join(warnings)
                + "\n\n\u4ECD\u7136\u7EE7\u7EED?"
            )
            self.log("Preflight \u8B66\u544A: " + " | ".join(warnings))
            return messagebox.askyesno("Preflight \u8B66\u544A", text)

        self.log(
            f"Preflight \u68C0\u67E5\u901A\u8FC7\uFF0C\u5DF2\u62BD\u6837\u8D28\u63A7 "
            f"{len(self.last_quality_reports)} \u4E2A\u6587\u4EF6\u3002"
        )
        return True

    # --- UI State ---
    def _set_ui_state(self, running=True):
        """Enable/disable UI elements during processing."""
        state = "disabled" if running else "normal"

        self.log_panel.run_btn.config(state=state)
        self.log_panel.count_btn.config(state=state)
        self.log_panel.cancel_btn.config(
            state="normal" if running else "disabled"
        )

        control_types = (
            ttk.Entry, ttk.Checkbutton, ttk.Spinbox,
            ttk.Button, ttk.Combobox, ttk.Radiobutton,
        )

        def walk(widget):
            for child in widget.winfo_children():
                if child in (
                    self.log_panel.log_txt,
                    self.log_panel.run_btn,
                    self.log_panel.count_btn,
                    self.log_panel.cancel_btn,
                    self.q_calc_tab,  # Q Calculator stays active during processing
                ):
                    continue
                if isinstance(child, control_types):
                    try:
                        child.config(state=state)
                    except Exception:
                        pass
                walk(child)

        walk(self)

        self.log_panel.run_btn.config(state=state)
        self.log_panel.count_btn.config(state=state)
        self.log_panel.cancel_btn.config(
            state="normal" if running else "disabled"
        )

        # Restore readonly widgets when idle
        if not running:
            self.processing_tab.dark_entry.config(state='readonly')
            self.processing_tab.flat_entry.config(state='readonly')
            self.processing_tab.mask_entry.config(state='readonly')
            self.io_tab.workflow_preset_cb.config(state='readonly')
            self.geometry_tab.rotate_cb.config(state='readonly')
            self.geometry_tab.norm_cb.config(state='readonly')
            self.geometry_tab.transform_cb.config(state='readonly')
            self.output_tab.xy_y_axis_origin_cb.config(state='readonly')
            self.output_tab.png_scale_cb.config(state='readonly')

    # --- Conversion ---
    def run_conversion(self):
        if self.is_running:
            return messagebox.showwarning(
                "正在运行",
                "当前批处理尚未结束，请等待完成或先取消当前任务。",
            )

        # Apply workflow preset if selected
        preset = self.io_tab.workflow_preset_var.get()
        if preset != "Custom":
            self._apply_workflow_preset()

        mode = self.io_tab.input_mode_var.get()
        if mode == "directory":
            root = self.io_tab.dir_var.get().strip()
            if not root or not os.path.isdir(root):
                return messagebox.showwarning(
                    "\u8F93\u5165\u65E0\u6548", "\u8BF7\u9009\u62E9\u6709\u6548\u7684\u8F93\u5165\u76EE\u5F55\u3002"
                )
        else:
            if not self.selected_files:
                return messagebox.showwarning(
                    "\u65E0\u6587\u4EF6", "\u8BF7\u9009\u62E9\u4E00\u4E2A\u6216\u591A\u4E2A\u5177\u4F53\u6587\u4EF6\u3002"
                )
            root = (
                str(self.selected_common_root)
                if self.selected_common_root
                else ""
            )

        self.count_files(show_dialog=False)
        if not self.filelist:
            return messagebox.showwarning(
                "\u65E0\u6587\u4EF6", "\u6CA1\u6709\u6587\u4EF6\u53EF\u5904\u7406\u3002"
            )

        outroot = self.io_tab.outdir_var.get().strip()
        if not outroot:
            outroot = self._get_default_output_root()
        try:
            Path(outroot).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.log(f"输出目录不可用: {outroot} ({e})")
            return messagebox.showerror(
                "输出目录不可用",
                f"无法创建或访问输出目录:\n{outroot}\n\n{e}",
            )
        self.io_tab.outdir_var.set(outroot)

        formats = [
            fmt for fmt, var in self.output_tab.format_vars.items() if var.get()
        ]
        if not formats:
            return messagebox.showwarning(
                "\u65E0\u8F93\u51FA", "\u8BF7\u9009\u62E9\u81F3\u5C11\u4E00\u79CD\u8F93\u51FA\u683C\u5F0F\u3002"
            )

        try:
            max_workers = int(self.log_panel.max_thr_var.get())
            if max_workers < 1 or max_workers > 64:
                raise ValueError("线程数必须在 1-64 之间")
            roi = parse_roi_text(self.processing_tab.roi_var.get())
            min_i = parse_optional_float(self.processing_tab.min_intensity_var.get())
            max_i = parse_optional_float(self.processing_tab.max_intensity_var.get())
            pclip_low = parse_optional_float(self.geometry_tab.pclip_low_var.get())
            pclip_high = parse_optional_float(self.geometry_tab.pclip_high_var.get())
            try:
                xy_zero_tol = float(self.output_tab.xy_zero_tol.get())
            except Exception as exc:
                raise ValueError("零值容差必须是 >= 0 的有限数值") from exc
            if not math.isfinite(xy_zero_tol) or xy_zero_tol < 0:
                raise ValueError("零值容差必须是 >= 0 的有限数值")
            if pclip_low is not None and not (0.0 <= pclip_low <= 100.0):
                raise ValueError("\u767E\u5206\u4F4D\u4E0B\u9650\u5FC5\u987B\u5728 [0,100]")
            if pclip_high is not None and not (0.0 <= pclip_high <= 100.0):
                raise ValueError("\u767E\u5206\u4F4D\u4E0A\u9650\u5FC5\u987B\u5728 [0,100]")
            if (
                pclip_low is not None
                and pclip_high is not None
                and pclip_high < pclip_low
            ):
                raise ValueError("\u767E\u5206\u4F4D\u4E0A\u9650\u5FC5\u987B >= \u4E0B\u9650")
            bin_factor = int(self.geometry_tab.bin_factor_var.get())
            if bin_factor <= 0:
                raise ValueError("Binning \u5FC5\u987B >= 1")
            gamma = float(self.geometry_tab.gamma_var.get())
            if gamma <= 0:
                raise ValueError("Gamma \u5FC5\u987B > 0")
            hot_w = int(self.geometry_tab.hot_pixel_window_var.get())
            hot_sigma = float(self.geometry_tab.hot_pixel_sigma_var.get())
            if hot_w < 3:
                raise ValueError("\u70ED\u50CF\u7D20\u7A97\u53E3\u5FC5\u987B >= 3")
            if hot_sigma <= 0:
                raise ValueError("\u70ED\u50CF\u7D20\u4FE1\u53F7\u5F3A\u5EA6\u5FC5\u987B > 0")
            png_opts = {
                "scale": self.output_tab.png_scale_var.get(),
                "vmin": self.output_tab.png_min_var.get(),
                "vmax": self.output_tab.png_max_var.get(),
                "colormap": self.output_tab.png_colormap_var.get(),
            }
            if "png" in formats:
                png_opts = validate_png_options(png_opts)
        except Exception as e:
            return messagebox.showerror(
                "\u8BBE\u7F6E\u65E0\u6548", f"\u5904\u7406\u8BBE\u7F6E\u9519\u8BEF: {e}"
            )

        xy_opts = {
            "header": self.output_tab.xy_header.get(),
            "one_based": self.output_tab.xy_one_based.get(),
            "skip_zeros": self.output_tab.xy_skip_zeros.get(),
            "zero_tol": xy_zero_tol,
            "y_axis_origin": self.output_tab.xy_y_axis_origin_var.get(),
        }
        proc_opts = {
            "dark_frame": self.dark_frame,
            "flat_frame": self.flat_frame,
            "flat_is_dark_subtracted": self.processing_tab.flat_is_dark_subtracted_var.get(),
            "roi": roi,
            "mask_frame": self.mask_frame,
            "mask_nonzero_is_invalid": self.processing_tab.mask_nonzero_is_invalid_var.get(),
            "clip_negative": self.processing_tab.clip_negative_var.get(),
            "bg_offset": float(self.processing_tab.bg_offset_var.get()),
            "min_intensity": min_i,
            "max_intensity": max_i,
            "rotate_deg": self.geometry_tab.rotate_var.get(),
            "flip_x": self.geometry_tab.flip_x_var.get(),
            "flip_y": self.geometry_tab.flip_y_var.get(),
            "bin_factor": bin_factor,
            "pclip_low": pclip_low,
            "pclip_high": pclip_high,
            "intensity_transform": self.geometry_tab.intensity_transform_var.get(),
            "gamma": gamma,
            "norm_mode": self.geometry_tab.norm_mode_var.get(),
            "hot_pixel_enable": self.geometry_tab.hot_pixel_enable_var.get(),
            "hot_pixel_window": hot_w,
            "hot_pixel_sigma": hot_sigma,
            "lossless_matrix": self.output_tab.lossless_matrix_var.get(),
        }

        if not self._run_preflight_checks(
            outroot=outroot, formats=formats, roi=roi,
            bin_factor=bin_factor, min_intensity=min_i,
            max_intensity=max_i,
        ):
            return

        args_list = [
            (
                fp, rp, root, outroot, formats,
                xy_opts, png_opts, self.io_tab.h5_path_var.get(), proc_opts,
                self.cancellation_event, self.output_tab.overwrite_var.get(),
            )
            for fp, rp in self.filelist
        ]

        self.cancellation_event.clear()
        self.is_running = True
        self._set_ui_state(running=True)
        self.log_panel.prog['maximum'] = len(self.filelist)
        self.log_panel.prog['value'] = 0
        self.start_time = datetime.now()
        self.log_panel.run_log_lines = []
        self.log(
            f"--- \u5F00\u59CB\u8F6C\u6362 {len(self.filelist)} \u4E2A\u6587\u4EF6 | "
            f"\u7EBF\u7A0B={max_workers} | "
            f"\u683C\u5F0F={','.join(formats)} ---"
        )

        self.done_count = 0
        self.stats = {"success": 0, "failed": 0, "skipped": 0, "cancelled": 0}
        self.log_panel.update_stats_display(
            self.stats, 0, len(self.filelist), self.start_time
        )

        def on_done_threadsafe(logs):
            # Bug Fix: Count per-file, not per-format
            has_success = False
            has_failed = False
            has_skipped = False
            has_cancelled = False

            for msg in logs:
                self.log(msg)
                if "SUCCESS:" in msg:
                    has_success = True
                elif "FAILED:" in msg or "ERROR" in msg:
                    has_failed = True
                elif "SKIPPED:" in msg:
                    has_skipped = True
                elif "CANCELLED" in msg or "Cancelled" in msg:
                    has_cancelled = True

            with self.count_lock:
                if has_cancelled:
                    self.stats["cancelled"] += 1
                elif has_failed:
                    self.stats["failed"] += 1
                elif has_skipped and not has_success:
                    self.stats["skipped"] += 1
                elif has_success:
                    self.stats["success"] += 1

                self.done_count += 1
                done_count = self.done_count
                stats_copy = dict(self.stats)

            self.log_panel.prog['value'] = done_count
            self.log_panel.update_stats_display(
                stats_copy, done_count, len(self.filelist), self.start_time
            )

            # Update title with progress
            progress_pct = (self.done_count / len(args_list)) * 100
            self.title(
                f"{APP_TITLE} {APP_VERSION} - {self.done_count}/{len(args_list)} "
                f"({progress_pct:.1f}%)"
            )

        def main_thread_func():
            try:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers
                ) as executor:
                    self.thread_pool = executor
                    futures = [
                        executor.submit(process_one_file, args)
                        for args in args_list
                    ]
                    for fut in concurrent.futures.as_completed(futures):
                        if fut.cancelled():
                            self.after(
                                0,
                                lambda: on_done_threadsafe(
                                    ["CANCELLED: future cancelled"]
                                ),
                            )
                            continue
                        try:
                            logs = fut.result()
                        except Exception as e:
                            logs = [f"FAILED: worker exception -> {e}"]
                        self.after(0, lambda logs=logs: on_done_threadsafe(logs))
            except Exception as e:
                self.thread_pool = None
                self.after(0, lambda e=e: self._handle_worker_thread_error(e))
                return

            self.thread_pool = None
            self.after(0, lambda: self._finalize_run(outroot))

        threading.Thread(target=main_thread_func, daemon=True).start()

    def _handle_worker_thread_error(self, exc):
        self.log(f"批处理线程异常: {exc}")
        self.is_running = False
        self._set_ui_state(running=False)
        self.title(f"{APP_TITLE} {APP_VERSION}")
        messagebox.showerror(
            "批处理异常",
            f"批处理线程发生未处理异常，任务已停止:\n{exc}",
        )

    def _finalize_run(self, outroot):
        elapsed = (
            (datetime.now() - self.start_time).total_seconds()
            if self.start_time
            else 0.0
        )
        if self.cancellation_event.is_set():
            self.log("--- \u8F6C\u6362\u5DF2\u88AB\u7528\u6237\u53D6\u6D88 ---")
        else:
            self.log("--- \u8F6C\u6362\u5B8C\u6210 ---")

        self._set_ui_state(running=False)
        self.is_running = False
        self.log_panel.update_stats_display(
            self.stats, self.done_count, len(self.filelist), self.start_time
        )
        self.title(f"{APP_TITLE} {APP_VERSION}")

        # Write run report
        report_path = None
        try:
            report_path = self._write_run_report(outroot)
            self.log(f"\u8FD0\u884C\u62A5\u544A\u5DF2\u4FDD\u5B58: {report_path}")
        except Exception as e:
            self.log(f"\u65E0\u6CD5\u4FDD\u5B58\u8FD0\u884C\u62A5\u544A: {e}")

        summary = (
            f"\u5B8C\u6210\u3002\n"
            f"\u6587\u4EF6\u6570: {len(self.filelist)}\n"
            f"\u6210\u529F: {self.stats['success']}\n"
            f"\u5931\u8D25: {self.stats['failed']}\n"
            f"\u8DF3\u8FC7: {self.stats['skipped']}\n"
            f"\u53D6\u6D88: {self.stats['cancelled']}\n"
            f"\u7528\u65F6: {elapsed:.1f}s"
        )
        if report_path:
            summary += f"\n\n\u62A5\u544A:\n{report_path}"

        if messagebox.askyesno(
            "\u6279\u91CF\u5904\u7406\u5B8C\u6210", summary + "\n\n\u6253\u5F00\u8F93\u51FA\u76EE\u5F55?"
        ):
            try:
                if sys.platform.startswith("win"):
                    os.startfile(outroot)
                elif sys.platform == "darwin":
                    import subprocess
                    subprocess.Popen(["open", outroot])
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", outroot])
            except Exception as e:
                self.log(f"\u65E0\u6CD5\u6253\u5F00\u8F93\u51FA\u76EE\u5F55: {e}")

    def _write_run_report(self, outroot):
        run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = Path(outroot) / f"run_report_{run_stamp}.txt"
        run_logs = self.log_panel.run_log_lines
        elapsed = ""
        if self.start_time:
            elapsed_sec = int((datetime.now() - self.start_time).total_seconds())
            elapsed = f"{elapsed_sec}s"

        formats = [
            fmt for fmt, var in self.output_tab.format_vars.items() if var.get()
        ]
        manual_review_logs = [
            line
            for line in run_logs
            if "REVIEW:" in line or "WARNING:" in line or "FAILED:" in line
        ]
        qc_reports = list(self.last_quality_reports)
        qc_review_reports = [
            report for report in qc_reports if report.review_required
        ]

        lines = [
            f"{APP_TITLE} {APP_VERSION}",
            f"Timestamp: {datetime.now().isoformat(timespec='seconds')}",
            f"Input Mode: {self.io_tab.input_mode_var.get()}",
            f"Input Count: {len(self.filelist)}",
            f"Output: {outroot}",
            f"Formats: {', '.join(formats)}",
            (
                "PNG Display: "
                f"scale={self.output_tab.png_scale_var.get()}, "
                f"I Min/I Max={self.output_tab.png_min_var.get()} / "
                f"{self.output_tab.png_max_var.get()}, "
                f"colormap={self.output_tab.png_colormap_var.get()}"
                if "png" in formats else "PNG Display: <not selected>"
            ),
            f"Elapsed: {elapsed}",
            f"Success: {self.stats['success']}",
            f"Failed: {self.stats['failed']}",
            f"Skipped: {self.stats['skipped']}",
            f"Cancelled: {self.stats['cancelled']}",
            "",
            "---- Processing Parameters ----",
            f"HDF5 Path: {self.io_tab.h5_path_var.get()}",
            f"ROI: {self.processing_tab.roi_var.get() or '<none>'}",
            f"Dark Frame: {self.processing_tab.dark_frame_var.get()}",
            f"Flat Frame: {self.processing_tab.flat_frame_var.get()}",
            f"Mask Frame: {self.processing_tab.mask_frame_var.get()}",
            f"Mask Nonzero Invalid: {self.processing_tab.mask_nonzero_is_invalid_var.get()}",
            f"Clip Negative: {self.processing_tab.clip_negative_var.get()}",
            f"BG Offset: {self.processing_tab.bg_offset_var.get()}",
            f"I Min/I Max: {self.processing_tab.min_intensity_var.get()} / {self.processing_tab.max_intensity_var.get()}",
            f"Rotate: {self.geometry_tab.rotate_var.get()}",
            f"Flip X/Y: {self.geometry_tab.flip_x_var.get()} / {self.geometry_tab.flip_y_var.get()}",
            f"Binning: {self.geometry_tab.bin_factor_var.get()}",
            f"Percentile Clip: {self.geometry_tab.pclip_low_var.get()} / {self.geometry_tab.pclip_high_var.get()}",
            f"Intensity Transform: {self.geometry_tab.intensity_transform_var.get()}",
            f"Gamma: {self.geometry_tab.gamma_var.get()}",
            f"Normalization: {self.geometry_tab.norm_mode_var.get()}",
            f"Hot Pixel: {self.geometry_tab.hot_pixel_enable_var.get()} "
            f"(window={self.geometry_tab.hot_pixel_window_var.get()}, "
            f"sigma={self.geometry_tab.hot_pixel_sigma_var.get()})",
            "",
            "---- Preflight QC Sample Summary ----",
        ]
        if qc_reports:
            for report in qc_reports:
                lines.append(quality_summary_line(report))
                for finding in report.findings:
                    lines.append(
                        f"  [{finding.level}] {finding.message} ({finding.basis})"
                    )
                for suggestion in report.suggestions:
                    lines.append(
                        f"  [SUGGESTION] {suggestion.action} "
                        f"Basis: {suggestion.reason}"
                    )
        else:
            lines.append("<no preflight QC sample recorded>")

        lines.extend([
            "",
            "---- Manual Review Required ----",
        ])
        if qc_review_reports or manual_review_logs:
            for report in qc_review_reports:
                lines.append(
                    f"{report.source_name}: preflight QC warning/error present"
                )
            lines.extend(manual_review_logs)
        else:
            lines.append("<none recorded>")

        lines.extend([
            "",
            "---- Logs ----",
        ])
        lines.extend(run_logs)
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path

    def cancel_conversion(self):
        """Cancel the ongoing conversion."""
        if not self.is_running and not self.thread_pool:
            return
        self.log("!!! \u8BF7\u6C42\u53D6\u6D88\uFF0C\u6B63\u5728\u7B49\u5F85\u5F53\u524D\u4EFB\u52A1\u5B8C\u6210... !!!")
        self.cancellation_event.set()
        self.log_panel.cancel_btn.config(state="disabled")

        # Bug Fix: Python 3.9+ compatibility for cancel_futures
        if self.thread_pool and hasattr(self.thread_pool, 'shutdown'):
            if sys.version_info >= (3, 9):
                self.thread_pool.shutdown(wait=False, cancel_futures=True)
            else:
                self.thread_pool.shutdown(wait=False)
            self.log("\u7EBF\u7A0B\u6C60\u5DF2\u5173\u95ED\u3002")

    # --- Config Management ---
    def _load_config(self):
        try:
            if not os.path.exists(CONFIG_FILE):
                return
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)

            io = self.io_tab
            p = self.processing_tab
            o = self.output_tab
            g = self.geometry_tab

            io.dir_var.set(config.get('input_dir', ''))
            io.outdir_var.set(config.get('output_dir', ''))
            io.input_mode_var.set(config.get('input_mode', 'directory'))

            raw_selected = config.get('selected_files', [])
            self.selected_files = [p for p in raw_selected if os.path.exists(p)]
            self.selected_common_root = None
            io._update_selected_files_summary()

            self.log_panel.max_thr_var.set(
                config.get('max_threads', os.cpu_count() or 4)
            )
            io.h5_path_var.set(config.get('h5_path', DEFAULT_H5_PATH))
            p.roi_var.set(config.get('roi', ''))

            for fmt, var in o.format_vars.items():
                var.set(config.get('formats', {}).get(fmt, False))
            o.format_vars['xycsv'].set(
                config.get('formats', {}).get('xycsv', True)
            )
            o.format_vars['npy'].set(
                config.get('formats', {}).get('npy', False)
            )

            o.xy_header.set(config.get('xy_options', {}).get('header', True))
            o.xy_one_based.set(config.get('xy_options', {}).get('one_based', False))
            o.xy_skip_zeros.set(config.get('xy_options', {}).get('skip_zeros', True))
            o.xy_zero_tol.set(config.get('xy_options', {}).get('zero_tol', 0.0))
            o.xy_y_axis_origin_var.set(
                config.get('xy_options', {}).get('y_axis_origin', 'top-left')
            )
            png_options = config.get('png_options', {})
            o.png_scale_var.set(png_options.get('scale', 'linear'))
            o.png_min_var.set(png_options.get('vmin', ''))
            o.png_max_var.set(png_options.get('vmax', ''))
            o.png_colormap_var.set(png_options.get('colormap', 'viridis'))
            o.overwrite_var.set(config.get('overwrite', False))
            o.lossless_matrix_var.set(config.get('lossless_matrix', True))

            io.workflow_preset_var.set(config.get('workflow_preset', 'Custom'))
            p.bg_offset_var.set(config.get('bg_offset', 0.0))
            p.clip_negative_var.set(config.get('clip_negative', False))
            p.mask_nonzero_is_invalid_var.set(
                config.get('mask_nonzero_is_invalid', True)
            )
            p.min_intensity_var.set(config.get('min_intensity', ''))
            p.max_intensity_var.set(config.get('max_intensity', ''))
            g.rotate_var.set(config.get('rotate_deg', '0'))
            g.flip_x_var.set(config.get('flip_x', False))
            g.flip_y_var.set(config.get('flip_y', False))
            g.bin_factor_var.set(config.get('bin_factor', 1))
            g.norm_mode_var.set(config.get('norm_mode', 'none'))
            g.pclip_low_var.set(config.get('pclip_low', ''))
            g.pclip_high_var.set(config.get('pclip_high', ''))
            g.intensity_transform_var.set(config.get('intensity_transform', 'none'))
            g.gamma_var.set(config.get('gamma', 1.0))
            g.hot_pixel_enable_var.set(config.get('hot_pixel_enable', False))
            g.hot_pixel_window_var.set(config.get('hot_pixel_window', 3))
            g.hot_pixel_sigma_var.set(config.get('hot_pixel_sigma', 8.0))

            # Q Calculator
            q_cfg = config.get('q_calc', {})
            if q_cfg:
                self.q_calc_tab.load_config(q_cfg)

            # Dark frame
            dark_path = config.get('dark_frame_path', '')
            if dark_path and os.path.exists(dark_path):
                try:
                    self.dark_frame = load_image(
                        Path(dark_path), io.h5_path_var.get()
                    )
                    p.dark_frame_var.set(dark_path)
                except Exception as e:
                    self.dark_frame = None
                    p.dark_frame_var.set("\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")
                    self.log(f"\u65E0\u6CD5\u6062\u590D\u6697\u5E27: {e}")
            else:
                self.dark_frame = None

            # Flat frame
            flat_path = config.get('flat_frame_path', '')
            if flat_path and os.path.exists(flat_path):
                try:
                    self.flat_frame = load_image(
                        Path(flat_path), io.h5_path_var.get()
                    )
                    p.flat_frame_var.set(flat_path)
                except Exception as e:
                    self.flat_frame = None
                    p.flat_frame_var.set("\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")
                    self.log(f"\u65E0\u6CD5\u6062\u590D\u5E73\u573A: {e}")
            else:
                self.flat_frame = None
            p.flat_is_dark_subtracted_var.set(
                config.get('flat_is_dark_subtracted', True)
            )

            # Mask frame
            mask_path = config.get('mask_frame_path', '')
            if mask_path and os.path.exists(mask_path):
                try:
                    self.mask_frame = load_image(
                        Path(mask_path), io.h5_path_var.get()
                    )
                    p.mask_frame_var.set(mask_path)
                except Exception as e:
                    self.mask_frame = None
                    p.mask_frame_var.set("\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")
                    self.log(f"\u65E0\u6CD5\u6062\u590D\u63A9\u819C: {e}")
            else:
                self.mask_frame = None

            self.log("\u5DF2\u4ECE config.json \u52A0\u8F7D\u8BBE\u7F6E\u3002")
        except Exception as e:
            self.log(f"\u65E0\u6CD5\u52A0\u8F7D\u914D\u7F6E: {e}")

    def _save_config(self):
        try:
            self._save_config_impl()
        except Exception as e:
            try:
                self.log(f"保存配置错误: {e}")
            except Exception:
                print(f"保存配置错误: {e}")
            try:
                messagebox.showerror(
                    "保存配置失败",
                    f"无法保存 config.json。\n\n{e}",
                )
            except Exception:
                pass

    def _save_config_impl(self):
        io = self.io_tab
        p = self.processing_tab
        o = self.output_tab
        g = self.geometry_tab

        # Bug Fix: safe path checking for dark/mask
        dark_path = p.dark_frame_var.get()
        flat_path = p.flat_frame_var.get()
        mask_path = p.mask_frame_var.get()
        none_text = "\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09"
        if dark_path == none_text or not os.path.exists(dark_path):
            dark_path = ""
        if flat_path == none_text or not os.path.exists(flat_path):
            flat_path = ""
        if mask_path == none_text or not os.path.exists(mask_path):
            mask_path = ""

        config = {
            'input_mode': io.input_mode_var.get(),
            'input_dir': io.dir_var.get(),
            'selected_files': list(self.selected_files),
            'output_dir': io.outdir_var.get(),
            'max_threads': self.log_panel.max_thr_var.get(),
            'h5_path': io.h5_path_var.get(),
            'roi': p.roi_var.get(),
            'formats': {fmt: var.get() for fmt, var in o.format_vars.items()},
            'xy_options': {
                'header': o.xy_header.get(),
                'one_based': o.xy_one_based.get(),
                'skip_zeros': o.xy_skip_zeros.get(),
                'zero_tol': o.xy_zero_tol.get(),
                'y_axis_origin': o.xy_y_axis_origin_var.get(),
            },
            'png_options': {
                'scale': o.png_scale_var.get(),
                'vmin': o.png_min_var.get(),
                'vmax': o.png_max_var.get(),
                'colormap': o.png_colormap_var.get(),
            },
            'overwrite': o.overwrite_var.get(),
            'lossless_matrix': o.lossless_matrix_var.get(),
            'workflow_preset': io.workflow_preset_var.get(),
            'bg_offset': p.bg_offset_var.get(),
            'clip_negative': p.clip_negative_var.get(),
            'mask_nonzero_is_invalid': p.mask_nonzero_is_invalid_var.get(),
            'min_intensity': p.min_intensity_var.get(),
            'max_intensity': p.max_intensity_var.get(),
            'rotate_deg': g.rotate_var.get(),
            'flip_x': g.flip_x_var.get(),
            'flip_y': g.flip_y_var.get(),
            'bin_factor': g.bin_factor_var.get(),
            'norm_mode': g.norm_mode_var.get(),
            'pclip_low': g.pclip_low_var.get(),
            'pclip_high': g.pclip_high_var.get(),
            'intensity_transform': g.intensity_transform_var.get(),
            'gamma': g.gamma_var.get(),
            'hot_pixel_enable': g.hot_pixel_enable_var.get(),
            'hot_pixel_window': g.hot_pixel_window_var.get(),
            'hot_pixel_sigma': g.hot_pixel_sigma_var.get(),
            'dark_frame_path': dark_path,
            'flat_frame_path': flat_path,
            'flat_is_dark_subtracted': p.flat_is_dark_subtracted_var.get(),
            'mask_frame_path': mask_path,
            'q_calc': self.q_calc_tab.get_config(),
            'q_calc_custom_presets': self._load_config_raw().get('q_calc_custom_presets', {}),
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            raise RuntimeError(f"保存配置错误: {e}") from e

    def _load_config_raw(self) -> dict:
        """Read config.json and return the raw dict (for Q-calculator custom presets)."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _update_config_value(self, key, value):
        """Update a single top-level key in config.json without touching other settings."""
        try:
            config = self._load_config_raw()
            config[key] = value
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def _on_close(self):
        if self.thread_pool:
            if messagebox.askyesno(
                "\u9000\u51FA",
                "\u6B63\u5728\u8F6C\u6362\u4E2D\uFF0C\u786E\u5B9A\u8981\u9000\u51FA\u5417?",
            ):
                self.cancel_conversion()
                self._save_config()
                self.destroy()
                return
            else:
                return
        self._save_config()
        self.destroy()
