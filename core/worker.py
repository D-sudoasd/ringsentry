"""Worker function for threaded batch processing."""

from pathlib import Path

import numpy as np

from .quality import analyze_image_quality, quality_summary_line
from .processing import processing_is_identity
from .loader import load_image_with_info
from .processing import apply_processing
from .writer import save_array
from .utils import get_output_base_name, summarize_array_stats


def _processing_risk_logs(file_name: str, arr, proc_opts: dict) -> list:
    """Generate GUI-visible warnings for operations that may change data meaning."""
    logs = []
    h, w = arr.shape
    roi = proc_opts.get("roi")
    if roi is not None:
        _, _, roi_w, roi_h = [int(v) for v in roi]
        h, w = roi_h, roi_w

    if str(proc_opts.get("rotate_deg", "0")) in ("90", "270"):
        h, w = w, h

    bin_factor = int(proc_opts.get("bin_factor", 1) or 1)
    if bin_factor > 1 and ((h % bin_factor) != 0 or (w % bin_factor) != 0):
        h2 = (h // bin_factor) * bin_factor
        w2 = (w // bin_factor) * bin_factor
        logs.append(
            f"WARNING: {file_name} binning={bin_factor} will crop "
            f"{h - h2} rows and {w - w2} cols before averaging"
        )

    mask = proc_opts.get("mask_frame")
    if mask is not None:
        mask_arr = np.asarray(mask)
        if roi is not None and mask_arr.ndim == 2:
            x, y, roi_w, roi_h = [int(v) for v in roi]
            mask_arr = mask_arr[y:y + roi_h, x:x + roi_w]
        invalid = (
            (mask_arr != 0)
            if proc_opts.get("mask_nonzero_is_invalid", True)
            else (mask_arr == 0)
        )
        logs.append(
            f"INFO: {file_name} mask marks "
            f"{int(np.count_nonzero(invalid))} pixels as invalid"
        )

    return logs


def process_one_file(args):
    """Worker function to process a single file.

    Args is a tuple of:
        (file_path, rel_path, root, outroot, formats,
         xy_opts, png_opts, h5_path, proc_opts, cancellation_event, overwrite)
    """
    if len(args) == 10:
        (
            file_path, rel_path, root, outroot, formats,
            xy_opts, h5_path, proc_opts, cancellation_event, overwrite
        ) = args
        png_opts = {}
    else:
        (
            file_path, rel_path, root, outroot, formats,
            xy_opts, png_opts, h5_path, proc_opts, cancellation_event, overwrite
        ) = args
    logs = []

    if cancellation_event.is_set():
        return [f"Cancelled processing for {file_path.name}"]

    try:
        loaded = load_image_with_info(file_path, h5_path)
        arr = loaded["data"]
        source_meta = loaded["metadata"]
        quality_report = analyze_image_quality(
            arr,
            metadata=source_meta,
            source_name=file_path.name,
        )
        logs.append(quality_summary_line(quality_report))
        for finding in quality_report.findings:
            if finding.level in {"WARNING", "ERROR"}:
                logs.append(
                    f"{finding.level}: {file_path.name} QC {finding.message} "
                    f"({finding.basis})"
                )
        for suggestion in quality_report.suggestions:
            logs.append(
                f"SUGGESTION: {file_path.name} {suggestion.action} "
                f"Basis: {suggestion.reason}"
            )
        if quality_report.review_required:
            logs.append(
                f"REVIEW: {file_path.name} has QC warnings; "
                "please inspect this file in the run report."
            )
        logs.extend(_processing_risk_logs(file_path.name, arr, proc_opts))
        processed_arr = apply_processing(
            arr,
            dark_frame=proc_opts.get("dark_frame"),
            flat_frame=proc_opts.get("flat_frame"),
            flat_is_dark_subtracted=proc_opts.get("flat_is_dark_subtracted", True),
            roi=proc_opts.get("roi"),
            mask_frame=proc_opts.get("mask_frame"),
            mask_nonzero_is_invalid=proc_opts.get("mask_nonzero_is_invalid", True),
            clip_negative=proc_opts.get("clip_negative", False),
            bg_offset=proc_opts.get("bg_offset", 0.0),
            min_intensity=proc_opts.get("min_intensity"),
            max_intensity=proc_opts.get("max_intensity"),
            rotate_deg=proc_opts.get("rotate_deg", "0"),
            flip_x=proc_opts.get("flip_x", False),
            flip_y=proc_opts.get("flip_y", False),
            bin_factor=proc_opts.get("bin_factor", 1),
            pclip_low=proc_opts.get("pclip_low"),
            pclip_high=proc_opts.get("pclip_high"),
            intensity_transform=proc_opts.get("intensity_transform", "none"),
            gamma=proc_opts.get("gamma", 1.0),
            norm_mode=proc_opts.get("norm_mode", "none"),
            hot_pixel_enable=proc_opts.get("hot_pixel_enable", False),
            hot_pixel_window=proc_opts.get("hot_pixel_window", 3),
            hot_pixel_sigma=proc_opts.get("hot_pixel_sigma", 8.0),
        )
        logs.append(
            f"INFO: {file_path.name} [{source_meta.get('source_kind')}, "
            f"{source_meta.get('dtype')}] -> "
            f"{summarize_array_stats(processed_arr)}"
        )
    except Exception as e:
        import traceback
        return [f"ERROR loading/processing {file_path.name}: {e}",
                f"  Traceback: {traceback.format_exc().splitlines()[-1]}"]

    identity_processing = processing_is_identity(proc_opts)
    preserve_raw_matrix = (
        bool(proc_opts.get("lossless_matrix", True)) and identity_processing
    )

    for fmt in formats:
        if cancellation_event.is_set():
            logs.append(f"Cancelled {file_path.name} [{fmt}]")
            break
        try:
            out_dir = Path(outroot) / rel_path.parent / fmt
            out_dir.mkdir(parents=True, exist_ok=True)

            ext = {'xycsv': 'csv', 'xydat': 'dat'}.get(fmt, fmt)
            out_path = out_dir / f"{get_output_base_name(file_path)}.{ext}"

            if out_path.exists() and not overwrite:
                logs.append(
                    f"SKIPPED: {file_path.name} [{fmt}] -> \u8F93\u51FA\u5DF2\u5B58\u5728"
                )
                continue

            array_for_export = (
                arr if (fmt in ('edf', 'tif', 'npy') and preserve_raw_matrix)
                else processed_arr
            )
            preserve_dtype = fmt in ('edf', 'tif', 'npy') and preserve_raw_matrix
            export_meta = {
                "OriginalFile": file_path.name,
                "OriginalKind": source_meta.get("source_kind"),
                "OriginalDType": source_meta.get("dtype"),
                "LosslessMatrixExport": preserve_dtype,
            }

            success, msg, points = save_array(
                array_for_export,
                out_path,
                fmt,
                xy_header=xy_opts["header"],
                xy_one_based=xy_opts["one_based"],
                xy_skip_zeros=xy_opts["skip_zeros"],
                xy_zero_tol=xy_opts["zero_tol"],
                xy_y_axis_origin=xy_opts["y_axis_origin"],
                cancellation_event=cancellation_event,
                preserve_dtype=preserve_dtype,
                metadata=export_meta,
                png_options=png_opts,
            )

            if cancellation_event.is_set():
                logs.append(f"CANCELLED during write: {file_path.name} [{fmt}]")
                if out_path.exists():
                    out_path.unlink()
            elif success:
                mode = "RAW" if preserve_dtype else "PROC"
                detail = f"; {msg}" if msg and msg != "OK" else ""
                logs.append(
                    f"SUCCESS: {file_path.name} [{fmt}/{mode}] -> "
                    f"{out_path} ({points} points{detail})"
                )
            else:
                logs.append(f"FAILED: {file_path.name} [{fmt}] -> {msg}")
                if out_path.exists():
                    out_path.unlink()
        except Exception as e:
            logs.append(f"FAILED: {file_path.name} [{fmt}] -> {e}")
    return logs
