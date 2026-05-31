# UI/UX Audit - 2026-05-31

## Scope

Audited the Tkinter GUI entry points under `gui/`: main window, Notebook tabs, file selection, processing controls, output settings, geometry/Q tools, preview/gallery windows, status/log area, and CBF overexposure repair workflow.

## Main Findings

### Layout Crowding Or Clipping

- Main workflow tabs originally stacked many `LabelFrame` sections vertically while the bottom log panel stayed fixed. This created height pressure at small windows and high DPI. The input/output, preprocessing, output, geometry, and quality tabs now use scrollable bodies, but overexposure repair still has dense nested tabs and action rows.
- Output formats tab still mixes matrix outputs, text outputs, XY options, PNG display settings, and overwrite/lossless behavior on one page. It is scrollable now, but the information hierarchy remains noisy.
- Q calculator has a better split layout than most tabs, but its left panel contains many compact controls and uses global mouse-wheel binding, which can interfere with other scroll regions.
- Preview and gallery windows have useful large image areas, but their toolbars are compact and do not share the main app's button hierarchy.

### Duplicate Or Confusing Entrances

- File and calibration controls had repeated generic actions such as Browse/Clear/Manage. Input and preprocessing pages now use contextual names such as "选择输入文件", "清空暗帧", and "管理平场".
- Output page has multiple CSV/DAT choices: matrix CSV/DAT and XY CSV/DAT. These are valid but need stronger grouping and tooltips to prevent users from selecting the wrong export form.
- Q calculator has compact `CSV` and `PNG` buttons, which are export actions but read like format toggles.
- Overexposure repair has scan, dry-run, repair, stop, open output, and open report in one dense row. The actions are distinct but their order and visual priority need clearer grouping.

### Non-Intuitive Naming

- Output page labels such as `PNG Scale`, `PNG I Min`, `PNG I Max`, and the long lossless matrix checkbox are technical and visually heavy.
- Q calculator button text such as `>>> 计算 / Calculate <<<` and `从当前图像获取探测器尺寸` looks script-like rather than polished.
- Overexposure repair has many mojibake strings in the current file encoding, so labels can render as unreadable text in the source and potentially in the GUI.

### Missing Tooltip, Disabled State, Or Feedback

- PNG display range controls are visible and editable even when PNG export is not selected. They should be disabled until PNG is enabled.
- Destructive or risky options such as overwrite output/original are present. Some have tooltips, but they need clearer grouping and visual treatment.
- Log output is always visible and now shorter, but the run controls still do not expose a compact status summary before/after processing beyond progress/stats.
- Gallery and preview use status hints, but mouse-wheel handling should avoid global `bind_all` patterns.

### Unclear Tab Hierarchy

- Output formats needs a stronger flow: matrix preservation, human-viewable display images, XY export, then global behavior.
- Overexposure repair is functionally separate from normal preprocessing and should visually read like a safe repair workflow: files, rule, safety, metadata, log, then actions.
- Q calculator is feature-rich and should keep plot/results dominant while reducing visual weight of parameter text.

### Size, Spacing, Scroll, DPI

- The main window minimum is `1100x800`; after scrollable tabs and compact log height this is safer, but high DPI still needs validation by runtime screenshots or manual checks.
- Long text checkbuttons and labels should be shortened, with detail moved into tooltips.
- Tree/table column widths in Q calculator are manually fixed; they may need future DPI-aware adjustment.

## Immediate Next Fixes

1. DONE: Disable PNG option fields until PNG export is selected.
2. DONE: Shorten and clarify output page labels and the lossless export checkbox.
3. DONE: Preserve all output format variables and config keys.
4. DONE: Add regression tests for PNG control state and contextual button labels.
5. DONE: Add shared plotting/export presets for raw inspection, single-column, double-column, presentation, and publication outputs.
6. DONE: Add PNG colormap/dpi/preset controls while keeping PNG export display-only and pixel-size preserving.
7. DONE: Upgrade Q calculator figure export from PNG-only to PNG/PDF/SVG/EPS with the shared presets.
8. Later: clean overexposure repair mojibake labels and action grouping without touching repair logic.
9. Later: add true axis/colorbar publication export for processed 2D images if the project adds a figure-based export path beyond raw display PNG.
