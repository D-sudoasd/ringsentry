"""Tab 5: Q-Calculator -- Q <-> Pixel radius converter and detector visualizer."""

from __future__ import annotations

import re
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import numpy as np

from gui.tooltip import ToolTip
from core.diffraction_model import DiffractionModel, BEAMLINE_PRESETS

# Use ASCII-safe display strings to avoid rendering issues on Windows
_ANGSTROM = "A"      # Angstrom symbol fallback
_THETA = "2th"       # 2theta display fallback
_DEG = "deg"         # degree symbol fallback


# ---------------------------------------------------------------------------
# Embedded matplotlib plot panel
# ---------------------------------------------------------------------------

class _DetectorPlotPanel(ttk.Frame):
    """Matplotlib detector-view panel embedded inside the tab."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)

        import matplotlib
        try:
            if matplotlib.get_backend().lower() != "tkagg":
                matplotlib.use("TkAgg")
        except Exception:
            pass
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        from matplotlib.figure import Figure
        from matplotlib.patches import Rectangle, Circle

        self._Figure = Figure
        self._Rectangle = Rectangle
        self._Circle = Circle
        self._matplotlib = matplotlib

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
        q_results: list,
        selected_q: float | None = None,
        info_text: str | None = None,
    ) -> None:
        self.ax.clear()

        W = float(det_cfg["width"])
        H = float(det_cfg["height"])
        CX = float(det_cfg["center_x"])
        CY = float(det_cfg["center_y"])

        self.ax.set_xlim(0, W)
        self.ax.set_ylim(H, 0)

        rect = self._Rectangle(
            (0, 0), W, H, linewidth=1.5, edgecolor="#666666",
            facecolor="none", linestyle="--",
        )
        self.ax.add_patch(rect)
        self.ax.plot(CX, CY, "r+", markersize=12, markeredgewidth=2, label="Beam Center")

        valid_rings = [r for r in q_results if r.get("valid", False)]
        if valid_rings:
            colors = self._matplotlib.cm.viridis(np.linspace(0, 1, len(valid_rings)))
            for i, res in enumerate(valid_rings):
                r = float(res["r_px"])
                q_val = float(res["q"])

                lw = 1.6
                if selected_q is not None and abs(q_val - selected_q) <= 1e-9:
                    lw = 3.0

                circle = self._Circle(
                    (CX, CY), r, fill=False, color=colors[i],
                    linewidth=lw, alpha=0.9,
                )
                self.ax.add_patch(circle)

                lx = CX + r
                if 0.0 < lx < W and 0.0 < CY < H:
                    self.ax.text(
                        lx, CY, f"{q_val:.3g}", fontsize=8,
                        color=colors[i], fontweight="bold",
                    )

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
                bbox=dict(
                    boxstyle="round,pad=0.35", facecolor="white",
                    alpha=0.8, edgecolor="#cccccc",
                ),
            )

        self.figure.tight_layout()
        self.canvas.draw()

    def connect(self, event_name: str, callback):
        return self.canvas.mpl_connect(event_name, callback)

    def export_png(self, path: str, dpi: int = 200) -> None:
        self.figure.savefig(path, dpi=dpi, bbox_inches="tight")


# ---------------------------------------------------------------------------
# Q-Calculator Tab
# ---------------------------------------------------------------------------

class QCalculatorTab(ttk.Frame):
    """Q <-> Pixel radius calculator and detector-view visualizer."""

    Q_UNITS = ("nm^-1", "A^-1")  # ASCII-safe: avoid Unicode rendering issues

    def __init__(self, parent, app):
        super().__init__(parent, padding=4)
        self.app = app

        self.vars: dict[str, tk.StringVar] = {}
        self.entries: dict[str, ttk.Entry] = {}
        self.result_data: list[dict] = []
        self._plot_rings: list[dict] = []
        self._selected_q_nm: float | None = None
        self._syncing_energy_wl: bool = False

        self._create_widgets()

        # Load default preset
        self.load_preset("BL19B2 (SAXS)")
        self._sync_energy_from_wavelength()
        self.run_calculation()

    # ------------------------------------------------------------------ UI

    def _create_widgets(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # --- Left panel (scrollable, wider) ---
        left_outer = ttk.Frame(paned)
        paned.add(left_outer, weight=0)

        left_canvas = tk.Canvas(left_outer, width=420, highlightthickness=0)
        left_scroll = ttk.Scrollbar(left_outer, orient="vertical", command=left_canvas.yview)
        self._left_frame = ttk.Frame(left_canvas)

        self._left_frame.bind(
            "<Configure>",
            lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")),
        )
        left_canvas.create_window((0, 0), window=self._left_frame, anchor="nw")
        # Make inner frame resize with canvas width
        left_canvas.bind(
            "<Configure>",
            lambda e: left_canvas.itemconfigure(
                left_canvas.find_all()[0] if left_canvas.find_all() else 0,
                width=e.width,
            ),
        )
        left_canvas.configure(yscrollcommand=left_scroll.set)

        left_canvas.pack(side="left", fill="both", expand=True)
        left_scroll.pack(side="right", fill="y")

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        left_canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        left = self._left_frame

        # --- Right panel (plot) ---
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        self._build_left_panel(left)
        self._build_right_panel(right)

    # ---- Left panel widgets ----

    def _build_left_panel(self, left: ttk.Frame):
        # -- Preset --
        lf_preset = ttk.LabelFrame(left, text="  Beamline Preset / \u7ebf\u7ad9\u9884\u8bbe  ", padding=8)
        lf_preset.pack(fill="x", padx=4, pady=(0, 6))

        self.vars["preset"] = tk.StringVar(value=list(BEAMLINE_PRESETS.keys())[0])

        preset_row = ttk.Frame(lf_preset)
        preset_row.pack(fill="x")
        self.cb_preset = ttk.Combobox(
            preset_row, textvariable=self.vars["preset"],
            values=list(BEAMLINE_PRESETS.keys()), state="readonly", width=28,
        )
        self.cb_preset.pack(side="left", fill="x", expand=True)
        self.cb_preset.bind(
            "<<ComboboxSelected>>",
            lambda e: self.load_preset(self.vars["preset"].get()),
        )
        ToolTip(self.cb_preset, "\u8f7d\u5165\u5e38\u89c1\u7ebf\u7ad9\u51e0\u4f55\u53c2\u6570\uff0c\u53ef\u4f5c\u4e3a\u521d\u59cb\u6a21\u677f")

        btn_save_preset = ttk.Button(
            preset_row, text="\u4fdd\u5b58\u9884\u8bbe", command=self._save_custom_preset,
        )
        btn_save_preset.pack(side="right", padx=(6, 0))
        ToolTip(btn_save_preset, "\u5c06\u5f53\u524d\u53c2\u6570\u4fdd\u5b58\u4e3a\u81ea\u5b9a\u4e49\u9884\u8bbe")

        # -- Geometry --
        lf_geom = ttk.LabelFrame(left, text="  Geometry / \u51e0\u4f55\u53c2\u6570  ", padding=10)
        lf_geom.pack(fill="x", padx=4, pady=(0, 6))

        # Helper: label + entry on one row
        def _add_param(parent_frame, label_text, key, default, tooltip=""):
            row = ttk.Frame(parent_frame)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label_text, width=18, anchor="w").pack(side="left")
            ent = self._make_entry(row, key, default)
            ent.pack(side="right", fill="x", expand=True)
            if tooltip:
                ToolTip(ent, tooltip)
            return ent

        e_wl = _add_param(
            lf_geom, "Wavelength \u03bb (\u00c5):", "wavelength_A", "0.413",
            "\u8f93\u5165\u6ce2\u957f\uff0c\u4f1a\u81ea\u52a8\u8054\u52a8\u66f4\u65b0\u80fd\u91cf E",
        )
        e_wl.bind("<KeyRelease>", lambda e: self._sync_energy_from_wavelength())

        e_E = _add_param(
            lf_geom, "Energy E (keV):", "energy_keV", "30.0",
            "\u8f93\u5165\u80fd\u91cf\uff0c\u4f1a\u81ea\u52a8\u8054\u52a8\u66f4\u65b0\u6ce2\u957f",
        )
        e_E.bind("<KeyRelease>", lambda e: self._sync_wavelength_from_energy())

        ttk.Label(
            lf_geom,
            text="  >> \u8f93\u5165 \u03bb \u6216 E \u5373\u53ef\uff0c\u53e6\u4e00\u4e2a\u81ea\u52a8\u66f4\u65b0",
            foreground="#555555", font=("", 8),
        ).pack(anchor="w", pady=(0, 4))

        _add_param(lf_geom, "Distance D (mm):", "distance_mm", "3000",
                    "\u6837\u54c1\u5230\u63a2\u6d4b\u5668\u8ddd\u79bb D (mm)")
        _add_param(lf_geom, "Pixel Size p (mm):", "pixel_size_mm", "0.172",
                    "\u63a2\u6d4b\u5668\u50cf\u7d20\u5c3a\u5bf8 p (mm/px)")

        # Center + Detector size (2x2 grid)
        sep = ttk.Separator(lf_geom, orient="horizontal")
        sep.pack(fill="x", pady=6)

        frm_det = ttk.Frame(lf_geom)
        frm_det.pack(fill="x")

        # Row 0: center
        ttk.Label(frm_det, text="Center X (px):").grid(row=0, column=0, sticky="e", padx=(0, 4), pady=3)
        self._make_entry(frm_det, "center_x", "1000", width=10).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(frm_det, text="Center Y (px):").grid(row=0, column=2, sticky="e", padx=(8, 4), pady=3)
        self._make_entry(frm_det, "center_y", "1000", width=10).grid(row=0, column=3, sticky="ew", pady=3)

        # Row 1: detector size
        ttk.Label(frm_det, text="Detector W (px):").grid(row=1, column=0, sticky="e", padx=(0, 4), pady=3)
        self._make_entry(frm_det, "det_w", "2000", width=10, validator="int").grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(frm_det, text="Detector H (px):").grid(row=1, column=2, sticky="e", padx=(8, 4), pady=3)
        self._make_entry(frm_det, "det_h", "2000", width=10, validator="int").grid(row=1, column=3, sticky="ew", pady=3)

        frm_det.columnconfigure(1, weight=1)
        frm_det.columnconfigure(3, weight=1)

        ToolTip(self.entries["center_x"], "\u675f\u5fc3X (\u50cf\u7d20)\u3002\u53f3\u952e\u56fe\u50cf\u53ef\u76f4\u63a5\u8bbe\u7f6e")
        ToolTip(self.entries["center_y"], "\u675f\u5fc3Y (\u50cf\u7d20)\u3002\u53f3\u952e\u56fe\u50cf\u53ef\u76f4\u63a5\u8bbe\u7f6e")
        ToolTip(self.entries["det_w"], "\u63a2\u6d4b\u5668\u5bbd\u5ea6 (\u50cf\u7d20)")
        ToolTip(self.entries["det_h"], "\u63a2\u6d4b\u5668\u9ad8\u5ea6 (\u50cf\u7d20)")

        # Auto-detect button
        btn_detect = ttk.Button(
            lf_geom, text=">> \u4ece\u5f53\u524d\u56fe\u50cf\u83b7\u53d6\u63a2\u6d4b\u5668\u5c3a\u5bf8 <<",
            command=self._auto_detect_detector_size,
        )
        btn_detect.pack(fill="x", pady=(8, 2))
        ToolTip(btn_detect, "\u4ece\u4e3b\u7a0b\u5e8f\u5df2\u52a0\u8f7d\u7684\u7b2c\u4e00\u5f20\u56fe\u50cf\u81ea\u52a8\u586b\u5145 W/H \u548c\u675f\u5fc3")

        # -- Target Q --
        lf_calc = ttk.LabelFrame(left, text="  Target Q / \u76ee\u6807 Q  ", padding=10)
        lf_calc.pack(fill="x", padx=4, pady=(0, 6))

        unit_row = ttk.Frame(lf_calc)
        unit_row.pack(fill="x", pady=(0, 6))
        ttk.Label(unit_row, text="Q \u5355\u4f4d:", width=6).pack(side="left")
        self.vars["q_unit"] = tk.StringVar(value="nm^-1")
        self.cb_q_unit = ttk.Combobox(
            unit_row, textvariable=self.vars["q_unit"],
            values=self.Q_UNITS, state="readonly", width=8,
        )
        self.cb_q_unit.pack(side="left", padx=(0, 10))
        self.cb_q_unit.bind("<<ComboboxSelected>>", lambda e: self.run_calculation())
        ToolTip(self.cb_q_unit, "\u5207\u6362 Q \u5355\u4f4d (nm^-1 / A^-1)\u8868\u683c\u548c\u8bfb\u6570\u4f1a\u540c\u6b65\u8f6c\u6362")

        btn_help = ttk.Button(unit_row, text="\u7269\u7406\u542b\u4e49", command=self._show_physics_help)
        btn_help.pack(side="right")
        ToolTip(btn_help, "\u67e5\u770b Q / 2theta / r \u6620\u5c04\u5173\u7cfb\u8bf4\u660e")

        # Range / List sub-tabs
        nb = ttk.Notebook(lf_calc)
        nb.pack(fill="x")

        tab_range = ttk.Frame(nb, padding=8)
        tab_list = ttk.Frame(nb, padding=8)
        nb.add(tab_range, text=" Range ")
        nb.add(tab_list, text=" List ")

        # Range inputs
        frm_q = ttk.Frame(tab_range)
        frm_q.pack(fill="x")
        frm_q.columnconfigure(1, weight=1)
        frm_q.columnconfigure(3, weight=1)

        for i, (lbl, key, default) in enumerate([
            ("Start:", "q_start", "0.10"),
            ("End:", "q_end", "2.00"),
            ("Step:", "q_step", "0.10"),
        ]):
            r = i
            ttk.Label(frm_q, text=lbl, width=6).grid(row=r, column=0, sticky="e", padx=(0, 4), pady=2)
            self._make_entry(frm_q, key, default, width=12).grid(row=r, column=1, sticky="ew", padx=(0, 8), pady=2)

        ToolTip(self.entries["q_start"], "Q \u8d77\u59cb\u503c (\u5f53\u524d\u5355\u4f4d)")
        ToolTip(self.entries["q_end"], "Q \u7ec8\u6b62\u503c (\u5f53\u524d\u5355\u4f4d)")
        ToolTip(self.entries["q_step"], "Q \u6b65\u957f (\u5f53\u524d\u5355\u4f4d)")

        # List input
        ttk.Label(tab_list, text="\u6bcf\u884c\u6216\u7528\u9017\u53f7/\u7a7a\u683c\u5206\u9694\u8f93\u5165 Q:").pack(anchor="w")
        self.q_text = tk.Text(tab_list, height=5, wrap="none", font=("Consolas", 9))
        self.q_text.pack(fill="x", pady=(4, 0))
        ttk.Label(
            tab_list,
            text="(\u82e5\u975e\u7a7a\uff0c\u5217\u8868\u4f1a\u8986\u76d6 Range \u8bbe\u7f6e)",
            foreground="#666666", font=("", 8),
        ).pack(anchor="w", pady=(2, 0))

        # -- Action buttons --
        btn_row = ttk.Frame(left)
        btn_row.pack(fill="x", padx=4, pady=6)

        btn_calc = ttk.Button(btn_row, text=">>> \u8ba1\u7b97 / Calculate <<<", command=self.run_calculation)
        btn_calc.pack(side="left", fill="x", expand=True)
        ToolTip(btn_calc, "\u6267\u884c Q \u2192 \u50cf\u7d20\u534a\u5f84\u8ba1\u7b97 (\u6216\u6309 Enter)")

        ttk.Button(btn_row, text="CSV", width=5, command=self._export_csv).pack(side="left", padx=(6, 2))
        ttk.Button(btn_row, text="PNG", width=5, command=self._export_png).pack(side="left")

        # -- Results table --
        lf_res = ttk.LabelFrame(left, text="  Results / \u7ed3\u679c  ", padding=6)
        lf_res.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        cols = ("Q", "2th(deg)", "d(A)", "r(mm)", "r(px)")
        self.tree = ttk.Treeview(lf_res, columns=cols, show="headings", height=8)
        col_widths = {"Q": 72, "2th(deg)": 70, "d(A)": 72, "r(mm)": 68, "r(px)": 68}
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=col_widths.get(c, 68), anchor="center", minwidth=50)

        sb = ttk.Scrollbar(lf_res, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill=tk.BOTH, expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        ttk.Button(left, text="\u590d\u5236\u8868\u683c (Copy TSV)", command=self._copy_table).pack(fill="x", padx=4)

    # ---- Right panel (plot) ----

    def _build_right_panel(self, right: ttk.Frame):
        self.plot_panel = _DetectorPlotPanel(right)
        self.plot_panel.pack(fill=tk.BOTH, expand=True)

        self.plot_panel.connect("button_press_event", self._on_plot_click)
        self.plot_panel.connect("motion_notify_event", self._on_plot_motion)

        self.status_var = tk.StringVar(
            value="Ready. Left-click: Q readout. Right-click: set beam center."
        )
        status = tk.Label(
            right, textvariable=self.status_var,
            relief=tk.SUNKEN, anchor="w", bg="#e7e7e7", font=("Consolas", 9),
            padx=4, pady=2,
        )
        status.pack(fill="x")

    # ------------------------------------------------------------------ helpers

    def _make_entry(
        self, parent, key: str, default: str,
        width: int = 12, validator: str = "float",
    ) -> ttk.Entry:
        var = tk.StringVar(value=str(default))
        self.vars[key] = var
        vcmd = None
        if validator == "float":
            vcmd = (self.register(lambda s: self._is_float_text(s)), "%P")
        elif validator == "int":
            vcmd = (self.register(lambda s: self._is_int_text(s)), "%P")
        entry = ttk.Entry(
            parent, textvariable=var, width=width,
            validate="key", validatecommand=vcmd,
        )
        self.entries[key] = entry
        return entry

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
            raise ValueError(f"{key} must be >= 0.")
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
            raise ValueError(f"{key} must be >= 0.")
        return val

    def _q_unit_factor_to_nm(self) -> float:
        return 10.0 if self.vars["q_unit"].get() == "A^-1" else 1.0

    def _q_unit_factor_from_nm(self) -> float:
        return 0.1 if self.vars["q_unit"].get() == "A^-1" else 1.0

    # ------------------------------------------------------------------ sync

    def _sync_energy_from_wavelength(self):
        if self._syncing_energy_wl:
            return
        self._syncing_energy_wl = True
        try:
            wl = float(self.vars["wavelength_A"].get().strip())
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
            E = float(self.vars["energy_keV"].get().strip())
            if E > 0:
                wl = DiffractionModel.calc_wavelength_A(E)
                self.vars["wavelength_A"].set(f"{wl:.6g}")
        except Exception:
            pass
        finally:
            self._syncing_energy_wl = False

    # ------------------------------------------------------------------ params

    def get_params(self) -> dict | None:
        keys_float_pos = {"wavelength_A", "energy_keV", "distance_mm", "pixel_size_mm"}
        keys_float = {"center_x", "center_y", "q_start", "q_end", "q_step"}
        keys_int_pos = {"det_w", "det_h"}

        p: dict = {}
        try:
            for k in keys_float_pos:
                p[k] = self._parse_float(k, positive=True)
            for k in keys_float:
                p[k] = self._parse_float(k, positive=None)
            for k in keys_int_pos:
                p[k] = self._parse_int(k, positive=True)
        except ValueError as e:
            messagebox.showerror("Parameter Error", f"Invalid input:\n\n{e}")
            return None

        if p["q_step"] == 0:
            messagebox.showerror("Parameter Error", "q_step cannot be 0.")
            return None

        # Keep wavelength consistent with energy
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

        n_est = int(abs((q1 - q0) / dq)) + 1
        if n_est > 5000:
            raise ValueError(f"Too many points ({n_est}). Increase step or narrow range.")

        q_vals = list(np.arange(q0, q1 + dq / 2.0, dq))
        return sorted([q for q in q_vals if q >= 0])

    # ------------------------------------------------------------------ calc

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
        theta_max = math.radians(two_theta_max / 2.0)
        lam_nm = wl * 0.1
        q_max_det = (4.0 * math.pi * math.sin(theta_max)) / lam_nm if lam_nm > 0 else 0.0

        return (
            f"E={E:.3g} keV,  lambda={wl:.4g} A\n"
            f"2th_max ~ {two_theta_max:.2f} deg\n"
            f"Q_max ~ {q_max_det:.3g} nm^-1"
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
            messagebox.showerror("Q Error", f"Cannot parse Q:\n\n{e}")
            return

        qmax_ewald = DiffractionModel.qmax_nm_inv(float(p["wavelength_A"]))

        self.tree.delete(*self.tree.get_children())
        self.result_data = []
        self._plot_rings = []
        self._selected_q_nm = None

        for q_nm in q_vals_nm:
            r_mm, r_px, two_th, valid = DiffractionModel.q_to_radius(
                q_nm, float(p["wavelength_A"]), float(p["distance_mm"]),
                float(p["pixel_size_mm"]),
            )
            d_A = DiffractionModel.q_to_d_spacing(q_nm, unit="A")

            row = dict(
                q=q_nm,
                q_display=q_nm * self._q_unit_factor_from_nm(),
                two_theta=two_th,
                d_A=d_A,
                r_mm=r_mm,
                r_px=r_px,
                valid=bool(valid),
            )
            self.result_data.append(row)

            if valid:
                self.tree.insert("", "end", values=(
                    f"{row['q_display']:.4g}",
                    f"{two_th:.4f}",
                    f"{d_A:.4g}",
                    f"{r_mm:.2f}",
                    f"{r_px:.2f}",
                ))
                self._plot_rings.append(dict(q=q_nm, r_px=r_px, valid=True))

        det_cfg = dict(
            width=float(p["det_w"]), height=float(p["det_h"]),
            center_x=float(p["center_x"]), center_y=float(p["center_y"]),
        )
        info_text = self._make_info_text(p)
        self.plot_panel.draw_scene(
            det_cfg, self._plot_rings,
            selected_q=self._selected_q_nm, info_text=info_text,
        )

        valid_n = len(self._plot_rings)
        if valid_n == 0:
            self.status_var.set(
                f"No valid rings. Ewald Qmax ~ {qmax_ewald:.3g} nm^-1."
            )
        else:
            u = self.vars["q_unit"].get()
            q_disp_max = max(
                (r["q_display"] for r in self.result_data if r["valid"]),
                default=0.0,
            )
            self.status_var.set(
                f"{valid_n} rings calculated. Qmax(valid) ~ {q_disp_max:.4g} {u}"
            )

    # ------------------------------------------------------------------ interactions

    def _on_plot_click(self, event):
        if event.inaxes != self.plot_panel.ax or event.xdata is None:
            return
        p = self.get_params()
        if not p:
            return
        x, y = float(event.xdata), float(event.ydata)

        if getattr(event, "button", None) == 3:
            self.vars["center_x"].set(f"{x:.2f}")
            self.vars["center_y"].set(f"{y:.2f}")
            self.run_calculation()
            self.status_var.set(f"Beam center updated: ({x:.2f}, {y:.2f})")
            return

        q_nm, two_theta, r_mm = DiffractionModel.pixel_to_q(
            x, y,
            float(p["center_x"]), float(p["center_y"]),
            float(p["distance_mm"]), float(p["pixel_size_mm"]),
            float(p["wavelength_A"]),
        )
        d_A = DiffractionModel.q_to_d_spacing(q_nm, unit="A")
        q_disp = q_nm * self._q_unit_factor_from_nm()
        u = self.vars["q_unit"].get()
        self.status_var.set(
            f"({x:.1f}, {y:.1f}) -> Q={q_disp:.5g} {u}, "
            f"2th={two_theta:.4f} deg, d={d_A:.4g} A, r={r_mm:.2f} mm"
        )

    def _on_plot_motion(self, event):
        if event.inaxes != self.plot_panel.ax or event.xdata is None:
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
        q_nm, two_theta, _r = DiffractionModel.pixel_to_q(x, y, cx, cy, dist, px, wl)
        q_disp = q_nm * self._q_unit_factor_from_nm()
        u = self.vars["q_unit"].get()
        self.status_var.set(
            f"({x:.1f}, {y:.1f}) -> Q={q_disp:.5g} {u}, 2th={two_theta:.4f} deg"
        )

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
            center_x=float(p["center_x"]), center_y=float(p["center_y"]),
        )
        info_text = self._make_info_text(p)
        self.plot_panel.draw_scene(
            det_cfg, self._plot_rings,
            selected_q=self._selected_q_nm, info_text=info_text,
        )

    # ------------------------------------------------------------------ presets

    def load_preset(self, name: str):
        if name not in BEAMLINE_PRESETS:
            return
        p = BEAMLINE_PRESETS[name]
        for k, v in p.items():
            if k in self.vars:
                self.vars[k].set(str(v))
        self._sync_energy_from_wavelength()

    def _save_custom_preset(self):
        name = simpledialog.askstring(
            "Save Preset", "Enter preset name:", parent=self,
        )
        if not name or not name.strip():
            return
        name = name.strip()
        try:
            p = self.get_params()
            if not p:
                return
        except Exception:
            messagebox.showerror("Error", "Current parameters are invalid.")
            return

        preset_data = dict(
            wavelength_A=float(p["wavelength_A"]),
            distance_mm=float(p["distance_mm"]),
            pixel_size_mm=float(p["pixel_size_mm"]),
            center_x=float(p["center_x"]),
            center_y=float(p["center_y"]),
            det_w=int(p["det_w"]),
            det_h=int(p["det_h"]),
        )

        BEAMLINE_PRESETS[name] = preset_data
        self.cb_preset.configure(values=list(BEAMLINE_PRESETS.keys()))
        self.vars["preset"].set(name)

        custom = self.app._load_config_raw().get("q_calc_custom_presets", {})
        custom[name] = preset_data
        self.app._update_config_value("q_calc_custom_presets", custom)
        self.app.log(f"Q Calculator: preset '{name}' saved.")

    def _load_custom_presets(self, cfg: dict):
        custom = cfg.get("q_calc_custom_presets", {})
        for name, data in custom.items():
            BEAMLINE_PRESETS[name] = data
        if custom:
            self.cb_preset.configure(values=list(BEAMLINE_PRESETS.keys()))

    # ------------------------------------------------------------------ auto-detect

    def _auto_detect_detector_size(self):
        """Fill det_w/det_h from the first loaded image."""
        try:
            if not self.app.filelist:
                self.app.count_files(show_dialog=False)
            if not self.app.filelist:
                messagebox.showinfo(
                    "No Image",
                    "No loaded images found. Please select files in the I/O tab first.",
                )
                return

            from core.loader import load_image
            first_file = (
                self.app.filelist[0][0]
                if isinstance(self.app.filelist[0], tuple)
                else self.app.filelist[0]
            )
            img = load_image(first_file, self.app.io_tab.h5_path_var.get())
            h, w = img.shape
            self.vars["det_w"].set(str(w))
            self.vars["det_h"].set(str(h))
            self.vars["center_x"].set(f"{w / 2:.1f}")
            self.vars["center_y"].set(f"{h / 2:.1f}")
            self.app.log(f"Q Calculator: detected image size {w}x{h}")
            self.run_calculation()
        except Exception as e:
            messagebox.showerror("Load Failed", f"Cannot read image size: {e}")

    # ------------------------------------------------------------------ export

    def _export_csv(self):
        if not self.result_data:
            messagebox.showwarning("Empty", "No data to export.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        import pandas as pd
        df = pd.DataFrame(self.result_data)
        cols = ["q", "q_display", "two_theta", "d_A", "r_mm", "r_px", "valid"]
        df = df[[c for c in cols if c in df.columns]]
        u = self.vars["q_unit"].get()
        df.rename(columns={"q": "q_nm^-1", "q_display": f"q_{u}", "d_A": "d(A)"}, inplace=True)
        df.to_csv(path, index=False)
        self.app.log(f"Q Calculator: CSV exported -- {path}")

    def _export_png(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")],
        )
        if not path:
            return
        try:
            self.plot_panel.export_png(path)
            self.app.log(f"Q Calculator: PNG exported -- {path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _copy_table(self):
        rows = ["\t".join(["Q", "2th(deg)", "d(A)", "r(mm)", "r(px)"])]
        for item in self.tree.get_children():
            vals = self.tree.item(item, "values")
            rows.append("\t".join(str(v) for v in vals))
        text = "\n".join(rows)
        self.app.clipboard_clear()
        self.app.clipboard_append(text)
        self.status_var.set("Table copied to clipboard (TSV).")

    # ------------------------------------------------------------------ help

    def _show_physics_help(self):
        messagebox.showinfo(
            "Physics Help",
            "Detector View:\n\n"
            "1) Red '+' = beam center.\n"
            "   Right-click anywhere to set beam center.\n\n"
            "2) Each circle = constant-Q ring (Debye-Scherrer).\n"
            "   Larger radius -> larger 2theta -> larger Q.\n\n"
            "3) Relations:\n"
            "   r = distance from beam center on detector (mm)\n"
            "   tan(2th) = r / D   (D = sample-detector distance)\n"
            "   Q = 4pi sin(th) / lambda\n"
            "   d = 2pi / Q  (plane spacing)\n"
            "   lambda[A] = 12.3984 / E[keV]\n\n"
            "4) Left-click any point -> show Q, d, 2th for that pixel.\n"
        )

    # ------------------------------------------------------------------ config

    def get_config(self) -> dict:
        return {k: v.get() for k, v in self.vars.items() if k != "preset"}

    def load_config(self, cfg: dict):
        self._load_custom_presets(cfg)
        for k, v in cfg.items():
            if k == "q_calc_custom_presets":
                continue
            if k in self.vars:
                self.vars[k].set(str(v))
        self._sync_energy_from_wavelength()
