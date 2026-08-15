import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

tk = pytest.importorskip("tkinter")

from gui.app import App  # noqa: E402
from gui.calibration_frame import CalibrationManagerDialog  # noqa: E402


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _report_app(input_file: Path):
    return SimpleNamespace(
        io_tab=SimpleNamespace(
            input_mode_var=Value("files"),
            dir_var=Value(""),
            workflow_preset_var=Value("Custom"),
            h5_path_var=Value("/entry/data/data"),
        ),
        output_tab=SimpleNamespace(
            format_vars={"npy": Value(True), "png": Value(False)},
            overwrite_var=Value(False),
            lossless_matrix_var=Value(True),
            xy_header=Value(True),
            xy_one_based=Value(False),
            xy_skip_zeros=Value(True),
            xy_zero_tol=Value(0.0),
            xy_y_axis_origin_var=Value("top-left"),
            png_scale_var=Value("linear"),
            png_min_var=Value(""),
            png_max_var=Value(""),
            png_colormap_var=Value("viridis"),
            png_dpi_var=Value(300),
            plot_export_preset_var=Value("Raw inspection"),
        ),
        processing_tab=SimpleNamespace(
            roi_var=Value(""),
            dark_frame_var=Value("2 frames combined (mean)"),
            flat_frame_var=Value("flat.edf"),
            flat_is_dark_subtracted_var=Value(True),
            mask_frame_var=Value("none"),
            mask_nonzero_is_invalid_var=Value(True),
            clip_negative_var=Value(False),
            bg_offset_var=Value(0.0),
            min_intensity_var=Value(""),
            max_intensity_var=Value(""),
        ),
        geometry_tab=SimpleNamespace(
            rotate_var=Value("0"),
            flip_x_var=Value(False),
            flip_y_var=Value(False),
            bin_factor_var=Value(1),
            pclip_low_var=Value(""),
            pclip_high_var=Value(""),
            intensity_transform_var=Value("none"),
            gamma_var=Value(1.0),
            norm_mode_var=Value("none"),
            hot_pixel_enable_var=Value(False),
            hot_pixel_window_var=Value(3),
            hot_pixel_sigma_var=Value(8.0),
        ),
        log_panel=SimpleNamespace(
            max_thr_var=Value(4),
            run_log_lines=["SUCCESS: synthetic.edf [npy/RAW]"],
        ),
        last_max_workers=4,
        filelist=[(input_file, Path("synthetic.edf"))],
        dark_frame_provenance={
            "mode": "combined",
            "method": "mean",
            "files": ["dark-1.edf", "dark-2.edf"],
        },
        flat_frame_provenance={
            "mode": "single",
            "files": ["flat.edf"],
        },
        last_quality_reports=[],
        start_time=None,
        stats={"success": 1, "failed": 0, "skipped": 0, "cancelled": 0},
    )


def test_run_report_records_reproducibility_options_and_input_files(tmp_path):
    input_file = tmp_path / "synthetic.edf"
    app = _report_app(input_file)

    report_path = App._write_run_report(app, tmp_path)
    report = report_path.read_text(encoding="utf-8")

    assert "Max Workers: 4" in report
    assert "Workflow Preset: Custom" in report
    assert "Overwrite Existing: False" in report
    assert "Lossless Matrix Requested: True" in report
    assert (
        "XY Export: header=True, one_based=False, skip_zeros=True, "
        "zero_tol=0.0, y_axis_origin=top-left"
    ) in report
    assert "Flat Already Dark-subtracted: True" in report
    assert '"method": "mean"' in report
    assert '"dark-1.edf"' in report
    assert "---- Input Files ----" in report
    assert str(input_file) in report


def _new_hidden_root_or_skip():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display is unavailable: {exc}")
    root.withdraw()
    return root


@pytest.mark.parametrize(
    ("frame_type", "method", "expected"),
    [
        ("dark", "mean", np.array([[2.0, 3.0], [4.0, 5.0]], dtype=np.float32)),
        ("flat", "median", np.array([[2.0, 3.0], [4.0, 5.0]], dtype=np.float32)),
    ],
)
def test_multiframe_calibration_records_combination_provenance_in_run_report(
    tmp_path, monkeypatch, frame_type, method, expected
):
    """Exercise the real dialog's file-loading and aggregation path headlessly."""
    paths = [tmp_path / "calibration-1.edf", tmp_path / "calibration-2.edf"]
    for path in paths:
        path.touch()
    arrays = {
        str(paths[0]): np.array([[1, 2], [3, 4]], dtype=np.float32),
        str(paths[1]): np.array([[3, 4], [5, 6]], dtype=np.float32),
    }
    root = _new_hidden_root_or_skip()
    app = SimpleNamespace(
        io_tab=SimpleNamespace(h5_path_var=Value("/entry/data/data")),
        processing_tab=SimpleNamespace(
            dark_frame_var=Value("none"), flat_frame_var=Value("none")
        ),
        log=lambda _message: None,
    )
    try:
        monkeypatch.setattr(
            "gui.calibration_frame.filedialog.askopenfilenames",
            lambda **_kwargs: tuple(map(str, paths)),
        )
        monkeypatch.setattr(
            "gui.calibration_frame.load_image",
            lambda path, _h5_path: arrays[str(path)],
        )
        dialog = CalibrationManagerDialog(root, app, frame_type=frame_type)
        monkeypatch.setattr(dialog, "_update_preview", lambda: None)

        dialog._add_files()
        dialog.average_method_var.set(method)
        dialog._compute_average()
        np.testing.assert_allclose(dialog._averaged, expected)
        dialog._apply_and_close()

        provenance = getattr(app, f"{frame_type}_frame_provenance")
        assert provenance == {
            "mode": "combined",
            "method": method,
            "files": [str(path.resolve()) for path in paths],
        }

        report_app = _report_app(tmp_path / "input.edf")
        report_app.__dict__[f"{frame_type}_frame_provenance"] = provenance
        report = App._write_run_report(report_app, tmp_path).read_text(encoding="utf-8")
        assert "RingSentry v7.0.0" in report
        assert f'"method": "{method}"' in report
        for path in paths:
            assert json.dumps(str(path.resolve())) in report
    finally:
        root.destroy()


def test_multiframe_calibration_rejects_shape_mismatch_and_clear_or_cancel_is_safe(
    tmp_path, monkeypatch
):
    paths = [tmp_path / "calibration-1.edf", tmp_path / "calibration-2.edf"]
    for path in paths:
        path.touch()
    arrays = {
        str(paths[0]): np.ones((2, 2), dtype=np.float32),
        str(paths[1]): np.ones((3, 2), dtype=np.float32),
    }
    root = _new_hidden_root_or_skip()
    app = SimpleNamespace(
        io_tab=SimpleNamespace(h5_path_var=Value("/entry/data/data")),
        processing_tab=SimpleNamespace(
            dark_frame_var=Value("original"), flat_frame_var=Value("none")
        ),
        log=lambda _message: None,
    )
    errors = []
    try:
        monkeypatch.setattr(
            "gui.calibration_frame.filedialog.askopenfilenames",
            lambda **_kwargs: tuple(map(str, paths)),
        )
        monkeypatch.setattr(
            "gui.calibration_frame.load_image",
            lambda path, _h5_path: arrays[str(path)],
        )
        monkeypatch.setattr(
            "gui.calibration_frame.messagebox.showerror",
            lambda title, message: errors.append((title, message)),
        )
        dialog = CalibrationManagerDialog(root, app, frame_type="dark")
        monkeypatch.setattr(dialog, "_update_preview", lambda: None)

        dialog._add_files()
        dialog._compute_average()
        assert dialog._averaged is None
        assert errors and "尺寸不匹配" in errors[0][0]

        dialog._clear_all()
        assert dialog._file_paths == []
        assert dialog._arrays == []
        assert dialog._averaged is None
        dialog.destroy()  # Cancel does not apply partial calibration state.
        assert not hasattr(app, "dark_frame")
    finally:
        root.destroy()


def test_multiframe_calibration_recomputes_after_files_or_method_change(
    tmp_path, monkeypatch
):
    paths = [tmp_path / "calibration-1.edf", tmp_path / "calibration-2.edf"]
    for path in paths:
        path.touch()
    arrays = {
        str(paths[0]): np.array([[1.0, 5.0]], dtype=np.float32),
        str(paths[1]): np.array([[3.0, 1.0]], dtype=np.float32),
    }
    root = _new_hidden_root_or_skip()
    app = SimpleNamespace(
        io_tab=SimpleNamespace(h5_path_var=Value("/entry/data/data")),
        processing_tab=SimpleNamespace(
            dark_frame_var=Value("none"), flat_frame_var=Value("none")
        ),
        log=lambda _message: None,
    )
    try:
        monkeypatch.setattr(
            "gui.calibration_frame.filedialog.askopenfilenames",
            lambda **_kwargs: tuple(map(str, paths)),
        )
        monkeypatch.setattr(
            "gui.calibration_frame.load_image",
            lambda path, _h5_path: arrays[str(path)],
        )
        dialog = CalibrationManagerDialog(root, app, frame_type="dark")
        monkeypatch.setattr(dialog, "_update_preview", lambda: None)

        dialog._add_files()
        dialog._compute_average()
        np.testing.assert_array_equal(
            dialog._averaged, np.array([[2.0, 3.0]], dtype=np.float32)
        )

        dialog.average_method_var.set("median")
        assert dialog._averaged is None
        dialog._compute_average()
        np.testing.assert_array_equal(
            dialog._averaged, np.array([[2.0, 3.0]], dtype=np.float32)
        )

        dialog.file_listbox.selection_set(1)
        dialog._remove_selected()
        assert dialog._averaged is None
        dialog._apply_and_close()

        np.testing.assert_array_equal(app.dark_frame, arrays[str(paths[0])])
        assert app.dark_frame_provenance == {
            "mode": "combined",
            "method": "median",
            "files": [str(paths[0].resolve())],
        }
    finally:
        root.destroy()
