import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import tifffile

from core.edf_io import write_edf
from core.output_safety import (
    UnsafeOutputPathError,
    ensure_output_directory,
    plan_output_paths,
    release_output_reservation,
    reserve_output_path,
)
from core import worker as worker_module
from core.worker import process_one_file
from core.writer import save_array


class OutputPlanningTests(unittest.TestCase):
    def test_single_input_keeps_legacy_output_name(self):
        root = Path("out")
        source = Path("sample.edf")

        plan = plan_output_paths(
            [(source, Path("sample.edf"))], root, ["npy"]
        )

        self.assertEqual(
            plan.path_for(source, "npy"),
            root / "npy" / "sample.npy",
        )

    def test_same_stem_inputs_get_source_specific_names(self):
        root = Path("out")
        edf = Path("sample.edf")
        tif = Path("sample.tif")

        plan = plan_output_paths(
            [(edf, Path("sample.edf")), (tif, Path("sample.tif"))],
            root,
            ["npy", "csv"],
        )

        self.assertEqual(
            plan.path_for(edf, "npy"),
            root / "npy" / "sample__edf.npy",
        )
        self.assertEqual(
            plan.path_for(tif, "npy"),
            root / "npy" / "sample__tif.npy",
        )
        self.assertNotEqual(
            plan.path_for(edf, "csv"), plan.path_for(tif, "csv")
        )

    def test_each_format_is_globally_unique_when_a_generated_name_is_a_real_stem(self):
        root = Path("out")
        edf = Path("sample.edf")
        tif = Path("sample.tif")
        already_tagged = Path("sample__edf.edf")

        plan = plan_output_paths(
            [
                (edf, Path(edf.name)),
                (tif, Path(tif.name)),
                (already_tagged, Path(already_tagged.name)),
            ],
            root,
            ["npy"],
        )

        planned = [
            plan.path_for(source, "npy")
            for source in (edf, tif, already_tagged)
        ]
        self.assertEqual(
            len({path.name.casefold() for path in planned}),
            len(planned),
        )
        self.assertEqual(
            plan.path_for(already_tagged, "npy"),
            root / "npy" / "sample__edf.npy",
        )


class OutputDirectorySafetyTests(unittest.TestCase):
    def test_format_symlink_outside_output_root_is_rejected(self):
        with self.subTest("symlink"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                root = tmp / "out"
                outside = tmp / "outside"
                root.mkdir()
                outside.mkdir()
                fmt_dir = root / "npy"
                try:
                    fmt_dir.symlink_to(outside, target_is_directory=True)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"symlink creation unavailable: {exc}")

                with self.assertRaises(UnsafeOutputPathError):
                    ensure_output_directory(root, Path("."), "npy")


class AtomicWriterTests(unittest.TestCase):
    def test_cancelled_write_preserves_existing_output_and_cleans_temp(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            output = tmp / "sample.csv"
            original = b"keep this output\n"
            output.write_bytes(original)
            event = threading.Event()
            event.set()

            success, message, points = save_array(
                np.ones((2, 2), dtype=np.float32),
                output,
                "csv",
                cancellation_event=event,
            )

            self.assertFalse(success)
            self.assertIn("cancel", message.lower())
            self.assertEqual(points, 0)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(
                list(output.parent.glob(f".{output.name}.*")), []
            )

    def test_npy_without_extension_publishes_sample_npy_without_residue(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            output_without_extension = tmp / "sample"

            success, message, points = save_array(
                np.arange(4, dtype=np.float32).reshape(2, 2),
                output_without_extension,
                "npy",
            )

            output = tmp / "sample.npy"
            self.assertTrue(success, message)
            self.assertEqual(points, 4)
            self.assertFalse(output_without_extension.exists())
            np.testing.assert_array_equal(np.load(output), [[0, 1], [2, 3]])
            self.assertEqual(list(tmp.glob(".sample*")), [])


class WorkerOutputSafetyTests(unittest.TestCase):
    @staticmethod
    def _xy_options():
        return {
            "header": True,
            "one_based": False,
            "skip_zeros": False,
            "zero_tol": 0.0,
            "y_axis_origin": "top-left",
        }

    @staticmethod
    def _processing_options():
        return {"roi": None, "bin_factor": 1, "lossless_matrix": True}

    def _worker_args(
        self,
        source,
        output_root,
        event,
        overwrite=True,
        formats=None,
    ):
        return (
            source,
            Path(source.name),
            source.parent,
            output_root,
            formats or ["npy"],
            self._xy_options(),
            "/entry/data/data",
            self._processing_options(),
            event,
            overwrite,
        )

    def _assert_reservation_released(self, canonical, source, probe_source):
        probe = reserve_output_path(canonical, probe_source)
        try:
            self.assertEqual(probe, canonical)
        finally:
            release_output_reservation(probe, probe_source)

    def test_no_plan_worker_releases_reservation_for_all_terminal_outcomes(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            success_source = tmp / "success.tif"
            tifffile.imwrite(success_source, np.ones((2, 2), dtype=np.float32))
            success_root = tmp / "success-out"
            success_event = threading.Event()
            success_logs = process_one_file(
                self._worker_args(success_source, success_root, success_event)
            )
            self.assertTrue(any(line.startswith("SUCCESS:") for line in success_logs))
            self._assert_reservation_released(
                success_root / "npy" / "success.npy",
                success_source,
                tmp / "success-probe.tif",
            )

            skip_source = tmp / "skip.tif"
            tifffile.imwrite(skip_source, np.ones((2, 2), dtype=np.float32))
            skip_root = tmp / "skip-out"
            (skip_root / "npy").mkdir(parents=True)
            (skip_root / "npy" / "skip.npy").write_bytes(b"existing")
            skip_logs = process_one_file(
                self._worker_args(skip_source, skip_root, threading.Event(), False)
            )
            self.assertTrue(any(line.startswith("SKIPPED:") for line in skip_logs))
            self._assert_reservation_released(
                skip_root / "npy" / "skip.npy",
                skip_source,
                tmp / "skip-probe.tif",
            )

            cancelled_source = tmp / "cancelled.tif"
            tifffile.imwrite(cancelled_source, np.ones((2, 2), dtype=np.float32))
            cancelled_root = tmp / "cancelled-out"
            cancelled_event = threading.Event()

            def cancel_during_write(*_args, **_kwargs):
                cancelled_event.set()
                return False, "CANCELLED during write", 0

            with patch.object(worker_module, "save_array", cancel_during_write):
                cancelled_logs = process_one_file(
                    self._worker_args(
                        cancelled_source, cancelled_root, cancelled_event
                    )
                )
            self.assertTrue(
                any(line.startswith("CANCELLED") for line in cancelled_logs)
            )
            self._assert_reservation_released(
                cancelled_root / "npy" / "cancelled.npy",
                cancelled_source,
                tmp / "cancelled-probe.tif",
            )

            failed_source = tmp / "failed.tif"
            tifffile.imwrite(failed_source, np.ones((2, 2), dtype=np.float32))
            failed_root = tmp / "failed-out"

            def fail_write(*_args, **_kwargs):
                return False, "write failed", 0

            with patch.object(worker_module, "save_array", fail_write):
                failed_logs = process_one_file(
                    self._worker_args(failed_source, failed_root, threading.Event())
                )
            self.assertTrue(any(line.startswith("FAILED:") for line in failed_logs))
            self._assert_reservation_released(
                failed_root / "npy" / "failed.npy",
                failed_source,
                tmp / "failed-probe.tif",
            )

    def test_success_remains_success_when_cancelled_after_atomic_publish(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "after-publish.tif"
            output_root = tmp / "out"
            tifffile.imwrite(source, np.ones((2, 2), dtype=np.float32))
            event = threading.Event()

            def publish_then_cancel(*args, **kwargs):
                result = save_array(*args, **kwargs)
                event.set()
                return result

            with patch.object(worker_module, "save_array", publish_then_cancel):
                logs = process_one_file(
                    self._worker_args(source, output_root, event)
                )

            self.assertTrue(any(line.startswith("SUCCESS:") for line in logs), logs)
            self.assertFalse(any(line.startswith("CANCELLED") for line in logs), logs)
            self.assertTrue((output_root / "npy" / "after-publish.npy").exists())

    def test_worker_reserves_a_distinct_name_for_same_stem_inputs(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            output_root = tmp / "out"
            values = np.arange(4, dtype=np.float32).reshape(2, 2)
            write_edf(values, tmp / "sample.edf")
            tifffile.imwrite(tmp / "sample.tif", values)

            for name in ("sample.edf", "sample.tif"):
                logs = process_one_file(
                    (
                        tmp / name,
                        Path(name),
                        tmp,
                        output_root,
                        ["npy"],
                        self._xy_options(),
                        "/entry/data/data",
                        self._processing_options(),
                        threading.Event(),
                        True,
                    )
                )
                self.assertFalse(
                    [line for line in logs if line.startswith(("ERROR", "FAILED"))],
                    logs,
                )

            self.assertTrue((output_root / "npy" / "sample.npy").exists())
            self.assertTrue(
                (output_root / "npy" / "sample__tif.npy").exists()
            )

class AtomicWriterFailureTests(unittest.TestCase):
    def test_failed_write_preserves_existing_output_and_cleans_temp(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            output = tmp / "sample.npy"
            original = b"keep this output"
            output.write_bytes(original)

            success, _message, points = save_array(
                np.ones((2, 2), dtype=np.float32), output, "unsupported"
            )

            self.assertFalse(success)
            self.assertEqual(points, 0)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(
                list(output.parent.glob(f".{output.name}.*")), []
            )

    def test_successful_write_atomically_publishes_without_temp_file(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            output = tmp / "sample.npy"

            success, message, points = save_array(
                np.arange(4, dtype=np.float32).reshape(2, 2),
                output,
                "npy",
            )

            self.assertTrue(success, message)
            self.assertEqual(points, 4)
            np.testing.assert_array_equal(np.load(output), [[0, 1], [2, 3]])
            self.assertEqual(
                list(output.parent.glob(f".{output.name}.*")), []
            )


if __name__ == "__main__":
    unittest.main()
