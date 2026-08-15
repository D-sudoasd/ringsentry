"""Run a deterministic RingSentry preprocessing example on synthetic data.

The generated array is a labelled demonstration image, not an experimental
measurement, a detector simulation, or a performance benchmark.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import numpy as np


# Allow ``python examples/minimal_preprocessing.py`` from a source checkout.
if __package__ in (None, ""):
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))

from core.processing import apply_processing
from core.quality import analyze_image_quality
from core.writer import save_array


SYNTHETIC_SEED = 20260730
SYNTHETIC_SHAPE: Tuple[int, int] = (128, 128)

PROCESSING_OPTIONS = {
    "bg_offset": 35.0,
    "clip_negative": True,
    "pclip_low": 0.5,
    "pclip_high": 99.5,
    "bin_factor": 2,
    "intensity_transform": "log1p",
    "norm_mode": "minmax",
}

PNG_OPTIONS = {
    "scale": "linear",
    "vmin": 0.0,
    "vmax": 1.0,
    "colormap": "viridis",
    "dpi": 150,
}

OUTPUT_NAMES = {
    "raw_npy": "synthetic_raw.npy",
    "processed_npy": "synthetic_processed.npy",
    "display_png": "synthetic_processed_display.png",
    "summary_json": "summary.json",
}


def generate_synthetic_detector_image(seed: int = SYNTHETIC_SEED) -> np.ndarray:
    """Return a deterministic, finite 2D array with two synthetic radial rings."""
    rng = np.random.default_rng(int(seed))
    height, width = SYNTHETIC_SHAPE
    yy, xx = np.indices((height, width), dtype=np.float32)
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    radius = np.hypot(xx - center_x, yy - center_y)
    angle = np.arctan2(yy - center_y, xx - center_x)

    background = 40.0 + 0.012 * xx + 0.008 * yy
    inner_ring = 14.0 * np.exp(-0.5 * ((radius - 28.0) / 2.4) ** 2)
    inner_ring *= 1.0 + 0.10 * np.cos(4.0 * angle)
    outer_ring = 8.0 * np.exp(-0.5 * ((radius - 46.0) / 3.5) ** 2)
    outer_ring *= 1.0 + 0.08 * np.sin(3.0 * angle)
    noise = rng.normal(0.0, 1.2, size=SYNTHETIC_SHAPE).astype(np.float32)

    return np.asarray(background + inner_ring + outer_ring + noise, dtype=np.float32)


def _array_summary(arr: np.ndarray) -> Dict[str, object]:
    finite = np.isfinite(arr)
    values = np.asarray(arr)[finite]
    return {
        "shape": [int(value) for value in arr.shape],
        "dtype": str(arr.dtype),
        "finite_count": int(np.count_nonzero(finite)),
        "total_pixels": int(arr.size),
        "min": float(np.min(values)) if values.size else None,
        "max": float(np.max(values)) if values.size else None,
    }


def _save_required(
    arr: np.ndarray,
    path: Path,
    fmt: str,
    *,
    png_options: Optional[Dict[str, object]] = None,
) -> str:
    success, message, point_count = save_array(
        arr,
        path,
        fmt,
        preserve_dtype=True,
        metadata={"OriginalKind": "synthetic", "SyntheticData": True},
        png_options=png_options,
    )
    if not success:
        raise RuntimeError(f"Could not write {path.name}: {message}")
    if point_count != arr.size:
        raise RuntimeError(
            f"Unexpected point count for {path.name}: {point_count} != {arr.size}"
        )
    return str(message)


def run_example(output_dir: Path) -> Dict[str, object]:
    """Generate, process, save, and summarize the synthetic example."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = generate_synthetic_detector_image()
    quality = analyze_image_quality(
        raw,
        metadata={
            "source_kind": "synthetic",
            "source_name": "synthetic_diffraction_rings",
            "dtype": str(raw.dtype),
        },
        source_name="synthetic_diffraction_rings",
    )
    processed = apply_processing(raw, **PROCESSING_OPTIONS)

    output_paths = {
        key: output_dir / filename for key, filename in OUTPUT_NAMES.items()
    }
    writer_messages = {
        "raw_npy": _save_required(raw, output_paths["raw_npy"], "npy"),
        "processed_npy": _save_required(
            processed, output_paths["processed_npy"], "npy"
        ),
        "display_png": _save_required(
            processed,
            output_paths["display_png"],
            "png",
            png_options=PNG_OPTIONS,
        ),
    }

    summary: Dict[str, object] = {
        "example": "RingSentry synthetic 2D diffraction-ring preprocessing",
        "data_origin": "synthetic",
        "disclaimer": (
            "Synthetic data only; not an experimental measurement, "
            "performance benchmark, or scientific result."
        ),
        "seed": SYNTHETIC_SEED,
        "generation": {
            "description": (
                "Two analytic radial Gaussian rings on a smooth background "
                "with seeded Gaussian noise."
            ),
            "shape": list(SYNTHETIC_SHAPE),
            "dtype": "float32",
        },
        "processing": dict(PROCESSING_OPTIONS),
        "raw": _array_summary(raw),
        "processed": _array_summary(processed),
        "quality_control": {
            "source_name": quality.source_name,
            "source_kind": quality.source_kind,
            "review_required": bool(quality.review_required),
            "findings": [asdict(finding) for finding in quality.findings],
            "suggestions": [asdict(suggestion) for suggestion in quality.suggestions],
        },
        "display": {
            "purpose": "display only; quantitative arrays are stored as NPY",
            **dict(PNG_OPTIONS),
        },
        "outputs": dict(OUTPUT_NAMES),
        "writer_messages": writer_messages,
    }

    output_paths["summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    raw_summary = summary["raw"]
    processed_summary = summary["processed"]
    quality_summary = summary["quality_control"]
    findings = quality_summary["findings"]
    finding_text = ", ".join(
        f"{finding['level']}:{finding['category']}" for finding in findings
    ) or "none"
    print(
        "SYNTHETIC DATA ONLY: this example is not an experimental measurement "
        "or performance benchmark."
    )
    print(
        f"raw shape={tuple(raw_summary['shape'])}, "
        f"finite={raw_summary['finite_count']}/{raw_summary['total_pixels']}"
    )
    print(
        f"processed shape={tuple(processed_summary['shape'])}, "
        f"finite={processed_summary['finite_count']}/{processed_summary['total_pixels']}"
    )
    print(
        f"QC review_required={str(quality_summary['review_required']).lower()}, "
        f"findings={finding_text}"
    )
    print(f"outputs={output_dir.resolve()}")
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate and preprocess a deterministic synthetic 2D diffraction-ring array."
        )
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for NPY, PNG, and JSON outputs.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    run_example(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
