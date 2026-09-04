"""Batch thumbnail gallery for quick QC of multiple files.

Architecture
------------
Images are loaded in a background thread to keep the GUI responsive.
Results are passed to the main thread via a queue.Queue, and the main
thread polls the queue every 100 ms using win.after().  This avoids
calling tkinter from a background thread (tkinter is NOT thread-safe).
"""

import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np

from core.loader import load_image, _lazy_import_matplotlib
from core.plot_style import apply_matplotlib_style, style_axis
from gui.layout import wheel_scroll_units
from gui.windowing import fit_window_to_screen

_wheel_scroll_units = wheel_scroll_units


def _thumbnail_dimensions(shape, max_size=64):
    """Fit ``(height, width)`` into a square box without distorting it."""
    height, width = int(shape[0]), int(shape[1])
    max_size = max(1, int(max_size))
    if height <= 0 or width <= 0:
        return max_size, max_size

    scale = min(max_size / width, max_size / height)
    display_width = max(1, int(round(width * scale)))
    display_height = max(1, int(round(height * scale)))
    return display_width, display_height


def _open_full_preview(app, file_path):
    """Open a gallery item without changing the app's current file list."""
    from gui.preview import show_preview

    show_preview(app, target_file=file_path)


def _bind_preview_activation(widget, app, file_path):
    """Make a thumbnail usable by pointer and keyboard without changing input state."""
    widget.configure(takefocus=True, cursor="hand2")

    def activate(_event=None):
        _open_full_preview(app, file_path)
        return "break"

    widget.bind("<Button-1>", activate, add="+")
    widget.bind("<Return>", activate, add="+")
    widget.bind("<space>", activate, add="+")
    return activate


def show_gallery(app):
    """Open a scrollable thumbnail gallery window."""
    if not app.filelist:
        app.count_files(show_dialog=False)
    if not app.filelist:
        messagebox.showinfo(
            "\u65E0\u6587\u4EF6",
            "\u6CA1\u6709\u627E\u5230\u53EF\u9884\u89C8\u7684\u6587\u4EF6\u3002"
        )
        return

    Figure, FigureCanvasTkAgg = _lazy_import_matplotlib()
    import matplotlib.cm
    import matplotlib
    apply_matplotlib_style(matplotlib, preset="raw_inspection")

    try:
        from PIL import Image as PILImage, ImageTk as PILImageTk
        has_pil = True
    except ImportError:
        has_pil = False

    win = tk.Toplevel(app)
    win.title("\u6279\u91CF\u7F29\u7565\u56FE\u9884\u89C8 (Batch Thumbnail Gallery)")
    fit_window_to_screen(
        win,
        preferred_size=(1200, 800),
        minimum_size=(760, 520),
    )

    THUMB_SIZE = 64
    COLS = 8

    # --- Controls ---
    ctrl_frame = ttk.Frame(win)
    ctrl_frame.pack(fill="x", padx=5, pady=5)

    max_thumbs_var = tk.IntVar(value=100)
    ttk.Label(ctrl_frame, text="\u6700\u5927\u663E\u793A\u6570:").pack(
        side="left", padx=5
    )
    ttk.Spinbox(
        ctrl_frame, from_=10, to=500,
        textvariable=max_thumbs_var, width=6,
    ).pack(side="left")
    ttk.Button(
        ctrl_frame, text="\u5237\u65B0",
        command=lambda: load_thumbnails(),
    ).pack(side="left", padx=10)
    progress_var = tk.StringVar(value="")
    ttk.Label(ctrl_frame, textvariable=progress_var).pack(side="left", padx=10)
    ttk.Label(
        ctrl_frame,
        text="\u70B9\u51FB\u7F29\u7565\u56FE\u6253\u5F00\u5B8C\u6574\u9884\u89C8",
        style="Muted.TLabel",
    ).pack(side="right", padx=5)

    # --- Scrollable area ---
    canvas_frame = ttk.Frame(win)
    canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)

    outer_canvas = tk.Canvas(canvas_frame)
    scrollbar = ttk.Scrollbar(
        canvas_frame, orient="vertical", command=outer_canvas.yview
    )
    inner_frame = ttk.Frame(outer_canvas)

    inner_frame.bind(
        "<Configure>",
        lambda e: outer_canvas.configure(
            scrollregion=outer_canvas.bbox("all")
        ),
    )
    canvas_window_id = outer_canvas.create_window(
        (0, 0), window=inner_frame, anchor="nw"
    )
    outer_canvas.configure(yscrollcommand=scrollbar.set)

    def _on_canvas_configure(event):
        outer_canvas.itemconfig(canvas_window_id, width=event.width)

    outer_canvas.bind("<Configure>", _on_canvas_configure)

    outer_canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Mouse wheel scrolling
    def _on_mousewheel(event):
        try:
            if not outer_canvas.winfo_viewable():
                return None
        except tk.TclError:
            return None
        x0 = outer_canvas.winfo_rootx()
        y0 = outer_canvas.winfo_rooty()
        x1 = x0 + outer_canvas.winfo_width()
        y1 = y0 + outer_canvas.winfo_height()
        if not (x0 <= event.x_root < x1 and y0 <= event.y_root < y1):
            return None
        units = wheel_scroll_units(event)
        if not units:
            return None
        outer_canvas.yview_scroll(units, "units")
        return "break"

    win.bind("<MouseWheel>", _on_mousewheel, add="+")
    win.bind("<Button-4>", _on_mousewheel, add="+")
    win.bind("<Button-5>", _on_mousewheel, add="+")

    # photo_refs keeps a strong reference to PhotoImage objects so they
    # are not garbage-collected before the widget renders them.
    photo_refs = []
    gallery_state = {
        "generation": 0,
        "cancel_event": None,
        "closed": False,
    }

    def _window_exists():
        if gallery_state["closed"]:
            return False
        try:
            return bool(win.winfo_exists())
        except tk.TclError:
            return False

    def _close_gallery():
        gallery_state["closed"] = True
        cancel_event = gallery_state["cancel_event"]
        if cancel_event is not None:
            cancel_event.set()
        try:
            win.destroy()
        except tk.TclError:
            pass

    win.protocol("WM_DELETE_WINDOW", _close_gallery)

    def _make_thumbnail_widget(idx, file_path, thumb_data, orig_shape):
        row_idx = idx // COLS
        col_idx = idx % COLS

        frame = ttk.Frame(inner_frame, relief="solid", borderwidth=1)
        frame.grid(row=row_idx, column=col_idx, padx=2, pady=2, sticky="nsew")

        if thumb_data is None:
            fail_label = ttk.Label(frame, text="\u52A0\u8F7D\u5931\u8D25", font=("", 8))
            fail_label.pack()
            name = file_path.name
            if len(name) > 14:
                name = name[:11] + "..."
            name_label = ttk.Label(frame, text=name, font=("Consolas", 7))
            name_label.pack()
            _bind_preview_activation(fail_label, app, file_path)
            _bind_preview_activation(name_label, app, file_path)
            return

        display_width, display_height = _thumbnail_dimensions(
            orig_shape or thumb_data.shape, THUMB_SIZE
        )

        if has_pil:
            # PIL path: normalize -> apply colormap -> resize.
            # ~10x faster than creating a matplotlib Figure per thumbnail.
            finite = thumb_data[np.isfinite(thumb_data)]
            if finite.size > 0:
                vmin, vmax = np.percentile(finite, [2, 98])
            else:
                vmin, vmax = 0, 1
            if vmax <= vmin:
                vmax = vmin + 1
            normalized = np.clip(
                (thumb_data - vmin) / (vmax - vmin), 0, 1
            )
            rgba = matplotlib.cm.viridis(normalized)
            uint8_data = (rgba * 255).astype(np.uint8)

            pil_img = PILImage.fromarray(uint8_data)
            pil_img = pil_img.resize(
                (display_width, display_height), PILImage.Resampling.BILINEAR
            )
            photo = PILImageTk.PhotoImage(pil_img)
            photo_refs.append(photo)

            label = ttk.Label(frame, image=photo)
            label.image = photo
            label.pack()
            _bind_preview_activation(label, app, file_path)
        else:
            # Fallback: small matplotlib figure (slower, but works without PIL)
            fig_thumb = Figure(
                figsize=(display_width / 50, display_height / 50), dpi=50
            )
            ax = fig_thumb.add_subplot(111)
            ax.imshow(thumb_data, cmap='viridis', aspect='equal')
            ax.axis('off')
            style_axis(ax, preset="raw_inspection")
            fig_thumb.tight_layout(pad=0)

            canvas_thumb = FigureCanvasTkAgg(fig_thumb, master=frame)
            canvas_thumb.draw()
            canvas_widget = canvas_thumb.get_tk_widget()
            canvas_widget.pack()
            _bind_preview_activation(canvas_widget, app, file_path)

        # Filename label
        name = file_path.name
        if len(name) > 14:
            name = name[:11] + "..."
        ttk.Label(frame, text=name, font=("Consolas", 7)).pack()

        if orig_shape:
            ttk.Label(
                frame,
                text=f"{orig_shape[0]}x{orig_shape[1]}",
                font=("Consolas", 6),
                style="Muted.TLabel",
            ).pack()

    def load_thumbnails():
        # Refreshes invalidate every result from the previous worker before
        # clearing the view, so an old worker can never repopulate this view.
        previous_cancel = gallery_state["cancel_event"]
        if previous_cancel is not None:
            previous_cancel.set()
        gallery_state["generation"] += 1
        generation = gallery_state["generation"]
        worker_cancel = threading.Event()
        gallery_state["cancel_event"] = worker_cancel
        # Each refresh owns its queue.  A stale poll must never consume and
        # discard a result produced by the newer refresh generation.
        result_queue = queue.Queue()

        for widget in inner_frame.winfo_children():
            widget.destroy()
        photo_refs.clear()

        # Snapshot all Tk-backed values before starting the worker.  The
        # background thread must only use ordinary Python values thereafter.
        files = list(app.filelist[:max_thumbs_var.get()])
        h5_path = app.io_tab.h5_path_var.get()
        total = len(files)

        def worker():
            """Background thread: load + downsample one image at a time."""
            for idx, file_entry in enumerate(files):
                if worker_cancel.is_set():
                    return
                if isinstance(file_entry, tuple):
                    file_path = file_entry[0]
                else:
                    file_path = file_entry
                try:
                    img = load_image(file_path, h5_path)
                    h, w = img.shape
                    # Choose the largest downsample factor that keeps both
                    # dimensions >= THUMB_SIZE after rebinning.
                    scale = max(1, min(h // THUMB_SIZE, w // THUMB_SIZE))
                    from core.utils import rebin_mean_2d
                    thumb = rebin_mean_2d(
                        img.astype(np.float32), scale
                    )
                    result_queue.put(
                        (generation, idx, file_path, thumb, img.shape, total)
                    )
                except Exception:
                    result_queue.put(
                        (generation, idx, file_path, None, None, total)
                    )

        # Declare the worker thread early so poll_results can reference it
        t = threading.Thread(target=worker, daemon=True)

        def poll_results():
            """Main-thread callback: drain queue, schedule next poll."""
            if not _window_exists():
                return
            if gallery_state["generation"] != generation:
                return

            def drain_results():
                """Render only results belonging to this refresh generation."""
                try:
                    while True:
                        (
                            result_generation,
                            idx,
                            fpath,
                            thumb_data,
                            orig_shape,
                            total_q,
                        ) = result_queue.get_nowait()
                        if result_generation != generation:
                            continue
                        progress_var.set(f"{idx + 1}/{total_q}")
                        _make_thumbnail_widget(
                            idx, fpath, thumb_data, orig_shape
                        )
                except queue.Empty:
                    pass

            # Drain all available results from the queue
            drain_results()

            # A refresh may have happened while this callback was running.
            # The new generation owns all subsequent polling and completion UI.
            if gallery_state["generation"] != generation:
                return

            if t.is_alive():
                # Worker still running — poll again in 100 ms
                win.after(100, poll_results)
            else:
                # Worker finished — do one final drain in case last
                # items arrived between the drain and the alive check
                drain_results()
                if gallery_state["generation"] == generation:
                    progress_var.set(f"\u5B8C\u6210: {total} \u4E2A\u6587\u4EF6")

        t.start()
        win.after(100, poll_results)

    load_thumbnails()
