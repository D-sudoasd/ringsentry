"""Tab 1: Input/Output configuration."""

from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog

from gui.layout import ScrollableFrame
from gui.tooltip import ToolTip


class IOTab(ttk.Frame):
    """Input and Output settings tab."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=0)
        self.app = app
        self._create_widgets()

    def _create_widgets(self):
        # Use grid for structured layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.scrollable = ScrollableFrame(self, padding=15)
        self.scrollable.grid(row=0, column=0, sticky="nsew")
        self.body = self.scrollable.body
        body = self.body
        body.columnconfigure(1, weight=1)

        row = 0

        # --- Input Mode ---
        mode_frame = ttk.LabelFrame(body, text="\u8F93\u5165\u6A21\u5F0F", padding=10)
        mode_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        mode_frame.columnconfigure(1, weight=1)

        self.input_mode_var = tk.StringVar(value="directory")
        rb_dir = ttk.Radiobutton(
            mode_frame, text="\u6587\u4EF6\u5939\u6A21\u5F0F",
            value="directory", variable=self.input_mode_var,
        )
        rb_dir.grid(row=0, column=0, sticky="w", padx=5)
        ToolTip(rb_dir, "\u9012\u5F52\u626B\u63CF\u6240\u9009\u6587\u4EF6\u5939\u53CA\u5176\u5B50\u6587\u4EF6\u5939\u4E2D\u7684\u5168\u90E8\u652F\u6301\u683C\u5F0F\u6587\u4EF6")

        rb_files = ttk.Radiobutton(
            mode_frame, text="\u6307\u5B9A\u6587\u4EF6\u6A21\u5F0F",
            value="files", variable=self.input_mode_var,
        )
        rb_files.grid(row=0, column=1, sticky="w", padx=5)
        ToolTip(rb_files, "\u53EA\u5904\u7406\u4F60\u660E\u786E\u9009\u4E2D\u7684\u5177\u4F53\u6587\u4EF6\uFF0C\u4E0D\u518D\u626B\u63CF\u6574\u4E2A\u6587\u4EF6\u5939")

        row += 1

        # --- Input Folder ---
        dir_frame = ttk.LabelFrame(body, text="\u8F93\u5165\u6587\u4EF6\u5939", padding=10)
        dir_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        dir_frame.columnconfigure(0, weight=1)

        self.dir_var = tk.StringVar()
        dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var, font=("Consolas", 9))
        dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ToolTip(dir_entry, "\u9009\u62E9\u5305\u542B\u5F85\u5904\u7406\u56FE\u50CF\u6587\u4EF6\u7684\u6839\u76EE\u5F55\uFF0C\u7A0B\u5E8F\u4F1A\u81EA\u52A8\u9012\u5F52\u67E5\u627E")
        dir_btn = ttk.Button(
            dir_frame,
            text="\u9009\u62E9\u8F93\u5165\u6587\u4EF6\u5939",
            command=self._select_dir,
            width=14,
        )
        dir_btn.grid(row=0, column=1)

        row += 1

        # --- Selected Files ---
        files_frame = ttk.LabelFrame(body, text="\u5DF2\u9009\u6587\u4EF6", padding=10)
        files_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        files_frame.columnconfigure(0, weight=1)

        self.selected_files_var = tk.StringVar(value="\u65E0")
        files_entry = ttk.Entry(
            files_frame, textvariable=self.selected_files_var, state='readonly',
            font=("Consolas", 9),
        )
        files_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ToolTip(files_entry, "\u663E\u793A\u5F53\u524D\u5DF2\u9009\u4E2D\u7684\u5177\u4F53\u6587\u4EF6")

        btn_frame = ttk.Frame(files_frame)
        btn_frame.grid(row=0, column=1)
        files_btn = ttk.Button(
            btn_frame,
            text="\u9009\u62E9\u8F93\u5165\u6587\u4EF6",
            command=self._select_files,
            width=12,
        )
        files_btn.pack(side="left", padx=(0, 5))
        clear_btn = ttk.Button(
            btn_frame,
            text="\u6E05\u7A7A\u6587\u4EF6\u5217\u8868",
            command=self._clear_selected_files,
            width=12,
        )
        clear_btn.pack(side="left")
        ToolTip(files_btn, "\u9009\u62E9\u4E00\u4E2A\u6216\u591A\u4E2A\u5177\u4F53\u6587\u4EF6\u8FDB\u884C\u5904\u7406\uFF0C\u652F\u6301\u591A\u9009")
        ToolTip(clear_btn, "\u6E05\u7A7A\u5F53\u524D\u5DF2\u9009\u6587\u4EF6\u5217\u8868")

        row += 1

        # --- Output Root ---
        out_frame = ttk.LabelFrame(body, text="\u8F93\u51FA\u76EE\u5F55", padding=10)
        out_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        out_frame.columnconfigure(0, weight=1)

        self.outdir_var = tk.StringVar()
        outdir_entry = ttk.Entry(out_frame, textvariable=self.outdir_var, font=("Consolas", 9))
        outdir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ToolTip(
            outdir_entry,
            "\u8F93\u51FA\u6587\u4EF6\u7684\u4FDD\u5B58\u76EE\u5F55\u3002\n"
            "\u5982\u679C\u4E0D\u6307\u5B9A\uFF1A\u76EE\u5F55\u6A21\u5F0F\u9ED8\u8BA4\u8F93\u51FA\u5230\u8F93\u5165\u76EE\u5F55\u4E0B\u7684 _converted",
        )
        outdir_btn = ttk.Button(
            out_frame,
            text="\u9009\u62E9\u8F93\u51FA\u76EE\u5F55",
            command=self._select_outdir,
            width=12,
        )
        outdir_btn.grid(row=0, column=1)

        row += 1

        # --- HDF5 Path ---
        h5_frame = ttk.LabelFrame(body, text="HDF5 \u6570\u636E\u96C6\u8DEF\u5F84", padding=10)
        h5_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        h5_frame.columnconfigure(0, weight=1)

        self.h5_path_var = tk.StringVar(value="/entry/data/data")
        h5_entry = ttk.Entry(h5_frame, textvariable=self.h5_path_var, font=("Consolas", 9))
        h5_entry.grid(row=0, column=0, sticky="ew")
        ToolTip(h5_entry, "HDF5 \u5185\u90E8\u6570\u636E\u96C6\u8DEF\u5F84\uFF0C\u9ED8\u8BA4 /entry/data/data")

        row += 1

        # --- Workflow Preset ---
        preset_frame = ttk.LabelFrame(body, text="\u5DE5\u4F5C\u6D41\u9884\u8BBE", padding=10)
        preset_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        preset_frame.columnconfigure(0, weight=1)

        self.workflow_preset_var = tk.StringVar(value="Custom")
        self.workflow_preset_cb = ttk.Combobox(
            preset_frame,
            values=["Custom", "SAXS Quick", "SXRD Quick", "GIWAXS Quick"],
            textvariable=self.workflow_preset_var,
            state="readonly",
            width=24,
        )
        self.workflow_preset_cb.grid(row=0, column=0, sticky="w")
        self.workflow_preset_cb.bind(
            "<<ComboboxSelected>>", self._on_workflow_preset_selected
        )
        ToolTip(self.workflow_preset_cb, "\u4E00\u952E\u5E94\u7528\u5E38\u89C1\u573A\u666F\u53C2\u6570\u6A21\u677F")

    # --- Callbacks ---

    def _select_dir(self):
        d = filedialog.askdirectory(title="\u9009\u62E9\u8F93\u5165\u6839\u76EE\u5F55")
        if d:
            self.dir_var.set(d)
            self.input_mode_var.set("directory")
            self._set_default_output_root_if_empty()
            self.app.log(f"\u5DF2\u9009\u62E9\u8F93\u5165\u6587\u4EF6\u5939: {d}")

    def _select_files(self):
        patterns = (
            "*.tif *.tiff *.mccd *.marccd *.cbf *.edf *.h5 *.hdf5 "
            "*.[0-9][0-9][0-9] *.[0-9][0-9][0-9][0-9] *.[0-9][0-9][0-9][0-9][0-9] "
            "*.[0-9][0-9][0-9][0-9][0-9][0-9] *.*"
        )
        files = filedialog.askopenfilenames(
            title="\u9009\u62E9\u5177\u4F53\u8F93\u5165\u6587\u4EF6",
            filetypes=[("\u63A2\u6D4B\u5668\u6587\u4EF6", patterns), ("\u6240\u6709\u6587\u4EF6", "*.*")],
        )
        if not files:
            return
        self.app.selected_files = list(files)
        self.input_mode_var.set("files")
        self.app.filelist = []
        self._update_selected_files_summary()
        filelist, common_root, skipped = self.app._get_active_input_filelist()
        self.app.selected_common_root = common_root
        self._set_default_output_root_if_empty()
        if skipped:
            self.app.log(f"\u8DF3\u8FC7 {len(skipped)} \u4E2A\u4E0D\u652F\u6301/\u7F3A\u5931\u7684\u9009\u5B9A\u9879")
        self.app.log(f"\u5DF2\u9009\u62E9 {len(filelist)} \u4E2A\u8F93\u5165\u6587\u4EF6")

    def _clear_selected_files(self):
        self.app.selected_files = []
        self.app.selected_common_root = None
        self.app.filelist = []
        self._update_selected_files_summary()
        self.app.log("\u5DF2\u6E05\u7A7A\u9009\u5B9A\u6587\u4EF6\u5217\u8868")

    def _select_outdir(self):
        d = filedialog.askdirectory(title="\u9009\u62E9\u8F93\u51FA\u76EE\u5F55")
        if d:
            self.outdir_var.set(d)

    def _set_default_output_root_if_empty(self):
        """Show the computed output directory without replacing user input."""
        if self.outdir_var.get().strip():
            return

        default_root = ""
        get_default = getattr(self.app, "_get_default_output_root", None)
        if get_default is not None:
            try:
                default_root = get_default()
            except Exception:
                default_root = ""

        if not default_root:
            if self.input_mode_var.get() == "directory":
                root = self.dir_var.get().strip()
                default_root = str(Path(root) / "_converted") if root else ""
            else:
                selected = getattr(self.app, "selected_files", [])
                common_root = getattr(self.app, "selected_common_root", None)
                if common_root:
                    default_root = str(Path(common_root) / "_converted")
                elif selected:
                    default_root = str(Path(selected[0]).resolve().parent / "_converted")

        if default_root:
            self.outdir_var.set(str(default_root))
            self.app.log(f"\u5DF2\u663E\u793A\u9ED8\u8BA4\u8F93\u51FA\u76EE\u5F55: {default_root}")

    def _on_workflow_preset_selected(self, _event=None):
        """Apply a selected preset immediately so visible fields stay in sync."""
        preset = self.workflow_preset_var.get()
        try:
            self.app._apply_workflow_preset()
        except Exception as exc:
            self.app.log(f"\u5DE5\u4F5C\u6D41\u9884\u8BBE\u5E94\u7528\u5931\u8D25 ({preset}): {exc}")
            return
        self.app.log(
            f"\u5DE5\u4F5C\u6D41\u9884\u8BBE\u5DF2\u5373\u65F6\u5E94\u7528: {preset}\uFF1B\u76F8\u5173\u53C2\u6570\u5DF2\u540C\u6B65\u3002"
        )

    def _update_selected_files_summary(self):
        if not self.app.selected_files:
            self.selected_files_var.set("\u65E0")
            return
        names = [Path(p).name for p in self.app.selected_files]
        if len(names) <= 3:
            summary = "; ".join(names)
        else:
            summary = "; ".join(names[:3]) + f" ... (+{len(names) - 3} \u66F4\u591A)"
        self.selected_files_var.set(f"{len(names)} \u4E2A\u6587\u4EF6: {summary}")
