"""Tab 3: Output formats and XY options."""

import tkinter as tk
from tkinter import ttk

from gui.layout import ScrollableFrame
from gui.tooltip import ToolTip
from core.constants import FORMAT_DESCRIPTIONS
from core.plot_style import (
    PLOT_PRESET_LABELS,
    PUBLICATION_COLORMAPS,
    get_plot_preset,
)


class OutputTab(ttk.Frame):
    """Output format selection tab."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=0)
        self.app = app
        self._create_widgets()

    def _create_widgets(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.scrollable = ScrollableFrame(self, padding=15)
        self.scrollable.grid(row=0, column=0, sticky="nsew")
        self.body = self.scrollable.body
        body = self.body
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # --- Matrix Formats (left column) ---
        matrix_frame = ttk.LabelFrame(body, text="\u77E9\u9635\u683C\u5F0F", padding=10)
        matrix_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 10))

        self.format_vars = {
            'edf': tk.BooleanVar(),
            'tif': tk.BooleanVar(),
            'npy': tk.BooleanVar(),
            'png': tk.BooleanVar(),
            'dat': tk.BooleanVar(),
            'csv': tk.BooleanVar(),
            'xycsv': tk.BooleanVar(value=True),
            'xydat': tk.BooleanVar(),
        }
        self.plot_export_preset_var = tk.StringVar(value="Raw inspection")

        matrix_formats = [
            ('edf', 'EDF'),
            ('tif', 'TIFF'),
            ('npy', 'NPY (NumPy)'),
        ]
        for i, (key, label) in enumerate(matrix_formats):
            cb = ttk.Checkbutton(
                matrix_frame, text=label, variable=self.format_vars[key]
            )
            cb.grid(row=i, column=0, sticky="w", pady=2)
            ToolTip(cb, FORMAT_DESCRIPTIONS.get(key, ""))

        # --- Display PNG Export ---
        png_frame = ttk.LabelFrame(body, text="PNG \u663E\u793A\u56FE", padding=10)
        png_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        png_frame.columnconfigure(1, weight=1)
        png_frame.columnconfigure(3, weight=1)

        self.png_cb = ttk.Checkbutton(
            png_frame,
            text="PNG (\u6279\u91CF\u663E\u793A\u56FE)",
            variable=self.format_vars['png'],
            command=self._sync_png_controls,
        )
        self.png_cb.grid(row=0, column=0, sticky="w", pady=2)
        ToolTip(self.png_cb, FORMAT_DESCRIPTIONS.get('png', ""))

        ttk.Label(png_frame, text="\u663E\u793A\u6620\u5C04:").grid(
            row=0, column=1, sticky="e", padx=(12, 5), pady=2
        )
        self.png_scale_var = tk.StringVar(value="linear")
        self.png_scale_cb = ttk.Combobox(
            png_frame,
            values=["linear", "log"],
            textvariable=self.png_scale_var,
            state="readonly",
            width=8,
        )
        self.png_scale_cb.grid(row=0, column=2, sticky="w", pady=2)
        ToolTip(
            self.png_scale_cb,
            "PNG \u663E\u793A\u5F3A\u5EA6\u5F62\u5F0F:\n"
            "- linear: \u7EBF\u6027\u6620\u5C04\u5230 0-255\n"
            "- log: \u5728\u56FA\u5B9A\u8303\u56F4\u5185\u505A log10(1 + I - Imin) \u663E\u793A\u538B\u7F29",
        )

        ttk.Label(png_frame, text="I Min:").grid(
            row=1, column=0, sticky="w", pady=(6, 2)
        )
        self.png_min_var = tk.StringVar()
        self.png_min_entry = ttk.Entry(
            png_frame, textvariable=self.png_min_var, width=12
        )
        self.png_min_entry.grid(
            row=1, column=1, sticky="w", padx=(5, 12), pady=(6, 2)
        )
        ToolTip(
            self.png_min_entry,
            "\u5904\u7406\u540E\u5F3A\u5EA6\u7684 PNG \u663E\u793A\u4E0B\u9650\u3002"
            "\u9009\u62E9 PNG \u65F6\u5FC5\u586B\uFF0C\u53EA\u5F71\u54CD PNG\u3002",
        )

        ttk.Label(png_frame, text="I Max:").grid(
            row=1, column=2, sticky="e", padx=(12, 5), pady=(6, 2)
        )
        self.png_max_var = tk.StringVar()
        self.png_max_entry = ttk.Entry(
            png_frame, textvariable=self.png_max_var, width=12
        )
        self.png_max_entry.grid(row=1, column=3, sticky="w", pady=(6, 2))
        ToolTip(
            self.png_max_entry,
            "\u5904\u7406\u540E\u5F3A\u5EA6\u7684 PNG \u663E\u793A\u4E0A\u9650\u3002"
            "\u540C\u4E00\u6279\u56FE\u5EFA\u8BAE\u4F7F\u7528\u56FA\u5B9A\u8303\u56F4\u4FBF\u4E8E\u6BD4\u8F83\u3002",
        )
        self.png_colormap_var = tk.StringVar(value="viridis")
        ttk.Label(png_frame, text="\u989C\u8272\u6620\u5C04:").grid(
            row=2, column=0, sticky="w", pady=(6, 2)
        )
        self.png_colormap_cb = ttk.Combobox(
            png_frame,
            values=list(PUBLICATION_COLORMAPS),
            textvariable=self.png_colormap_var,
            state="readonly",
            width=10,
        )
        self.png_colormap_cb.grid(row=2, column=1, sticky="w", padx=(5, 12), pady=(6, 2))
        ToolTip(
            self.png_colormap_cb,
            "\u79D1\u5B66\u56FE\u50CF\u989C\u8272\u6620\u5C04\u3002"
            "\u9ED8\u8BA4 viridis\uFF1B\u907F\u514D\u5F69\u8679\u8272\u56FE\u5E26\u6765\u7684\u89C6\u89C9\u504F\u5DEE\u3002",
        )

        ttk.Label(png_frame, text="DPI:").grid(
            row=2, column=2, sticky="e", padx=(12, 5), pady=(6, 2)
        )
        self.png_dpi_var = tk.IntVar(value=300)
        self.png_dpi_spin = ttk.Spinbox(
            png_frame,
            from_=72,
            to=1200,
            increment=50,
            textvariable=self.png_dpi_var,
            width=7,
        )
        self.png_dpi_spin.grid(row=2, column=3, sticky="w", pady=(6, 2))
        ToolTip(
            self.png_dpi_spin,
            "PNG \u6587\u4EF6\u7684 dpi \u5143\u6570\u636E\u3002\u8BBA\u6587\u521D\u7A3F\u5EFA\u8BAE 300-600 dpi\u3002",
        )

        ttk.Label(png_frame, text="\u5BFC\u51FA\u9884\u8BBE:").grid(
            row=3, column=0, sticky="w", pady=(6, 2)
        )
        self.plot_export_preset_cb = ttk.Combobox(
            png_frame,
            values=list(PLOT_PRESET_LABELS),
            textvariable=self.plot_export_preset_var,
            state="readonly",
            width=22,
        )
        self.plot_export_preset_cb.grid(
            row=3, column=1, columnspan=2, sticky="w", padx=(5, 12), pady=(6, 2)
        )
        self.plot_export_preset_cb.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._apply_plot_export_preset(),
        )
        ToolTip(
            self.plot_export_preset_cb,
            "\u9884\u8BBE\u4F1A\u540C\u6B65 PNG colormap \u548C dpi\uFF1B"
            "\u56FE\u50CF\u50CF\u7D20\u5C3A\u5BF8\u4FDD\u6301\u539F\u59CB\u77E9\u9635\u5C3A\u5BF8\u3002",
        )

        self.png_controls = [
            self.png_scale_cb,
            self.png_min_entry,
            self.png_max_entry,
            self.png_colormap_cb,
            self.png_dpi_spin,
            self.plot_export_preset_cb,
        ]

        # Text matrix formats
        text_frame = ttk.LabelFrame(body, text="\u6587\u672C\u77E9\u9635", padding=10)
        text_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=(0, 10))

        text_formats = [
            ('dat', 'DAT (\u77E9\u9635)'),
            ('csv', 'CSV (\u77E9\u9635)'),
        ]
        for i, (key, label) in enumerate(text_formats):
            cb = ttk.Checkbutton(
                text_frame, text=label, variable=self.format_vars[key]
            )
            cb.grid(row=i, column=0, sticky="w", pady=2)
            ToolTip(cb, FORMAT_DESCRIPTIONS.get(key, ""))

        # --- XY Column Formats (right column) ---
        xy_formats_frame = ttk.LabelFrame(body, text="XY \u5217\u683C\u5F0F", padding=10)
        xy_formats_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=(0, 10))

        xy_formats = [
            ('xycsv', 'CSV (XY \u5217)'),
            ('xydat', 'DAT (XY \u5217)'),
        ]
        for i, (key, label) in enumerate(xy_formats):
            cb = ttk.Checkbutton(
                xy_formats_frame, text=label, variable=self.format_vars[key]
            )
            cb.grid(row=i, column=0, sticky="w", pady=2)
            ToolTip(cb, FORMAT_DESCRIPTIONS.get(key, ""))

        # --- XY Column Options ---
        xy_opts_frame = ttk.LabelFrame(body, text="XY \u5217\u9009\u9879", padding=10)
        xy_opts_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 0), pady=(0, 10))

        self.xy_header = tk.BooleanVar(value=True)
        self.xy_one_based = tk.BooleanVar(value=False)
        self.xy_skip_zeros = tk.BooleanVar(value=True)
        self.xy_zero_tol = tk.DoubleVar(value=0.0)

        cb_header = ttk.Checkbutton(
            xy_opts_frame, text='\u5305\u542B\u8868\u5934 (x,y,I)',
            variable=self.xy_header,
        )
        cb_header.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        ToolTip(cb_header, "\u5728\u6587\u4EF6\u7B2C\u4E00\u884C\u5305\u542B\u5217\u6807\u9898")

        cb_one_based = ttk.Checkbutton(
            xy_opts_frame, text='1-Based \u7D22\u5F15',
            variable=self.xy_one_based,
        )
        cb_one_based.grid(row=1, column=0, columnspan=2, sticky="w", pady=2)
        ToolTip(cb_one_based, "\u4F7F\u7528\u4ECE1\u5F00\u59CB\u7684\u7D22\u5F15\uFF08\u800C\u975E\u4ECE0\uFF09")

        cb_skip_zeros = ttk.Checkbutton(
            xy_opts_frame, text='\u8DF3\u8FC7\u96F6\u503C\u50CF\u7D20',
            variable=self.xy_skip_zeros,
        )
        cb_skip_zeros.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)
        ToolTip(cb_skip_zeros, "\u8DF3\u8FC7\u5F3A\u5EA6\u4E3A0\u6216\u4F4E\u4E8E\u9608\u503C\u7684\u50CF\u7D20\uFF0C\u5927\u5E45\u51CF\u5C0F\u6587\u4EF6\u5927\u5C0F")

        ttk.Label(xy_opts_frame, text='\u96F6\u503C\u5BB9\u5DEE:').grid(
            row=3, column=0, sticky="w", pady=2
        )
        tol_entry = ttk.Entry(xy_opts_frame, textvariable=self.xy_zero_tol, width=10)
        tol_entry.grid(row=3, column=1, sticky="w", pady=2, padx=(5, 0))
        ToolTip(tol_entry, "\u5F53\u8DF3\u8FC7\u96F6\u503C\u50CF\u7D20\u65F6\uFF0C\u53EA\u6709\u5F3A\u5EA6 > \u9608\u503C\u7684\u50CF\u7D20\u4F1A\u88AB\u4FDD\u7559")

        # Y-axis Origin
        ttk.Label(xy_opts_frame, text='Y \u8F74\u539F\u70B9:').grid(
            row=4, column=0, sticky="w", pady=(8, 2)
        )
        self.xy_y_axis_origin_var = tk.StringVar(value="top-left")
        self.xy_y_axis_origin_cb = ttk.Combobox(
            xy_opts_frame,
            values=["top-left", "bottom-left"],
            textvariable=self.xy_y_axis_origin_var,
            state="readonly",
            width=12,
        )
        self.xy_y_axis_origin_cb.grid(row=4, column=1, sticky="w", pady=(8, 2), padx=(5, 0))
        ToolTip(
            self.xy_y_axis_origin_cb,
            "XY\u5217\u5BFC\u51FA\u7684Y\u5750\u6807\u539F\u70B9\u7EA6\u5B9A:\n"
            "- top-left: y=0 \u5BF9\u5E94\u6570\u7EC4\u7B2C\u4E00\u884C\uFF08\u9ED8\u8BA4\u63A8\u8350\uFF09\n"
            "- bottom-left: y=0 \u5BF9\u5E94\u56FE\u50CF\u5E95\u90E8",
        )

        # --- General Options ---
        general_frame = ttk.LabelFrame(body, text="\u5E38\u89C4\u9009\u9879", padding=10)
        general_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        self.overwrite_var = tk.BooleanVar(value=False)
        cb_overwrite = ttk.Checkbutton(
            general_frame, text='\u8986\u76D6\u5DF2\u6709\u6587\u4EF6',
            variable=self.overwrite_var,
        )
        cb_overwrite.pack(anchor='w', pady=2)
        ToolTip(cb_overwrite, "\u8986\u76D6\u5DF2\u5B58\u5728\u7684\u8F93\u51FA\u6587\u4EF6\uFF0C\u4E0D\u52FE\u9009\u5219\u81EA\u52A8\u8DF3\u8FC7")

        self.lossless_matrix_var = tk.BooleanVar(value=True)
        self.lossless_matrix_cb = ttk.Checkbutton(
            general_frame,
            text='\u65E0\u9884\u5904\u7406\u65F6\u4FDD\u7559\u539F\u59CB\u77E9\u9635',
            variable=self.lossless_matrix_var,
        )
        self.lossless_matrix_cb.pack(anchor='w', pady=2)
        ToolTip(
            self.lossless_matrix_cb,
            "\u542F\u7528\u540E\uFF0C\u53EA\u8981\u6CA1\u6709\u4EFB\u4F55\u9884\u5904\u7406\u6B65\u9AA4\uFF0C\n"
            "\u5BFC\u51FA EDF/NPY \u65F6\u4F1A\u76F4\u63A5\u4FDD\u7559\u539F\u59CB\u50CF\u7D20\u77E9\u9635\u4E0E\u539F\u59CB dtype\u3002\n"
            "CBF int32 \u5BFC\u51FA TIFF \u65F6\u4F1A\u6539\u5199\u4E3A ImageJ/Fiji \u66F4\u6613\u8BFB\u53D6\u7684 dtype\u3002",
        )
        self._sync_png_controls()

    def _apply_plot_export_preset(self):
        """Apply display-export preset values without changing selected formats."""
        preset = get_plot_preset(self.plot_export_preset_var.get())
        self.png_colormap_var.set(preset["colormap"])
        self.png_dpi_var.set(int(preset["dpi"]))

    def _sync_png_controls(self):
        """Enable PNG display controls only when PNG export is selected."""
        enabled = self.format_vars['png'].get()
        self.png_scale_cb.configure(state="readonly" if enabled else "disabled")
        self.png_colormap_cb.configure(state="readonly" if enabled else "disabled")
        self.plot_export_preset_cb.configure(state="readonly" if enabled else "disabled")
        entry_state = "normal" if enabled else "disabled"
        for control in (self.png_min_entry, self.png_max_entry, self.png_dpi_spin):
            control.configure(state=entry_state)
