"""Generate the two repository-owned figures used by the JOSS manuscript.

The script uses only RingSentry source code and a deterministic synthetic
array.  It does not load experimental data or report performance results.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg", force=True)

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from core.processing import apply_processing
from core.quality import analyze_image_quality
from examples.minimal_preprocessing import (
    PROCESSING_OPTIONS,
    SYNTHETIC_SEED,
    generate_synthetic_detector_image,
)


FIGURE_STEMS = ("architecture_workflow", "synthetic_processing")
SUPPORTED_FORMATS = ("svg", "png", "pdf")

COLORS = {
    "blue": "#0072B2",
    "sky": "#56B4E9",
    "green": "#009E73",
    "orange": "#E69F00",
    "vermillion": "#D55E00",
    "ink": "#202124",
    "gray": "#666666",
    "light_blue": "#E8F3F8",
    "light_green": "#E8F5F0",
    "light_orange": "#FFF3DC",
    "light_gray": "#F5F5F5",
    "white": "#FFFFFF",
}


def configure_style() -> None:
    """Apply one accessible publication style to both figures."""
    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            # The manuscript scales these 180 mm figures down slightly.  Keep
            # the source text at or above 8 pt so the final PDF remains legible.
            "font.size": 8.4,
            "axes.titlesize": 8.8,
            "axes.labelsize": 8.4,
            "xtick.labelsize": 8.4,
            "ytick.labelsize": 8.4,
            "legend.fontsize": 8.4,
            "figure.titlesize": 9.6,
            "axes.linewidth": 0.6,
            "lines.linewidth": 1.0,
            "savefig.dpi": 600,
            "svg.fonttype": "none",
            "svg.hashsalt": "ringsentry-joss-figures",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _add_stage_box(
    ax,
    x: float,
    y: float,
    width: float,
    height: float,
    number: str,
    title: str,
    body: str,
    facecolor: str,
    edgecolor: str,
) -> None:
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.008,rounding_size=0.012",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=0.8,
    )
    ax.add_patch(patch)
    ax.text(
        x + 0.012,
        y + height - 0.020,
        f"{number}  {title}",
        ha="left",
        va="top",
        fontsize=8.6,
        fontweight="bold",
        color=COLORS["ink"],
    )
    ax.text(
        x + width / 2.0,
        y + height - 0.063,
        body,
        ha="center",
        va="top",
        fontsize=8.4,
        linespacing=1.25,
        color=COLORS["ink"],
    )


def _add_arrow(ax, start: Tuple[float, float], end: Tuple[float, float]) -> None:
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=8,
        linewidth=0.8,
        color=COLORS["ink"],
        shrinkA=2,
        shrinkB=2,
    )
    ax.add_patch(arrow)


def _add_independent_tool(
    ax,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    module: str,
    body: str,
    caution: str,
    edgecolor: str,
) -> None:
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.010,rounding_size=0.012",
        facecolor=COLORS["white"],
        edgecolor=edgecolor,
        linewidth=0.8,
        linestyle=(0, (5, 2.5)),
    )
    ax.add_patch(patch)
    ax.text(
        x + 0.016,
        y + height - 0.018,
        title,
        ha="left",
        va="top",
        fontsize=8.6,
        fontweight="bold",
        color=edgecolor,
    )
    ax.text(
        x + 0.016,
        y + height - 0.052,
        module,
        ha="left",
        va="top",
        fontsize=8.4,
        color=COLORS["gray"],
    )
    ax.text(
        x + 0.016,
        y + height - 0.082,
        body,
        ha="left",
        va="top",
        fontsize=8.4,
        linespacing=1.25,
        color=COLORS["ink"],
    )
    ax.text(
        x + 0.016,
        y + 0.014,
        caution,
        ha="left",
        va="bottom",
        fontsize=8.4,
        fontweight="bold",
        color=COLORS["ink"],
    )


def create_architecture_workflow():
    """Create the verified RingSentry architecture and workflow diagram."""
    # 7.1 in = 180.3 mm, kept below Nature's 183 mm two-column width.
    fig, ax = plt.subplots(figsize=(7.1, 5.6))
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.axis("off")

    ax.text(
        0.5,
        0.970,
        "RingSentry architecture and auditable processing workflow",
        ha="center",
        va="top",
        fontsize=9.6,
        fontweight="bold",
        color=COLORS["ink"],
    )
    ax.text(
        0.025,
        0.910,
        "Main batch path (GUI-orchestrated; per-file core data path)",
        ha="left",
        va="center",
        fontsize=8.4,
        color=COLORS["gray"],
    )

    y = 0.685
    height = 0.170
    stage_specs = (
        (
            0.025,
            0.150,
            "1",
            "Entry / GUI",
            "main.py → App\nexplicit\nparameters",
            COLORS["light_blue"],
            COLORS["blue"],
        ),
        (
            0.189,
            0.174,
            "2",
            "Discover / load",
            "core.loader\nfiles → 2D arrays",
            COLORS["light_blue"],
            COLORS["blue"],
        ),
        (
            0.377,
            0.180,
            "3",
            "QC / preflight",
            "core.quality\nread-only QC / plan",
            COLORS["light_green"],
            COLORS["green"],
        ),
        (
            0.571,
            0.214,
            "4",
            "Processing",
            "core.worker\n→ apply_processing",
            COLORS["light_orange"],
            COLORS["orange"],
        ),
        (
            0.799,
            0.176,
            "5",
            "Write / report",
            "core.writer\n+ gui.app report",
            COLORS["light_blue"],
            COLORS["blue"],
        ),
    )
    for x, width, number, title, body, face, edge in stage_specs:
        _add_stage_box(ax, x, y, width, height, number, title, body, face, edge)

    for left, right in (
        (0.175, 0.189),
        (0.363, 0.377),
        (0.557, 0.571),
        (0.785, 0.799),
    ):
        _add_arrow(ax, (left, y + height / 2.0), (right, y + height / 2.0))

    process_box = FancyBboxPatch(
        (0.025, 0.365),
        0.950,
        0.225,
        boxstyle="round,pad=0.010,rounding_size=0.012",
        facecolor=COLORS["light_gray"],
        edgecolor=COLORS["orange"],
        linewidth=0.75,
    )
    ax.add_patch(process_box)
    ax.text(
        0.045,
        0.565,
        "apply_processing: fixed, explicit operation order",
        ha="left",
        va="top",
        fontsize=8.6,
        fontweight="bold",
        color=COLORS["ink"],
    )
    ordered_lines = (
        "1 Dark subtraction  →  2 Flat correction  →  3 Background offset  →  "
        "4 Validate clipping parameters",
        "5 ROI  →  6 Mask  →  7 Absolute clipping  →  8 Percentile clipping",
        "9 Negative clipping  →  10 Hot-pixel suppression  →  11 Rotate / flip  →  "
        "12 Block-mean binning",
        "13 Intensity transform  →  14 Gamma  →  15 Normalization",
    )
    for index, line in enumerate(ordered_lines):
        ax.text(
            0.500,
            0.510 - index * 0.041,
            line,
            ha="center",
            va="center",
            fontsize=8.4,
            color=COLORS["ink"],
        )
    _add_arrow(ax, (0.680, 0.685), (0.680, 0.600))

    ax.text(
        0.5,
        0.335,
        "Independent tools (separate GUI tabs and core modules; not batch stages)",
        ha="center",
        va="center",
        fontsize=8.4,
        fontweight="bold",
        color=COLORS["gray"],
    )
    _add_independent_tool(
        ax,
        0.025,
        0.055,
        0.455,
        0.245,
        "Independent: CBF zero-value repair",
        "core.overexposure_repair",
        "Scan → target mask → write / read-back\n"
        "→ verify → CSV / configuration / QC reports",
        "Configured zeros only; cannot recover\ntrue saturated intensity.",
        COLORS["vermillion"],
    )
    _add_independent_tool(
        ax,
        0.520,
        0.055,
        0.455,
        0.245,
        "Independent: Q geometry calculator",
        "core.diffraction_model",
        "User λ / distance / pixel size /\n"
        "beam center → ideal-planar Q / 2θ / r / d\n"
        "+ detector view / export",
        "No image calibration, integration, peak fitting,\nor refinement.",
        COLORS["green"],
    )
    ax.text(
        0.5,
        0.008,
        "Scope: inspectable preprocessing, quality control, geometry conversion, "
        "and export of 2D detector images.",
        ha="center",
        va="bottom",
        fontsize=8.4,
        color=COLORS["gray"],
    )
    return fig


def _radial_mean(
    arr: np.ndarray, radius_scale: float = 1.0
) -> Tuple[np.ndarray, np.ndarray]:
    data = np.asarray(arr, dtype=np.float64)
    yy, xx = np.indices(data.shape, dtype=np.float64)
    center_x = (data.shape[1] - 1) / 2.0
    center_y = (data.shape[0] - 1) / 2.0
    radius = np.hypot(xx - center_x, yy - center_y) * float(radius_scale)
    radius_bin = np.floor(radius).astype(np.int64)
    finite = np.isfinite(data)
    sums = np.bincount(radius_bin[finite], weights=data[finite])
    counts = np.bincount(radius_bin[finite])
    valid = counts > 0
    means = np.full(counts.shape, np.nan, dtype=np.float64)
    means[valid] = sums[valid] / counts[valid]
    return np.arange(means.size, dtype=np.float64) + 0.5, means


def _display_normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(values)
    result = np.full(values.shape, np.nan, dtype=np.float64)
    if not np.any(finite):
        return result
    vmin = float(np.min(values[finite]))
    vmax = float(np.max(values[finite]))
    if vmax > vmin:
        result[finite] = (values[finite] - vmin) / (vmax - vmin)
    else:
        result[finite] = 0.0
    return result


def _array_fact_line(label: str, arr: np.ndarray) -> str:
    finite_count = int(np.count_nonzero(np.isfinite(arr)))
    return (
        f"{label}: {arr.shape[0]} × {arr.shape[1]}, {arr.dtype}, "
        f"finite {finite_count:,}/{arr.size:,}"
    )


def create_synthetic_processing():
    """Create a no-real-data demonstration using the shipped example seam."""
    raw = generate_synthetic_detector_image()
    processed = apply_processing(raw, **PROCESSING_OPTIONS)
    quality = analyze_image_quality(
        raw,
        metadata={
            "source_kind": "synthetic",
            "source_name": "synthetic_diffraction_rings",
            "dtype": str(raw.dtype),
        },
        source_name="synthetic_diffraction_rings",
    )

    fig = plt.figure(figsize=(7.1, 5.2), constrained_layout=False)
    grid = fig.add_gridspec(
        1,
        3,
        left=0.070,
        right=0.980,
        bottom=0.360,
        top=0.795,
        wspace=0.48,
        width_ratios=(1.0, 1.0, 1.35),
    )
    raw_ax = fig.add_subplot(grid[0, 0])
    processed_ax = fig.add_subplot(grid[0, 1])
    profile_ax = fig.add_subplot(grid[0, 2])

    fig.text(
        0.5,
        0.950,
        "Deterministic synthetic preprocessing example",
        ha="center",
        va="top",
        fontsize=9.6,
        fontweight="bold",
        color=COLORS["ink"],
    )
    fig.text(
        0.5,
        0.875,
        "Fixed-seed synthetic image and settings from the shipped minimal "
        "preprocessing example; processed by the RingSentry core",
        ha="center",
        va="center",
        fontsize=8.4,
        color=COLORS["gray"],
    )

    raw_image = raw_ax.imshow(raw, origin="upper", cmap="cividis", interpolation="nearest")
    raw_ax.set_title("Raw synthetic matrix", pad=5)
    raw_ax.set_xlabel("Detector x (pixels)")
    raw_ax.set_ylabel("Detector y (pixels)")
    raw_colorbar = fig.colorbar(
        raw_image,
        ax=raw_ax,
        orientation="horizontal",
        fraction=0.060,
        pad=0.175,
        aspect=28,
    )
    raw_colorbar.set_label("Synthetic intensity (a.u.)", fontsize=8.4, labelpad=2)
    raw_colorbar.ax.tick_params(labelsize=8.4, width=0.5, length=2.0)

    processed_image = processed_ax.imshow(
        processed,
        origin="upper",
        cmap="cividis",
        interpolation="nearest",
        vmin=0.0,
        vmax=1.0,
    )
    processed_ax.set_title("Processed matrix", pad=5)
    processed_ax.set_xlabel("Output x (pixels)")
    processed_ax.set_ylabel("Output y (pixels)")
    processed_colorbar = fig.colorbar(
        processed_image,
        ax=processed_ax,
        orientation="horizontal",
        fraction=0.060,
        pad=0.175,
        aspect=28,
    )
    processed_colorbar.set_label("Normalized value", fontsize=8.4, labelpad=2)
    processed_colorbar.ax.tick_params(labelsize=8.4, width=0.5, length=2.0)

    raw_radius, raw_profile = _radial_mean(raw)
    scale = float(PROCESSING_OPTIONS.get("bin_factor", 1))
    processed_radius, processed_profile = _radial_mean(
        processed, radius_scale=scale
    )
    profile_ax.plot(
        raw_radius,
        _display_normalize(raw_profile),
        color=COLORS["blue"],
        linestyle="-",
        marker="o",
        markevery=8,
        markersize=2.8,
        label="Raw synthetic",
    )
    profile_ax.plot(
        processed_radius,
        _display_normalize(processed_profile),
        color=COLORS["orange"],
        linestyle="--",
        marker="s",
        markevery=7,
        markersize=2.7,
        label="Processed",
    )
    profile_ax.set_title("Radial mean (display-normalized)", pad=5)
    profile_ax.set_xlabel("Radius (input-pixel equivalent)")
    profile_ax.set_ylabel("Separately normalized mean (a.u.)")
    profile_ax.set_ylim(-0.04, 1.08)
    profile_ax.grid(axis="y", color="#D0D0D0", linewidth=0.5, linestyle=":")
    profile_ax.spines["top"].set_visible(False)
    profile_ax.spines["right"].set_visible(False)
    profile_ax.legend(loc="upper right", frameon=False, handlelength=2.6)
    for label, axis in zip(("a", "b", "c"), (raw_ax, processed_ax, profile_ax)):
        axis.text(
            -0.16,
            1.10,
            label,
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=10.0,
            fontweight="bold",
            color=COLORS["ink"],
        )

    findings = ", ".join(item.category for item in quality.findings) or "none"
    processing_text = (
        "Processing: background offset 35 → percentile clipping 0.5–99.5 →\n"
        "negative clipping → "
        "2 × block mean → log1p → min–max normalization"
    )
    fact_text = (
        f"Seed: {SYNTHETIC_SEED}   |   Shipped example: examples/minimal_preprocessing.py\n"
        f"{_array_fact_line('Raw', raw)}\n"
        f"{_array_fact_line('Processed', processed)}\n"
        f"QC findings: {findings}; review_required={str(quality.review_required).lower()}\n"
        f"{processing_text}"
    )
    fig.text(
        0.055,
        0.055,
        fact_text,
        ha="left",
        va="bottom",
        fontsize=8.4,
        linespacing=1.35,
        color=COLORS["ink"],
        bbox={
            "boxstyle": "round,pad=0.32",
            "facecolor": COLORS["light_gray"],
            "edgecolor": "#B8B8B8",
            "linewidth": 0.7,
        },
    )
    return fig


def _save_figure(fig, output_dir: Path, stem: str, formats: Iterable[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for fmt in formats:
        output_path = output_dir / f"{stem}.{fmt}"
        metadata: Optional[Dict[str, object]]
        if fmt == "svg":
            metadata = {"Creator": "RingSentry paper/figures/make_figures.py", "Date": None}
        elif fmt == "pdf":
            metadata = {
                "Creator": "RingSentry paper/figures/make_figures.py",
                "CreationDate": None,
                "ModDate": None,
            }
        else:
            metadata = {"Software": "RingSentry paper/figures/make_figures.py"}
        fig.savefig(
            output_path,
            format=fmt,
            dpi=600,
            metadata=metadata,
        )
        print(f"WROTE {output_path.resolve()}")


def generate_figures(output_dir: Path, formats: Sequence[str]) -> None:
    configure_style()
    creators = (
        (FIGURE_STEMS[0], create_architecture_workflow),
        (FIGURE_STEMS[1], create_synthetic_processing),
    )
    for stem, creator in creators:
        figure = creator()
        try:
            _save_figure(figure, output_dir, stem, formats)
        finally:
            plt.close(figure)


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the RingSentry JOSS architecture and synthetic figures."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Destination directory (default: paper/figures).",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=SUPPORTED_FORMATS,
        default=list(SUPPORTED_FORMATS),
        help="One or more output formats; default: svg, pdf, and png.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    formats = tuple(dict.fromkeys(args.formats))
    generate_figures(args.output_dir, formats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
