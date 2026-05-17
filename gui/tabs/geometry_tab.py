"""Tab 4: Geometry transforms and scaling."""

import tkinter as tk
from tkinter import ttk

from gui.tooltip import ToolTip


class GeometryTab(ttk.Frame):
    """Geometry and scaling options tab."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=15)
        self.app = app
        self._create_widgets()

    def _create_widgets(self):
        self.columnconfigure(0, weight=1)

        # --- Rotation & Flip ---
        rot_frame = ttk.LabelFrame(self, text="\u65CB\u8F6C\u4E0E\u7FFB\u8F6C", padding=10)
        rot_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        rot_frame.columnconfigure(1, weight=1)

        self.rotate_var = tk.StringVar(value="0")
        self.flip_x_var = tk.BooleanVar(value=False)
        self.flip_y_var = tk.BooleanVar(value=False)

        ttk.Label(rot_frame, text="\u65CB\u8F6C (Rotate):").grid(
            row=0, column=0, sticky="w", padx=5
        )
        self.rotate_cb = ttk.Combobox(
            rot_frame, values=["0", "90", "180", "270"],
            textvariable=self.rotate_var, state="readonly", width=8,
        )
        self.rotate_cb.grid(row=0, column=1, sticky="w", padx=5)

        cb_fx = ttk.Checkbutton(rot_frame, text='\u7FFB\u8F6C X (Flip X)', variable=self.flip_x_var)
        cb_fx.grid(row=0, column=2, padx=10)
        ToolTip(cb_fx, "\u6C34\u5E73\u7FFB\u8F6C\u56FE\u50CF")

        cb_fy = ttk.Checkbutton(rot_frame, text='\u7FFB\u8F6C Y (Flip Y)', variable=self.flip_y_var)
        cb_fy.grid(row=0, column=3, padx=10)
        ToolTip(cb_fy, "\u5782\u76F4\u7FFB\u8F6C\u56FE\u50CF")

        # --- Binning ---
        bin_frame = ttk.LabelFrame(self, text="\u5408\u5E76 (Binning)", padding=10)
        bin_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        self.bin_factor_var = tk.IntVar(value=1)
        ttk.Label(bin_frame, text="\u5408\u5E76\u56E0\u5B50:").pack(side="left", padx=5)
        sp_bin = ttk.Spinbox(
            bin_frame, from_=1, to=16, textvariable=self.bin_factor_var, width=6
        )
        sp_bin.pack(side="left", padx=5)
        ToolTip(
            sp_bin,
            "\u5408\u5E76\u56E0\u5B50\uFF0C\u5C06 factor x factor \u50CF\u7D20\u5757\u53D6\u5747\u503C\u3002\n"
            "\u5982\u679C\u5C3A\u5BF8\u4E0D\u80FD\u6574\u9664\uFF0C\u53F3\u4FA7/\u5E95\u90E8\u8FB9\u7F18\u4F1A\u88AB\u88C1\u6389\u5E76\u5199\u5165\u65E5\u5FD7\u3002",
        )

        # --- Normalization ---
        norm_frame = ttk.LabelFrame(self, text="\u5F52\u4E00\u5316 (Normalization)", padding=10)
        norm_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        norm_frame.columnconfigure(1, weight=1)

        self.norm_mode_var = tk.StringVar(value="none")
        ttk.Label(norm_frame, text="\u6A21\u5F0F:").grid(row=0, column=0, sticky="w", padx=5)
        self.norm_cb = ttk.Combobox(
            norm_frame, values=["none", "max1", "minmax"],
            textvariable=self.norm_mode_var, state="readonly", width=10,
        )
        self.norm_cb.grid(row=0, column=1, sticky="w", padx=5)
        ToolTip(
            self.norm_cb,
            "\u5F52\u4E00\u5316\u6A21\u5F0F:\n"
            "- none: \u4E0D\u5F52\u4E00\u5316\n"
            "- max1: \u9664\u4EE5\u6700\u5927\u503C\uFF0C\u4F7F\u6700\u5927\u503C=1\n"
            "- minmax: \u7F29\u653E\u5230 [0,1] \u533A\u95F4",
        )

        # --- Percentile Clipping ---
        pclip_frame = ttk.LabelFrame(self, text="\u767E\u5206\u4F4D\u88C1\u526A (Percentile Clip)", padding=10)
        pclip_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        pclip_frame.columnconfigure(1, weight=1)
        pclip_frame.columnconfigure(3, weight=1)

        self.pclip_low_var = tk.StringVar()
        self.pclip_high_var = tk.StringVar()

        ttk.Label(pclip_frame, text="\u4E0B\u9650 %:").grid(row=0, column=0, padx=5)
        pclip_low_entry = ttk.Entry(pclip_frame, textvariable=self.pclip_low_var, width=10)
        pclip_low_entry.grid(
            row=0, column=1, sticky="w", padx=5
        )
        ttk.Label(pclip_frame, text="\u4E0A\u9650 %:").grid(row=0, column=2, padx=5)
        pclip_high_entry = ttk.Entry(pclip_frame, textvariable=self.pclip_high_var, width=10)
        pclip_high_entry.grid(
            row=0, column=3, sticky="w", padx=5
        )
        ToolTip(
            pclip_low_entry,
            "\u767E\u5206\u4F4D\u4E0B\u9650\uFF0C\u8303\u56F4 0-100\u3002\n"
            "\u4F8B\u5982 1 \u8868\u793A\u628A\u6700\u4F4E 1% \u6781\u7AEF\u503C\u88C1\u5230\u8BE5\u9608\u503C\u3002",
        )
        ToolTip(
            pclip_high_entry,
            "\u767E\u5206\u4F4D\u4E0A\u9650\uFF0C\u8303\u56F4 0-100\u3002\n"
            "\u4F8B\u5982 99 \u8868\u793A\u628A\u6700\u9AD8 1% \u6781\u7AEF\u503C\u88C1\u5230\u8BE5\u9608\u503C\u3002",
        )

        # --- Intensity Transform ---
        trans_frame = ttk.LabelFrame(self, text="\u5F3A\u5EA6\u53D8\u6362 (Intensity Transform)", padding=10)
        trans_frame.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        trans_frame.columnconfigure(1, weight=1)

        self.intensity_transform_var = tk.StringVar(value="none")
        self.gamma_var = tk.DoubleVar(value=1.0)

        ttk.Label(trans_frame, text="\u53D8\u6362:").grid(row=0, column=0, padx=5)
        self.transform_cb = ttk.Combobox(
            trans_frame, values=["none", "log1p", "log10p", "sqrt"],
            textvariable=self.intensity_transform_var, state="readonly", width=10,
        )
        self.transform_cb.grid(row=0, column=1, sticky="w", padx=5)
        ToolTip(
            self.transform_cb,
            "\u5F3A\u5EA6\u53D8\u6362:\n"
            "- none: \u4E0D\u53D8\u6362\n"
            "- log1p: ln(1 + x)\uFF0C\u81EA\u7136\u5BF9\u6570\u53D8\u6362\uFF0C\u907F\u514D log(0)\n"
            "- log10p: log10(1 + x)\uFF0C\u5E38\u7528\u5BF9\u6570\u53D8\u6362\n"
            "- sqrt: \u221Ax\uFF0C\u5E73\u65B9\u6839\u53D8\u6362"
        )

        ttk.Label(trans_frame, text="Gamma:").grid(row=0, column=2, padx=(15, 5))
        ent_gamma = ttk.Entry(trans_frame, textvariable=self.gamma_var, width=8)
        ent_gamma.grid(row=0, column=3, sticky="w")
        ToolTip(
            ent_gamma,
            "Gamma \u6821\u6B63\u6307\u6570\uFF0C\u5FC5\u987B > 0\u3002\n"
            "1.0 \u8868\u793A\u4E0D\u505A\u53D8\u6362\uFF1B\u5C0F\u4E8E 1 \u4F1A\u62C9\u9AD8\u5F31\u4FE1\u53F7\uFF0C\u5927\u4E8E 1 \u4F1A\u538B\u4F4E\u5F31\u4FE1\u53F7\u3002",
        )

        # --- Hot Pixel Suppression ---
        hot_frame = ttk.LabelFrame(self, text="\u70ED\u50CF\u7D20\u6291\u5236 (Hot Pixel Suppression)", padding=10)
        hot_frame.grid(row=5, column=0, sticky="ew", pady=(0, 10))

        self.hot_pixel_enable_var = tk.BooleanVar(value=False)
        self.hot_pixel_window_var = tk.IntVar(value=3)
        self.hot_pixel_sigma_var = tk.DoubleVar(value=8.0)

        cb_hot = ttk.Checkbutton(
            hot_frame, text='\u542F\u7528\u70ED\u50CF\u7D20\u6291\u5236',
            variable=self.hot_pixel_enable_var,
        )
        cb_hot.pack(side="left", padx=5)
        ToolTip(cb_hot, "\u542F\u7528\u5C40\u90E8\u4E2D\u503C+MAD\u574F\u70B9\u6291\u5236\uFF0C\u6291\u5236\u5B64\u7ACB\u4EAE\u70B9")

        ttk.Label(hot_frame, text="\u7A97\u53E3:").pack(side="left", padx=(15, 4))
        sp_hot_w = ttk.Spinbox(
            hot_frame, from_=3, to=11, increment=2,
            textvariable=self.hot_pixel_window_var, width=5,
        )
        sp_hot_w.pack(side="left")
        ToolTip(sp_hot_w, "\u574F\u70B9\u68C0\u6D4B\u7A97\u53E3\u5927\u5C0F\uFF08\u5947\u6570\uFF09")

        ttk.Label(hot_frame, text="\u4FE1\u53F7\u5F3A\u5EA6:").pack(side="left", padx=(15, 4))
        ent_hot_sigma = ttk.Entry(hot_frame, textvariable=self.hot_pixel_sigma_var, width=8)
        ent_hot_sigma.pack(side="left")
        ToolTip(
            ent_hot_sigma,
            "\u9608\u503C\u5F3A\u5EA6\u56E0\u5B50\uFF0C\u8D8A\u5927\u8D8A\u4FDD\u5B88\uFF0C\u63A8\u83506-10\n"
            "\u68C0\u6D4B\u516C\u5F0F: threshold = median + sigma \u00D7 1.4826 \u00D7 MAD"
        )

        # --- Reset ---
        ttk.Button(
            self, text="\u91CD\u7F6E\u5168\u90E8\u51E0\u4F55/\u7F29\u653E\u53C2\u6570",
            command=self._reset_geometry_scaling,
        ).grid(row=6, column=0, sticky="w", pady=(10, 0))

    def _reset_geometry_scaling(self):
        self.rotate_var.set("0")
        self.flip_x_var.set(False)
        self.flip_y_var.set(False)
        self.bin_factor_var.set(1)
        self.norm_mode_var.set("none")
        self.pclip_low_var.set("")
        self.pclip_high_var.set("")
        self.intensity_transform_var.set("none")
        self.gamma_var.set(1.0)
        self.hot_pixel_enable_var.set(False)
        self.hot_pixel_window_var.set(3)
        self.hot_pixel_sigma_var.set(8.0)
        self.app.log("\u5DF2\u91CD\u7F6E\u51E0\u4F55/\u7F29\u653E\u53C2\u6570")
