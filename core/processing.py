"""Numerical preprocessing pipeline for 2D diffraction detector images.

This module is part of the scientific data path, not a display-only layer.
Operations that can change data interpretation, such as masking, clipping,
flat-field invalid pixels, and binning edge cropping, are validated strictly
and logged where possible.
"""

import logging
from typing import Optional

import numpy as np


logger = logging.getLogger(__name__)


def _as_2d_float32(arr, name: str) -> np.ndarray:
    """Convert input to a 2D float32 image and reject ambiguous shapes."""
    out = np.asarray(arr, dtype=np.float32)
    if out.ndim != 2:
        raise ValueError(
            f"{name} \u5FC5\u987B\u662F 2D \u56FE\u50CF\uFF0C\u5F53\u524D shape={out.shape}"
        )
    return out


def _require_same_shape(reference: np.ndarray, candidate: np.ndarray, message: str):
    """Raise when a calibration/mask image shape does not match the raw image."""
    if candidate.shape != reference.shape:
        raise ValueError(message)


def _finite_float(value, name: str) -> float:
    """Parse a finite float parameter."""
    value = float(value)
    if not np.isfinite(value):
        raise ValueError(f"{name} \u5FC5\u987B\u662F\u6709\u9650\u6570\u503C")
    return value


def _hot_pixel_replace(
    arr: np.ndarray, window: int = 3, sigma: float = 8.0
) -> np.ndarray:
    """Suppress isolated hot pixels using local median + MAD threshold.

    A pixel is treated as an isolated hot pixel when:

        value > local_median + sigma * 1.4826 * local_MAD

    The 1.4826 factor converts MAD to a Gaussian-equivalent standard
    deviation.  NaN values are ignored in the local median/MAD calculation.
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
        h_img, w_img = a.shape
        med = np.empty_like(a, dtype=np.float32)
        mad = np.empty_like(a, dtype=np.float32)
        for yy in range(h_img):
            for xx in range(w_img):
                blk = ap[yy:yy + w, xx:xx + w]
                m = np.nanmedian(blk)
                med[yy, xx] = m
                mad[yy, xx] = np.nanmedian(np.abs(blk - m))

    threshold = med + sigma * 1.4826 * mad
    finite = np.isfinite(a) & np.isfinite(med) & np.isfinite(threshold)
    hot = finite & (a > threshold)
    if not np.any(hot):
        return a

    out = a.copy()
    out[hot] = med[hot]
    logger.info("Hot pixel suppression: %d pixels replaced", int(np.count_nonzero(hot)))
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
    """Apply the preprocessing pipeline to a 2D detector image.

    ``flat_frame`` is a relative detector-response map. It must either already
    be dark-subtracted (``flat_is_dark_subtracted=True``) or be accompanied by
    the matching ``dark_frame``. The function does not normalize raw flat
    counts automatically, so callers that require scale-preserving correction
    must normalize the response map before calling this function.

    Order of operations:
    dark subtraction, flat correction, background offset, ROI, mask,
    intensity clipping, percentile clipping, negative clipping, hot-pixel
    suppression, rotation/flip, binning, intensity transform, gamma, and
    normalization.
    """
    arr = _as_2d_float32(arr, "\u539F\u59CB\u56FE\u50CF")
    original_shape = arr.shape

    # 1. Dark frame subtraction: result = raw - dark.
    dark = None
    if dark_frame is not None:
        dark = _as_2d_float32(dark_frame, "\u6697\u5E27")
        _require_same_shape(
            arr,
            dark,
            "\u6697\u5E27\u5C3A\u5BF8\u5FC5\u987B\u4E0E\u56FE\u50CF\u5C3A\u5BF8\u4E00\u81F4",
        )
        arr = arr - dark

    # 2. Flat field correction.  Near-zero denominator is invalid.
    if flat_frame is not None:
        if not flat_is_dark_subtracted and dark is None:
            raise ValueError(
                "flat_is_dark_subtracted=False 时必须同时提供匹配的暗场"
            )
        flat = _as_2d_float32(flat_frame, "\u5E73\u573A")
        _require_same_shape(
            arr,
            flat,
            "\u5E73\u573A\u5E27\u5C3A\u5BF8\u5FC5\u987B\u4E0E\u56FE\u50CF\u5C3A\u5BF8\u4E00\u81F4",
        )
        denom = flat if flat_is_dark_subtracted or dark is None else (flat - dark)
        with np.errstate(divide='ignore', invalid='ignore'):
            safe = np.isfinite(denom) & (np.abs(denom) > 1e-10)
            invalid_n = int(denom.size - np.count_nonzero(safe))
            if invalid_n:
                logger.warning(
                    "Flat correction: %d invalid/near-zero denominator pixels set to NaN",
                    invalid_n,
                )
            arr = np.where(safe, arr / denom, np.nan)

    # 3. Constant background subtraction.
    bg = _finite_float(bg_offset, "BG Offset") if bg_offset is not None else 0.0
    if bg != 0.0:
        arr = arr - bg

    # 4. Intensity range validation.
    min_i = None if min_intensity is None else _finite_float(min_intensity, "I Min")
    max_i = None if max_intensity is None else _finite_float(max_intensity, "I Max")
    if min_i is not None and max_i is not None and min_i > max_i:
        raise ValueError("I Min \u5FC5\u987B <= I Max")

    mask = None if mask_frame is None else np.asarray(mask_frame)

    # 5. ROI cropping.  Coordinates are x=column, y=row, origin=top-left.
    if roi is not None:
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
        if mask is not None:
            if mask.shape != original_shape:
                raise ValueError(
                    "\u63A9\u819C\u5C3A\u5BF8\u5FC5\u987B\u4E0E\u539F\u59CB\u56FE\u50CF\u5C3A\u5BF8\u4E00\u81F4"
                )
            mask = mask[y:y + h, x:x + w]

    # 6. Mask application.
    if mask is not None:
        if mask.shape != arr.shape:
            raise ValueError(
                "\u63A9\u819C\u5C3A\u5BF8\u5FC5\u987B\u4E0E\u5904\u7406\u540E\u56FE\u50CF\u5C3A\u5BF8\u4E00\u81F4"
            )
        mask_bool = (mask != 0) if mask_nonzero_is_invalid else (mask == 0)
        masked_n = int(np.count_nonzero(mask_bool))
        if masked_n:
            logger.info("Mask applied: %d pixels set to NaN", masked_n)
        arr = np.where(mask_bool, np.nan, arr)

    # 7. Absolute intensity clipping.
    if min_i is not None:
        before = int(np.count_nonzero(np.isfinite(arr)))
        arr = np.where(arr >= min_i, arr, np.nan)
        clipped = before - int(np.count_nonzero(np.isfinite(arr)))
        if clipped:
            logger.info("I Min clipping: %d pixels set to NaN", clipped)
    if max_i is not None:
        before = int(np.count_nonzero(np.isfinite(arr)))
        arr = np.where(arr <= max_i, arr, np.nan)
        clipped = before - int(np.count_nonzero(np.isfinite(arr)))
        if clipped:
            logger.info("I Max clipping: %d pixels set to NaN", clipped)

    # 8. Percentile clipping.
    valid = np.isfinite(arr)
    if pclip_low is not None or pclip_high is not None:
        if not np.any(valid):
            logger.warning("Percentile clipping skipped: no finite pixels")
        else:
            lo_q = 0.0 if pclip_low is None else _finite_float(pclip_low, "PClip Low")
            hi_q = 100.0 if pclip_high is None else _finite_float(pclip_high, "PClip High")
            if not (0.0 <= lo_q <= 100.0 and 0.0 <= hi_q <= 100.0):
                raise ValueError(
                    "\u767E\u5206\u4F4D\u88C1\u526A\u5FC5\u987B\u5728 [0, 100] \u8303\u56F4\u5185"
                )
            if hi_q < lo_q:
                raise ValueError(
                    "\u767E\u5206\u4F4D\u4E0A\u9650\u5FC5\u987B >= \u767E\u5206\u4F4D\u4E0B\u9650"
                )
            lo_v = float(np.nanpercentile(arr, lo_q))
            hi_v = float(np.nanpercentile(arr, hi_q))
            if lo_v <= hi_v:
                arr = np.clip(arr, lo_v, hi_v)

    # 9. Negative value clipping.
    if clip_negative:
        negative_n = int(np.count_nonzero(np.isfinite(arr) & (arr < 0)))
        if negative_n:
            logger.info("Negative clipping: %d pixels set to 0", negative_n)
        arr = np.where(arr < 0, 0.0, arr)

    # 10. Hot pixel suppression.
    if hot_pixel_enable:
        arr = _hot_pixel_replace(arr, window=hot_pixel_window, sigma=hot_pixel_sigma)

    # 11. Rotation and flipping.
    rot_map = {"0": 0, "90": 1, "180": 2, "270": 3}
    if str(rotate_deg) not in rot_map:
        raise ValueError("\u65CB\u8F6C\u89D2\u5EA6\u5FC5\u987B\u662F 0/90/180/270")
    k = rot_map[str(rotate_deg)]
    if k:
        arr = np.rot90(arr, k=k)
    if flip_x:
        arr = np.fliplr(arr)
    if flip_y:
        arr = np.flipud(arr)

    # 12. Binning by block average.  Non-divisible edges are cropped by helper.
    bin_factor = int(bin_factor)
    if bin_factor < 1:
        raise ValueError("Binning \u5FC5\u987B >= 1")
    arr = rebin_mean_2d(arr, bin_factor)

    # 13. Intensity transform.
    if intensity_transform not in ("none", "log1p", "log10p", "sqrt"):
        raise ValueError(
            "intensity_transform \u5FC5\u987B\u662F: none, log1p, log10p, sqrt"
        )
    if intensity_transform != "none":
        finite = np.isfinite(arr)
        if np.any(finite):
            arr = arr.copy()
            neg = finite & (arr < 0)
            if np.any(neg):
                logger.info(
                    "%s transform: %d negative pixels set to NaN",
                    intensity_transform,
                    int(np.count_nonzero(neg)),
                )
                arr[neg] = np.nan
                finite = np.isfinite(arr)
            if intensity_transform == "log1p":
                arr[finite] = np.log1p(arr[finite])
            elif intensity_transform == "log10p":
                arr[finite] = np.log10(arr[finite] + 1.0)
            elif intensity_transform == "sqrt":
                arr[finite] = np.sqrt(arr[finite])

    # 14. Gamma correction.
    gamma = _finite_float(gamma, "Gamma")
    if gamma <= 0:
        raise ValueError("gamma \u5FC5\u987B > 0")
    if gamma != 1.0:
        finite = np.isfinite(arr)
        if np.any(finite):
            arr = arr.copy()
            neg = finite & (arr < 0)
            if np.any(neg):
                logger.info("Gamma correction: %d negative pixels set to NaN", int(np.count_nonzero(neg)))
                arr[neg] = np.nan
                finite = np.isfinite(arr)
            arr[finite] = np.power(arr[finite], gamma)

    # 15. Normalization.
    if norm_mode not in ("none", "max1", "minmax"):
        raise ValueError("norm_mode \u5FC5\u987B\u662F: none, max1, minmax")
    valid = np.isfinite(arr)
    if np.any(valid) and norm_mode != "none":
        vals = arr[valid]
        if norm_mode == "max1":
            vmax = float(np.max(vals))
            if vmax == 0:
                logger.warning("max1 normalization skipped: max is 0")
            elif np.isfinite(vmax):
                arr = arr / vmax
        elif norm_mode == "minmax":
            vmin = float(np.min(vals))
            vmax = float(np.max(vals))
            if vmax > vmin and np.isfinite(vmin) and np.isfinite(vmax):
                arr = (arr - vmin) / (vmax - vmin)
            elif vmax == vmin:
                logger.warning("minmax normalization skipped: image is constant")

    return arr.astype(np.float32, copy=False)


def rebin_mean_2d(arr: np.ndarray, factor: int) -> np.ndarray:
    """Rebin a 2D array by averaging blocks."""
    from .utils import rebin_mean_2d as _rebin
    return _rebin(arr, factor)


def processing_is_identity(proc_opts: dict) -> bool:
    """Check whether processing options represent a no-op transform."""
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
