"""Tab 2: Processing options."""

from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from gui.layout import ScrollableFrame
from gui.tooltip import ToolTip
from core.loader import load_image


class ProcessingTab(ttk.Frame):
    """Preprocessing settings tab."""

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
        body.columnconfigure(1, weight=1)

        row = 0

        # --- Dark Frame ---
        dark_frame = ttk.LabelFrame(body, text="\u6697\u5E27 (Dark Frame)", padding=10)
        dark_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        dark_frame.columnconfigure(0, weight=1)

        self.dark_frame_var = tk.StringVar(value="\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")
        self.dark_entry = ttk.Entry(
            dark_frame, textvariable=self.dark_frame_var, state='readonly',
            font=("Consolas", 9),
        )
        self.dark_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ToolTip(
            self.dark_entry,
            "\u6697\u5E27\u51CF\u9664\u7528\u4E8E\u53BB\u9664\u63A2\u6D4B\u5668\u80CC\u666F/\u6697\u7535\u6D41\n"
            "\u8BA1\u7B97\u516C\u5F0F: result = raw - dark"
        )

        dark_browse = ttk.Button(
            dark_frame,
            text="\u9009\u62E9\u6697\u5E27",
            command=self._select_dark_frame,
            width=10,
        )
        dark_browse.grid(row=0, column=1, padx=(0, 5))
        dark_clear = ttk.Button(
            dark_frame,
            text="\u6E05\u7A7A\u6697\u5E27",
            command=self._clear_dark_frame,
            width=10,
        )
        dark_clear.grid(row=0, column=2, padx=(0, 5))
        dark_manage = ttk.Button(
            dark_frame,
            text="\u7BA1\u7406\u6697\u5E27",
            command=self._manage_dark_frames,
            width=10,
        )
        dark_manage.grid(row=0, column=3)

        row += 1

        # --- Flat Field ---
        flat_frame_lf = ttk.LabelFrame(body, text="\u5E73\u573A (Flat Field)", padding=10)
        flat_frame_lf.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        flat_frame_lf.columnconfigure(0, weight=1)

        self.flat_frame_var = tk.StringVar(value="\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")
        self.flat_entry = ttk.Entry(
            flat_frame_lf, textvariable=self.flat_frame_var, state='readonly',
            font=("Consolas", 9),
        )
        self.flat_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ToolTip(
            self.flat_entry,
            "\u5E73\u573A\u6821\u6B63\u7528\u4E8E\u6D88\u9664\u63A2\u6D4B\u5668\u54CD\u5E94\u4E0D\u5747\u5300\u6027\n"
            "\u8BA1\u7B97\u516C\u5F0F: result = (raw - dark) / flat"
        )

        flat_browse = ttk.Button(
            flat_frame_lf,
            text="\u9009\u62E9\u5E73\u573A",
            command=self._select_flat_frame,
            width=10,
        )
        flat_browse.grid(row=0, column=1, padx=(0, 5))
        flat_clear = ttk.Button(
            flat_frame_lf,
            text="\u6E05\u7A7A\u5E73\u573A",
            command=self._clear_flat_frame,
            width=10,
        )
        flat_clear.grid(row=0, column=2, padx=(0, 5))
        flat_manage = ttk.Button(
            flat_frame_lf,
            text="\u7BA1\u7406\u5E73\u573A",
            command=self._manage_flat_frames,
            width=10,
        )
        flat_manage.grid(row=0, column=3)

        self.flat_is_dark_subtracted_var = tk.BooleanVar(value=True)
        cb_flat_ds = ttk.Checkbutton(
            flat_frame_lf,
            text="\u5E73\u573A\u5DF2\u51CF\u6697 (Flat already dark-subtracted)",
            variable=self.flat_is_dark_subtracted_var,
        )
        cb_flat_ds.grid(row=1, column=0, columnspan=4, sticky="w", padx=5, pady=(4, 0))
        ToolTip(
            cb_flat_ds,
            "\u52FE\u9009: \u5E73\u573A\u5DF2\u7ECF\u51CF\u53BB\u6697\u5E27\uFF0C\u516C\u5F0F (raw-dark)/flat\n"
            "\u53D6\u6D88: \u5E73\u573A\u672A\u51CF\u6697\uFF0C\u516C\u5F0F (raw-dark)/(flat-dark)"
        )

        row += 1

        # --- Mask File ---
        mask_frame = ttk.LabelFrame(body, text="\u63A9\u819C (Mask File)", padding=10)
        mask_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        mask_frame.columnconfigure(0, weight=1)

        self.mask_frame_var = tk.StringVar(value="\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")
        self.mask_entry = ttk.Entry(
            mask_frame, textvariable=self.mask_frame_var, state='readonly',
            font=("Consolas", 9),
        )
        self.mask_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ToolTip(
            self.mask_entry,
            "\u63A9\u819C\u6587\u4EF6\u7528\u4E8E\u5C4F\u853D\u574F\u70B9/\u9634\u5F71\u533A\u57DF\n"
            "\u9ED8\u8BA4: mask\u975E\u96F6\u50CF\u7D20 \u2192 \u8BBE\u4E3A NaN (\u65E0\u6548)\n"
            "\u53EF\u901A\u8FC7\u201C\u63A9\u819C\u6781\u6027\u201D\u9009\u9879\u53CD\u8F6C"
        )

        mask_browse = ttk.Button(
            mask_frame,
            text="\u9009\u62E9\u63A9\u819C",
            command=self._select_mask_frame,
            width=10,
        )
        mask_browse.grid(row=0, column=1, padx=(0, 5))
        mask_clear = ttk.Button(
            mask_frame,
            text="\u6E05\u7A7A\u63A9\u819C",
            command=self._clear_mask_frame,
            width=10,
        )
        mask_clear.grid(row=0, column=2)

        row += 1

        # --- ROI ---
        roi_frame = ttk.LabelFrame(body, text="ROI \u88C1\u526A (X,Y,W,H)", padding=10)
        roi_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        roi_frame.columnconfigure(0, weight=1)

        self.roi_var = tk.StringVar()
        roi_entry = ttk.Entry(roi_frame, textvariable=self.roi_var, font=("Consolas", 9))
        roi_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ToolTip(
            roi_entry,
            "\u88C1\u526A\u533A\u57DF\u683C\u5F0F: X,Y,W,H\n"
            "X=\u5217\u504F\u79BB (column), Y=\u884C\u504F\u79FB (row)\n"
            "\u5750\u6807\u539F\u70B9: \u5DE6\u4E0A\u89D2, y\u5411\u4E0B\u589E\u52A0\n"
            "\u4F8B\u5982: 100,120,800,800"
        )

        preview_btn = ttk.Button(
            roi_frame,
            text="\u5355\u56FE\u9884\u89C8",
            command=self.app.preview_image,
            width=10,
        )
        preview_btn.grid(row=0, column=1, padx=(0, 5))
        ToolTip(preview_btn, "\u9884\u89C8\u5904\u7406\u524D\u540E\u6548\u679C\u5E76\u4EA4\u4E92\u9009\u62E9 ROI")

        gallery_btn = ttk.Button(
            roi_frame, text="\u6279\u91CF\u9884\u89C8", command=self.app.show_gallery, width=10
        )
        gallery_btn.grid(row=0, column=2, padx=(0, 5))
        ToolTip(gallery_btn, "\u6279\u91CF\u7F29\u7565\u56FE\u9884\u89C8\u591A\u4E2A\u6587\u4EF6")

        roi_clear = ttk.Button(
            roi_frame,
            text="\u6E05\u7A7A ROI",
            command=lambda: self.roi_var.set(""),
            width=8,
        )
        roi_clear.grid(row=0, column=3)

        row += 1

        # --- Advanced Options ---
        adv_frame = ttk.LabelFrame(body, text="\u9AD8\u7EA7\u9009\u9879", padding=10)
        adv_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        adv_frame.columnconfigure(1, weight=1)
        adv_frame.columnconfigure(3, weight=1)

        # Row 0: BG Offset + Clip Negative
        ttk.Label(adv_frame, text="\u80CC\u666F\u504F\u79FB (BG Offset):").grid(
            row=0, column=0, sticky="w", padx=5, pady=3
        )
        self.bg_offset_var = tk.DoubleVar(value=0.0)
        bg_entry = ttk.Entry(adv_frame, textvariable=self.bg_offset_var, width=10)
        bg_entry.grid(row=0, column=1, sticky="w", padx=5, pady=3)
        ToolTip(
            bg_entry,
            "\u4ECE\u6240\u6709\u50CF\u7D20\u4E2D\u51CF\u53BB\u4E00\u4E2A\u5E38\u6570\u80CC\u666F\u503C\u3002\n"
            "\u5982\u679C\u4E0D\u786E\u5B9A\uFF0C\u4FDD\u6301 0\u3002",
        )

        self.clip_negative_var = tk.BooleanVar(value=False)
        cb_clip = ttk.Checkbutton(
            adv_frame, text="\u88C1\u526A\u8D1F\u503C (Clip Negative)",
            variable=self.clip_negative_var,
        )
        cb_clip.grid(row=0, column=2, columnspan=2, sticky="w", padx=5, pady=3)
        ToolTip(cb_clip, "\u5C06\u6240\u6709\u8D1F\u503C\u8BBE\u4E3A 0")

        # Row 1: I Min / I Max
        ttk.Label(adv_frame, text="\u5F3A\u5EA6\u6700\u5C0F\u503C (I Min):").grid(
            row=1, column=0, sticky="w", padx=5, pady=3
        )
        self.min_intensity_var = tk.StringVar()
        min_entry = ttk.Entry(adv_frame, textvariable=self.min_intensity_var, width=10)
        min_entry.grid(
            row=1, column=1, sticky="w", padx=5, pady=3
        )
        ToolTip(
            min_entry,
            "\u5C0F\u4E8E I Min \u7684\u50CF\u7D20\u4F1A\u88AB\u8BBE\u4E3A NaN\uFF0C\u4E0D\u53C2\u4E0E\u540E\u7EED\u5E73\u5747\u6216\u5BFC\u51FA\u7B5B\u9009\u3002",
        )

        ttk.Label(adv_frame, text="\u5F3A\u5EA6\u6700\u5927\u503C (I Max):").grid(
            row=1, column=2, sticky="w", padx=5, pady=3
        )
        self.max_intensity_var = tk.StringVar()
        max_entry = ttk.Entry(adv_frame, textvariable=self.max_intensity_var, width=10)
        max_entry.grid(
            row=1, column=3, sticky="w", padx=5, pady=3
        )
        ToolTip(
            max_entry,
            "\u5927\u4E8E I Max \u7684\u50CF\u7D20\u4F1A\u88AB\u8BBE\u4E3A NaN\u3002\n"
            "\u5E38\u7528\u4E8E\u6392\u9664\u9971\u548C\u70B9\u6216\u660E\u663E\u5F02\u5E38\u503C\u3002",
        )

        # Row 2: Mask polarity
        self.mask_nonzero_is_invalid_var = tk.BooleanVar(value=True)
        cb_mask = ttk.Checkbutton(
            adv_frame,
            text="\u63A9\u819C\u6781\u6027: \u975E\u96F6=\u65E0\u6548 (Mask Nonzero=Invalid)",
            variable=self.mask_nonzero_is_invalid_var,
        )
        cb_mask.grid(row=2, column=0, columnspan=4, sticky="w", padx=5, pady=3)
        ToolTip(
            cb_mask,
            "\u63A9\u819C\u6781\u6027\u5B9A\u4E49:\n"
            "- \u52FE\u9009: mask!=0 \u89C6\u4E3A\u65E0\u6548\u50CF\u7D20\uFF08\u9ED8\u8BA4\uFF09\n"
            "- \u53D6\u6D88: mask==0 \u89C6\u4E3A\u65E0\u6548\u50CF\u7D20",
        )

    # --- Callbacks ---

    def _select_dark_frame(self):
        patterns = "*.tif *.tiff *.mccd *.marccd *.cbf *.edf *.h5 *.hdf5 *.*"
        f = filedialog.askopenfilename(
            title="\u9009\u62E9\u6697\u5E27\u56FE\u50CF",
            filetypes=[("\u56FE\u50CF\u6587\u4EF6", patterns), ("\u6240\u6709\u6587\u4EF6", "*.*")],
        )
        if not f:
            return
        try:
            self.app.dark_frame = load_image(Path(f), self.app.io_tab.h5_path_var.get())
            self.dark_frame_var.set(f)
            self.app.log(
                f"\u5DF2\u52A0\u8F7D\u6697\u5E27: {f} (\u5C3A\u5BF8: {self.app.dark_frame.shape})"
            )
        except Exception as e:
            messagebox.showerror(
                "\u52A0\u8F7D\u6697\u5E27\u5931\u8D25", str(e)
            )
            self.app.dark_frame = None
            self.dark_frame_var.set("\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")

    def _clear_dark_frame(self):
        self.app.dark_frame = None
        self.dark_frame_var.set("\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")
        self.app.log("\u5DF2\u6E05\u7A7A\u6697\u5E27")

    def _select_mask_frame(self):
        patterns = "*.tif *.tiff *.mccd *.marccd *.cbf *.edf *.h5 *.hdf5 *.*"
        f = filedialog.askopenfilename(
            title="\u9009\u62E9\u63A9\u819C\u56FE\u50CF",
            filetypes=[("\u56FE\u50CF\u6587\u4EF6", patterns), ("\u6240\u6709\u6587\u4EF6", "*.*")],
        )
        if not f:
            return
        try:
            self.app.mask_frame = load_image(Path(f), self.app.io_tab.h5_path_var.get())
            self.mask_frame_var.set(f)
            self.app.log(
                f"\u5DF2\u52A0\u8F7D\u63A9\u819C: {f} (\u5C3A\u5BF8: {self.app.mask_frame.shape})"
            )
        except Exception as e:
            messagebox.showerror(
                "\u52A0\u8F7D\u63A9\u819C\u5931\u8D25", str(e)
            )
            self.app.mask_frame = None
            self.mask_frame_var.set("\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")

    def _clear_mask_frame(self):
        self.app.mask_frame = None
        self.mask_frame_var.set("\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")
        self.app.log("\u5DF2\u6E05\u7A7A\u63A9\u819C")

    # --- Flat Field Callbacks ---

    def _select_flat_frame(self):
        patterns = "*.tif *.tiff *.mccd *.marccd *.cbf *.edf *.h5 *.hdf5 *.*"
        f = filedialog.askopenfilename(
            title="\u9009\u62E9\u5E73\u573A\u56FE\u50CF",
            filetypes=[("\u56FE\u50CF\u6587\u4EF6", patterns), ("\u6240\u6709\u6587\u4EF6", "*.*")],
        )
        if not f:
            return
        try:
            self.app.flat_frame = load_image(Path(f), self.app.io_tab.h5_path_var.get())
            self.flat_frame_var.set(f)
            self.app.log(
                f"\u5DF2\u52A0\u8F7D\u5E73\u573A: {f} (\u5C3A\u5BF8: {self.app.flat_frame.shape})"
            )
        except Exception as e:
            messagebox.showerror(
                "\u52A0\u8F7D\u5E73\u573A\u5931\u8D25", str(e)
            )
            self.app.flat_frame = None
            self.flat_frame_var.set("\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")

    def _clear_flat_frame(self):
        self.app.flat_frame = None
        self.flat_frame_var.set("\u65E0\uFF08\u70B9\u51FB\u6D4F\u89C8\u9009\u62E9\uFF09")
        self.app.log("\u5DF2\u6E05\u7A7A\u5E73\u573A")

    # --- Calibration Manager Callbacks ---

    def _manage_dark_frames(self):
        from gui.calibration_frame import CalibrationManagerDialog
        CalibrationManagerDialog(self.app, self.app, frame_type="dark")

    def _manage_flat_frames(self):
        from gui.calibration_frame import CalibrationManagerDialog
        CalibrationManagerDialog(self.app, self.app, frame_type="flat")
