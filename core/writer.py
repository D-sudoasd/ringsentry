"""Output writers for various file formats."""

import threading
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .edf_io import write_edf


def _lazy_import_tifffile():
    import tifffile
    return tifffile


def _export_array_for_matrix(arr: np.ndarray, preserve_dtype: bool) -> np.ndarray:
    """Prepare array for matrix export, handling NaN/Inf values.

    NaN and Inf values are replaced with 0.0 for compatibility with formats
    that cannot represent them (TIFF, CSV, DAT).  A warning is logged if
    Inf values are found, as this may indicate data issues.
    """
    arr = np.asarray(arr)
    has_inf = np.any(np.isinf(arr))
    if has_inf:
        import logging
        n_inf = int(np.count_nonzero(np.isinf(arr)))
        logging.getLogger(__name__).warning(
            f"Export: {n_inf} Inf values found, replaced with 0.0"
        )
    if preserve_dtype:
        if np.issubdtype(arr.dtype, np.floating):
            return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        return arr
    return np.nan_to_num(
        arr.astype(np.float32, copy=False), nan=0.0, posinf=0.0, neginf=0.0
    )


def _save_matrix(
    arr: np.ndarray,
    out_path: Path,
    fmt: str,
    preserve_dtype: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Save 2D array as a matrix file (EDF/TIFF/NPY/DAT/CSV)."""
    arr = _export_array_for_matrix(arr, preserve_dtype=preserve_dtype)

    if fmt == 'edf':
        write_edf(arr, out_path, header_extra=metadata)
    elif fmt == 'tif':
        tf = _lazy_import_tifffile()
        tf.imwrite(str(out_path), arr, compression=None)
    elif fmt == 'npy':
        np.save(str(out_path), arr)
    elif fmt == 'dat':
        # Bug Fix: added encoding='utf-8'
        np.savetxt(
            str(out_path),
            np.asarray(arr, dtype=np.float64),
            fmt="%.6f",
            delimiter='\t',
            encoding='utf-8',
        )
    elif fmt == 'csv':
        # Bug Fix: added encoding='utf-8'
        pd.DataFrame(np.asarray(arr, dtype=np.float64)).to_csv(
            str(out_path), index=False, header=False, encoding='utf-8'
        )
    else:
        raise ValueError('\u4E0D\u652F\u6301\u7684\u77E9\u9635\u8F93\u51FA\u683C\u5F0F: ' + str(fmt))


def _write_xy_stream(
    arr: np.ndarray,
    out_path: Path,
    as_csv: bool,
    header: bool,
    one_based: bool,
    skip_zeros: bool,
    zero_tol: float,
    y_axis_origin: str = "top-left",
    cancellation_event: threading.Event = None,
) -> int:
    """Stream (x, y, I) triplets to file without holding all rows in memory.

    Coordinate conventions
    ---------------------
    - **x** = column index (0-based or 1-based depending on ``one_based``)
    - **y** = row index.  When ``y_axis_origin`` is ``"top-left"`` (default),
      y increases downward matching the array row order.  When ``"bottom-left"``,
      y is flipped so that y=0 corresponds to the bottom of the image:
      ``y_out = H - 1 - y``.
    - **I** = pixel intensity value at (x, y)

    Parameters
    ----------
    arr : np.ndarray
        2D image array (H rows x W columns).
    out_path : Path
        Output file path.
    as_csv : bool
        True → comma-separated, False → tab-separated.
    header : bool
        Include column header ``x,y,I`` as first line.
    one_based : bool
        Use 1-based indices (Matlab/Fortran style) instead of 0-based.
    skip_zeros : bool
        Skip pixels whose absolute intensity is <= ``zero_tol``.
    zero_tol : float
        Tolerance for the zero-skip filter.
    y_axis_origin : str
        ``"top-left"`` (default) or ``"bottom-left"``.
    cancellation_event : threading.Event or None
        Cancellation signal.

    Returns
    -------
    int
        Number of data points written.
    """
    H, W = arr.shape
    delim = ',' if as_csv else '\t'
    offset = 1 if one_based else 0
    total_points = 0
    y_axis_origin = str(y_axis_origin).strip().lower()
    if y_axis_origin not in ("top-left", "bottom-left"):
        raise ValueError("y_axis_origin \u5FC5\u987B\u662F 'top-left' \u6216 'bottom-left'")

    # Bug Fix: added encoding='utf-8'
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        if header:
            f.write(delim.join(['x', 'y', 'I']) + '\n')
        for y in range(H):
            if cancellation_event and cancellation_event.is_set():
                return total_points
            row = arr[y]
            if skip_zeros:
                mask = np.isfinite(row) & (np.abs(row) > zero_tol)
                xs = np.nonzero(mask)[0]
            else:
                xs = np.nonzero(np.isfinite(row))[0]
            if xs.size == 0:
                continue

            y_out = y if y_axis_origin == "top-left" else (H - 1 - y)

            lines = [
                f"{int(x_val + offset)}{delim}{int(y_out + offset)}{delim}{float(row[x_val]):.6f}\n"
                for x_val in xs
            ]
            f.writelines(lines)
            total_points += len(xs)

    return total_points


def save_array(
    arr: np.ndarray,
    out_path: Path,
    fmt: str,
    xy_header=True,
    xy_one_based=False,
    xy_skip_zeros=True,
    xy_zero_tol=0.0,
    xy_y_axis_origin: str = "top-left",
    cancellation_event: threading.Event = None,
    preserve_dtype: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Dispatcher for all output types.

    Returns:
        (success: bool, message: str, point_count: int)
    """
    try:
        if fmt in ('edf', 'tif', 'npy', 'dat', 'csv'):
            _save_matrix(
                arr, out_path, fmt,
                preserve_dtype=preserve_dtype,
                metadata=metadata,
            )
            return (True, "OK", arr.size)
        elif fmt == 'xycsv':
            points = _write_xy_stream(
                arr, out_path, as_csv=True, header=xy_header,
                one_based=xy_one_based, skip_zeros=xy_skip_zeros,
                zero_tol=xy_zero_tol, y_axis_origin=xy_y_axis_origin,
                cancellation_event=cancellation_event,
            )
            if points == 0:
                return (
                    False,
                    "\u65E0\u6570\u636E\u70B9\u5199\u5165\uFF08\u6240\u6709\u503C\u4F4E\u4E8E\u9608\u503C\uFF09",
                    0,
                )
            return (True, "OK", points)
        elif fmt == 'xydat':
            points = _write_xy_stream(
                arr, out_path, as_csv=False, header=xy_header,
                one_based=xy_one_based, skip_zeros=xy_skip_zeros,
                zero_tol=xy_zero_tol, y_axis_origin=xy_y_axis_origin,
                cancellation_event=cancellation_event,
            )
            if points == 0:
                return (
                    False,
                    "\u65E0\u6570\u636E\u70B9\u5199\u5165\uFF08\u6240\u6709\u503C\u4F4E\u4E8E\u9608\u503C\uFF09",
                    0,
                )
            return (True, "OK", points)
        else:
            raise ValueError('\u4E0D\u652F\u6301\u7684\u8F93\u51FA\u683C\u5F0F: ' + str(fmt))
    except Exception as e:
        return (False, str(e), 0)
