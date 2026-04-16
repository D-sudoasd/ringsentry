"""Theme and style configuration for the application."""

import tkinter as tk
from tkinter import ttk


def apply_theme(root: tk.Tk):
    """Apply the modern theme to the application."""
    try:
        import sv_ttk
        sv_ttk.set_theme("light")
    except ImportError:
        style = ttk.Style(root)
        style.theme_use('clam')


def configure_styles(root: tk.Tk):
    """Configure custom ttk styles."""
    style = ttk.Style(root)

    # Custom font for labels
    style.configure("TLabel", font=("Microsoft YaHei UI", 9))
    style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))
    style.configure("TCheckbutton", font=("Microsoft YaHei UI", 9))
    style.configure("TButton", font=("Microsoft YaHei UI", 9))
    style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))

    # Tab style
    style.configure("TNotebook.Tab", font=("Microsoft YaHei UI", 10), padding=[12, 6])

    # Log text style
    style.configure("Log.TFrame", background="#1e1e2e")

    # Stats labels
    style.configure("Success.TLabel", foreground="#2ecc71")
    style.configure("Failed.TLabel", foreground="#e74c3c")
    style.configure("Skipped.TLabel", foreground="#95a5a6")
    style.configure("Cancelled.TLabel", foreground="#e67e22")
