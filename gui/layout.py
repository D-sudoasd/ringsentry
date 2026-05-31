"""Reusable layout widgets for the desktop GUI."""

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    """A vertically scrollable ttk frame with a public ``body`` container."""

    def __init__(self, parent, padding=0, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.body = ttk.Frame(self.canvas, padding=padding)
        self._window_id = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.body.bind("<Configure>", self._sync_scroll_region)
        self.canvas.bind("<Configure>", self._sync_body_width)
        self.winfo_toplevel().bind("<MouseWheel>", self._on_mousewheel, add="+")

    def _sync_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_body_width(self, event):
        self.canvas.itemconfigure(self._window_id, width=event.width)

    def _on_mousewheel(self, event):
        x0 = self.canvas.winfo_rootx()
        y0 = self.canvas.winfo_rooty()
        x1 = x0 + self.canvas.winfo_width()
        y1 = y0 + self.canvas.winfo_height()
        if not (x0 <= event.x_root <= x1 and y0 <= event.y_root <= y1):
            return None
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"
