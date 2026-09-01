"""Image preview window with ROI selection, comparison view, and line profile."""

import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

import numpy as np

from gui.windowing import fit_window_to_screen

from core.loader import load_image, _lazy_import_matplotlib
from core.processing import apply_processing
from core.png_export import array_to_png_rgb, validate_png_options
from core.plot_style import apply_matplotlib_style, style_figure_axes
from core.utils import parse_roi_text, parse_optional_float, summarize_array_stats


def _sample_line_profile(img, x0, y0, x1, y1):
    """Sample intensity values along a line segment.

    Uses scipy.ndimage.map_coordinates if available, otherwise
    falls back to nearest-neighbor sampling.
    """
    n_samples = max(int(np.hypot(x1 - x0, y1 - y0)), 2)
    x_coords = np.linspace(x0, x1, n_samples)
    y_coords = np.linspace(y0, y1, n_samples)

    try:
        from scipy.ndimage import map_coordinates
        coords = np.array([y_coords, x_coords])
        profile = map_coordinates(
            img.astype(np.float64), coords, order=1, mode='nearest'
        )
    except ImportError:
        xi = np.clip(np.round(x_coords).astype(int), 0, img.shape[1] - 1)
        yi = np.clip(np.round(y_coords).astype(int), 0, img.shape[0] - 1)
        profile = img[yi, xi].astype(np.float64)

    distances = np.linspace(0, np.hypot(x1 - x0, y1 - y0), n_samples)
    return distances, profile


def _roi_from_drag_points(start, end):
    """Convert two image-space drag points to a top-left-origin ROI tuple."""
    x1, y1 = start
    x2, y2 = end
    x = int(min(x1, x2))
    y = int(min(y1, y2))
    w_roi = int(abs(x2 - x1))
    h_roi = int(abs(y2 - y1))
    if w_roi <= 1 or h_roi <= 1:
        return None
    return x, y, w_roi, h_roi


def _resolve_preview_target(app, target_file=None):
    """Return the file to preview, honoring an explicitly selected target."""
    if target_file is not None:
        return Path(target_file)

    if not app.filelist:
        app.count_files(show_dialog=False)
    if not app.filelist:
        return None

    first_file = app.filelist[0]
    if isinstance(first_file, tuple):
        first_file = first_file[0]
    return Path(first_file)


def _register_line_profile_axes(line_image_axes, ax_raw, ax_processed):
    """Keep line-selection axes synchronized after a figure redraw."""
    line_image_axes[:] = [ax_raw, ax_processed]


def _preview_processing_arrays(
    img,
    *,
    dark_frame=None,
    flat_frame=None,
    flat_is_dark_subtracted=True,
    roi=None,
    mask_frame=None,
    mask_nonzero_is_invalid=True,
    clip_negative=False,
    bg_offset=0.0,
    min_intensity=None,
    max_intensity=None,
    rotate_deg="0",
    flip_x=False,
    flip_y=False,
    bin_factor=1,
    pclip_low=None,
    pclip_high=None,
    intensity_transform="none",
    gamma=1.0,
    norm_mode="none",
    hot_pixel_enable=False,
    hot_pixel_window=3,
    hot_pixel_sigma=8.0,
):
    """Return coordinate and final arrays used by the interactive preview.

    The coordinate array deliberately omits ROI and geometry/scaling steps so
    ROI selection and line profiles stay in original-image coordinates.  The
    final array uses the same complete processing options as batch execution.
    """
    shared = {
        "dark_frame": dark_frame,
        "flat_frame": flat_frame,
        "flat_is_dark_subtracted": flat_is_dark_subtracted,
        "mask_frame": mask_frame,
        "mask_nonzero_is_invalid": mask_nonzero_is_invalid,
        "clip_negative": clip_negative,
        "bg_offset": bg_offset,
        "min_intensity": min_intensity,
        "max_intensity": max_intensity,
    }
    coordinate_img = apply_processing(img, roi=None, **shared)
    final_img = apply_processing(
        img,
        roi=roi,
        rotate_deg=rotate_deg,
        flip_x=flip_x,
        flip_y=flip_y,
        bin_factor=bin_factor,
        pclip_low=pclip_low,
        pclip_high=pclip_high,
        intensity_transform=intensity_transform,
        gamma=gamma,
        norm_mode=norm_mode,
        hot_pixel_enable=hot_pixel_enable,
        hot_pixel_window=hot_pixel_window,
        hot_pixel_sigma=hot_pixel_sigma,
        **shared,
    )
    return coordinate_img, final_img


class _PreviewSetupError(Exception):
    """Invalid preview settings that should use the settings-error dialog."""


def _tk_var_get(container, name, default=None):
    """Read a Tk variable from a tab without requiring every test double."""
    if container is None:
        return default
    var = getattr(container, name, None)
    if var is None:
        return default
    try:
        return var.get()
    except Exception:
        return default


def _set_preview_busy_cursor(app, busy):
    cursor = "watch" if busy else ""
    try:
        app.config(cursor=cursor)
    except (AttributeError, tk.TclError, RuntimeError, TypeError):
        pass


def _snapshot_preview_settings(app, first_file, png_enabled, png_opts):
    """Copy Tk-backed preview inputs so the worker never touches widgets."""
    proc_tab = getattr(app, "processing_tab", None)
    geo_tab = getattr(app, "geometry_tab", None)
    return {
        "first_file": first_file,
        "h5_path": _tk_var_get(getattr(app, "io_tab", None), "h5_path_var", ""),
        "roi_text": _tk_var_get(proc_tab, "roi_var", ""),
        "dark_frame": getattr(app, "dark_frame", None),
        "flat_frame": getattr(app, "flat_frame", None),
        "mask_frame": getattr(app, "mask_frame", None),
        "flat_is_dark_subtracted": _tk_var_get(
            proc_tab, "flat_is_dark_subtracted_var", True
        ),
        "mask_nonzero_is_invalid": _tk_var_get(
            proc_tab, "mask_nonzero_is_invalid_var", True
        ),
        "clip_negative": _tk_var_get(proc_tab, "clip_negative_var", False),
        "bg_offset": _tk_var_get(proc_tab, "bg_offset_var", 0.0),
        "min_intensity": parse_optional_float(
            _tk_var_get(proc_tab, "min_intensity_var", "")
        ),
        "max_intensity": parse_optional_float(
            _tk_var_get(proc_tab, "max_intensity_var", "")
        ),
        "rotate_deg": _tk_var_get(geo_tab, "rotate_var", "0"),
        "flip_x": _tk_var_get(geo_tab, "flip_x_var", False),
        "flip_y": _tk_var_get(geo_tab, "flip_y_var", False),
        "bin_factor": _tk_var_get(geo_tab, "bin_factor_var", 1),
        "pclip_low": parse_optional_float(_tk_var_get(geo_tab, "pclip_low_var", "")),
        "pclip_high": parse_optional_float(_tk_var_get(geo_tab, "pclip_high_var", "")),
        "intensity_transform": _tk_var_get(
            geo_tab, "intensity_transform_var", "none"
        ),
        "gamma": _tk_var_get(geo_tab, "gamma_var", 1.0),
        "norm_mode": _tk_var_get(geo_tab, "norm_mode_var", "none"),
        "hot_pixel_enable": _tk_var_get(geo_tab, "hot_pixel_enable_var", False),
        "hot_pixel_window": _tk_var_get(geo_tab, "hot_pixel_window_var", 3),
        "hot_pixel_sigma": _tk_var_get(geo_tab, "hot_pixel_sigma_var", 8.0),
        "png_enabled": png_enabled,
        "png_opts": png_opts,
    }


def _load_preview_payload(snapshot):
    """Load and process preview arrays. Safe to call off the Tk thread."""
    img = load_image(snapshot["first_file"], snapshot["h5_path"])
    try:
        roi = parse_roi_text(snapshot["roi_text"])
        if roi:
            x, y, w, h = roi
            if x + w > img.shape[1] or y + h > img.shape[0]:
                raise ValueError(
                    f"ROI \u8D85\u51FA\u56FE\u50CF\u8303\u56F4 {img.shape}"
                )
    except Exception as exc:
        raise _PreviewSetupError(str(exc)) from exc

    coordinate_img, processed_img = _preview_processing_arrays(
        img,
        dark_frame=snapshot["dark_frame"],
        flat_frame=snapshot["flat_frame"],
        flat_is_dark_subtracted=snapshot["flat_is_dark_subtracted"],
        roi=roi,
        mask_frame=snapshot["mask_frame"],
        mask_nonzero_is_invalid=snapshot["mask_nonzero_is_invalid"],
        clip_negative=snapshot["clip_negative"],
        bg_offset=snapshot["bg_offset"],
        min_intensity=snapshot["min_intensity"],
        max_intensity=snapshot["max_intensity"],
        rotate_deg=snapshot["rotate_deg"],
        flip_x=snapshot["flip_x"],
        flip_y=snapshot["flip_y"],
        bin_factor=snapshot["bin_factor"],
        pclip_low=snapshot["pclip_low"],
        pclip_high=snapshot["pclip_high"],
        intensity_transform=snapshot["intensity_transform"],
        gamma=snapshot["gamma"],
        norm_mode=snapshot["norm_mode"],
        hot_pixel_enable=snapshot["hot_pixel_enable"],
        hot_pixel_window=snapshot["hot_pixel_window"],
        hot_pixel_sigma=snapshot["hot_pixel_sigma"],
    )
    return {
        "raw_img": img.astype(np.float32),
        "coordinate_img": coordinate_img,
        "processed_img": processed_img,
        "roi": roi,
    }


def show_preview(app, target_file=None):
    """Open a preview window with comparison, single, and line profile modes."""
    first_file = _resolve_preview_target(app, target_file)
    if first_file is None:
        messagebox.showinfo(
            "\u65E0\u6587\u4EF6",
            "\u6CA1\u6709\u627E\u5230\u53EF\u9884\u89C8\u7684\u6587\u4EF6\u3002"
        )
        return

    try:
        png_enabled = app.output_tab.format_vars.get('png').get()
    except (AttributeError, KeyError):
        png_enabled = False
    if png_enabled:
        try:
            png_opts = validate_png_options(
                {
                    "scale": app.output_tab.png_scale_var.get(),
                    "vmin": app.output_tab.png_min_var.get(),
                    "vmax": app.output_tab.png_max_var.get(),
                    "colormap": app.output_tab.png_colormap_var.get(),
                    "dpi": app.output_tab.png_dpi_var.get(),
                }
            )
        except Exception as e:
            messagebox.showerror(
                "\u8BBE\u7F6E\u65E0\u6548", f"\u5904\u7406\u8BBE\u7F6E\u9519\u8BEF: {e}"
            )
            return
    else:
        png_opts = None

    snapshot = _snapshot_preview_settings(app, first_file, png_enabled, png_opts)
    result_queue = queue.Queue()
    _set_preview_busy_cursor(app, True)

    def worker():
        try:
            result_queue.put(("ok", _load_preview_payload(snapshot)))
        except Exception as exc:
            result_queue.put(("error", exc))

    def present():
        _set_preview_busy_cursor(app, False)
        try:
            if hasattr(app, "winfo_exists") and not app.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            kind, payload = result_queue.get_nowait()
        except queue.Empty:
            messagebox.showerror(
                "\u9884\u89C8\u9519\u8BEF",
                "\u65E0\u6CD5\u751F\u6210\u9884\u89C8: empty preview queue",
            )
            return
        if kind == "error":
            if isinstance(payload, _PreviewSetupError):
                messagebox.showerror(
                    "\u8BBE\u7F6E\u65E0\u6548",
                    f"\u5904\u7406\u8BBE\u7F6E\u9519\u8BEF: {payload}",
                )
            else:
                messagebox.showerror(
                    "\u9884\u89C8\u9519\u8BEF",
                    f"\u65E0\u6CD5\u751F\u6210\u9884\u89C8: {payload}",
                )
            return
        _present_preview_window(app, snapshot, payload)

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    after = getattr(app, "after", None)
    if callable(after):
        def poll():
            if worker_thread.is_alive():
                try:
                    after(50, poll)
                    return
                except (RuntimeError, tk.TclError):
                    pass
            present()

        try:
            after(50, poll)
            return
        except (RuntimeError, tk.TclError, TypeError):
            pass
    worker_thread.join()
    present()


def _present_preview_window(app, snapshot, payload):
    """Build matplotlib/Tk preview widgets. Must run on the Tk thread."""
    first_file = snapshot["first_file"]
    png_enabled = snapshot["png_enabled"]
    png_opts = snapshot["png_opts"]
    raw_img = payload["raw_img"]
    coordinate_img = payload["coordinate_img"]
    processed_img = payload["processed_img"]
    roi = payload["roi"]

    try:
        Figure, FigureCanvasTkAgg = _lazy_import_matplotlib()
        import matplotlib
        apply_matplotlib_style(matplotlib, preset="raw_inspection")

        win = tk.Toplevel(app)
        win.title(f"\u9884\u89C8: {first_file.name}")
        fit_window_to_screen(
            win,
            preferred_size=(1400, 700),
            minimum_size=(900, 560),
        )

        # ROI coordinates are part of the processing pipeline and always use
        # array coordinates: x=column, y=row, origin=top-left.  The XY export
        # y-origin option only affects exported coordinates, not ROI picking.
        preview_origin = 'upper'
        png_display_img = None
        png_title_suffix = ""
        if png_enabled:
            png_display_img = array_to_png_rgb(
                processed_img,
                vmin=png_opts["vmin"],
                vmax=png_opts["vmax"],
                scale=png_opts["scale"],
                colormap=png_opts["colormap"],
            )
            png_title_suffix = f" [PNG {png_opts['scale']}]"

        # --- Control toolbar ---
        control_frame = ttk.Frame(win)
        control_frame.pack(fill="x", padx=5, pady=5)

        view_mode = tk.StringVar(value="comparison")

        ttk.Radiobutton(
            control_frame, text="\u5BF9\u6BD4\u6A21\u5F0F",
            variable=view_mode, value="comparison",
            command=lambda: update_view(),
        ).pack(side="left", padx=5)
        ttk.Radiobutton(
            control_frame, text="\u5355\u56FE\u6A21\u5F0F",
            variable=view_mode, value="single",
            command=lambda: update_view(),
        ).pack(side="left", padx=5)
        ttk.Radiobutton(
            control_frame, text="\u7EBF\u5F62\u5256\u9762",
            variable=view_mode, value="line_profile",
            command=lambda: update_view(),
        ).pack(side="left", padx=5)

        mode_hint = tk.StringVar(
            value="\u62D6\u52A8\u9009\u62E9 ROI\uFF08\u5DE6\u4E0A\u539F\u70B9\uFF09"
        )
        ttk.Label(
            control_frame, textvariable=mode_hint,
            foreground="gray",
        ).pack(side="left", padx=20)

        def clear_roi_callback():
            app.processing_tab.roi_var.set("")
            win.destroy()
            show_preview(app, target_file=first_file)

        ttk.Button(
            control_frame, text="\u6E05\u7A7A ROI", command=clear_roi_callback
        ).pack(side="right", padx=5)
        ttk.Button(
            control_frame, text="\u786E\u8BA4", command=win.destroy
        ).pack(side="right", padx=5)

        # --- Figure and canvas ---
        fig = Figure(figsize=(14, 7))
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.get_tk_widget().pack(fill="both", expand=True)

        # --- Interaction state ---
        current_rect = [None]
        roi_data = {'start': None}
        roi_target_ax = [None]
        line_image_axes = []
        line_points = []
        line_artists = []

        def _imshow_coordinate(ax):
            return (
                ax.imshow(coordinate_img, cmap='viridis', origin=preview_origin),
                True,
            )

        def _imshow_processed(ax):
            if png_display_img is not None:
                return ax.imshow(png_display_img, origin=preview_origin), False
            return (
                ax.imshow(processed_img, cmap='viridis', origin=preview_origin),
                True,
            )

        def update_view():
            fig.clear()
            current_rect[0] = None
            roi_target_ax[0] = None
            line_image_axes.clear()
            mode = view_mode.get()
            line_points.clear()
            for a in line_artists:
                try:
                    a.remove()
                except Exception:
                    pass
            line_artists.clear()

            if mode == "comparison":
                mode_hint.set(
                    "\u5728\u5750\u6807\u9884\u89C8\u4E0A\u62D6\u52A8\u9009\u62E9 ROI\uFF08\u5DE6\u4E0A\u539F\u70B9\uFF09"
                )
                _draw_comparison()
            elif mode == "single":
                mode_hint.set("\u5355\u56FE\u663E\u793A\u6700\u7EC8\u5904\u7406\u7ED3\u679C")
                _draw_single()
            elif mode == "line_profile":
                mode_hint.set(
                    "\u70B9\u51FB\u4E24\u4E2A\u70B9\u5B9A\u4E49\u7EBF\u6BB5"
                )
                _draw_line_profile_base()

            style_figure_axes(fig, preset="raw_inspection")
            fig.tight_layout()
            canvas.draw()

        def _draw_roi_rect(ax):
            if roi:
                import matplotlib.patches as patches
                rect = patches.Rectangle(
                    (roi[0], roi[1]), roi[2], roi[3],
                    linewidth=2, edgecolor='r', facecolor='none',
                    linestyle='--',
                )
                ax.add_patch(rect)

        def _draw_histogram_dual(ax):
            finite_raw = raw_img[np.isfinite(raw_img)]
            finite_proc = processed_img[np.isfinite(processed_img)]
            if finite_raw.size > 0:
                ax.hist(
                    finite_raw.ravel(), bins=120, alpha=0.5,
                    color="#2a6f97", label="\u539F\u59CB",
                )
            if finite_proc.size > 0:
                ax.hist(
                    finite_proc.ravel(), bins=120, alpha=0.5,
                    color="#e74c3c", label="\u5904\u7406\u540E",
                )
            ax.legend(fontsize=8)
            ax.set_xlabel("Intensity")
            ax.set_ylabel("Pixel Count")
            ax.grid(True, ls='--', alpha=0.4)
            ax.set_title("\u5F3A\u5EA6\u76F4\u65B9\u56FE")
            combined = (
                f"[\u539F\u59CB] {summarize_array_stats(raw_img)}\n"
                f"[\u5904\u7406] {summarize_array_stats(processed_img)}"
            )
            ax.text(
                0.02, 0.98, combined,
                va='top', transform=ax.transAxes, fontsize=7,
            )

        def _draw_comparison():
            ax_raw = fig.add_subplot(131)
            ax_coord = fig.add_subplot(132)
            ax_hist = fig.add_subplot(133)

            im_raw = ax_raw.imshow(
                raw_img, cmap='viridis', origin=preview_origin
            )
            fig.colorbar(im_raw, ax=ax_raw, label='Intensity')
            ax_raw.set_title("\u539F\u59CB\u56FE\u50CF (Raw)")

            im_proc, show_colorbar = _imshow_coordinate(ax_coord)
            if show_colorbar:
                fig.colorbar(im_proc, ax=ax_coord, label='Intensity')
            ax_coord.set_title(
                "\u5750\u6807\u9884\u89C8\uFF08ROI \u9009\u62E9\u7528\uFF09"
            )
            _draw_roi_rect(ax_coord)
            roi_target_ax[0] = ax_coord

            _draw_histogram_dual(ax_hist)

        def _draw_single():
            ax_img = fig.add_subplot(121)
            ax_hist = fig.add_subplot(122)

            im, show_colorbar = _imshow_processed(ax_img)
            if show_colorbar:
                fig.colorbar(im, ax=ax_img, label='Intensity')
            ax_img.set_title(
                "\u6700\u7EC8\u5904\u7406\u7ED3\u679C"
                + png_title_suffix
            )

            finite = processed_img[np.isfinite(processed_img)]
            if finite.size > 0:
                ax_hist.hist(finite, bins=120, color="#2a6f97", alpha=0.8)
                ax_hist.set_xlabel("Intensity")
                ax_hist.set_ylabel("Pixel Count")
                ax_hist.grid(True, ls='--', alpha=0.4)
                ax_hist.set_title("\u5F3A\u5EA6\u76F4\u65B9\u56FE")
                stats_text = summarize_array_stats(processed_img)
                ax_hist.text(
                    0.02, 0.98, stats_text,
                    va='top', transform=ax_hist.transAxes, fontsize=9,
                )
            else:
                ax_hist.text(
                    0.02, 0.95,
                    "\u5904\u7406\u540E\u65E0\u6709\u6548\u50CF\u7D20\u3002",
                    va='top', transform=ax_hist.transAxes,
                )
                ax_hist.set_title("\u5F3A\u5EA6\u76F4\u65B9\u56FE")

        def _draw_line_profile_base():
            """Draw images with placeholder for line profile."""
            ax_raw = fig.add_subplot(131)
            ax_proc = fig.add_subplot(132)
            ax_profile = fig.add_subplot(133)

            ax_raw.imshow(raw_img, cmap='viridis', origin=preview_origin)
            ax_raw.set_title("\u539F\u59CB\u56FE\u50CF (\u70B9\u51FB\u5B9A\u4E49\u7EBF\u6BB5)")

            _imshow_coordinate(ax_proc)
            ax_proc.set_title("\u5750\u6807\u9884\u89C8\uFF08\u5256\u9762\u9009\u62E9\u7528\uFF09")
            _register_line_profile_axes(line_image_axes, ax_raw, ax_proc)

            ax_profile.set_xlabel("\u50CF\u7D20\u8DDD\u79BB (Pixel Distance)")
            ax_profile.set_ylabel("\u5F3A\u5EA6 (Intensity)")
            ax_profile.set_title(
                "\u7EBF\u5F62\u5256\u9762 (\u70B9\u51FB\u56FE\u50CF\u5B9A\u4E49\u7EBF\u6BB5)"
            )
            ax_profile.grid(True, ls='--', alpha=0.4)
            ax_profile.text(
                0.5, 0.5,
                "\u5728\u5DE6\u4FA7\u56FE\u50CF\u4E0A\u70B9\u51FB\u4E24\u4E2A\u70B9",
                ha='center', va='center', transform=ax_profile.transAxes,
                fontsize=10, color='gray',
            )

        def update_line_profile():
            if len(line_points) < 2:
                return
            x0, y0 = line_points[0]
            x1, y1 = line_points[1]

            dist_raw, prof_raw = _sample_line_profile(
                raw_img, x0, y0, x1, y1
            )
            dist_proc, prof_proc = _sample_line_profile(
                coordinate_img, x0, y0, x1, y1
            )

            fig.clear()
            ax_raw = fig.add_subplot(131)
            ax_proc = fig.add_subplot(132)
            ax_profile = fig.add_subplot(133)

            ax_raw.imshow(raw_img, cmap='viridis', origin=preview_origin)
            ax_raw.plot([x0, x1], [y0, y1], 'r-', linewidth=2)
            ax_raw.plot(x0, y0, 'ro', markersize=6)
            ax_raw.plot(x1, y1, 'ro', markersize=6)
            ax_raw.set_title("\u539F\u59CB\u56FE\u50CF + \u7EBF\u6BB5")

            _imshow_coordinate(ax_proc)
            ax_proc.plot([x0, x1], [y0, y1], 'r-', linewidth=2)
            ax_proc.plot(x0, y0, 'ro', markersize=6)
            ax_proc.plot(x1, y1, 'ro', markersize=6)
            ax_proc.set_title("\u5750\u6807\u9884\u89C8 + \u7EBF\u6BB5")

            ax_profile.plot(
                dist_raw, prof_raw, alpha=0.7,
                label="\u539F\u59CB", color="#2a6f97",
            )
            ax_profile.plot(
                dist_proc, prof_proc, alpha=0.7,
                label="\u5750\u6807\u9884\u89C8", color="#e74c3c",
            )
            ax_profile.set_xlabel("\u50CF\u7D20\u8DDD\u79BB (Pixel Distance)")
            ax_profile.set_ylabel("\u5F3A\u5EA6 (Intensity)")
            ax_profile.set_title("\u7EBF\u5F62\u5256\u9762 (Line Profile)")
            ax_profile.legend(fontsize=8)
            ax_profile.grid(True, ls='--', alpha=0.4)

            _register_line_profile_axes(line_image_axes, ax_raw, ax_proc)

            style_figure_axes(fig, preset="raw_inspection")
            fig.tight_layout()
            canvas.draw()
            line_points.clear()

        # --- Mouse event handlers ---
        def on_mouse_press(event):
            if event.inaxes is None or event.xdata is None:
                return

            mode = view_mode.get()

            if mode == "line_profile":
                if event.inaxes not in line_image_axes:
                    return
                line_points.append((event.xdata, event.ydata))
                if len(line_points) == 1:
                    marker_axes = []
                    if event.inaxes is not None:
                        marker_axes = [event.inaxes]
                    elif line_image_axes:
                        marker_axes = list(line_image_axes)
                    for ax in marker_axes:
                        if ax is None:
                            continue
                        artist, = ax.plot(
                            event.xdata, event.ydata,
                            'ro', markersize=6,
                        )
                        line_artists.append(artist)
                    if marker_axes:
                        canvas.draw()
                elif len(line_points) == 2:
                    update_line_profile()
                return

            # ROI mode (comparison or single)
            if event.inaxes is not roi_target_ax[0]:
                return
            roi_data['start'] = (event.xdata, event.ydata)

        def on_mouse_release(event):
            if view_mode.get() == "line_profile":
                return
            if event.inaxes is not roi_target_ax[0] or roi_data['start'] is None:
                return
            if event.xdata is None or event.ydata is None:
                return
            roi_tuple = _roi_from_drag_points(
                roi_data['start'], (event.xdata, event.ydata)
            )
            roi_data['start'] = None
            if roi_tuple is None:
                return
            x, y, w_roi, h_roi = roi_tuple

            roi_str = f"{x},{y},{w_roi},{h_roi}"
            app.processing_tab.roi_var.set(roi_str)
            app.log(f"ROI \u5DF2\u9009\u62E9: {roi_str}")
            win.destroy()
            show_preview(app, target_file=first_file)

        def on_mouse_move(event):
            if view_mode.get() == "line_profile":
                return
            if roi_data['start'] is None or event.inaxes is not roi_target_ax[0]:
                return
            if current_rect[0] is not None:
                try:
                    current_rect[0].remove()
                except Exception:
                    pass
            import matplotlib.patches as patches
            if event.xdata is None or event.ydata is None:
                return
            x1, y1 = roi_data['start']
            x2, y2 = (event.xdata, event.ydata)
            x = min(x1, x2)
            y = min(y1, y2)
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            current_rect[0] = patches.Rectangle(
                (x, y), w, h,
                linewidth=2, edgecolor='g', facecolor='none',
                linestyle=':',
            )
            roi_target_ax[0].add_patch(current_rect[0])
            canvas.draw_idle()

        canvas.mpl_connect('button_press_event', on_mouse_press)
        canvas.mpl_connect('button_release_event', on_mouse_release)
        canvas.mpl_connect('motion_notify_event', on_mouse_move)

        # Initial draw
        update_view()

    except Exception as e:
        messagebox.showerror(
            "\u9884\u89C8\u9519\u8BEF",
            f"\u65E0\u6CD5\u751F\u6210\u9884\u89C8: {e}"
        )
