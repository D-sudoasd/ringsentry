import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from core.processing import apply_processing
from examples.minimal_preprocessing import (
    SYNTHETIC_SEED,
    generate_synthetic_detector_image,
    run_example,
)


def test_synthetic_detector_image_is_deterministic():
    first = generate_synthetic_detector_image()
    second = generate_synthetic_detector_image()

    assert SYNTHETIC_SEED == 20260730
    assert first.shape == (128, 128)
    assert first.dtype == np.float32
    assert np.isfinite(first).all()
    assert np.array_equal(first, second)


def test_run_example_writes_deterministic_core_processing_outputs(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first_summary = run_example(first_dir)
    second_summary = run_example(second_dir)

    expected_names = {
        "raw_npy": "synthetic_raw.npy",
        "processed_npy": "synthetic_processed.npy",
        "display_png": "synthetic_processed_display.png",
        "summary_json": "summary.json",
    }
    assert first_summary == second_summary
    assert first_summary["data_origin"] == "synthetic"
    assert first_summary["seed"] == SYNTHETIC_SEED
    assert first_summary["outputs"] == expected_names
    assert "not an experimental measurement" in first_summary["disclaimer"]

    for output_name in expected_names.values():
        assert (first_dir / output_name).is_file()
        assert (second_dir / output_name).is_file()

    raw = np.load(first_dir / expected_names["raw_npy"])
    processed = np.load(first_dir / expected_names["processed_npy"])
    repeated_raw = np.load(second_dir / expected_names["raw_npy"])
    repeated_processed = np.load(second_dir / expected_names["processed_npy"])

    expected_processed = apply_processing(
        raw,
        bg_offset=35.0,
        clip_negative=True,
        pclip_low=0.5,
        pclip_high=99.5,
        bin_factor=2,
        intensity_transform="log1p",
        norm_mode="minmax",
    )
    assert np.array_equal(raw, repeated_raw)
    assert np.array_equal(processed, repeated_processed)
    np.testing.assert_allclose(processed, expected_processed, rtol=0.0, atol=0.0)
    assert processed.shape == (64, 64)
    assert np.isfinite(processed).all()

    with Image.open(first_dir / expected_names["display_png"]) as image:
        assert image.mode == "RGB"
        assert image.size == (64, 64)

    saved_summary = json.loads(
        (first_dir / expected_names["summary_json"]).read_text(encoding="utf-8")
    )
    assert saved_summary == first_summary
    assert saved_summary["raw"]["finite_count"] == raw.size
    assert saved_summary["processed"]["finite_count"] == processed.size
    assert saved_summary["quality_control"]["review_required"] is False
    assert saved_summary["quality_control"]["findings"] == []


def test_cli_accepts_output_directory_and_prints_verifiable_summary(tmp_path):
    output_dir = tmp_path / "cli-output"
    script = Path(__file__).parents[1] / "examples" / "minimal_preprocessing.py"

    result = subprocess.run(
        [sys.executable, str(script), "--output-dir", str(output_dir)],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "SYNTHETIC DATA ONLY" in result.stdout
    assert "raw shape=(128, 128), finite=16384/16384" in result.stdout
    assert "processed shape=(64, 64), finite=4096/4096" in result.stdout
    assert "QC review_required=false, findings=none" in result.stdout
    assert (output_dir / "summary.json").is_file()
