"""Image processing pipeline for 2D diffraction pattern preprocessing.

This module provides the core image processing functions used to prepare
2D diffraction images (SAXS, WAXS, SXRD, GIWAXS) for further analysis.
"""

from typing import Optional

import numpy as np


def _hot_pixel_replace(
    arr: np.ndarray, window: int = 3, sigma: float = 8.0
) -> np.ndarray:
    """Suppress isolated hot pixels using local median + MAD threshold.

    Algorithm
    ---------
    For each pixel, compute the local median and Median Absolute Deviation
    (MAD) within a sliding window of size ``window x window``.  A pixel is
    identified as *hot* when:

        value > median + sigma * 1.4826 * MAD

    The constant **1.4826** is the scaling factor that makes MAD consistent
    with the standard deviation under a normal distribution assumption
    (i.e., for Gaussian noise, ``1.4826 * MAD ≈ σ``).  Hot pixels are
    replaced with the local median value.

    This function is NaN-safe: NaN values in the input are excluded from
    the median and MAD calculations via ``np.nanmedian``.

    Parameters
    ----------
    arr : np.ndarray
        Input 2D image array (any numeric dtype, internally cast to float32).
    window : int, optional
        Size of the sliding window (must be odd, >= 3).  Default is 3.
    sigma : float, optional
        Threshold multiplier.  Larger values are more conservative (fewer
        pixels suppressed).  Recommended range: 6–10.  Default is 8.0.

    Returns
    -------
    np.ndarray
        Image with hot pixels replaced by local medians (float32).
    """
    w = int(window)
    if w < 3:
        w = 3
    if w % 2 == 0:
        w += 1
    sigma = float(sigma)
    if sigma <= 0:
        return arr

    a = np.asarray(arr, dtype=np.float32)
    pad = w // 2
    ap = np.pad(a, ((pad, pad), (pad, pad)), mode='reflect')

    try:
        sw = np.lib.stride_tricks.sliding_window_view(ap, (w, w))
        med = np.nanmedian(sw, axis=(-2, -1))
        mad = np.nanmedian(
            np.abs(sw - med[..., None, None]), axis=(-2, -1)
        )
    except Exception:
        # Fallback if sliding_window_view unavailable (NumPy < 1.20)
        h_img, w_img = a.shape
        med = np.empty_like(a, dtype=np.float32)
        mad = np.empty_like(a, dtype=np.float32)
        for yy in range(h_img):
            for xx in range(w_img):
                blk = ap[yy:yy + w, xx:xx + w]
                m = np.nanmedian(blk)
                med[yy, xx] = m
                mad[yy, xx] = np.nanmedian(np.abs(blk - m))

    # threshold = median + sigma * 1.4826 * MAD
    scale = 1.4826 * mad
    threshold = med + sigma * scale
    finite = np.isfinite(a) & np.isfinite(med) & np.isfinite(threshold)
    hot = finite & (a > threshold)
    if not np.any(hot):
        return a

    out = a.copy()
    out[hot] = med[hot]
    return out


def apply_processing(
    arr,
    dark_frame=None,
    flat_frame=None,
    flat_is_dark_subtracted: bool = True,
    roi=None,
    mask_frame=None,
    mask_nonzero_is_invalid: bool = True,
    clip_negative: bool = False,
    bg_offset: float = 0.0,
    min_intensity: Optional[float] = None,
    max_intensity: Optional[float] = None,
    rotate_deg: str = "0",
    flip_x: bool = False,
    flip_y: bool = False,
    bin_factor: int = 1,
    pclip_low: Optional[float] = None,
    pclip_high: Optional[float] = None,
    intensity_transform: str = "none",
    gamma: float = 1.0,
    norm_mode: str = "none",
    hot_pixel_enable: bool = False,
    hot_pixel_window: int = 3,
    hot_pixel_sigma: float = 8.0,
):
    """Apply the full preprocessing pipeline on a 2D diffraction image.

    Processing steps are applied in the following order:

    1.  **Dark frame subtraction** — ``result = raw - dark``
    1b. **Flat field correction** — ``result = result / flat``
    2.  **Background offset** — ``result = result - bg_offset``
    3.  **Intensity range validation** — check I Min <= I Max
    4.  **ROI cropping** — extract sub-region (x, y, w, h)
    5.  **Mask application** — set masked pixels to NaN
    6.  **Intensity clipping** — pixels outside [min, max] become NaN
    7.  **Percentile clipping** — clip to percentile range
    8.  **Negative value clipping** — set negative pixels to 0
    9.  **Hot pixel suppression** — local median + MAD detection
    10. **Rotation** — 0°, 90°, 180°, or 270°
    11. **Flipping** — horizontal and/or vertical
    12. **Binning** — block averaging (factor x factor)
    13. **Intensity transform** — log1p / log10p / sqrt
    14. **Gamma correction** — power-law transform
    15. **Normalization** — max1 / minmax

    Parameters
    ----------
    arr : array_like
        Input 2D image (any numeric dtype; internally cast to float32).
    dark_frame : array_like or None
        Dark frame for background subtraction.  Must match image dimensions.
    flat_frame : array_like or None
        Flat field image for detector response correction.
        If provided, the image is divided by the flat field after dark subtraction.
    flat_is_dark_subtracted : bool
        If True (default), flat field is already dark-subtracted:
        ``result = (raw - dark) / flat``.
        If False, the flat field itself needs dark subtraction:
        ``result = (raw - dark) / (flat - dark)``.
        When False and no dark_frame is provided, the formula
        simplifies to ``result / flat`` (no dark subtraction possible).
    roi : tuple(int, int, int, int) or None
        Region of interest as ``(x, y, w, h)`` where x is the column offset,
        y is the row offset, w is width (columns), h is height (rows).
        Coordinate origin is the **top-left** corner (y increases downward).
    mask_frame : array_like or None
        Mask image.  Non-zero (or zero, depending on polarity) pixels are
        set to NaN in the output.
    mask_nonzero_is_invalid : bool
        If True (default), non-zero mask pixels are treated as invalid.
        If False, zero mask pixels are treated as invalid.
    clip_negative : bool
        If True, set all negative values to 0.0.
    bg_offset : float
        Constant background value to subtract.
    min_intensity, max_intensity : float or None
        Intensity range — pixels outside this range become NaN.
    rotate_deg : str
        Rotation angle: "0", "90", "180", or "270".
    flip_x, flip_y : bool
        Flip horizontally / vertically.
    bin_factor : int
        Binning (block averaging) factor.  1 means no binning.
    pclip_low, pclip_high : float or None
        Percentile clipping range [0, 100].
    intensity_transform : str
        One of: "none", "log1p", "log10p", "sqrt".
    gamma : float
        Gamma correction exponent (must be > 0).  1.0 = no change.
    norm_mode : str
        Normalization mode: "none", "max1", or "minmax".
    hot_pixel_enable : bool
        Enable hot pixel suppression.
    hot_pixel_window : int
        Sliding window size for hot pixel detection (odd, >= 3).
    hot_pixel_sigma : float
        Threshold sigma for hot pixel detection.

    Returns
    -------
    np.ndarray
        Processed 2D image (float32).
    """
    arr = np.asarray(arr, dtype=np.float32)

    # 1. Dark frame subtraction: result = raw - dark
    if dark_frame is not None:
        if dark_frame.shape != arr.shape:
            raise ValueError(
                "\u6697\u5E27\u5C3A\u5BF8\u5FC5\u987B\u4E0E\u56FE\u50CF\u5C3A\u5BF8\u4E00\u81F4"
            )  # 暗帧尺寸必须与图像尺寸一致
        arr = arr - np.asarray(dark_frame, dtype=np.float32)

    # 1b. Flat field correction: result = (raw - dark) / flat
    if flat_frame is not None:
        flat = np.asarray(flat_frame, dtype=np.float32)
        if flat.shape != arr.shape:
            raise ValueError(
                "\u5E73\u573A\u5E27\u5C3A\u5BF8\u5FC5\u987B\u4E0E\u56FE\u50CF\u5C3A\u5BF8\u4E00\u81F4"
            )  # 平场帧尺寸必须与图像尺寸一致
        if flat_is_dark_subtracted:
            # Flat is already dark-subtracted: result / flat
            with np.errstate(divide='ignore', invalid='ignore'):
                # 1e-10 threshold: values near zero would produce numerical
                # noise or Inf in the division; treat them as invalid.
                safe = np.isfinite(flat) & (np.abs(flat) > 1e-10)
                arr = np.where(safe, arr / flat, np.nan)
        else:
            # Flat not dark-subtracted: result / (flat - dark)
            if dark_frame is not None:
                denom = flat - np.asarray(dark_frame, dtype=np.float32)
            else:
                denom = flat
            with np.errstate(divide='ignore', invalid='ignore'):
                # 1e-10 threshold: near-zero denominator → NaN
                safe = np.isfinite(denom) & (np.abs(denom) > 1e-10)
                arr = np.where(safe, arr / denom, np.nan)

    # 2. Background offset subtraction
    if bg_offset is not None and float(bg_offset) != 0.0:
        arr = arr - float(bg_offset)

    # 3. Intensity range validation
    if min_intensity is not None and max_intensity is not None:
        if float(min_intensity) > float(max_intensity):
            raise ValueError("I Min \u5FC5\u987B <= I Max")

    # 4. ROI cropping (x=column offset, y=row offset, origin=top-left)
    if roi:
        if len(roi) != 4:
            raise ValueError("ROI \u5FC5\u987B\u5305\u542B4\u4E2A\u503C: (x, y, w, h)")
        x, y, w, h = [int(v) for v in roi]
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            raise ValueError("ROI \u503C\u5FC5\u987B\u6EE1\u8DB3 x>=0, y>=0, w>0, h>0")
        if x + w > arr.shape[1] or y + h > arr.shape[0]:
            raise ValueError(
                f"ROI [{x},{y},{w},{h}] \u8D85\u51FA\u56FE\u50CF\u8303\u56F4 {arr.shape}"
            )
        arr = arr[y:y + h, x:x + w]
        if mask_frame is not None:
            mask_frame = np.asarray(mask_frame)[y:y + h, x:x + w]
    elif mask_frame is not None:
        mask_frame = np.asarray(mask_frame)

    # 5. Mask application
    if mask_frame is not None:
        if mask_frame.shape != arr.shape:
            raise ValueError(
                "\u63A9\u819C\u5C3A\u5BF8\u5FC5\u987B\u4E0E\u5904\u7406\u540E\u56FE\u50CF\u5C3A\u5BF8\u4E00\u81F4"
            )
        mask_bool = (
            (mask_frame != 0) if mask_nonzero_is_invalid else (mask_frame == 0)
        )
        arr = np.where(mask_bool, np.nan, arr)

    # 6. Intensity clipping (out-of-range pixels become NaN)
    if min_intensity is not None:
        arr = np.where(arr >= float(min_intensity), arr, np.nan)
    if max_intensity is not None:
        arr = np.where(arr <= float(max_intensity), arr, np.nan)

    # 7. Percentile clipping
    valid = np.isfinite(arr)
    if np.any(valid) and (pclip_low is not None or pclip_high is not None):
        lo_q = 0.0 if pclip_low is None else float(pclip_low)
        hi_q = 100.0 if pclip_high is None else float(pclip_high)
        if not (0.0 <= lo_q <= 100.0 and 0.0 <= hi_q <= 100.0):
            raise ValueError("\u767E\u5206\u4F4D\u88C1\u526A\u5FC5\u987B\u5728 [0, 100] \u8303\u56F4\u5185")
        if hi_q < lo_q:
            raise ValueError(
                "\u767E\u5206\u4F4D\u4E0A\u9650\u5FC5\u987B >= \u767E\u5206\u4F4D\u4E0B\u9650"
            )
        lo_v = float(np.nanpercentile(arr, lo_q))
        hi_v = float(np.nanpercentile(arr, hi_q))
        if lo_v <= hi_v:
            arr = np.clip(arr, lo_v, hi_v)

    # 8. Negative value clipping
    if clip_negative:
        arr = np.where(arr < 0, 0.0, arr)

    # 9. Hot pixel suppression (NaN-safe: uses np.nanmedian internally)
    if hot_pixel_enable:
        arr = _hot_pixel_replace(arr, window=hot_pixel_window, sigma=hot_pixel_sigma)

    # 10. Rotation
    rot_map = {"0": 0, "90": 1, "180": 2, "270": 3}
    k = rot_map.get(str(rotate_deg), 0)
    if k:
        arr = np.rot90(arr, k=k)
    # 11. Flipping
    if flip_x:
        arr = np.fliplr(arr)
    if flip_y:
        arr = np.flipud(arr)

    # 12. Binning (block averaging)
    arr = rebin_mean_2d(arr, int(bin_factor))

    if intensity_transform not in ("none", "log1p", "log10p", "sqrt"):
        raise ValueError(
            "intensity_transform \u5FC5\u987B\u662F: none, log1p, log10p, sqrt"
        )

    # Copy-once pattern: avoid repeated copies when both transform and gamma are active
    _copied_for_inplace = False

    # 13. Intensity transform
    if intensity_transform != "none":
        finite = np.isfinite(arr)
        if np.any(finite):
            if not _copied_for_inplace:
                arr = arr.copy()
                _copied_for_inplace = True
            # Negative values are invalid for log/sqrt transforms → set to NaN
            neg = finite & (arr < 0)
            if np.any(neg):
                arr[neg] = np.nan
                finite = np.isfinite(arr)
            if intensity_transform == "log1p":
                arr[finite] = np.log1p(arr[finite])      # ln(1 + x), avoids log(0)
            elif intensity_transform == "log10p":
                arr[finite] = np.log10(arr[finite] + 1.0) # log10(1 + x), avoids log(0)
            elif intensity_transform == "sqrt":
                arr[finite] = np.sqrt(arr[finite])         # square root

    # 14. Gamma correction: power-law transform I^gamma
    gamma = float(gamma)
    if not np.isfinite(gamma) or gamma <= 0:
        raise ValueError("gamma \u5FC5\u987B > 0")
    if gamma != 1.0:
        finite = np.isfinite(arr)
        if np.any(finite):
            if not _copied_for_inplace:
                arr = arr.copy()
                _copied_for_inplace = True
            neg = finite & (arr < 0)
            if np.any(neg):
                arr[neg] = np.nan
                finite = np.isfinite(arr)
            arr[finite] = np.power(arr[finite], gamma)

    # 15. Normalization
    if norm_mode not in ("none", "max1", "minmax"):
        raise ValueError("norm_mode \u5FC5\u987B\u662F: none, max1, minmax")
    valid = np.isfinite(arr)
    if np.any(valid) and norm_mode != "none":
        vals = arr[valid]
        if norm_mode == "max1":
            # Divide by max value so that max = 1
            vmax = float(np.max(vals))
            if vmax == 0:
                pass  # all-zero image: leave as-is
            elif np.isfinite(vmax):
                arr = arr / vmax
        elif norm_mode == "minmax":
            # Scale to [0, 1] range
            vmin = float(np.min(vals))
            vmax = float(np.max(vals))
            if vmax > vmin and np.isfinite(vmin) and np.isfinite(vmax):
                arr = (arr - vmin) / (vmax - vmin)
            elif vmax == vmin:
                pass  # flat image: leave as-is to avoid 0/0

    return arr.astype(np.float32, copy=False)


def rebin_mean_2d(arr: np.ndarray, factor: int) -> np.ndarray:
    """Rebin a 2D array by averaging blocks. Imported from utils for circular dependency avoidance."""
    from .utils import rebin_mean_2d as _rebin
    return _rebin(arr, factor)


def processing_is_identity(proc_opts: dict) -> bool:
    """Check whether the processing options represent a no-op (identity transform)."""
    return (
        proc_opts.get("dark_frame") is None
        and proc_opts.get("flat_frame") is None
        and proc_opts.get("roi") is None
        and proc_opts.get("mask_frame") is None
        and not proc_opts.get("clip_negative", False)
        and float(proc_opts.get("bg_offset", 0.0) or 0.0) == 0.0
        and proc_opts.get("min_intensity") is None
        and proc_opts.get("max_intensity") is None
        and str(proc_opts.get("rotate_deg", "0")) == "0"
        and not proc_opts.get("flip_x", False)
        and not proc_opts.get("flip_y", False)
        and int(proc_opts.get("bin_factor", 1) or 1) == 1
        and proc_opts.get("pclip_low") is None
        and proc_opts.get("pclip_high") is None
        and str(proc_opts.get("intensity_transform", "none")) == "none"
        and float(proc_opts.get("gamma", 1.0) or 1.0) == 1.0
        and str(proc_opts.get("norm_mode", "none")) == "none"
        and not proc_opts.get("hot_pixel_enable", False)
    )
