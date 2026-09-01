
# -*- coding: utf-8 -*-
"""
Advanced Q Calibrator (SAXS/XRD) — FINAL v2
------------------------------------------
Q ↔ Pixel radius calculator and detector-view visualizer for SAXS/WAXS/XRD planning.

v2 updates (requested):
1) Direct input of X-ray Energy (keV) with live sync to Wavelength (Å).
2) Clearer physical meaning on the right panel:
   - On-plot annotation (what rings/axes mean + core formulas).
   - "Physics Help" button explaining Q / 2θ / radius mapping.
   - Status bar readouts consistently report r(mm), 2θ(deg), Q(selected unit).

Interactions:
- Left click: Pixel → Q readout (status bar).
- Mouse move: live readout (status bar).
- Right click: set Beam Center (updates Center X/Y and redraws).
- Table row select: highlight that Q ring.

Dependencies: tkinter, numpy, pandas, matplotlib
"""

from __future__ import annotations

import re
import math
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import numpy as np
import pandas as pd

import matplotlib
try:
    if matplotlib.get_backend().lower() != "tkagg":
        matplotlib.use("TkAgg")
except Exception:
    pass

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle, Circle

# Allow ``python tools/q_calculator_standalone.py`` from a source checkout.
if __package__ in (None, ""):
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))

from core.diffraction_model import DiffractionModel, BEAMLINE_PRESETS


class HoverTip:
    """Simple tooltip for Tk widgets."""

    def __init__(self, widget, text: str, delay_ms: int = 280, wrap: int = 360):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.wrap = wrap
        self._job = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._job = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _show(self):
        if self._tip is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(
            tip,
            text=self.text,
            justify="left",
            wraplength=self.wrap,
            background="#fffde7",
            foreground="#1f2937",
            relief="solid",
            borderwidth=1,
            padding=(8, 6),
        )
        label.pack(fill="both", expand=True)
        self._tip = tip

    def _hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


# ----------------------------
# Plot panel
# ----------------------------
class PlotPanel(ttk.Frame):
    def __init__(self, parent: tk.Widget):
        super().__init__(parent)

        self.figure = Figure(figsize=(5.6, 4.4), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_aspect("equal")

        top = ttk.Frame(self)
        top.pack(fill=tk.X)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.toolbar = NavigationToolbar2Tk(self.canvas, top)
        self.toolbar.update()

        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def draw_scene(
        self,
        det_cfg: dict,
        q_results: list[dict],
        selected_q: float | None = None,
        info_text: str | None = None,
    ) -> None:
        self.ax.clear()

        W = float(det_cfg["width"])
        H = float(det_cfg["height"])
        CX = float(det_cfg["center_x"])
        CY = float(det_cfg["center_y"])

        # image-like coordinates
        self.ax.set_xlim(0, W)
        self.ax.set_ylim(H, 0)

        rect = Rectangle((0, 0), W, H, linewidth=1.5, edgecolor="#666666",
                         facecolor="none", linestyle="--")
        self.ax.add_patch(rect)

        self.ax.plot(CX, CY, "r+", markersize=12, markeredgewidth=2, label="Beam Center")

        valid_rings = [r for r in q_results if r.get("valid", False)]
        if valid_rings:
            colors = matplotlib.cm.viridis(np.linspace(0, 1, len(valid_rings)))
            for i, res in enumerate(valid_rings):
                r = float(res["r_px"])
                q_val = float(res["q"])

                lw = 1.6
                if selected_q is not None and abs(q_val - selected_q) <= 1e-9:
                    lw = 3.0

                circle = Circle((CX, CY), r, fill=False, color=colors[i], linewidth=lw, alpha=0.9)
                self.ax.add_patch(circle)

                lx = CX + r
                if 0.0 < lx < W and 0.0 < CY < H:
                    self.ax.text(lx, CY, f"{q_val:.3g}", fontsize=8, color=colors[i], fontweight="bold")

        self.ax.set_title("Detector View (constant-Q rings)", fontsize=10)
        self.ax.set_xlabel("Pixel X")
        self.ax.set_ylabel("Pixel Y")
        self.ax.legend(loc="upper right", fontsize="small")

        if info_text:
            self.ax.text(
                0.02, 0.98, info_text,
                transform=self.ax.transAxes,
                va="top", ha="left",
                fontsize=8, color="#333333",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.8, edgecolor="#cccccc")
            )

        self.figure.tight_layout()
        self.canvas.draw()

    def connect(self, event_name: str, callback):
        return self.canvas.mpl_connect(event_name, callback)

    def export_png(self, path: str, dpi: int = 200) -> None:
        self.figure.savefig(path, dpi=dpi, bbox_inches="tight")


# ----------------------------
# Main app
# ----------------------------
class AdvancedQApp(tk.Tk):
    Q_UNITS = ("nm^-1", "Å^-1")

    def __init__(self):
        super().__init__()

        self.title("Advanced Q Calibrator Pro (FINAL v2)")
        self.geometry("1200x780")
        self.minsize(1080, 700)

        self.style = ttk.Style(self)
        self._init_styles()

        self.vars: dict[str, tk.StringVar] = {}
        self.entries: dict[str, ttk.Entry] = {}
        self.result_data: list[dict] = []
        self._plot_rings: list[dict] = []
        self._selected_q_nm: float | None = None
        self._help_tips: list[HoverTip] = []

        self._syncing_energy_wl = False

        self._setup_ui()
        self._install_widget_hints()
        self._bind_shortcuts()

        self.load_preset("BL19B2 (SAXS)")
        self._sync_energy_from_wavelength()
        self.run_calculation()

    def _init_styles(self):
        try:
            self.style.configure("Invalid.TEntry", fieldbackground="#ffe6e6")
        except Exception:
            pass

    @staticmethod
    def _is_float_text(s: str) -> bool:
        if s == "":
            return True
        try:
            float(s)
            return True
        except Exception:
            return bool(re.fullmatch(r"[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d*)?", s)) or s in {"-", "+", ".", "-.", "+."}

    @staticmethod
    def _is_int_text(s: str) -> bool:
        return s == "" or bool(re.fullmatch(r"\d+", s))

    def _make_entry(self, parent, key: str, default: str, width: int = 12, validator: str = "float") -> ttk.Entry:
        var = tk.StringVar(value=str(default))
        self.vars[key] = var

        vcmd = None
        if validator == "float":
            vcmd = (self.register(lambda s: self._is_float_text(s)), "%P")
        elif validator == "int":
            vcmd = (self.register(lambda s: self._is_int_text(s)), "%P")

        entry = ttk.Entry(parent, textvariable=var, width=width, validate="key", validatecommand=vcmd)
        self.entries[key] = entry
        return entry

    def _set_entry_valid(self, key: str, valid: bool):
        entry = self.entries.get(key)
        if not entry:
            return
        entry.configure(style="TEntry" if valid else "Invalid.TEntry")

    def _attach_tip(self, widget, text: str):
        if widget is None or not text:
            return
        try:
            self._help_tips.append(HoverTip(widget, text))
        except Exception:
            pass

    def _install_widget_hints(self):
        self._attach_tip(getattr(self, "cb_preset", None), "载入常见线站几何参数，可作为初始模板。")
        self._attach_tip(getattr(self, "cb_q_unit", None), "切换 Q 单位（nm^-1 / Å^-1），表格和读数会同步转换。")
        self._attach_tip(self.entries.get("wavelength_A"), "输入波长 λ（Å），会自动联动更新能量 E。")
        self._attach_tip(self.entries.get("energy_keV"), "输入能量 E（keV），会自动联动更新波长 λ。")
        self._attach_tip(self.entries.get("distance_mm"), "样品到探测器距离 D（mm）。")
        self._attach_tip(self.entries.get("pixel_size_mm"), "探测器像素尺寸 p（mm/px）。")
        self._attach_tip(self.entries.get("center_x"), "束心 X（像素）。右键图像可直接设置。")
        self._attach_tip(self.entries.get("center_y"), "束心 Y（像素）。右键图像可直接设置。")
        self._attach_tip(self.entries.get("det_w"), "探测器宽度（像素）。")
        self._attach_tip(self.entries.get("det_h"), "探测器高度（像素）。")
        self._attach_tip(self.entries.get("q_start"), "Q 起始值（当前单位）。")
        self._attach_tip(self.entries.get("q_end"), "Q 终止值（当前单位）。")
        self._attach_tip(self.entries.get("q_step"), "Q 步长（当前单位）。范围模式会按该步长生成采样点。")
        self._attach_tip(getattr(self, "q_text", None), "列表模式: 每行或空格/逗号分隔输入 Q。非空时会覆盖 Range 页。")

    def _parse_float(self, key: str, positive: bool | None = None) -> float:
        s = self.vars[key].get().strip()
        try:
            val = float(s)
        except Exception:
            raise ValueError(f"{key} is not a valid number.")
        if not math.isfinite(val):
            raise ValueError(f"{key} must be finite.")
        if positive is True and val <= 0:
            raise ValueError(f"{key} must be > 0.")
        if positive is False and val < 0:
            raise ValueError(f"{key} must be ≥ 0.")
        return val

    def _parse_int(self, key: str, positive: bool | None = None) -> int:
        s = self.vars[key].get().strip()
        if s == "":
            raise ValueError(f"{key} is empty.")
        try:
            raw = float(s)
        except Exception:
            raise ValueError(f"{key} is not a valid integer.")
        if not math.isfinite(raw):
            raise ValueError(f"{key} must be finite.")
        if abs(raw - round(raw)) > 1e-9:
            raise ValueError(f"{key} must be an integer value.")
        val = int(round(raw))
        if positive is True and val <= 0:
            raise ValueError(f"{key} must be > 0.")
        if positive is False and val < 0:
            raise ValueError(f"{key} must be ≥ 0.")
        return val

    def _setup_ui(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left = ttk.Frame(paned, padding=10)
        right = ttk.Frame(paned)
        paned.add(left, weight=0)
        paned.add(right, weight=1)

        lf_preset = ttk.LabelFrame(left, text="Beamline Preset / 预设", padding=10)
        lf_preset.pack(fill="x", pady=6)

        self.vars["preset"] = tk.StringVar(value=list(BEAMLINE_PRESETS.keys())[0])
        self.cb_preset = ttk.Combobox(
            lf_preset, textvariable=self.vars["preset"], values=list(BEAMLINE_PRESETS.keys()), state="readonly"
        )
        self.cb_preset.pack(fill="x")
        self.cb_preset.bind("<<ComboboxSelected>>", lambda e: self.load_preset(self.vars["preset"].get()))

        lf_geom = ttk.LabelFrame(left, text="Geometry / 几何参数", padding=10)
        lf_geom.pack(fill="x", pady=6)

        row = ttk.Frame(lf_geom)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Wavelength λ (Å):", width=18).pack(side="left")
        e_wl = self._make_entry(row, "wavelength_A", "0.413", validator="float")
        e_wl.pack(side="right", fill="x", expand=True)
        e_wl.bind("<KeyRelease>", lambda e: self._sync_energy_from_wavelength())

        rowE = ttk.Frame(lf_geom)
        rowE.pack(fill="x", pady=2)
        ttk.Label(rowE, text="Energy E (keV):", width=18).pack(side="left")
        e_E = self._make_entry(rowE, "energy_keV", "30.0", validator="float")
        e_E.pack(side="right", fill="x", expand=True)
        e_E.bind("<KeyRelease>", lambda e: self._sync_wavelength_from_energy())

        ttk.Label(lf_geom, text="Tip: type either λ or E; the other updates automatically.", foreground="#555555").pack(anchor="w", pady=(2, 6))

        for label, key, default in [
            ("Sample Dist D (mm):", "distance_mm", "3000"),
            ("Pixel Size p (mm):", "pixel_size_mm", "0.172"),
        ]:
            row = ttk.Frame(lf_geom)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=18).pack(side="left")
            self._make_entry(row, key, default, validator="float").pack(side="right", fill="x", expand=True)

        frm_det = ttk.Frame(lf_geom)
        frm_det.pack(fill="x", pady=(6, 2))

        def add_det(label, key, default, r, c, validator):
            ttk.Label(frm_det, text=label).grid(row=r, column=c * 2, sticky="e", padx=2, pady=2)
            ent = self._make_entry(frm_det, key, default, width=10, validator=validator)
            ent.grid(row=r, column=c * 2 + 1, sticky="w", padx=2, pady=2)

        add_det("Center X (px):", "center_x", "1000", 0, 0, "float")
        add_det("Center Y (px):", "center_y", "1000", 0, 1, "float")
        add_det("Det W (px):", "det_w", "2000", 1, 0, "int")
        add_det("Det H (px):", "det_h", "2000", 1, 1, "int")

        lf_calc = ttk.LabelFrame(left, text="Target Q", padding=10)
        lf_calc.pack(fill="x", pady=6)

        unit_row = ttk.Frame(lf_calc)
        unit_row.pack(fill="x", pady=(0, 6))
        ttk.Label(unit_row, text="Q unit:", width=10).pack(side="left")
        self.vars["q_unit"] = tk.StringVar(value="nm^-1")
        self.cb_q_unit = ttk.Combobox(
            unit_row, textvariable=self.vars["q_unit"], values=self.Q_UNITS, state="readonly", width=8
        )
        self.cb_q_unit.pack(side="left")
        self.cb_q_unit.bind("<<ComboboxSelected>>", lambda e: self.run_calculation())
        ttk.Button(unit_row, text="Physics Help / 物理含义", command=self.show_physics_help).pack(side="right")

        nb = ttk.Notebook(lf_calc)
        nb.pack(fill="x", expand=False)

        tab_range = ttk.Frame(nb, padding=8)
        tab_list = ttk.Frame(nb, padding=8)
        nb.add(tab_range, text="Range")
        nb.add(tab_list, text="List")

        frm_q = ttk.Frame(tab_range)
        frm_q.pack(fill="x")
        for label, key, default, r, c in [
            ("Start:", "q_start", "0.10", 0, 0),
            ("End:", "q_end", "2.00", 0, 1),
            ("Step:", "q_step", "0.10", 1, 0),
        ]:
            ttk.Label(frm_q, text=label).grid(row=r, column=c * 2, sticky="e", padx=2, pady=2)
            self._make_entry(frm_q, key, default, width=10, validator="float").grid(row=r, column=c * 2 + 1, sticky="w", padx=2, pady=2)

        ttk.Label(tab_list, text="One Q per line (or separated by comma/space):").pack(anchor="w")
        self.q_text = tk.Text(tab_list, height=6, wrap="none")
        self.q_text.pack(fill="x", expand=False, pady=(4, 0))
        ttk.Label(tab_list, text="(If non-empty, this list overrides the Range tab.)", foreground="#666666").pack(anchor="w", pady=(4, 0))

        btn_row = ttk.Frame(left)
        btn_row.pack(fill="x", pady=(4, 4))
        ttk.Button(btn_row, text="▶ CALCULATE / 计算", command=self.run_calculation).pack(side="left", fill="x", expand=True)
        ttk.Button(btn_row, text="Export CSV", command=self.export_csv).pack(side="left", padx=6)
        ttk.Button(btn_row, text="Export PNG", command=self.export_png).pack(side="left")

        lf_res = ttk.LabelFrame(left, text="Results Table", padding=10)
        lf_res.pack(fill=tk.BOTH, expand=True, pady=6)

        cols = ("Q", "2Theta", "R_mm", "R_px")
        self.tree = ttk.Treeview(lf_res, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=86 if c == "Q" else 72, anchor="center")

        sb = ttk.Scrollbar(lf_res, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill=tk.BOTH, expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        ttk.Button(left, text="Copy Table (TSV)", command=self.copy_table).pack(fill="x", pady=(0, 6))

        self.plot_panel = PlotPanel(right)
        self.plot_panel.pack(fill=tk.BOTH, expand=True)
        self.plot_panel.connect("button_press_event", self._on_plot_click)
        self.plot_panel.connect("motion_notify_event", self._on_plot_motion)

        self.status_var = tk.StringVar(value="Ready. Left click: Q readout. Right click: set beam center.")
        status = tk.Label(right, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w", bg="#e7e7e7")
        status.pack(fill="x")

    def _bind_shortcuts(self):
        self.bind("<Return>", lambda e: self.run_calculation())
        self.bind("<Control-c>", lambda e: self.copy_table())

    def _sync_energy_from_wavelength(self):
        if self._syncing_energy_wl:
            return
        self._syncing_energy_wl = True
        try:
            wl_txt = self.vars["wavelength_A"].get().strip()
            wl = float(wl_txt)
            if wl > 0:
                E = DiffractionModel.calc_energy_kev(wl)
                self.vars["energy_keV"].set(f"{E:.6g}")
        except Exception:
            pass
        finally:
            self._syncing_energy_wl = False

    def _sync_wavelength_from_energy(self):
        if self._syncing_energy_wl:
            return
        self._syncing_energy_wl = True
        try:
            E_txt = self.vars["energy_keV"].get().strip()
            E = float(E_txt)
            if E > 0:
                wl = DiffractionModel.calc_wavelength_A(E)
                self.vars["wavelength_A"].set(f"{wl:.6g}")
        except Exception:
            pass
        finally:
            self._syncing_energy_wl = False

    def _q_unit_factor_to_nm(self) -> float:
        return 10.0 if self.vars["q_unit"].get() == "Å^-1" else 1.0

    def _q_unit_factor_from_nm(self) -> float:
        return 0.1 if self.vars["q_unit"].get() == "Å^-1" else 1.0

    def get_params(self) -> dict | None:
        for k in self.entries:
            self._set_entry_valid(k, True)

        keys_float_pos = {"wavelength_A", "energy_keV", "distance_mm", "pixel_size_mm"}
        keys_float = {"center_x", "center_y", "q_start", "q_end", "q_step"}
        keys_int_pos = {"det_w", "det_h"}

        p: dict[str, float | int] = {}
        try:
            for k in keys_float_pos:
                p[k] = self._parse_float(k, positive=True)
            for k in keys_float:
                p[k] = self._parse_float(k, positive=None)
            for k in keys_int_pos:
                p[k] = self._parse_int(k, positive=True)
        except ValueError as e:
            msg = str(e)
            bad_key = msg.split()[0] if msg else ""
            if bad_key in self.entries:
                self._set_entry_valid(bad_key, False)
                self.entries[bad_key].focus_set()
            messagebox.showerror("Parameter Error", "输入无效，请检查数值。\n\n" + msg)
            return None

        if p["q_step"] == 0:
            self._set_entry_valid("q_step", False)
            messagebox.showerror("Parameter Error", "q_step 不能为 0。")
            return None

        # Keep wavelength consistent with energy if they diverge materially
        wl = float(p["wavelength_A"])
        E = float(p["energy_keV"])
        wl_from_E = DiffractionModel.calc_wavelength_A(E)
        if wl_from_E > 0 and abs(wl - wl_from_E) / wl_from_E > 5e-3:
            self.vars["wavelength_A"].set(f"{wl_from_E:.6g}")
            p["wavelength_A"] = wl_from_E

        return p

    def _parse_q_list_or_range(self, p: dict) -> list[float]:
        text = self.q_text.get("1.0", "end").strip()
        factor_to_nm = self._q_unit_factor_to_nm()

        if text:
            parts = re.split(r"[\s,;]+", text)
            q_vals = []
            for part in parts:
                if not part:
                    continue
                v = float(part) * factor_to_nm
                if not math.isfinite(v):
                    raise ValueError("Q list contains non-finite value.")
                if v < 0:
                    raise ValueError("Q must be >= 0.")
                q_vals.append(v)
            if len(q_vals) > 5000:
                raise ValueError("Too many Q values in list (max 5000).")
            return sorted(set(q_vals))

        q0 = float(p["q_start"]) * factor_to_nm
        q1 = float(p["q_end"]) * factor_to_nm
        dq = float(p["q_step"]) * factor_to_nm

        if dq == 0:
            raise ValueError("q_step cannot be 0.")
        if (q1 - q0) * dq < 0:
            dq = -dq

        max_points = 5000
        n_est = int(abs((q1 - q0) / dq)) + 1
        if n_est > max_points:
            raise ValueError(f"Too many points ({n_est}). Increase step or narrow range (≤{max_points}).")

        q_vals = list(np.arange(q0, q1 + dq / 2.0, dq))
        return sorted([q for q in q_vals if q >= 0])

    def _make_info_text(self, p: dict) -> str:
        wl = float(p["wavelength_A"])
        E = DiffractionModel.calc_energy_kev(wl) if wl > 0 else 0.0
        D = float(p["distance_mm"])
        pix = float(p["pixel_size_mm"])
        det_w = float(p["det_w"])
        det_h = float(p["det_h"])
        cx = float(p["center_x"])
        cy = float(p["center_y"])

        rmax_px = DiffractionModel.max_radius_px(det_w, det_h, cx, cy)
        rmax_mm = rmax_px * pix
        two_theta_max = math.degrees(math.atan2(rmax_mm, D)) if D > 0 else 0.0
        q_max_det = DiffractionModel.detector_qmax_nm(
            det_w, det_h, cx, cy, D, pix, wl,
        )

        return (
            "Meaning:\n"
            " red '+' = beam center\n"
            " circles = constant-Q rings\n"
            " tan(2θ)=r/D,  Q=4πsinθ/λ\n"
            f" E={E:.3g} keV,  λ={wl:.4g} Å\n"
            f" 2θ_max≈{two_theta_max:.2f}°, Q_max≈{q_max_det:.3g} nm⁻¹"
        )

    def run_calculation(self):
        p = self.get_params()
        if not p:
            return

        try:
            q_vals_nm = self._parse_q_list_or_range(p)
            if not q_vals_nm:
                raise ValueError("Q list is empty.")
        except Exception as e:
            messagebox.showerror("Q Error", f"无法解析 Q。\n\nDetails: {e}")
            return

        qmax_ewald = DiffractionModel.qmax_nm_inv(float(p["wavelength_A"]))

        self.tree.delete(*self.tree.get_children())
        self.result_data = []
        self._plot_rings = []
        self._selected_q_nm = None

        for q_nm in q_vals_nm:
            r_mm, r_px, two_th, valid = DiffractionModel.q_to_radius(
                q_nm, float(p["wavelength_A"]), float(p["distance_mm"]), float(p["pixel_size_mm"])
            )
            row = dict(
                q=q_nm,
                q_display=q_nm * self._q_unit_factor_from_nm(),
                two_theta=two_th,
                r_mm=r_mm,
                r_px=r_px,
                valid=bool(valid),
            )
            self.result_data.append(row)

            if valid:
                self.tree.insert("", "end", values=(
                    f"{row['q_display']:.4g}",
                    f"{two_th:.4f}",
                    f"{r_mm:.2f}",
                    f"{r_px:.2f}",
                ))
                self._plot_rings.append(dict(q=q_nm, r_px=r_px, valid=True))

        det_cfg = dict(
            width=float(p["det_w"]), height=float(p["det_h"]),
            center_x=float(p["center_x"]), center_y=float(p["center_y"])
        )

        info_text = self._make_info_text(p)
        self.plot_panel.draw_scene(det_cfg, self._plot_rings, selected_q=self._selected_q_nm, info_text=info_text)

        valid_n = len(self._plot_rings)
        if valid_n == 0:
            self.status_var.set(f"No valid rings in view. Check geometry. Ewald Qmax≈{qmax_ewald:.3g} nm^-1.")
        else:
            u = self.vars["q_unit"].get()
            q_disp_max = max([r["q_display"] for r in self.result_data if r["valid"]], default=0.0)
            max_two = max([r["two_theta"] for r in self.result_data if r["valid"]], default=0.0)
            warn = ""
            if max(q_vals_nm) > qmax_ewald * 1.0001:
                warn = " (Some Q exceed Ewald limit; invalid.)"
            self.status_var.set(
                f"Calculated {valid_n} rings. Qmax(valid)≈{q_disp_max:.4g} {u}, 2θmax≈{max_two:.3f}°.{warn} "
                "Left click readout; Right click set center."
            )

    def _on_plot_click(self, event):
        if event.inaxes != self.plot_panel.ax or event.xdata is None or event.ydata is None:
            return

        p = self.get_params()
        if not p:
            return

        x, y = float(event.xdata), float(event.ydata)

        if getattr(event, "button", None) == 3:
            self.vars["center_x"].set(f"{x:.2f}")
            self.vars["center_y"].set(f"{y:.2f}")
            self.run_calculation()
            self.status_var.set(f"Beam center updated to (x={x:.2f}, y={y:.2f}).")
            return

        q_nm, two_theta, r_mm = DiffractionModel.pixel_to_q(
            x, y,
            float(p["center_x"]), float(p["center_y"]),
            float(p["distance_mm"]), float(p["pixel_size_mm"]),
            float(p["wavelength_A"]),
        )
        q_disp = q_nm * self._q_unit_factor_from_nm()
        u = self.vars["q_unit"].get()
        self.status_var.set(f"Selected x={x:.1f}, y={y:.1f} → r={r_mm:.2f} mm, 2θ={two_theta:.4f}°, Q={q_disp:.5g} {u}")

    def _on_plot_motion(self, event):
        if event.inaxes != self.plot_panel.ax or event.xdata is None or event.ydata is None:
            return
        try:
            wl = float(self.vars["wavelength_A"].get())
            dist = float(self.vars["distance_mm"].get())
            px = float(self.vars["pixel_size_mm"].get())
            cx = float(self.vars["center_x"].get())
            cy = float(self.vars["center_y"].get())
            if wl <= 0 or dist <= 0 or px <= 0:
                return
        except Exception:
            return
        x, y = float(event.xdata), float(event.ydata)
        q_nm, two_theta, _r_mm = DiffractionModel.pixel_to_q(x, y, cx, cy, dist, px, wl)
        q_disp = q_nm * self._q_unit_factor_from_nm()
        u = self.vars["q_unit"].get()
        self.status_var.set(f"Cursor x={x:.1f}, y={y:.1f} → Q={q_disp:.5g} {u}, 2θ={two_theta:.4f}°")

    def _on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            self._selected_q_nm = None
            return
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(self._plot_rings):
            self._selected_q_nm = float(self._plot_rings[idx]["q"])
        else:
            self._selected_q_nm = None

        p = self.get_params()
        if not p:
            return
        det_cfg = dict(
            width=float(p["det_w"]), height=float(p["det_h"]),
            center_x=float(p["center_x"]), center_y=float(p["center_y"])
        )
        info_text = self._make_info_text(p)
        self.plot_panel.draw_scene(det_cfg, self._plot_rings, selected_q=self._selected_q_nm, info_text=info_text)

    def export_csv(self):
        if not self.result_data:
            messagebox.showwarning("Empty", "No data to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        df = pd.DataFrame(self.result_data)
        df = df[["q", "q_display", "two_theta", "r_mm", "r_px", "valid"]]
        df.rename(columns={"q": "q_nm^-1", "q_display": f"q_{self.vars['q_unit'].get()}"}, inplace=True)
        df.to_csv(path, index=False)
        messagebox.showinfo("Success", f"Saved CSV:\n{path}")

    def export_png(self):
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not path:
            return
        try:
            self.plot_panel.export_png(path)
            messagebox.showinfo("Success", f"Saved PNG:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export PNG.\n\n{e}")

    def copy_table(self):
        rows = []
        rows.append("\t".join(["Q", "2Theta", "R_mm", "R_px"]))
        for item in self.tree.get_children():
            vals = self.tree.item(item, "values")
            rows.append("\t".join(str(v) for v in vals))
        text = "\n".join(rows)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Table copied to clipboard (TSV).")

    def show_physics_help(self):
        msg = (
            "右侧 Detector View 的物理含义：\n\n"
            "1) 红色“+”是直射光（beam center）。\n"
            "   你右键点击任何位置可把那里设为 beam center。\n\n"
            "2) 每一条圆环表示“相同 Q”的散射位置（德拜-谢乐环）。\n"
            "   环的半径越大 → 散射角 2θ 越大 → Q 越大。\n\n"
            "3) 几何关系：\n"
            "   r = 探测器上到 beam center 的距离 (mm)\n"
            "   tan(2θ) = r / D   (D = sample-detector distance)\n"
            "   Q = 4π sin(θ) / λ\n"
            "   λ[Å]=12.3984/E[keV]\n\n"
            "4) 图上坐标是像素(px)，但状态栏会给 r(mm)、2θ(°)、Q。\n"
            "   左键点击任意点 → 显示该点对应 Q。\n"
        )
        messagebox.showinfo("Physics Help / 物理含义", msg)

    def load_preset(self, name: str):
        if name not in BEAMLINE_PRESETS:
            return
        p = BEAMLINE_PRESETS[name]
        for k, v in p.items():
            if k in self.vars:
                self.vars[k].set(str(v))
        self._sync_energy_from_wavelength()
        self.run_calculation()


def main():
    app = AdvancedQApp()
    app.mainloop()


if __name__ == "__main__":
    main()
