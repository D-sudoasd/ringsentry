"""Automatic quality control for 2D detector images.

The QC rules are intentionally transparent and conservative.  They provide
facts, interpretations, and recommendations, but they never modify processing
parameters automatically.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class QualityFinding:
    """A QC finding with a level, message, and evidence basis."""

    level: str
    category: str
    message: str
    basis: str


@dataclass
class QualitySuggestion:
    """A non-mutating parameter or workflow suggestion."""

    action: str
    reason: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityReport:
    """Structured QC output for one image."""

    source_name: str
    source_kind: str
    dtype: str
    shape: Tuple[int, int]
    stats: Dict[str, Any]
    findings: List[QualityFinding]
    suggestions: List[QualitySuggestion]
    review_required: bool = False


def _safe_percentile(values: np.ndarray, q: float) -> Optional[float]:
    if values.size == 0:
        return None
    return float(np.percentile(values, q))


def _finite_values(arr: np.ndarray) -> np.ndarray:
    finite = np.isfinite(arr)
    return arr[finite]


def _suspected_extreme_count(values: np.ndarray) -> int:
    """Count robust high-side outliers using median + 8*MAD.

    This is a global robust rule, not a crystallographic interpretation.  It
    flags likely hot pixels or saturated speckles for manual review.
    """
    if values.size < 9:
        return 0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad <= 0 or not np.isfinite(mad):
        # 均一背景上叠加少量强亮点时 MAD 会等于 0。此时用“高于中位数”
        # 作为保守异常计数，避免 p99 恰好落在亮点值上而漏报。
        if not np.any(values > median):
            return 0
        threshold = median
    else:
        threshold = median + 8.0 * 1.4826 * mad
    return int(np.count_nonzero(values > threshold))


def analyze_image_quality(
    arr,
    metadata: Optional[Dict[str, Any]] = None,
    source_name: str = "",
) -> QualityReport:
    """Analyze a 2D image and return transparent QC facts and suggestions."""
    metadata = dict(metadata or {})
    a = np.asarray(arr)
    if a.ndim != 2:
        raise ValueError(f"QC expects a 2D image, got shape={a.shape}")

    total = int(a.size)
    finite_mask = np.isfinite(a)
    finite_count = int(np.count_nonzero(finite_mask))
    nan_count = int(np.count_nonzero(np.isnan(a)))
    inf_count = int(np.count_nonzero(np.isinf(a)))
    zero_count = int(np.count_nonzero(a == 0))
    negative_count = int(np.count_nonzero(finite_mask & (a < 0)))
    values = _finite_values(a.astype(np.float64, copy=False))

    dtype = str(metadata.get("dtype") or a.dtype)
    source_kind = str(metadata.get("source_kind") or "")
    source_name = source_name or str(metadata.get("source_name") or "")

    stats: Dict[str, Any] = {
        "total_pixels": total,
        "finite_count": finite_count,
        "nan_count": nan_count,
        "inf_count": inf_count,
        "zero_count": zero_count,
        "negative_count": negative_count,
        "zero_ratio": zero_count / total if total else 0.0,
        "negative_ratio": negative_count / total if total else 0.0,
        "finite_ratio": finite_count / total if total else 0.0,
    }

    if finite_count:
        vmin = float(np.min(values))
        vmax = float(np.max(values))
        median = float(np.median(values))
        p1 = _safe_percentile(values, 1.0)
        p99 = _safe_percentile(values, 99.0)
        stats.update({
            "min": vmin,
            "max": vmax,
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "median": median,
            "p1": p1,
            "p99": p99,
            "dynamic_range": vmax - vmin,
            "suspected_extreme_count": _suspected_extreme_count(values),
        })
    else:
        stats.update({
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "median": None,
            "p1": None,
            "p99": None,
            "dynamic_range": None,
            "suspected_extreme_count": 0,
        })

    saturated_high_count = 0
    try:
        if np.issubdtype(a.dtype, np.integer):
            info = np.iinfo(a.dtype)
            saturated_high_count = int(np.count_nonzero(a == info.max))
    except Exception:
        saturated_high_count = 0
    stats["saturated_high_count"] = saturated_high_count

    findings: List[QualityFinding] = []
    suggestions: List[QualitySuggestion] = []

    if finite_count == 0:
        findings.append(QualityFinding(
            "ERROR", "finite", "图像没有有限数值，不能用于定量处理。",
            f"finite_count=0, total={total}",
        ))
    if nan_count or inf_count:
        findings.append(QualityFinding(
            "WARNING", "invalid_values", "图像包含 NaN 或 Inf，需要确认来源。",
            f"nan={nan_count}, inf={inf_count}",
        ))
    if stats["zero_ratio"] > 0.90:
        findings.append(QualityFinding(
            "WARNING", "zeros", "零值像素比例很高，可能包含大面积 mask 或空白区域。",
            f"zero_ratio={stats['zero_ratio']:.3f}",
        ))
    elif stats["zero_ratio"] > 0.50:
        findings.append(QualityFinding(
            "INFO", "zeros", "零值像素比例偏高，导出 XY 时可考虑跳过零值。",
            f"zero_ratio={stats['zero_ratio']:.3f}",
        ))
    if stats["negative_ratio"] > 0.01:
        findings.append(QualityFinding(
            "WARNING", "negative", "负值比例超过 1%，请确认是否来自暗场扣除或背景扣除。",
            f"negative_ratio={stats['negative_ratio']:.3f}",
        ))
        suggestions.append(QualitySuggestion(
            "检查 dark/background 设置；仅在物理上确认负值无意义时再启用负值裁剪。",
            "负强度可能是有效背景扣除结果，也可能是参数设置错误。",
        ))
    if saturated_high_count:
        findings.append(QualityFinding(
            "WARNING", "saturation", "检测到 dtype 上限像素，可能存在饱和。",
            f"saturated_high_count={saturated_high_count}",
        ))
    if stats["suspected_extreme_count"] > max(10, total * 0.0001):
        findings.append(QualityFinding(
            "WARNING", "hot_pixels", "检测到较多极端亮点，可能需要热像素抑制。",
            f"suspected_extreme_count={stats['suspected_extreme_count']}",
        ))
        suggestions.append(QualitySuggestion(
            "建议预览 hot pixel suppression；推荐 window=3, sigma=8 起步。",
            "极端亮点数量超过 robust median+8*MAD 阈值。",
            {"hot_pixel_enable": True, "hot_pixel_window": 3, "hot_pixel_sigma": 8.0},
        ))

    if finite_count and stats["p99"] is not None and stats["median"] not in (None, 0):
        p99 = float(stats["p99"])
        median_abs = abs(float(stats["median"]))
        if median_abs > 0 and abs(p99) / median_abs > 50:
            suggestions.append(QualitySuggestion(
                "建议预览 percentile clip，例如 PClip Low=1, PClip High=99。",
                "p99 与中位数相差很大，显示或导出前应确认极端值是否合理。",
                {"pclip_low": 1.0, "pclip_high": 99.0},
            ))

    if source_kind == "cbf" and dtype in {"int32", "uint32", "int64", "uint64"}:
        suggestions.append(QualitySuggestion(
            "CBF 原始矩阵严格保真建议同时导出 EDF 或 NPY。",
            "TIFF 为兼容 ImageJ/Fiji 可能转换 dtype；日志会标注转换。",
            {"formats": ["edf", "npy"]},
        ))

    review_required = any(f.level in {"WARNING", "ERROR"} for f in findings)
    return QualityReport(
        source_name=source_name,
        source_kind=source_kind,
        dtype=dtype,
        shape=tuple(int(v) for v in a.shape),
        stats=stats,
        findings=findings,
        suggestions=suggestions,
        review_required=review_required,
    )


def assess_processing_plan(
    report: QualityReport,
    *,
    formats: Optional[Sequence[str]] = None,
    roi=None,
    bin_factor: int = 1,
    rotate_deg: str = "0",
) -> List[QualityFinding]:
    """Assess planned processing choices against one image QC report."""
    findings: List[QualityFinding] = []
    h, w = report.shape
    if roi is not None:
        x, y, roi_w, roi_h = [int(v) for v in roi]
        roi_invalid = (
            x < 0 or y < 0 or roi_w <= 0 or roi_h <= 0
            or x + roi_w > w or y + roi_h > h
        )
        if roi_invalid:
            findings.append(QualityFinding(
                "ERROR", "roi", "ROI 超出图像范围或尺寸非法。",
                f"roi={roi}, shape={report.shape}",
            ))
        else:
            h, w = roi_h, roi_w
    if str(rotate_deg) in ("90", "270"):
        h, w = w, h
    bin_factor = int(1 if bin_factor is None else bin_factor)
    if bin_factor < 1:
        findings.append(QualityFinding(
            "ERROR", "binning", "Binning 因子必须 >= 1。",
            f"bin_factor={bin_factor}",
        ))
        return findings
    if bin_factor > min(h, w):
        findings.append(QualityFinding(
            "ERROR", "binning", "Binning 因子大于有效图像尺寸。",
            f"bin_factor={bin_factor}, effective_shape={(h, w)}",
        ))
    elif bin_factor > 1 and ((h % bin_factor) or (w % bin_factor)):
        findings.append(QualityFinding(
            "WARNING", "binning", "Binning 会裁掉右侧或底部边缘像素。",
            f"bin_factor={bin_factor}, effective_shape={(h, w)}",
        ))
    tiff_dtype_risk = (
        formats
        and "tif" in formats
        and report.source_kind == "cbf"
        and report.dtype in {"int32", "uint32", "int64", "uint64"}
    )
    if tiff_dtype_risk:
        findings.append(QualityFinding(
            "INFO", "tiff_dtype", "CBF 转 TIFF 可能发生兼容 dtype 转换。",
            f"source_dtype={report.dtype}",
        ))
    return findings


def quality_summary_line(report: QualityReport) -> str:
    """Return a compact one-line QC summary for logs and reports."""
    s = report.stats
    return (
        f"QC: {report.source_name or '<array>'} [{report.source_kind}, {report.dtype}] "
        f"shape={report.shape}, finite={s['finite_count']}/{s['total_pixels']}, "
        f"nan={s['nan_count']}, inf={s['inf_count']}, "
        f"zero={s['zero_ratio']:.1%}, neg={s['negative_ratio']:.1%}, "
        f"min={s['min']}, max={s['max']}"
    )


def format_quality_report(report: QualityReport) -> str:
    """Format a QC report for the GUI text panel."""
    s = report.stats
    lines = [
        f"文件: {report.source_name or '<array>'}",
        f"格式/dtype: {report.source_kind or 'unknown'} / {report.dtype}",
        f"尺寸: {report.shape[0]} x {report.shape[1]}",
        f"有限值: {s['finite_count']}/{s['total_pixels']} ({s['finite_ratio']:.1%})",
        f"NaN/Inf: {s['nan_count']} / {s['inf_count']}",
        f"零值比例: {s['zero_ratio']:.1%}",
        f"负值比例: {s['negative_ratio']:.1%}",
        f"范围: min={s['min']}, max={s['max']}, median={s['median']}",
        f"p1/p99: {s['p1']} / {s['p99']}",
        f"疑似极端亮点: {s['suspected_extreme_count']}",
        f"饱和上限像素: {s['saturated_high_count']}",
    ]
    if report.findings:
        lines.append("\n风险/提示:")
        for finding in report.findings:
            lines.append(
                f"- [{finding.level}] {finding.message} ({finding.basis})"
            )
    if report.suggestions:
        lines.append("\n建议（不会自动应用）:")
        for suggestion in report.suggestions:
            lines.append(f"- {suggestion.action} 依据: {suggestion.reason}")
    if report.review_required:
        lines.append("\n结论: 建议人工复核后再批处理。")
    else:
        lines.append("\n结论: 未发现明显自动质控风险。")
    return "\n".join(lines)
