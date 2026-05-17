"""Utility functions for the image processor."""

from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from .constants import (
    NUMERIC_FRAME_SUFFIX_RE,
)


def check_disk_space(path: Path, required_bytes: int) -> bool:
    """Check if there's enough disk space."""
    try:
        import shutil
        stat = shutil.disk_usage(path)
        return stat.free >= required_bytes
    except Exception:
        return True


def parse_optional_float(text: str) -> Optional[float]:
    """Parse an optional float from text, returning None for empty strings."""
    s = str(text).strip()
    if not s:
        return None
    return float(s)


def parse_roi_text(roi_text: str) -> Optional[Tuple[int, int, int, int]]:
    """Parse ROI text 'X,Y,W,H' into a tuple of ints."""
    if not str(roi_text).strip():
        return None
    parts = [v.strip() for v in str(roi_text).split(',')]
    if len(parts) != 4:
        raise ValueError("ROI \u5FC5\u987B\u5305\u542B4\u4E2A\u503C: X,Y,W,H")
    x, y, w, h = [int(v) for v in parts]
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        raise ValueError("ROI \u503C\u5FC5\u987B\u6EE1\u8DB3: X>=0, Y>=0, W>0, H>0")
    return (x, y, w, h)


def rebin_mean_2d(arr: np.ndarray, factor: int) -> np.ndarray:
    """Rebin a 2D array by block-averaging.

    Each block of size ``factor x factor`` pixels is replaced by its mean.
    NaN values are excluded from the average via ``np.nanmean``, so masked
    pixels do not affect the result.

    **Edge handling**: if the image dimensions are not evenly divisible by
    ``factor``, the rightmost columns and bottom rows are silently cropped
    before binning.  For example, a 2049x2049 image with factor=2 becomes
    1024x1024 (the last row and column are discarded).

    Parameters
    ----------
    arr : np.ndarray
        Input 2D array.
    factor : int
        Binning factor (>= 2 triggers binning; 1 is a no-op).

    Returns
    -------
    np.ndarray
        Binned array of shape ``(h // factor, w // factor)``.
    """
    factor = int(factor)
    if factor <= 1:
        return arr
    h, w = arr.shape
    h2 = (h // factor) * factor
    w2 = (w // factor) * factor
    if h2 <= 0 or w2 <= 0:
        raise ValueError(
            f"Binning factor {factor} is too large for image size {arr.shape}."
        )
    if h2 != h or w2 != w:
        import logging
        logging.getLogger(__name__).info(
            f"Binning: image cropped from {h}x{w} to {h2}x{w2} "
            f"(lost {h - h2} rows, {w - w2} cols)"
        )
    arr_cropped = arr[:h2, :w2]
    return np.nanmean(
        arr_cropped.reshape(h2 // factor, factor, w2 // factor, factor),
        axis=(1, 3),
    )


def summarize_array_stats(arr: np.ndarray) -> str:
    """Return a one-line summary of array statistics."""
    a = np.asarray(arr)
    finite = np.isfinite(a)
    total = int(a.size)
    finite_n = int(np.count_nonzero(finite))
    nan_n = total - finite_n
    if finite_n == 0:
        return f"shape={a.shape}, finite=0/{total}, nan={nan_n}"
    vals = a[finite]
    return (
        f"shape={a.shape}, finite={finite_n}/{total}, nan={nan_n}, "
        f"min={float(np.min(vals)):.4g}, max={float(np.max(vals)):.4g}, "
        f"mean={float(np.mean(vals)):.4g}, std={float(np.std(vals)):.4g}"
    )


def is_numeric_frame_suffix(path: Path) -> bool:
    """Check if the file suffix matches a numeric frame pattern (.0001, .0015, etc.)."""
    return bool(NUMERIC_FRAME_SUFFIX_RE.match(path.suffix.lower()))


def get_output_base_name(file_path: Path) -> str:
    """Keep full numeric frame suffixes like .0015 to avoid filename collisions."""
    return file_path.name if is_numeric_frame_suffix(file_path) else file_path.stem


def _ensure_unique_relative_path(rel_path: Path, used: set) -> Path:
    """Ensure the relative path is unique within the given set of used paths."""
    rel_path = Path(rel_path)
    candidate = rel_path
    counter = 2
    while str(candidate).lower() in used:
        candidate = rel_path.parent / f"{rel_path.stem}__dup{counter}{rel_path.suffix}"
        counter += 1
    used.add(str(candidate).lower())
    return candidate
