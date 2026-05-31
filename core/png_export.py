"""Display-only PNG export helpers for processed diffraction images."""

from pathlib import Path
from typing import Any, Dict

import numpy as np
from PIL import Image

from core.plot_style import PUBLICATION_COLORMAPS


DEFAULT_PNG_COLORMAP = "viridis"
DEFAULT_PNG_DPI = 300


def _finite_float(value: Any, name: str) -> float:
    value = float(value)
    if not np.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def validate_png_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize PNG display options."""
    options = dict(options or {})
    scale = str(options.get("scale", "linear")).strip().lower()
    if scale not in ("linear", "log"):
        raise ValueError("PNG Scale must be 'linear' or 'log'")

    if "vmin" not in options or str(options.get("vmin", "")).strip() == "":
        raise ValueError("PNG I Min is required")
    if "vmax" not in options or str(options.get("vmax", "")).strip() == "":
        raise ValueError("PNG I Max is required")

    vmin = _finite_float(options["vmin"], "PNG I Min")
    vmax = _finite_float(options["vmax"], "PNG I Max")
    if vmax <= vmin:
        raise ValueError("PNG I Max must be > PNG I Min")

    colormap = str(options.get("colormap", DEFAULT_PNG_COLORMAP)).strip()
    if not colormap:
        colormap = DEFAULT_PNG_COLORMAP
    if colormap not in PUBLICATION_COLORMAPS:
        raise ValueError(
            "PNG colormap must be one of: " + ", ".join(PUBLICATION_COLORMAPS)
        )

    dpi_raw = options.get("dpi", DEFAULT_PNG_DPI)
    try:
        dpi = int(dpi_raw)
    except Exception as exc:
        raise ValueError("PNG dpi must be an integer") from exc
    if dpi < 72 or dpi > 1200:
        raise ValueError("PNG dpi must be between 72 and 1200")

    return {
        "scale": scale,
        "vmin": vmin,
        "vmax": vmax,
        "colormap": colormap,
        "dpi": dpi,
    }


def normalize_png_array(arr, vmin: float, vmax: float, scale: str = "linear") -> np.ndarray:
    """Normalize a 2D image to 0..1 for PNG display.

    Non-finite input pixels are returned as 0 here; ``array_to_png_rgb`` masks
    them to black after colormap application so they remain visually distinct
    from finite pixels at the lower display bound.
    """
    opts = validate_png_options(
        {"scale": scale, "vmin": vmin, "vmax": vmax, "colormap": DEFAULT_PNG_COLORMAP}
    )
    data = np.asarray(arr, dtype=np.float32)
    if data.ndim != 2:
        raise ValueError(f"PNG export expects a 2D array, got shape {data.shape}")

    finite = np.isfinite(data)
    clipped = np.empty_like(data, dtype=np.float32)
    clipped[finite] = np.clip(data[finite], opts["vmin"], opts["vmax"])
    clipped[~finite] = opts["vmin"]

    if opts["scale"] == "linear":
        norm = (clipped - opts["vmin"]) / (opts["vmax"] - opts["vmin"])
    else:
        shifted = clipped - opts["vmin"]
        denom = np.log10(1.0 + opts["vmax"] - opts["vmin"])
        norm = np.log10(1.0 + shifted) / denom

    norm = np.clip(norm, 0.0, 1.0)
    norm[~finite] = 0.0
    return norm.astype(np.float32, copy=False)


def array_to_png_rgb(
    arr,
    vmin: float,
    vmax: float,
    scale: str = "linear",
    colormap: str = DEFAULT_PNG_COLORMAP,
) -> np.ndarray:
    """Convert a 2D image to an 8-bit RGB PNG payload."""
    opts = validate_png_options(
        {"scale": scale, "vmin": vmin, "vmax": vmax, "colormap": colormap}
    )
    data = np.asarray(arr, dtype=np.float32)
    finite = np.isfinite(data)
    norm = normalize_png_array(data, vmin=opts["vmin"], vmax=opts["vmax"], scale=opts["scale"])

    try:
        import matplotlib
        cmap = matplotlib.colormaps[opts["colormap"]]
    except AttributeError:
        import matplotlib.cm as cm
        cmap = cm.get_cmap(opts["colormap"])
    rgb = np.rint(cmap(norm)[..., :3] * 255.0).astype(np.uint8)
    rgb[~finite] = 0
    return rgb


def save_png(arr, out_path: Path, png_options: Dict[str, Any]) -> str:
    """Save a processed 2D image as an RGB display PNG."""
    opts = validate_png_options(png_options)
    rgb = array_to_png_rgb(
        arr,
        vmin=opts["vmin"],
        vmax=opts["vmax"],
        scale=opts["scale"],
        colormap=opts["colormap"],
    )
    Image.fromarray(rgb).save(str(out_path), dpi=(opts["dpi"], opts["dpi"]))
    return (
        f"PNG display {opts['scale']} "
        f"[{opts['vmin']:.6g}, {opts['vmax']:.6g}] "
        f"{opts['colormap']} {opts['dpi']} dpi"
    )
