# GUI Layout Readability Design

## Goal

Improve RingSentry's main GUI so it feels more like a commercial scientific desktop tool while preserving all existing processing behavior, configuration variables, and command callbacks.

## Current Evidence

- Main window: `gui/app.py` builds a top notebook plus a fixed bottom log panel.
- Main workflow tabs: `gui/tabs/io_tab.py`, `processing_tab.py`, `output_tab.py`, and `geometry_tab.py` stack many `LabelFrame` sections directly inside a fixed notebook page.
- Existing geometry pressure is measurable: the output format tab requests about 657 px of content height, while the log panel requests about 239 px. At the current minimum window height of 800 px, this leaves too little vertical room for readable parameter pages.
- The Q calculator already uses a scrollable left panel, so a scrollable scientific-control layout matches an existing local pattern.

## First-Round Scope

This round addresses layout density, readability, and control clarity without modifying image-processing algorithms.

In scope:

- Add a reusable scrollable tab container for parameter-heavy pages.
- Apply it to the main parameter tabs where vertical crowding is most likely: input/output, preprocessing, output formats, geometry/scaling, and automatic QC.
- Make the bottom run/log panel less visually dominant by reducing default log height and improving spacing.
- Strengthen ttk styles for a calmer scientific software look: consistent typography, tab spacing, section spacing, and primary action styling.
- Add GUI structure tests that prove the reusable scroll container exists and the converted tabs still expose their original public variables and controls.

Out of scope for this round:

- No change to core image-processing math.
- No workflow wizard rewrite.
- No removal of existing buttons or output formats.
- No change to config key names.
- No change to the CBF overexposure repair workflow, except shared theme improvements.

## Design

### Layout Architecture

Create `gui/layout.py` with a `ScrollableFrame` widget. It owns a `Canvas`, a vertical scrollbar, and an inner `ttk.Frame`. Tabs that need vertical breathing room subclass or compose this helper so their existing controls live inside the scrollable body.

The helper must:

- Expand horizontally with the notebook page.
- Keep the inner frame width synchronized with the visible canvas width.
- Update scroll region when child content changes.
- Support mouse wheel scrolling while the pointer is over the scrollable region.

### Tab Conversion

For each crowded tab, keep existing variable names and callback methods on the tab object. Only the parent container for top-level widgets changes from the tab itself to a scrollable body frame.

This preserves existing app code such as `app.processing_tab.roi_var`, tests that inspect tab variables, and command bindings such as `self.app.preview_image`.

### Bottom Panel

The log panel remains always visible because it is part of the batch-processing workflow. Its default text height is reduced from 8 rows to 5 rows so parameter pages get more room. Progress and statistics remain visible.

### Visual Style

Use the existing `sv-ttk` light theme and configure ttk styles only. Keep the palette restrained: neutral background, clear text hierarchy, conservative accent color for the main run button, and no decorative gradients.

### Verification

Evidence for this round:

- `py -m pytest tests/test_gui_layout.py -q`
- `py -m pytest tests/test_gui_resilience.py::GuiResilienceTests::test_output_tab_has_png_options_default_off -q`
- `py -m compileall -q .`
- A Tk geometry smoke check that creates the app, updates idle tasks, and confirms converted tabs contain a scroll canvas.

## Risks

- Tk mouse-wheel bindings can leak globally if bound with `bind_all`. The helper should bind only on pointer enter and unbind on leave.
- Moving widget parents can break tests if public attributes disappear. The implementation must keep tab object attributes and variables unchanged.
- Reducing log height improves space but may show fewer lines initially. Existing scrollback remains in the `Text` widget.
