"""Tooltip class for Tkinter widgets."""

import tkinter as tk

from gui.styles import TOOLTIP_BACKGROUND, TOOLTIP_FOREGROUND
from gui.windowing import clamp_popup_geometry


class ToolTip:
    """Creates tooltips for Tkinter widgets."""

    _active = None

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
        self.widget.bind("<Unmap>", self.hide_tip, add="+")
        self.widget.bind("<Destroy>", self.hide_tip, add="+")
        self._install_toplevel_escape()

    def _install_toplevel_escape(self):
        """Dismiss the open tip with Escape even when another widget has focus."""
        try:
            toplevel = self.widget.winfo_toplevel()
        except (AttributeError, tk.TclError):
            return
        if getattr(toplevel, "_ringsentry_tooltip_escape", False):
            return
        try:
            toplevel.bind("<Escape>", ToolTip._hide_active, add="+")
        except tk.TclError:
            return
        toplevel._ringsentry_tooltip_escape = True

    @classmethod
    def _hide_active(cls, event=None):
        active = cls._active
        if active is None:
            return None
        active.hide_tip()
        return "break"

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

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            tw.wm_attributes("-topmost", True)
        except tk.TclError:
            pass

        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            background=TOOLTIP_BACKGROUND,
            foreground=TOOLTIP_FOREGROUND,
            relief="solid",
            borderwidth=1,
            font=("Microsoft YaHei UI", 9, "normal"),
            padx=8,
            pady=5,
            wraplength=360,
        )
        label.pack(ipadx=1)
        tw.update_idletasks()

        try:
            popup_width = max(1, int(tw.winfo_reqwidth()))
            popup_height = max(1, int(tw.winfo_reqheight()))
            screen_width = int(self.widget.winfo_screenwidth())
            screen_height = int(self.widget.winfo_screenheight())
            anchor = (
                int(self.widget.winfo_rootx()),
                int(self.widget.winfo_rooty()),
                int(self.widget.winfo_width()),
                int(self.widget.winfo_height()),
            )
        except (AttributeError, tk.TclError, TypeError, ValueError):
            tw.wm_geometry("+0+0")
            ToolTip._active = self
            return

        x, y = clamp_popup_geometry(
            (screen_width, screen_height),
            anchor,
            (popup_width, popup_height),
        )
        tw.wm_geometry(f"+{x}+{y}")
        ToolTip._active = self

    def hide_tip(self, event=None):
        if ToolTip._active is self:
            ToolTip._active = None
        tip_window = self.tip_window
        self.tip_window = None
        if tip_window is not None:
            try:
                tip_window.destroy()
            except tk.TclError:
                # Destruction is idempotent from the user's perspective.
                pass
        return None
