import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from core.utils import summarize_array_stats
from gui.app import (
    App,
    classify_batch_outcome,
    classify_batch_result,
    normalize_preflight_sample_count,
)


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_summarize_array_stats_keeps_nan_and_signed_infinity_distinct():
    summary = summarize_array_stats(
        np.array([[1.0, np.nan], [np.inf, -np.inf]], dtype=np.float64)
    )

    assert "finite=1/4" in summary
    assert "nan=1" in summary
    assert "posinf=1" in summary
    assert "neginf=1" in summary
    assert "nonfinite=3" in summary
    assert "min=1" in summary


def test_qc_error_with_success_is_success_but_worker_failure_is_failed():
    assert classify_batch_result(
        [
            "ERROR: sample.edf QC 图像包含异常值",
            "REVIEW: sample.edf has QC warnings",
            "SUCCESS: sample.edf [npy/PROC] -> out.npy",
        ]
    ) == "success"
    assert classify_batch_result(["FAILED: sample.edf [npy] -> write error"]) == "failed"
    assert classify_batch_result(["FAILED: worker exception -> boom"]) == "failed"
    assert classify_batch_result(["ERROR loading/processing sample.edf: bad input"]) == "failed"


def test_completion_outcome_distinguishes_success_failure_and_cancel():
    empty = {"success": 0, "failed": 0, "skipped": 0, "cancelled": 0}
    assert classify_batch_outcome({**empty, "success": 2}, 2) == "success"
    assert classify_batch_outcome({**empty, "success": 1, "failed": 1}, 2) == (
        "partial_failure"
    )
    assert classify_batch_outcome({**empty, "failed": 2}, 2) == "all_failed"
    assert classify_batch_outcome({**empty, "cancelled": 1}, 2) == "cancelled"
    assert classify_batch_outcome(empty, 2, cancellation_requested=True) == "cancelled"


def test_preflight_sample_count_uses_quality_setting_with_safety_ceiling():
    assert normalize_preflight_sample_count(7, 10) == 7
    assert normalize_preflight_sample_count(999, 999) == 20
    assert normalize_preflight_sample_count("not-a-number", 30) == 20
    assert normalize_preflight_sample_count(-1, 30) == 1
    assert normalize_preflight_sample_count(5, 0) == 0


def test_preflight_reads_quality_sample_count_and_caps_it(tmp_path, monkeypatch):
    files = [(tmp_path / f"sample-{i}.edf", Path(f"sample-{i}.edf")) for i in range(25)]
    app = SimpleNamespace(
        filelist=files,
        last_quality_reports=[],
        quality_tab=SimpleNamespace(sample_count_var=Value(7)),
        output_tab=SimpleNamespace(overwrite_var=Value(True)),
        io_tab=SimpleNamespace(h5_path_var=Value("/entry/data/data")),
        geometry_tab=SimpleNamespace(
            rotate_var=Value("0"),
            hot_pixel_enable_var=Value(False),
            hot_pixel_window_var=Value(3),
        ),
        dark_frame=None,
        flat_frame=None,
        mask_frame=None,
        log=lambda _message: None,
    )

    loaded = {
        "data": np.ones((2, 2), dtype=np.float32),
        "metadata": {},
    }
    monkeypatch.setattr("gui.app.load_image_with_info", lambda *_args: loaded)

    assert App._run_preflight_checks(
        app,
        outroot=tmp_path / "out",
        formats=[],
        roi=None,
        bin_factor=1,
        min_intensity=None,
        max_intensity=None,
    )
    assert len(app.last_quality_reports) == 7

    app.quality_tab.sample_count_var.set(999)
    assert App._run_preflight_checks(
        app,
        outroot=tmp_path / "out",
        formats=[],
        roi=None,
        bin_factor=1,
        min_intensity=None,
        max_intensity=None,
    )
    assert len(app.last_quality_reports) == 20


def test_run_report_includes_error_logs_in_manual_review(tmp_path):
    from tests.test_run_report import _report_app

    app = _report_app(tmp_path / "sample.edf")
    app.log_panel.run_log_lines = [
        "[12:00:00] ERROR: sample.edf QC warning",
        "[12:00:00] SUCCESS: sample.edf [npy/PROC] -> sample.npy",
    ]

    report = App._write_run_report(app, tmp_path).read_text(encoding="utf-8")

    manual_review = report.split("---- Manual Review Required ----", 1)[1]
    assert "ERROR: sample.edf QC warning" in manual_review


def test_run_report_excludes_logs_from_previous_run(tmp_path):
    from tests.test_run_report import _report_app

    app = _report_app(tmp_path / "sample.edf")
    app.log_panel.run_log_lines = [
        "[11:00:00] FAILED: old-run.edf [npy] -> old error",
        "[12:00:00] SUCCESS: sample.edf [npy/PROC] -> sample.npy",
    ]
    app._run_log_start_index = 1

    report = App._write_run_report(app, tmp_path).read_text(encoding="utf-8")

    assert "old-run.edf" not in report
    assert "SUCCESS: sample.edf" in report


def test_close_waits_for_delayed_batch_coordinator(monkeypatch):
    class DelayedCoordinator:
        alive = True

        def is_alive(self):
            return self.alive

    coordinator = DelayedCoordinator()
    callbacks = []
    state = {"cancelled": False, "saved": False, "destroyed": False}
    app = SimpleNamespace(
        overexposure_tab=SimpleNamespace(worker=None),
        _conversion_thread=coordinator,
        thread_pool=None,
        is_running=True,
        _close_poll_after_id=None,
        _close_requested=False,
        _pending_ui_after_ids=set(),
        _ui_callback_lock=threading.Lock(),
        after=lambda _delay, callback: callbacks.append(callback) or "close-poll",
        _save_config=lambda: state.__setitem__("saved", True),
        destroy=lambda: state.__setitem__("destroyed", True),
    )
    app._batch_is_active = lambda: App._batch_is_active(app)
    app._wait_for_batch_close = lambda: App._wait_for_batch_close(app)
    app._poll_batch_close = lambda: App._poll_batch_close(app)
    app._finish_close = lambda: App._finish_close(app)
    app.cancel_conversion = lambda: state.__setitem__("cancelled", True)
    monkeypatch.setattr("gui.app.messagebox.askyesno", lambda *_args: True)

    App._on_close(app)

    assert state == {"cancelled": True, "saved": False, "destroyed": False}
    assert len(callbacks) == 1

    coordinator.alive = False
    app.is_running = False
    callbacks[0]()

    assert state == {"cancelled": True, "saved": True, "destroyed": True}


def test_conversion_coordinator_clears_state_when_ui_callback_is_rejected(
    tmp_path, monkeypatch
):
    class Progress:
        def __setitem__(self, key, value):
            setattr(self, key, value)

    class ImmediateThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    class Future:
        def __init__(self, result):
            self._result = result

        def cancelled(self):
            return False

        def result(self):
            return self._result

    class ImmediateExecutor:
        def __init__(self, **_kwargs):
            self.futures = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def submit(self, function, args):
            future = Future(function(args))
            self.futures.append(future)
            return future

    source = tmp_path / "sample.tif"
    source.touch()
    out_dir = tmp_path / "output"

    def value(item):
        return Value(item)

    app = SimpleNamespace(
        is_running=False,
        selected_files=[str(source)],
        selected_common_root=tmp_path,
        filelist=[],
        io_tab=SimpleNamespace(
            workflow_preset_var=value("Custom"),
            input_mode_var=value("files"),
            dir_var=value(""),
            outdir_var=value(str(out_dir)),
            h5_path_var=value("/entry/data/data"),
        ),
        output_tab=SimpleNamespace(
            format_vars={"npy": value(True)},
            overwrite_var=value(False),
            lossless_matrix_var=value(True),
            xy_header=value(True),
            xy_one_based=value(False),
            xy_skip_zeros=value(True),
            xy_zero_tol=value(0.0),
            xy_y_axis_origin_var=value("top-left"),
            png_scale_var=value("linear"),
            png_min_var=value(""),
            png_max_var=value(""),
            png_colormap_var=value("viridis"),
            png_dpi_var=value(300),
        ),
        processing_tab=SimpleNamespace(
            roi_var=value(""),
            min_intensity_var=value(""),
            max_intensity_var=value(""),
            dark_frame_var=value("none"),
            flat_frame_var=value("none"),
            flat_is_dark_subtracted_var=value(False),
            mask_frame_var=value("none"),
            mask_nonzero_is_invalid_var=value(True),
            clip_negative_var=value(False),
            bg_offset_var=value(0.0),
        ),
        geometry_tab=SimpleNamespace(
            pclip_low_var=value(""),
            pclip_high_var=value(""),
            bin_factor_var=value(1),
            gamma_var=value(1.0),
            rotate_var=value("0"),
            flip_x_var=value(False),
            flip_y_var=value(False),
            intensity_transform_var=value("none"),
            norm_mode_var=value("none"),
            hot_pixel_enable_var=value(False),
            hot_pixel_window_var=value(3),
            hot_pixel_sigma_var=value(8.0),
        ),
        log_panel=SimpleNamespace(
            run_log_lines=[],
            max_thr_var=value(1),
            prog=Progress(),
            update_stats_display=lambda *_args: None,
        ),
        dark_frame=None,
        flat_frame=None,
        mask_frame=None,
        cancellation_event=threading.Event(),
        count_lock=threading.Lock(),
        thread_pool=None,
        _conversion_thread=None,
        _schedule_ui_callback=lambda _callback: False,
        _run_preflight_checks=lambda **_kwargs: True,
        _set_ui_state=lambda **_kwargs: None,
        log=lambda _message: None,
        count_files=lambda **_kwargs: setattr(
            app, "filelist", [(source, Path(source.name))]
        ),
    )
    monkeypatch.setattr("gui.app.threading.Thread", ImmediateThread)
    monkeypatch.setattr(
        "gui.app.concurrent.futures.ThreadPoolExecutor", ImmediateExecutor
    )
    monkeypatch.setattr(
        "gui.app.concurrent.futures.as_completed", lambda futures: futures
    )
    monkeypatch.setattr(
        "gui.app.process_one_file", lambda _args: ["SUCCESS: sample.tif"]
    )

    App.run_conversion(app)

    assert app.thread_pool is None
    assert app._conversion_thread is None
    assert app.is_running is False
    assert App._batch_is_active(app) is False
