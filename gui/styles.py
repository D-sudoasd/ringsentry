"""Theme and style configuration for the application."""

import tkinter as tk
from tkinter import ttk


# Keep the application background and status colors in one place so that the
# labels used by the progress panel remain readable when the theme changes.
APP_BACKGROUND = "#f6f7f9"
LOG_BACKGROUND = "#1e1e2e"
LOG_FOREGROUND = "#cdd6f4"
TOOLTIP_BACKGROUND = "#fff8d6"
TOOLTIP_FOREGROUND = "#20242a"
INVALID_ROW_FOREGROUND = "#595959"
STATUS_COLORS = {
    "Success.TLabel": "#146c2e",
    "Failed.TLabel": "#b42318",
    "Skipped.TLabel": "#56616f",
    "Cancelled.TLabel": "#9a3412",
}


def apply_theme(root: tk.Tk):
    """Apply the modern theme to the application."""
    try:
        import sv_ttk
        sv_ttk.set_theme("light")
        root._ringsentry_sv_ttk = True
    except ImportError:
        style = ttk.Style(root)
        style.theme_use('clam')
        root._ringsentry_sv_ttk = False


def configure_styles(root: tk.Tk):
    """Configure custom ttk styles."""
    style = ttk.Style(root)
    bg = APP_BACKGROUND
    text = "#20242a"
    muted = "#5f6670"
    accent = "#1769aa"

    # Custom font for labels
    style.configure("TFrame", background=bg)
    style.configure("TLabel", font=("Microsoft YaHei UI", 9), foreground=text)
    style.configure("Muted.TLabel", font=("Microsoft YaHei UI", 9), foreground=muted)
    style.configure("TLabelframe", padding=8)
    style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))
    style.configure("TCheckbutton", font=("Microsoft YaHei UI", 9))
    style.configure("TButton", font=("Microsoft YaHei UI", 9))
    # sv_ttk Accent.TButton already uses a filled accent with a light label.
    # Forcing a dark-blue foreground there makes the Run button unreadable.
    accent_options = {"font": ("Microsoft YaHei UI", 10, "bold")}
    if not getattr(root, "_ringsentry_sv_ttk", False):
        accent_options["foreground"] = accent
    style.configure("Accent.TButton", **accent_options)

    # Tab style
    style.configure("TNotebook.Tab", font=("Microsoft YaHei UI", 10), padding=[16, 8])

    # Log text style
    style.configure("Log.TFrame", background=LOG_BACKGROUND)

    # Stats labels.  These colors retain the semantic distinction while
    # meeting WCAG AA normal-text contrast against the application background.
    for style_name, foreground in STATUS_COLORS.items():
        style.configure(style_name, background=bg, foreground=foreground)
