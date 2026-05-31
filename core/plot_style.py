"""Shared plotting style presets for display and publication exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any


PUBLICATION_COLORMAPS = ("viridis", "cividis", "magma", "plasma", "gray")

PLOT_EXPORT_PRESETS: dict[str, dict[str, Any]] = {
    "single_column": {
        "label": "Single-column figure",
        "figure_size": (3.35, 2.5),
        "dpi": 600,
        "font_size": 8,
        "label_size": 9,
        "legend_size": 7,
        "line_width": 1.1,
        "marker_size": 3.5,
        "axis_width": 0.8,
        "colorbar_fraction": 0.046,
        "colorbar_pad": 0.04,
        "constrained_layout": True,
        "colormap": "viridis",
    },
    "double_column": {
        "label": "Double-column figure",
        "figure_size": (7.1, 3.8),
        "dpi": 600,
        "font_size": 9,
        "label_size": 10,
        "legend_size": 8,
        "line_width": 1.2,
        "marker_size": 4.0,
        "axis_width": 0.9,
        "colorbar_fraction": 0.04,
        "colorbar_pad": 0.035,
        "constrained_layout": True,
        "colormap": "viridis",
    },
    "presentation": {
        "label": "Presentation",
        "figure_size": (8.0, 4.8),
        "dpi": 300,
        "font_size": 12,
        "label_size": 14,
        "legend_size": 11,
        "line_width": 1.8,
        "marker_size": 5.5,
        "axis_width": 1.1,
        "colorbar_fraction": 0.045,
        "colorbar_pad": 0.04,
        "constrained_layout": True,
        "colormap": "cividis",
    },
    "raw_inspection": {
        "label": "Raw inspection",
        "figure_size": (6.0, 4.0),
        "dpi": 150,
        "font_size": 9,
        "label_size": 10,
        "legend_size": 8,
        "line_width": 1.0,
        "marker_size": 3.0,
        "axis_width": 0.8,
        "colorbar_fraction": 0.046,
        "colorbar_pad": 0.04,
        "constrained_layout": False,
        "colormap": "viridis",
    },
    "publication": {
        "label": "Publication",
        "figure_size": (5.2, 3.6),
        "dpi": 600,
        "font_size": 9,
        "label_size": 10,
        "legend_size": 8,
        "line_width": 1.2,
        "marker_size": 4.0,
        "axis_width": 0.9,
        "colorbar_fraction": 0.04,
        "colorbar_pad": 0.035,
        "constrained_layout": True,
        "colormap": "viridis",
    },
}

PLOT_PRESET_LABELS = tuple(
    preset["label"] for preset in PLOT_EXPORT_PRESETS.values()
)


def _normalize_preset_name(name: str | None) -> str:
    if not name:
        return "publication"
    text = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    for key, preset in PLOT_EXPORT_PRESETS.items():
        if text in {key, str(preset["label"]).lower().replace(" ", "_")}:
            return key
    return "publication"


def get_plot_preset(name: str | None = None) -> dict[str, Any]:
    """Return a copy of a plotting/export preset."""
    return dict(PLOT_EXPORT_PRESETS[_normalize_preset_name(name)])


def apply_matplotlib_style(matplotlib_module, preset: str | None = None) -> dict[str, Any]:
    """Apply a restrained scientific plotting style to matplotlib rcParams."""
    cfg = get_plot_preset(preset)
    matplotlib_module.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": cfg["font_size"],
            "axes.labelsize": cfg["label_size"],
            "axes.titlesize": cfg["label_size"],
            "axes.linewidth": cfg["axis_width"],
            "axes.grid": False,
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "legend.frameon": False,
            "legend.fontsize": cfg["legend_size"],
            "lines.linewidth": cfg["line_width"],
            "lines.markersize": cfg["marker_size"],
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.major.width": cfg["axis_width"],
            "ytick.major.width": cfg["axis_width"],
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )
    return cfg


def style_axis(ax, preset: str | None = None) -> None:
    """Apply publication-style axis cosmetics without changing plotted data."""
    cfg = get_plot_preset(preset)
    ax.tick_params(
        direction="out",
        width=cfg["axis_width"],
        labelsize=cfg["font_size"],
        top=False,
        right=False,
    )
    for spine in ax.spines.values():
        spine.set_linewidth(cfg["axis_width"])


def style_figure_axes(fig, preset: str | None = None) -> None:
    """Style all axes in a figure while preserving existing artists."""
    for ax in fig.get_axes():
        style_axis(ax, preset=preset)


def save_figure(fig, path: str | Path, preset: str | None = None) -> None:
    """Save a matplotlib figure with paper-safe defaults."""
    cfg = get_plot_preset(preset)
    out_path = Path(path)
    original_size = tuple(fig.get_size_inches())
    original_layout_engine = (
        fig.get_layout_engine() if hasattr(fig, "get_layout_engine") else None
    )
    original_constrained = (
        fig.get_constrained_layout()
        if not hasattr(fig, "get_layout_engine") and hasattr(fig, "get_constrained_layout")
        else None
    )

    try:
        fig.set_size_inches(*cfg["figure_size"], forward=True)
        if hasattr(fig, "set_layout_engine"):
            fig.set_layout_engine("constrained" if cfg["constrained_layout"] else None)
        else:
            fig.set_constrained_layout(bool(cfg["constrained_layout"]))
        fig.savefig(
            str(out_path),
            dpi=int(cfg["dpi"]),
            bbox_inches="tight",
            pad_inches=0.03,
            facecolor="white",
            edgecolor="none",
        )
    finally:
        fig.set_size_inches(*original_size, forward=True)
        if hasattr(fig, "set_layout_engine"):
            fig.set_layout_engine(original_layout_engine)
        elif hasattr(fig, "set_constrained_layout"):
            fig.set_constrained_layout(bool(original_constrained))
        canvas = getattr(fig, "canvas", None)
        if canvas is not None:
            canvas.draw_idle()
