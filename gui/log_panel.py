"""Log panel with progress bar, statistics, and log text."""

from datetime import datetime
import tkinter as tk
from tkinter import ttk

from gui.styles import LOG_BACKGROUND, LOG_FOREGROUND
from gui.tooltip import ToolTip


class LogPanel(ttk.Frame):
    """Bottom panel with execution controls, progress, stats, and log text."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self.run_log_lines = []
        self._create_widgets()

    def _create_widgets(self):
        self.columnconfigure(0, weight=1)

        # --- Execution Controls ---
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ctrl_frame.columnconfigure(2, weight=1)

        ttk.Label(ctrl_frame, text="\u7EBF\u7A0B\u6570:").grid(row=0, column=0, padx=(0, 5))
        self.max_thr_var = tk.IntVar(
            value=__import__('os').cpu_count() or 4
        )
        thread_spinbox = ttk.Spinbox(
            ctrl_frame, from_=1, to=64,
            textvariable=self.max_thr_var, width=5,
        )
        thread_spinbox.grid(row=0, column=1, padx=(0, 10))
        ToolTip(thread_spinbox, "\u6700\u5927\u5E76\u53D1\u7EBF\u7A0B\u6570\uFF0C\u63A8\u8350\u8BBE\u7F6E\u4E3A CPU \u6838\u5FC3\u6570")

        self.count_btn = ttk.Button(
            ctrl_frame, text="\u7EDF\u8BA1\u6587\u4EF6", command=self.app.count_files,
        )
        self.count_btn.grid(row=0, column=2, sticky='e', padx=(0, 5))
        ToolTip(self.count_btn, "\u7EDF\u8BA1\u8F93\u5165\u76EE\u5F55\u4E2D\u5F85\u5904\u7406\u7684\u6587\u4EF6\u6570\u91CF")

        self.run_btn = ttk.Button(
            ctrl_frame, text="\u5F00\u59CB\u8F6C\u6362",
            command=self.app.run_conversion,
            style="Accent.TButton",
        )
        self.run_btn.grid(row=0, column=3, padx=5)
        ToolTip(
            self.run_btn,
            "\u5F00\u59CB\u6279\u5904\u7406\u3002\u5EFA\u8BAE\u5148\u5728\u201C\u81EA\u52A8\u8D28\u63A7\u201D\u9875\u62BD\u6837\u68C0\u67E5\uFF0C"
            "\u518D\u6839\u636E\u62A5\u544A\u51B3\u5B9A\u662F\u5426\u542F\u7528\u70ED\u50CF\u7D20\u3001ROI \u6216\u88C1\u526A\u53C2\u6570\u3002",
        )

        self.cancel_btn = ttk.Button(
            ctrl_frame, text="\u53D6\u6D88",
            command=self.app.cancel_conversion, state="disabled",
        )
        self.cancel_btn.grid(row=0, column=4)

        # --- Progress + Stats ---
        prog_frame = ttk.Frame(self)
        prog_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        prog_frame.columnconfigure(0, weight=1)

        self.prog = ttk.Progressbar(prog_frame, mode='determinate')
        self.prog.grid(row=0, column=0, sticky="ew", padx=(0, 15))

        # Bug Fix: Stats in a separate row, not overlapping progress bar
        stats_frame = ttk.Frame(self)
        stats_frame.grid(row=2, column=0, sticky="ew", pady=(0, 5))

        self.stats_labels = {}
        stats_config = [
            ("success", "\u6210\u529F", "Success.TLabel"),
            ("failed", "\u5931\u8D25", "Failed.TLabel"),
            ("skipped", "\u8DF3\u8FC7", "Skipped.TLabel"),
            ("cancelled", "\u53D6\u6D88", "Cancelled.TLabel"),
        ]
        for key, text, style in stats_config:
            label = ttk.Label(stats_frame, text=f"{text}: 0", style=style)
            label.pack(side="left", padx=10)
            self.stats_labels[key] = label

        self.eta_label = ttk.Label(stats_frame, text="")
        self.eta_label.pack(side="right", padx=10)

        # --- Log Text ---
        log_label_frame = ttk.LabelFrame(self, text="\u65E5\u5FD7", padding=5)
        log_label_frame.grid(row=3, column=0, sticky="nsew")
        log_label_frame.columnconfigure(0, weight=1)
        log_label_frame.rowconfigure(0, weight=1)

        # Bug Fix: Add scrollbar to log text
        log_scroll = ttk.Scrollbar(log_label_frame)
        log_scroll.grid(row=0, column=1, sticky="ns")

        self.log_txt = tk.Text(
            log_label_frame, height=5,
            font=("Consolas", 9), wrap="word",
            bg=LOG_BACKGROUND, fg=LOG_FOREGROUND,
            insertbackground=LOG_FOREGROUND,
            yscrollcommand=log_scroll.set,
            takefocus=True,
            highlightthickness=1,
        )
        self.log_txt.grid(row=0, column=0, sticky="nsew")
        log_scroll.config(command=self.log_txt.yview)
        self.log_txt.configure(state="disabled")

        self.rowconfigure(3, weight=1)

    def log(self, msg):
        """Append a timestamped message to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        self.run_log_lines.append(line)
        self.log_txt.configure(state="normal")
        self.log_txt.insert('end', line + "\n")
        self.log_txt.see('end')
        self.log_txt.configure(state="disabled")

    def update_stats_display(self, stats, done_count, total_count, start_time):
        """Update statistics labels and ETA."""
        stats_text = {
            "success": f"\u6210\u529F: {stats['success']}",
            "failed": f"\u5931\u8D25: {stats['failed']}",
            "skipped": f"\u8DF3\u8FC7: {stats['skipped']}",
            "cancelled": f"\u53D6\u6D88: {stats['cancelled']}",
        }
        for key, label in self.stats_labels.items():
            label.config(text=stats_text.get(key, ""))

        # ETA
        if start_time and total_count > 0 and done_count > 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > 0:
                rate = done_count / elapsed
                remaining = (total_count - done_count) / rate
                self.eta_label.config(
                    text=f"\u9884\u8BA1\u5269\u4F59: {int(remaining // 60)}:{int(remaining % 60):02d}"
                )
            else:
                self.eta_label.config(text="")
        else:
            self.eta_label.config(text="")
