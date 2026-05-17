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
from pathlib import Path

import numpy as np

from core.loader import load_image, _lazy_import_matplotlib


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

    try:
        from PIL import Image as PILImage, ImageTk as PILImageTk
        has_pil = True
    except ImportError:
        has_pil = False

    win = tk.Toplevel(app)
    win.title("\u6279\u91CF\u7F29\u7565\u56FE\u9884\u89C8 (Batch Thumbnail Gallery)")
    win.geometry("1200x800")

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
        foreground="gray",
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
        outer_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_mousewheel(event):
        outer_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_mousewheel(event):
        outer_canvas.unbind_all("<MouseWheel>")

    outer_canvas.bind("<Enter>", _bind_mousewheel)
    outer_canvas.bind("<Leave>", _unbind_mousewheel)

    result_queue = queue.Queue()
    # photo_refs keeps a strong reference to PhotoImage objects so they
    # are not garbage-collected before the widget renders them.
    photo_refs = []

    def _open_full_preview(file_path):
        """Open full preview for a specific file."""
        saved = app.filelist
        app.filelist = [(file_path, Path(file_path.name))]
        from gui.preview import show_preview
        show_preview(app)
        app.filelist = saved

    def _make_thumbnail_widget(idx, file_path, thumb_data, orig_shape):
        row_idx = idx // COLS
        col_idx = idx % COLS

        frame = ttk.Frame(inner_frame, relief="solid", borderwidth=1)
        frame.grid(row=row_idx, column=col_idx, padx=2, pady=2, sticky="nsew")

        if thumb_data is None:
            ttk.Label(frame, text="\u52A0\u8F7D\u5931\u8D25", font=("", 8)).pack()
            return

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
                (THUMB_SIZE, THUMB_SIZE), PILImage.Resampling.BILINEAR
            )
            photo = PILImageTk.PhotoImage(pil_img)
            photo_refs.append(photo)

            label = ttk.Label(frame, image=photo)
            label.image = photo
            label.pack()

            def on_click(event, fp=file_path):
                _open_full_preview(fp)

            label.bind("<Button-1>", on_click)
        else:
            # Fallback: small matplotlib figure (slower, but works without PIL)
            fig_thumb = Figure(figsize=(1.2, 1.2), dpi=50)
            ax = fig_thumb.add_subplot(111)
            ax.imshow(thumb_data, cmap='viridis', aspect='auto')
            ax.axis('off')
            fig_thumb.tight_layout(pad=0)

            canvas_thumb = FigureCanvasTkAgg(fig_thumb, master=frame)
            canvas_thumb.draw()
            canvas_thumb.get_tk_widget().pack()

            def on_click(event, fp=file_path):
                _open_full_preview(fp)

            canvas_thumb.mpl_connect('button_press_event', on_click)

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
                foreground="gray",
            ).pack()

    def load_thumbnails():
        for widget in inner_frame.winfo_children():
            widget.destroy()
        photo_refs.clear()

        files = app.filelist[:max_thumbs_var.get()]
        total = len(files)

        # Thread-safe cancellation flag (set when window is closed)
        _worker_cancel = threading.Event()
        win.protocol(
            "WM_DELETE_WINDOW",
            lambda: (_worker_cancel.set(), win.destroy()),
        )

        def worker():
            """Background thread: load + downsample one image at a time."""
            for idx, (file_path, rel_path) in enumerate(files):
                if _worker_cancel.is_set():
                    return
                try:
                    img = load_image(
                        file_path, app.io_tab.h5_path_var.get()
                    )
                    h, w = img.shape
                    # Choose the largest downsample factor that keeps both
                    # dimensions >= THUMB_SIZE after rebinning.
                    scale = max(1, min(h // THUMB_SIZE, w // THUMB_SIZE))
                    from core.utils import rebin_mean_2d
                    thumb = rebin_mean_2d(
                        img.astype(np.float32), scale
                    )
                    result_queue.put(
                        (idx, file_path, thumb, img.shape, total)
                    )
                except Exception:
                    result_queue.put(
                        (idx, file_path, None, None, total)
                    )

        # Declare the worker thread early so poll_results can reference it
        t = threading.Thread(target=worker, daemon=True)

        def poll_results():
            """Main-thread callback: drain queue, schedule next poll."""
            if not win.winfo_exists():
                return
            # Drain all available results from the queue
            try:
                while True:
                    idx, fpath, thumb_data, orig_shape, total_q = (
                        result_queue.get_nowait()
                    )
                    progress_var.set(f"{idx + 1}/{total_q}")
                    _make_thumbnail_widget(
                        idx, fpath, thumb_data, orig_shape
                    )
            except queue.Empty:
                pass

            if t.is_alive():
                # Worker still running — poll again in 100 ms
                win.after(100, poll_results)
            else:
                # Worker finished — do one final drain in case last
                # items arrived between the drain and the alive check
                try:
                    while True:
                        idx, fpath, thumb_data, orig_shape, total_q = (
                            result_queue.get_nowait()
                        )
                        progress_var.set(f"{idx + 1}/{total_q}")
                        _make_thumbnail_widget(
                            idx, fpath, thumb_data, orig_shape
                        )
                except queue.Empty:
                    pass
                progress_var.set(f"\u5B8C\u6210: {total} \u4E2A\u6587\u4EF6")

        t.start()
        win.after(100, poll_results)

    load_thumbnails()
