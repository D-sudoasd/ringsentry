"""Calibration frame manager for multi-frame dark/flat averaging.

Allows loading multiple dark or flat field images and combining them
via mean or median to produce a single calibration frame.  The result
is applied to the main app's processing pipeline.

Memory notes
------------
- Mean mode uses incremental summation (float64 accumulator) to avoid
  loading all frames into one np.stack — for 50 frames of 4096×4096
  float32 this saves ~3 GB compared to stacking.
- Median mode requires stacking all frames — acceptable for moderate
  frame counts (< 30) but may use significant memory for large arrays.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import numpy as np

from core.loader import load_image, _lazy_import_matplotlib
from core.plot_style import apply_matplotlib_style, style_figure_axes
from core.utils import summarize_array_stats


class CalibrationManagerDialog(tk.Toplevel):
    """Dialog for managing multi-frame dark/flat calibration."""

    def __init__(self, parent, app, frame_type="dark"):
        """
        Parameters
        ----------
        parent : tk.Widget
            Parent widget.
        app : App
            Main application instance.
        frame_type : str
            "dark" or "flat".
        """
        super().__init__(parent)
        self.app = app
        self.frame_type = frame_type
        frame_label = "\u6697\u5E27" if frame_type == "dark" else "\u5E73\u573A"
        frame_label_en = "Dark" if frame_type == "dark" else "Flat"
        self.title(
            f"\u7BA1\u7406{frame_label} (Manage {frame_label_en} Frames)"
        )
        self.geometry("800x550")
        self.transient(parent)
        self.grab_set()

        self._file_paths = []
        self._arrays = []
        self._averaged = None

        self._create_widgets()

    def _create_widgets(self):
        frame_label = "\u6697\u5E27" if self.frame_type == "dark" else "\u5E73\u573A"
        # File list
        list_frame = ttk.LabelFrame(
            self,
            text=f"\u5DF2\u52A0\u8F7D\u7684{frame_label}\u6587\u4EF6",
            padding=10,
        )
        list_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(
            list_frame, height=6, font=("Consolas", 9),
            selectmode="extended",
        )
        list_scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.file_listbox.yview
        )
        self.file_listbox.configure(yscrollcommand=list_scroll.set)
        self.file_listbox.grid(row=0, column=0, sticky="nsew")
        list_scroll.grid(row=0, column=1, sticky="ns")

        # Buttons
        btn_frame = ttk.Frame(list_frame)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))

        ttk.Button(
            btn_frame, text="\u6DFB\u52A0\u6587\u4EF6", command=self._add_files
        ).pack(side="left", padx=5)
        ttk.Button(
            btn_frame, text="\u79FB\u9664\u9009\u4E2D", command=self._remove_selected
        ).pack(side="left", padx=5)
        ttk.Button(
            btn_frame, text="\u6E05\u7A7A\u5168\u90E8", command=self._clear_all
        ).pack(side="left", padx=5)

        # Averaging options
        opt_frame = ttk.LabelFrame(self, text="\u5408\u5E76\u9009\u9879", padding=10)
        opt_frame.pack(fill="x", padx=10, pady=5)

        self.average_method_var = tk.StringVar(value="mean")
        ttk.Radiobutton(
            opt_frame, text="\u5747\u503C (Mean)",
            variable=self.average_method_var, value="mean",
        ).pack(side="left", padx=10)
        ttk.Radiobutton(
            opt_frame, text="\u4E2D\u503C (Median)",
            variable=self.average_method_var, value="median",
        ).pack(side="left", padx=10)

        ttk.Button(
            opt_frame, text="\u8BA1\u7B97\u5E73\u5747",
            command=self._compute_average,
        ).pack(side="right", padx=5)

        # Stats
        self.stats_var = tk.StringVar(value="\u5C1A\u672A\u8BA1\u7B97")
        stats_label = ttk.Label(
            opt_frame, textvariable=self.stats_var, font=("Consolas", 9)
        )
        stats_label.pack(side="right", padx=10)

        # Preview
        preview_frame = ttk.LabelFrame(self, text="\u9884\u89C8", padding=10)
        preview_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._preview_canvas_frame = ttk.Frame(preview_frame)
        self._preview_canvas_frame.pack(fill="both", expand=True)

        # Bottom buttons
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(
            bottom_frame, text="\u786E\u8BA4\u5E76\u5E94\u7528",
            command=self._apply_and_close,
        ).pack(side="right", padx=5)
        ttk.Button(
            bottom_frame, text="\u53D6\u6D88",
            command=self.destroy,
        ).pack(side="right", padx=5)

    def _add_files(self):
        patterns = "*.tif *.tiff *.mccd *.marccd *.cbf *.edf *.h5 *.hdf5 *.*"
        frame_label = "\u6697\u5E27" if self.frame_type == "dark" else "\u5E73\u573A"
        files = filedialog.askopenfilenames(
            title=f"\u9009\u62E9{frame_label}\u6587\u4EF6",
            filetypes=[
                ("\u56FE\u50CF\u6587\u4EF6", patterns),
                ("\u6240\u6709\u6587\u4EF6", "*.*"),
            ],
        )
        for f in files:
            if f in self._file_paths:
                continue
            try:
                arr = load_image(
                    Path(f), self.app.io_tab.h5_path_var.get()
                )
                self._file_paths.append(f)
                self._arrays.append(arr)
                self.file_listbox.insert(
                    "end", f"{Path(f).name} ({arr.shape})"
                )
            except Exception as e:
                messagebox.showerror(
                    "\u52A0\u8F7D\u5931\u8D25",
                    f"{Path(f).name}: {e}",
                )

    def _remove_selected(self):
        selection = list(self.file_listbox.curselection())
        for idx in reversed(selection):
            self.file_listbox.delete(idx)
            del self._file_paths[idx]
            del self._arrays[idx]

    def _clear_all(self):
        self.file_listbox.delete(0, "end")
        self._file_paths.clear()
        self._arrays.clear()
        self._averaged = None
        self.stats_var.set("\u5C1A\u672A\u8BA1\u7B97")

    def _compute_average(self):
        if not self._arrays:
            messagebox.showwarning(
                "\u65E0\u6570\u636E",
                "\u8BF7\u5148\u6DFB\u52A0\u81F3\u5C11\u4E00\u4E2A\u6587\u4EF6\u3002"
            )
            return

        # Check shapes match
        shapes = [a.shape for a in self._arrays]
        if len(set(shapes)) > 1:
            messagebox.showerror(
                "\u5C3A\u5BF8\u4E0D\u5339\u914D",
                f"\u6240\u6709\u5E27\u5FC5\u987B\u5177\u6709\u76F8\u540C\u5C3A\u5BF8\u3002"
                f"\u53D1\u73B0: {set(shapes)}"
            )
            return

        method = self.average_method_var.get()
        target_shape = shapes[0]

        if method == "mean":
            # Incremental sum: avoids np.stack() which would hold all
            # frames in memory simultaneously.  Accumulate in float64
            # for numerical precision, convert to float32 at the end.
            cumulative = np.zeros(target_shape, dtype=np.float64)
            for arr in self._arrays:
                cumulative += arr.astype(np.float64)
            self._averaged = (cumulative / len(self._arrays)).astype(np.float32)
        else:
            # Median: requires stacking all frames into a 3D array.
            # np.nanmedian automatically ignores NaN values in each frame.
            stacked = np.stack(
                [a.astype(np.float32) for a in self._arrays], axis=0
            )
            self._averaged = np.nanmedian(stacked, axis=0)

        self.stats_var.set(
            f"\u5408\u5E76 {len(self._arrays)} \u5E27 ({method}) | "
            f"{summarize_array_stats(self._averaged)}"
        )
        self._update_preview()

    def _update_preview(self):
        if self._averaged is None:
            return

        Figure, FigureCanvasTkAgg = _lazy_import_matplotlib()
        import matplotlib
        apply_matplotlib_style(matplotlib, preset="raw_inspection")

        # Clear previous preview
        for w in self._preview_canvas_frame.winfo_children():
            w.destroy()

        fig = Figure(figsize=(4, 3), dpi=80)
        ax = fig.add_subplot(111)
        ax.imshow(self._averaged, cmap='viridis')
        fig.colorbar(ax.images[0], ax=ax)
        ax.set_title(
            f"\u5E73\u5747\u7ED3\u679C ({self.average_method_var.get()})"
        )
        style_figure_axes(fig, preset="raw_inspection")
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self._preview_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _apply_and_close(self):
        if self._averaged is None:
            if self._arrays:
                self._compute_average()
                # _compute_average may fail (e.g. shape mismatch),
                # leaving _averaged still None — bail out if so.
                if self._averaged is None:
                    return
            else:
                self.destroy()
                return

        n = len(self._arrays)
        method = self.average_method_var.get()

        if self.frame_type == "dark":
            self.app.dark_frame = self._averaged
            self.app.processing_tab.dark_frame_var.set(
                f"{n} \u5E27\u5408\u5E76 ({method})"
            )
            self.app.log(
                f"\u5DF2\u8BA1\u7B97\u6697\u5E27: {n} \u5E27, {method}, "
                f"\u5C3A\u5BF8 {self._averaged.shape}"
            )
        else:
            self.app.flat_frame = self._averaged
            self.app.processing_tab.flat_frame_var.set(
                f"{n} \u5E27\u5408\u5E76 ({method})"
            )
            self.app.log(
                f"\u5DF2\u8BA1\u7B97\u5E73\u573A: {n} \u5E27, {method}, "
                f"\u5C3A\u5BF8 {self._averaged.shape}"
            )

        self.destroy()
