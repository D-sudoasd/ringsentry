"""Tooltip class for Tkinter widgets."""

import tkinter as tk


class ToolTip:
    """Creates tooltips for Tkinter widgets."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        # ``FocusIn``/``FocusOut`` make the same help available to keyboard
        # users.  ``add='+'`` is important here: attaching a tooltip must not
        # replace a widget's existing pointer or focus bindings.
        self.widget.bind("<Enter>", self.show_tip, add="+")
        self.widget.bind("<Leave>", self.hide_tip, add="+")
        self.widget.bind("<FocusIn>", self.show_tip, add="+")
        self.widget.bind("<FocusOut>", self.hide_tip, add="+")
        self.widget.bind("<Escape>", self.hide_tip, add="+")

    def show_tip(self, event=None):
        if not self.text:
            return

        if self.tip_window is not None:
            try:
                if self.tip_window.winfo_exists():
                    return
            except AttributeError:
                # Lightweight test doubles and older Tk wrappers may not
                # expose ``winfo_exists``; a non-None handle is still enough
                # to prevent a duplicate tooltip.
                return
            except tk.TclError:
                # The window may have been closed by the window manager.
                self.tip_window = None

        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            tw, text=self.text, justify='left',
            background="#ffffe0", relief='solid', borderwidth=1,
            font=("Microsoft YaHei UI", 9, "normal"), padx=6, pady=4,
        )
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tip_window = self.tip_window
        self.tip_window = None
        if tip_window is not None:
            try:
                tip_window.destroy()
            except tk.TclError:
                # Destruction is idempotent from the user's perspective.
                pass
