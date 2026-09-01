"""Reusable layout widgets for the desktop GUI."""

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    """A vertically scrollable ttk frame with a public ``body`` container.

    Mouse and keyboard events are attached to the containing toplevel with
    widget-local filtering. This keeps controls inside ``body`` focusable
    without using global event bindings that steal events from other scroll
    regions.
    """

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

        self._top_level = self.winfo_toplevel()
        self._top_level_binding_ids = []
        self._bind_top_level_events()
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _sync_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_body_width(self, event):
        self.canvas.itemconfigure(self._window_id, width=event.width)

    def _bind_top_level_events(self):
        """Install scoped event handlers and remember IDs for cleanup."""
        bindings = (
            ("<MouseWheel>", self._on_mousewheel),
            ("<Button-4>", self._on_mousewheel),
            ("<Button-5>", self._on_mousewheel),
            ("<KeyPress>", self._on_keypress),
            ("<FocusIn>", self._on_focus_in),
        )
        for sequence, callback in bindings:
            try:
                funcid = self._top_level.bind(sequence, callback, add="+")
            except tk.TclError:
                # A partially constructed/destroyed toplevel should not make
                # the frame unusable.
                continue
            if funcid:
                self._top_level_binding_ids.append((sequence, funcid))

    def _unbind_top_level_events(self):
        """Remove only this frame's handlers from the containing toplevel."""
        for sequence, funcid in self._top_level_binding_ids:
            try:
                self._top_level.unbind(sequence, funcid)
            except tk.TclError:
                pass
        self._top_level_binding_ids.clear()

    def _on_destroy(self, event=None):
        """Release toplevel binding scripts when this frame is destroyed."""
        if event is not None and getattr(event, "widget", self) is not self:
            return None
        self._unbind_top_level_events()
        return None

    @staticmethod
    def _is_text_entry_widget(widget):
        """Return whether keypress should stay with a text-entry control."""
        if widget is None:
            return False
        if isinstance(
            widget, (tk.Entry, tk.Spinbox, tk.Text, ttk.Entry, ttk.Combobox, ttk.Spinbox)
        ):
            return True
        try:
            widget_class = str(widget.winfo_class())
        except (AttributeError, tk.TclError):
            widget_class = type(widget).__name__
        return widget_class in {
            "Entry",
            "TEntry",
            "Combobox",
            "TCombobox",
            "Spinbox",
            "TSpinbox",
            "Text",
        }

    def _is_scrollable_widget(self, widget):
        """Return whether ``widget`` is this frame or one of its children."""
        if widget is None:
            return False

        targets = (self, self.body, self.canvas, self.scrollbar)
        if any(widget is target for target in targets):
            return True

        try:
            widget_path = str(widget)
            for target in targets:
                target_path = str(target)
                if widget_path == target_path or widget_path.startswith(
                    target_path + "."
                ):
                    return True
        except (AttributeError, tk.TclError):
            return False
        return False

    def _event_over_canvas(self, event):
        """Return whether a pointer event is inside this canvas viewport."""
        x_root = getattr(event, "x_root", None)
        y_root = getattr(event, "y_root", None)
        if x_root is None or y_root is None:
            return self._is_scrollable_widget(getattr(event, "widget", None))

        try:
            x0 = self.canvas.winfo_rootx()
            y0 = self.canvas.winfo_rooty()
            x1 = x0 + self.canvas.winfo_width()
            y1 = y0 + self.canvas.winfo_height()
        except tk.TclError:
            return False

        return x0 <= x_root < x1 and y0 <= y_root < y1

    def _on_mousewheel(self, event):
        if not self._event_over_canvas(event):
            return None

        event_num = getattr(event, "num", None)
        if str(event_num) == "4":
            units = -1
        elif str(event_num) == "5":
            units = 1
        else:
            try:
                delta = float(getattr(event, "delta", 0) or 0)
            except (TypeError, ValueError):
                return None
            if delta == 0:
                return None
            # Windows commonly reports multiples of 120; macOS trackpads
            # often report small +/-1 deltas. Preserve both by guaranteeing
            # at least one unit for every non-zero event.
            magnitude = max(1, int(abs(delta) / 120))
            units = -magnitude if delta > 0 else magnitude

        self.canvas.yview_scroll(units, "units")
        return "break"

    def _on_keypress(self, event):
        """Scroll when navigation keys are pressed inside this frame."""
        widget = getattr(event, "widget", None)
        if widget is None:
            try:
                widget = self.focus_get()
            except tk.TclError:
                widget = None
        if not self._is_scrollable_widget(widget):
            return None
        if self._is_text_entry_widget(widget):
            return None

        key = str(getattr(event, "keysym", "")).lower()
        key = key.replace("_", "").replace("-", "")
        if key in {"prior", "pageup", "kpprior"}:
            self.canvas.yview_scroll(-1, "pages")
        elif key in {"next", "pagedown", "kpnext"}:
            self.canvas.yview_scroll(1, "pages")
        elif key == "home":
            self.canvas.yview_moveto(0)
        elif key == "end":
            self.canvas.yview_moveto(1)
        else:
            return None
        return "break"

    def _on_focus_in(self, event):
        """Keep a focused child visible in the canvas viewport."""
        widget = getattr(event, "widget", None)
        if self._is_scrollable_widget(widget):
            self._scroll_widget_into_view(widget)
        return None

    def _scroll_widget_into_view(self, widget):
        """Scroll just enough for a focused child to become visible."""
        if not self._is_scrollable_widget(widget):
            return None

        try:
            self.canvas.update_idletasks()
            canvas_top = self.canvas.winfo_rooty()
            viewport_height = self.canvas.winfo_height()
            widget_top = widget.winfo_rooty()
            widget_bottom = widget_top + widget.winfo_height()
        except (AttributeError, tk.TclError):
            return None

        if viewport_height <= 0 or widget_bottom <= widget_top:
            return None

        delta = 0
        viewport_top = canvas_top
        viewport_bottom = canvas_top + viewport_height
        if widget_top < viewport_top:
            delta = widget_top - viewport_top
        elif widget_bottom > viewport_bottom:
            delta = widget_bottom - viewport_bottom
        if delta == 0:
            return None

        try:
            bbox = self.canvas.bbox("all")
            if not bbox:
                return None
            content_top, content_bottom = float(bbox[1]), float(bbox[3])
            content_height = content_bottom - content_top
            if content_height <= viewport_height:
                return None

            current_top = float(self.canvas.canvasy(0))
            max_top = content_bottom - viewport_height
            target_top = min(max(current_top + delta, content_top), max_top)
            self.canvas.yview_moveto(
                (target_top - content_top) / (content_height - viewport_height)
            )
        except (
            AttributeError,
            tk.TclError,
            TypeError,
            ValueError,
            ZeroDivisionError,
        ):
            return None
        return None
