# GUI Layout Readability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a scrollable, more readable GUI layout foundation for RingSentry's crowded main workflow tabs without changing processing behavior.

**Architecture:** Add a small reusable `ScrollableFrame` in `gui/layout.py`, then move top-level controls in crowded tabs into that scrollable body while preserving tab attributes and callbacks. Keep visual polish in `gui/styles.py` and reduce bottom log panel height in `gui/log_panel.py`.

**Tech Stack:** Python 3, Tkinter/ttk, sv-ttk, unittest/pytest.

---

### Task 1: Add GUI Layout Regression Tests

**Files:**
- Create: `tests/test_gui_layout.py`

- [ ] **Step 1: Write failing tests**

```python
import unittest

try:
    import tkinter as tk
except Exception:
    tk = None


class GuiLayoutTests(unittest.TestCase):
    def setUp(self):
        if tk is None:
            self.skipTest("tkinter is not available")

    def test_scrollable_frame_exposes_body_and_canvas(self):
        from gui.layout import ScrollableFrame

        root = tk.Tk()
        root.withdraw()
        try:
            frame = ScrollableFrame(root, padding=12)
            frame.pack(fill="both", expand=True)
            tk.Label(frame.body, text="inside").pack()
            root.update_idletasks()

            self.assertIsNotNone(frame.body)
            self.assertGreaterEqual(frame.canvas.winfo_reqwidth(), 1)
        finally:
            root.destroy()

    def test_main_parameter_tabs_are_scrollable_without_losing_public_vars(self):
        from gui.app import App

        try:
            app = App()
            app.withdraw()
            app.update_idletasks()
        except tk.TclError as exc:
            self.skipTest(f"Tk display is unavailable: {exc}")

        try:
            tabs = [
                app.io_tab,
                app.processing_tab,
                app.output_tab,
                app.geometry_tab,
                app.quality_tab,
            ]
            for tab in tabs:
                self.assertTrue(hasattr(tab, "scrollable"))
                self.assertTrue(hasattr(tab, "body"))

            self.assertTrue(hasattr(app.processing_tab, "roi_var"))
            self.assertTrue(hasattr(app.output_tab, "format_vars"))
            self.assertTrue(hasattr(app.geometry_tab, "bin_factor_var"))
            self.assertTrue(hasattr(app.quality_tab, "result_text"))
        finally:
            app.destroy()
```

- [ ] **Step 2: Run tests to verify RED**

Run: `py -m pytest tests/test_gui_layout.py -q`

Expected: FAIL because `gui.layout` does not exist or converted tabs do not expose `scrollable`.

### Task 2: Implement Reusable ScrollableFrame

**Files:**
- Create: `gui/layout.py`

- [ ] **Step 1: Add minimal implementation**

```python
import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, padding=0, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas, padding=padding)
        self._window_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.body.bind("<Configure>", self._sync_scroll_region)
        self.canvas.bind("<Configure>", self._sync_body_width)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _sync_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_body_width(self, event):
        self.canvas.itemconfigure(self._window_id, width=event.width)

    def _bind_mousewheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
```

- [ ] **Step 2: Run first layout test**

Run: `py -m pytest tests/test_gui_layout.py::GuiLayoutTests::test_scrollable_frame_exposes_body_and_canvas -q`

Expected: PASS.

### Task 3: Convert Crowded Tabs to Scrollable Bodies

**Files:**
- Modify: `gui/tabs/io_tab.py`
- Modify: `gui/tabs/processing_tab.py`
- Modify: `gui/tabs/output_tab.py`
- Modify: `gui/tabs/geometry_tab.py`
- Modify: `gui/tabs/quality_tab.py`

- [ ] **Step 1: Import `ScrollableFrame`**

Add `from gui.layout import ScrollableFrame` to each converted tab.

- [ ] **Step 2: Create `self.scrollable` and `self.body`**

In each tab constructor, keep `super().__init__(parent, padding=0)`, then in `_create_widgets` create:

```python
self.columnconfigure(0, weight=1)
self.rowconfigure(0, weight=1)
self.scrollable = ScrollableFrame(self, padding=15)
self.scrollable.grid(row=0, column=0, sticky="nsew")
self.body = self.scrollable.body
body = self.body
```

- [ ] **Step 3: Move only top-level widget parents**

For each top-level frame currently parented to `self`, parent it to `body` instead. Keep all `StringVar`, `BooleanVar`, `Button`, `Entry`, and callback attribute names unchanged.

- [ ] **Step 4: Run converted-tab test**

Run: `py -m pytest tests/test_gui_layout.py::GuiLayoutTests::test_main_parameter_tabs_are_scrollable_without_losing_public_vars -q`

Expected: PASS.

### Task 4: Reduce Bottom Log Panel Dominance

**Files:**
- Modify: `gui/log_panel.py`

- [ ] **Step 1: Reduce default log height**

Change `height=8` on `self.log_txt` to `height=5`.

- [ ] **Step 2: Keep progress and stats unchanged**

Do not rename `prog`, `stats_labels`, `eta_label`, `count_btn`, `run_btn`, or `cancel_btn`.

- [ ] **Step 3: Run resilience smoke test**

Run: `py -m pytest tests/test_gui_resilience.py::GuiResilienceTests::test_output_tab_has_png_options_default_off -q`

Expected: PASS.

### Task 5: Style Polish and Full Verification

**Files:**
- Modify: `gui/styles.py`

- [ ] **Step 1: Strengthen ttk styles**

Configure these styles:

```python
style.configure("TFrame", background="#f6f7f9")
style.configure("TLabelframe", padding=8)
style.configure("TNotebook.Tab", font=("Microsoft YaHei UI", 10), padding=[16, 8])
style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))
```

- [ ] **Step 2: Run verification**

Run:

```bash
py -m pytest tests/test_gui_layout.py -q
py -m pytest tests/test_gui_resilience.py::GuiResilienceTests::test_output_tab_has_png_options_default_off -q
py -m compileall -q .
```

Expected: all commands exit 0.

## Self-Review

- The plan covers layout crowding, readability, preserved public variables, reduced log panel dominance, and verification.
- It does not alter image-processing behavior or config semantics.
- It contains no deferred implementation placeholders.
