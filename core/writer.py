"""Output writers for various file formats."""

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .edf_io import write_edf
from .png_export import save_png


logger = logging.getLogger(__name__)


def _lazy_import_tifffile():
    import tifffile
    return tifffile


def _nonfinite_replacement_note(arr: np.ndarray, fmt: str) -> Optional[str]:
    """Describe non-finite values replaced by a text matrix export."""
    nan_count = int(np.count_nonzero(np.isnan(arr)))
    posinf_count = int(np.count_nonzero(np.isposinf(arr)))
    neginf_count = int(np.count_nonzero(np.isneginf(arr)))
    nonfinite_count = nan_count + posinf_count + neginf_count
    if not nonfinite_count:
        return None
    return (
        f"{fmt.upper()} compatibility export: replaced {nonfinite_count} "
        "non-finite values with 0.0 "
        f"(NaN={nan_count}, +Inf={posinf_count}, -Inf={neginf_count})"
    )


def _export_array_for_matrix(
    arr: np.ndarray,
    preserve_dtype: bool,
    fmt: str,
) -> np.ndarray:
    """Prepare an array according to the target matrix format.

    Floating-point NPY, EDF, and TIFF payloads retain IEEE NaN and Inf values.
    Text matrix formats replace non-finite values with 0.0 for compatibility
    and log the exact replacement counts.
    """
    arr = np.asarray(arr)
    export_arr = arr if preserve_dtype else arr.astype(np.float32, copy=False)
    if fmt in ('npy', 'edf', 'tif'):
        return export_arr

    note = _nonfinite_replacement_note(export_arr, fmt)
    if note:
        logger.warning(note)
    return np.nan_to_num(
        export_arr,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )


def _tiff_imagej_supported_dtype(dtype: np.dtype) -> bool:
    """Return True when tifffile can write this dtype as ImageJ TIFF."""
    dtype = np.dtype(dtype).newbyteorder('=')
    return dtype in {
        np.dtype(np.uint8),
        np.dtype(np.uint16),
        np.dtype(np.int16),
        np.dtype(np.float32),
    }


def _prepare_tiff_array(
    arr: np.ndarray,
    preserve_dtype: bool,
    metadata: Optional[Dict[str, Any]],
) -> Tuple[np.ndarray, Dict[str, Any], bool, Optional[str]]:
    """Prepare a TIFF payload with practical compatibility for CBF exports.

    CBF images decoded by FabIO are commonly signed int32 arrays.  That is a
    valid TIFF dtype, but ImageJ/Fiji and several detector-analysis tools do
    not handle signed 32-bit TIFF consistently.  For raw CBF -> TIFF export,
    use ImageJ-compatible dtypes whenever a value-preserving conversion is
    reasonable; EDF/NPY remain the exact-preservation formats.
    """
    arr = np.asarray(arr)
    meta = dict(metadata or {})
    source_kind = str(
        meta.get("OriginalKind") or meta.get("source_kind") or ""
    ).lower()
    note = None

    if preserve_dtype and source_kind == "cbf" and not _tiff_imagej_supported_dtype(arr.dtype):
        original_dtype = str(arr.dtype)
        if arr.dtype.kind in ("i", "u"):
            if arr.size:
                finite_arr = arr[np.isfinite(arr)] if arr.dtype.kind == "f" else arr
                min_value = int(np.min(finite_arr))
                max_value = int(np.max(finite_arr))
            else:
                min_value = 0
                max_value = 0

            if min_value >= 0 and max_value <= np.iinfo(np.uint16).max:
                arr = arr.astype(np.uint16)
                cast_note = "uint16 lossless"
            elif (
                min_value >= np.iinfo(np.int16).min
                and max_value <= np.iinfo(np.int16).max
            ):
                arr = arr.astype(np.int16)
                cast_note = "int16 lossless"
            else:
                arr = arr.astype(np.float32)
                cast_note = "float32 compatibility"
                note = (
                    f"TIFF CBF compatibility cast: {original_dtype} -> float32"
                )
                if max(abs(min_value), abs(max_value)) > 2 ** 24:
                    note += (
                        "; values exceed float32 exact integer range, "
                        "use EDF/NPY for exact preservation"
                    )
                    logger.warning(
                        "TIFF export: CBF integer values exceed float32 exact "
                        "integer range; use EDF/NPY for exact preservation."
                    )
        else:
            arr = arr.astype(np.float32)
            cast_note = "float32 compatibility"
            note = f"TIFF CBF compatibility cast: {original_dtype} -> float32"

        meta["TIFFOriginalDType"] = original_dtype
        meta["TIFFStoredDType"] = str(arr.dtype)
        meta["TIFFCompatibilityCast"] = cast_note
        if note is None:
            note = (
                f"TIFF CBF compatibility cast: {original_dtype} -> {arr.dtype} "
                "(lossless)"
            )

    imagej = _tiff_imagej_supported_dtype(arr.dtype)
    return np.ascontiguousarray(arr), meta, imagej, note


def _write_tiff(
    arr: np.ndarray,
    out_path: Path,
    preserve_dtype: bool,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Write a 2D matrix TIFF suitable for scientific image readers."""
    tf = _lazy_import_tifffile()
    arr, meta, imagej, note = _prepare_tiff_array(
        arr, preserve_dtype, metadata
    )
    meta.setdefault("axes", "YX")
    meta.setdefault("Software", "RingSentry")

    if imagej:
        tf.imwrite(
            str(out_path),
            arr,
            imagej=True,
            metadata=meta,
            photometric="minisblack",
            compression=None,
        )
    else:
        description = json.dumps(meta, ensure_ascii=False, sort_keys=True)
        tf.imwrite(
            str(out_path),
            arr,
            description=description,
            photometric="minisblack",
            compression=None,
        )
    return note


def _save_matrix(
    arr: np.ndarray,
    out_path: Path,
    fmt: str,
    preserve_dtype: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Save 2D array as a matrix file (EDF/TIFF/NPY/DAT/CSV)."""
    replacement_note = None
    source_arr = np.asarray(arr)
    if fmt in ('dat', 'csv'):
        export_source = source_arr if preserve_dtype else source_arr.astype(np.float32, copy=False)
        replacement_note = _nonfinite_replacement_note(export_source, fmt)
    arr = _export_array_for_matrix(
        arr,
        preserve_dtype=preserve_dtype,
        fmt=fmt,
    )

    if fmt == 'edf':
        write_edf(arr, out_path, header_extra=metadata)
        return "OK"
    elif fmt == 'tif':
        note = _write_tiff(
            arr,
            out_path,
            preserve_dtype=preserve_dtype,
            metadata=metadata,
        )
        return note or "OK"
    elif fmt == 'npy':
        np.save(str(out_path), arr)
        return "OK"
    elif fmt == 'dat':
        # Bug Fix: added encoding='utf-8'
        np.savetxt(
            str(out_path),
            np.asarray(arr, dtype=np.float64),
            fmt="%.6f",
            delimiter='\t',
            encoding='utf-8',
        )
        return replacement_note or "OK"
    elif fmt == 'csv':
        # Bug Fix: added encoding='utf-8'
        pd.DataFrame(np.asarray(arr, dtype=np.float64)).to_csv(
            str(out_path), index=False, header=False, encoding='utf-8'
        )
        return replacement_note or "OK"
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


def _save_array_payload(
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
    png_options: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Dispatcher for all output types.

    Returns:
        (success: bool, message: str, point_count: int)
    """
    try:
        if fmt == 'png':
            msg = save_png(arr, out_path, png_options or {})
            return (True, msg, arr.size)
        if fmt in ('edf', 'tif', 'npy', 'dat', 'csv'):
            msg = _save_matrix(
                arr, out_path, fmt,
                preserve_dtype=preserve_dtype,
                metadata=metadata,
            )
            return (True, msg, arr.size)
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


def _normalise_output_path(out_path: Path, fmt: str) -> Path:
    """Give extension-sensitive writers the suffix they require."""
    out_path = Path(out_path)
    if str(fmt).lower() == "npy" and not out_path.suffix:
        return out_path.with_name(f"{out_path.name}.npy")
    return out_path


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
    png_options: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Write an output through a same-directory temporary file.

    The existing public API is retained.  A successful, non-cancelled payload
    is published with ``os.replace``; failures and cancellation only remove
    the temporary file, so an existing final output remains untouched.
    """
    out_path = _normalise_output_path(out_path, fmt)
    temp_path = None
    try:
        if cancellation_event and cancellation_event.is_set():
            return (False, "CANCELLED before write", 0)

        # Keep the final suffix so np.save does not append a second ``.npy``.
        # The temporary file lives beside the destination for same-volume
        # atomic replacement on Windows and POSIX.
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{out_path.name}.",
            suffix=out_path.suffix,
            dir=str(out_path.parent),
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)

        success, message, points = _save_array_payload(
            arr,
            temp_path,
            fmt,
            xy_header=xy_header,
            xy_one_based=xy_one_based,
            xy_skip_zeros=xy_skip_zeros,
            xy_zero_tol=xy_zero_tol,
            xy_y_axis_origin=xy_y_axis_origin,
            cancellation_event=cancellation_event,
            preserve_dtype=preserve_dtype,
            metadata=metadata,
            png_options=png_options,
        )
        if not success:
            return (False, message, points)
        if cancellation_event and cancellation_event.is_set():
            return (False, "CANCELLED during write", points)

        os.replace(str(temp_path), str(out_path))
        temp_path = None
        return (True, message, points)
    except Exception as e:
        return (False, str(e), 0)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
