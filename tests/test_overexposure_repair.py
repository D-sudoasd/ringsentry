import json
import os
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
from importlib.util import find_spec
from pathlib import Path

import numpy as np

from core import overexposure_repair as repair

try:
    import fabio
    from fabio.cbfimage import cbfimage
except Exception:
    fabio = None
    cbfimage = None


def write_cbf(path, data):
    cbfimage(data=np.asarray(data, dtype=np.int32)).write(str(path))


def read_cbf(path):
    return np.asarray(fabio.open(str(path)).data)


class OverexposureRepairTests(unittest.TestCase):
    def setUp(self):
        if fabio is None or cbfimage is None:
            self.skipTest("fabio is not installed")

    def make_config(self, input_dir, output_dir, *, dry_run=False):
        return repair.ProcessConfig(
            input_dir=Path(input_dir),
            output_dir=Path(output_dir),
            recursive=False,
            skip_output_dir=True,
            preserve_subfolders=False,
            suffix="",
            overwrite_output=True,
            overwrite_original=False,
            copy_unmodified=True,
            mode="all_zero",
            zero_value=0,
            replacement_value=32766,
            verify_after_write=True,
            compute_sha256=True,
            generate_html_report=True,
            workers=1,
            dry_run=dry_run,
        ).normalized()

    def test_scan_dry_run_and_repair_preserve_non_target_pixels(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data_dir = tmp / "input"
            scan_out = tmp / "scan"
            dry_out = tmp / "dry"
            repair_out = tmp / "repair"
            data_dir.mkdir()

            original = np.array([[5, 0, 7], [8, 9, 10]], dtype=np.int32)
            companion = np.array([[1, 2], [3, 4]], dtype=np.int32)
            write_cbf(data_dir / "hot.cbf", original)
            write_cbf(data_dir / "clean.cbf", companion)

            scan_results, scan_summary = repair.run_batch(
                self.make_config(data_dir, scan_out),
                action="scan",
            )
            self.assertEqual(scan_summary.total_files, 2)
            self.assertEqual(
                {Path(r.input_file).name: r.target_pixels for r in scan_results},
                {"clean.cbf": 0, "hot.cbf": 1},
            )

            dry_results, dry_summary = repair.run_batch(
                self.make_config(data_dir, dry_out, dry_run=True),
                action="repair",
            )
            self.assertEqual(dry_summary.dry_run_files, 1)
            self.assertEqual(dry_summary.copied_unmodified, 1)
            self.assertFalse((dry_out / "hot.cbf").exists())
            self.assertTrue((dry_out / "clean.cbf").exists())
            self.assertTrue(any(r.status == "dry_run" for r in dry_results))
            dry_config = json.loads(Path(dry_summary.config_path).read_text(encoding="utf-8"))
            self.assertEqual(dry_config["software"], {
                "name": "RingSentry",
                "version": "7.0.0",
                "component_name": "CBF Zero2Sat overexposure repair",
            })
            dry_html = Path(dry_summary.html_path).read_text(encoding="utf-8")
            self.assertIn("RingSentry QC Report", dry_html)
            self.assertIn("RingSentry v7.0.0", dry_html)
            self.assertIn("CBF Zero2Sat overexposure repair", dry_html)

            repair_cfg = self.make_config(data_dir, repair_out)
            results, summary = repair.run_batch(
                repair_cfg,
                action="repair",
            )
            self.assertEqual(summary.total_files, 2)
            self.assertEqual(summary.repaired, 1)
            self.assertEqual(summary.verified, 1)
            self.assertEqual(summary.total_replaced_pixels, 1)
            self.assertEqual(summary.nontarget_changed_before_write, 0)
            self.assertEqual(summary.readback_different_pixels, 0)
            self.assertTrue(Path(summary.csv_path).exists())
            self.assertTrue(Path(summary.html_path).exists())
            self.assertTrue(Path(summary.config_path).exists())

            repair_config = json.loads(Path(summary.config_path).read_text(encoding="utf-8"))
            self.assertEqual(repair_config["software"], dry_config["software"])
            validation_index_path = repair.write_validation_index_from_results(
                data_dir, repair_out, repair_cfg, results
            )
            self.assertIsNotNone(validation_index_path)
            validation_index = json.loads(validation_index_path.read_text(encoding="utf-8"))
            self.assertEqual(validation_index["app_name"], "CBF Zero2Sat Research Tool")
            self.assertEqual(validation_index["app_version"], "2.0")
            self.assertEqual(validation_index["software"], dry_config["software"])
            self.assertEqual(validation_index["schema_version"], 2)
            self.assertFalse(validation_index["trusted_for_cleanup"])
            self.assertEqual(
                validation_index["cleanup_policy"],
                "report_only_no_automatic_original_removal",
            )
            self.assertTrue(
                all(record["original_sha256"] for record in validation_index["records"])
            )
            self.assertTrue(
                all(record["output_sha256"] for record in validation_index["records"])
            )
            repair_html = Path(summary.html_path).read_text(encoding="utf-8")
            self.assertIn("RingSentry QC Report", repair_html)
            self.assertIn("RingSentry v7.0.0", repair_html)
            self.assertIn("CBF Zero2Sat overexposure repair", repair_html)

            repaired_hot = read_cbf(repair_out / "hot.cbf")
            self.assertEqual(int(repaired_hot[0, 1]), 32766)
            self.assertEqual(int(repaired_hot[0, 0]), 5)
            self.assertEqual(int(repaired_hot[1, 2]), 10)
            self.assertTrue(np.array_equal(read_cbf(repair_out / "clean.cbf"), companion))

            by_name = {Path(r.input_file).name: r for r in results}
            self.assertEqual(by_name["hot.cbf"].status, "repaired_verified")
            self.assertEqual(by_name["clean.cbf"].status, "copied_unmodified")

    def test_gui_tab_module_imports(self):
        if find_spec("tkinter") is None:
            self.skipTest("tkinter is not installed")

        import gui.tabs.overexposure_tab as tab

        self.assertEqual(tab.IMPORT_ERROR, None)
        self.assertTrue(hasattr(tab, "OverexposureRepairTab"))
        self.assertEqual(
            tab.APP_TITLE,
            "RingSentry v7.0.0 — CBF Zero2Sat overexposure repair",
        )

    def test_gui_build_config_rejects_blank_output_directory(self):
        if find_spec("tkinter") is None:
            self.skipTest("tkinter is not installed")

        import gui.tabs.overexposure_tab as tab

        class Var:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            input_dir.mkdir()
            view = object.__new__(tab.OverexposureRepairTab)
            view.input_dir = Var(str(input_dir))
            view.output_dir = Var("   ")
            view.recursive = Var(True)
            view.skip_output_dir = Var(True)
            view.preserve_subfolders = Var(True)
            view.suffix = Var("_zero2sat")
            view.overwrite_output = Var(True)
            view.copy_unmodified = Var(False)
            view.mode = Var("all_zero")
            view.zero_value = Var("0")
            view.replacement_value = Var("32766")
            view.bright_threshold = Var("20000")
            view.radius = Var("3")
            view.verify_after_write = Var(True)
            view.compute_sha256 = Var(False)
            view.generate_html_report = Var(False)
            view.workers = Var("1")
            view.dry_run = Var(True)
            view.project_name = Var("")
            view.operator = Var("")
            view.sample = Var("")
            view.beamline = Var("")
            view.detector = Var("")
            view.experiment_date = Var("")
            view.notes_text = mock.Mock()
            view.notes_text.get.return_value = ""

            with self.assertRaisesRegex(ValueError, "请指定输出文件夹"):
                view.build_config()

    def test_gui_build_config_rejects_blank_input_directory(self):
        if find_spec("tkinter") is None:
            self.skipTest("tkinter is not installed")

        import gui.tabs.overexposure_tab as tab

        class Var:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            view = object.__new__(tab.OverexposureRepairTab)
            view.input_dir = Var("   ")
            view.output_dir = Var(str(output_dir))
            view.recursive = Var(True)
            view.skip_output_dir = Var(True)
            view.preserve_subfolders = Var(True)
            view.suffix = Var("_zero2sat")
            view.overwrite_output = Var(True)
            view.copy_unmodified = Var(False)
            view.mode = Var("all_zero")
            view.zero_value = Var("0")
            view.replacement_value = Var("32766")
            view.bright_threshold = Var("20000")
            view.radius = Var("3")
            view.verify_after_write = Var(True)
            view.compute_sha256 = Var(False)
            view.generate_html_report = Var(False)
            view.workers = Var("1")
            view.dry_run = Var(True)
            view.project_name = Var("")
            view.operator = Var("")
            view.sample = Var("")
            view.beamline = Var("")
            view.detector = Var("")
            view.experiment_date = Var("")
            view.notes_text = mock.Mock()
            view.notes_text.get.return_value = ""

            with self.assertRaisesRegex(ValueError, "请指定输入文件夹"):
                view.build_config()

    def test_gui_defaults_to_dry_run(self):
        if find_spec("tkinter") is None:
            self.skipTest("tkinter is not installed")

        import tkinter as tk
        import gui.tabs.overexposure_tab as tab

        try:
            root = tk.Tk()
            root.withdraw()
        except Exception as exc:
            self.skipTest(f"Tk display is unavailable: {exc}")

        try:
            view = tab.OverexposureRepairTab(root, None)
            self.assertTrue(view.dry_run.get())
            rules = view.tab_rules.grid_slaves(row=0, column=0)[0]
            self.assertIn(
                "采集链证据",
                rules.grid_slaves(row=0, column=4)[0].cget("text"),
            )
            self.assertNotIn(
                "推荐",
                rules.grid_slaves(row=1, column=0)[0].cget("text"),
            )
            self.assertIn(
                "beamstop",
                view.tab_rules.grid_slaves(row=1, column=0)[0].cget("text"),
            )
        finally:
            root.destroy()

    def test_run_batch_honors_cancel_event_before_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data_dir = tmp / "input"
            output_dir = tmp / "out"
            data_dir.mkdir()
            write_cbf(data_dir / "hot.cbf", np.array([[0, 1], [2, 3]], dtype=np.int32))

            cancel_event = threading.Event()
            cancel_event.set()

            results, summary = repair.run_batch(
                self.make_config(data_dir, output_dir),
                action="scan",
                cancel_event=cancel_event,
            )

            self.assertEqual(results, [])
            self.assertEqual(summary.total_files, 0)

    def test_same_input_and_output_with_suffix_keeps_scan_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            input_dir.mkdir()
            source = input_dir / "sample.cbf"
            write_cbf(source, np.array([[1, 0]], dtype=np.int32))

            cfg = repair.ProcessConfig(
                input_dir=input_dir,
                output_dir=input_dir,
                recursive=True,
                skip_output_dir=True,
                preserve_subfolders=False,
                suffix="_fixed",
                overwrite_output=True,
                overwrite_original=False,
                copy_unmodified=False,
                generate_html_report=False,
            ).normalized()
            results, summary = repair.run_batch(cfg, action="scan")

            self.assertEqual(summary.total_files, 1)
            self.assertEqual([Path(result.input_file) for result in results], [source.resolve()])

    def test_same_input_and_output_skips_generated_suffix_but_keeps_standalone_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            input_dir.mkdir()
            source = input_dir / "sample.cbf"
            write_cbf(source, np.array([[1, 0]], dtype=np.int32))

            cfg = repair.ProcessConfig(
                input_dir=input_dir,
                output_dir=input_dir,
                recursive=True,
                skip_output_dir=True,
                preserve_subfolders=False,
                suffix="_fixed",
                overwrite_output=True,
                overwrite_original=False,
                copy_unmodified=False,
                generate_html_report=False,
            ).normalized()
            repair.run_batch(cfg, action="repair")
            generated = input_dir / "sample_fixed.cbf"
            self.assertTrue(generated.exists())

            standalone_source = input_dir / "original_fixed.cbf"
            write_cbf(standalone_source, np.array([[2, 3]], dtype=np.int32))

            results, summary = repair.run_batch(cfg, action="scan")

            self.assertEqual(summary.total_files, 2)
            self.assertEqual(
                {Path(result.input_file).name for result in results},
                {source.name, standalone_source.name},
            )
            self.assertNotIn(generated.resolve(), {Path(result.input_file) for result in results})

    def test_scan_skips_only_output_strict_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_dir = tmp / "input"
            input_dir.mkdir()
            write_cbf(input_dir / "source.cbf", np.array([[1, 2]], dtype=np.int32))

            output_child = input_dir / "output"
            output_child.mkdir()
            write_cbf(output_child / "generated.cbf", np.array([[3, 4]], dtype=np.int32))
            self.assertEqual(
                repair.iter_cbf_files(input_dir, output_child, recursive=True),
                [(input_dir / "source.cbf").resolve()],
            )

            output_ancestor = tmp / "ancestor"
            output_ancestor.mkdir()
            discovered = repair.iter_cbf_files(
                input_dir, output_ancestor, recursive=True
            )
            self.assertEqual(
                discovered,
                sorted(
                    [
                        (input_dir / "source.cbf").resolve(),
                        (output_child / "generated.cbf").resolve(),
                    ]
                ),
            )

    def test_preserve_subfolders_false_rejects_duplicate_output_mapping_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_dir = tmp / "input"
            first_dir = input_dir / "first"
            second_dir = input_dir / "second"
            first_dir.mkdir(parents=True)
            second_dir.mkdir()
            first_source = first_dir / "same.cbf"
            second_source = second_dir / "same.cbf"
            write_cbf(first_source, np.array([[0, 1]], dtype=np.int32))
            write_cbf(second_source, np.array([[0, 2]], dtype=np.int32))
            output_dir = tmp / "output"
            cfg = repair.ProcessConfig(
                input_dir=input_dir,
                output_dir=output_dir,
                recursive=True,
                skip_output_dir=True,
                preserve_subfolders=False,
                suffix="",
                overwrite_output=True,
                overwrite_original=False,
                copy_unmodified=True,
                workers=4,
                generate_html_report=False,
            ).normalized()

            with self.assertRaisesRegex(ValueError, "Output mapping collisions") as raised:
                repair.run_batch(cfg, action="repair")

            message = str(raised.exception)
            self.assertIn(str(first_source.resolve()), message)
            self.assertIn(str(second_source.resolve()), message)
            self.assertFalse(output_dir.exists())

    def test_config_rejects_original_file_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with self.assertRaisesRegex(ValueError, "Original CBF overwrite is disabled"):
                repair.ProcessConfig(
                    input_dir=tmp / "input",
                    output_dir=tmp / "output",
                    overwrite_original=True,
                    backup_before_overwrite=False,
                ).normalized()

    def test_readback_verification_rejects_dtype_change(self):
        original = np.array([[1, 0]], dtype=np.int32)
        expected = np.array([[1, 32766]], dtype=np.int32)
        target_mask = original == 0
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dtype-change.cbf"
            with mock.patch.object(
                repair,
                "read_image_data",
                return_value=(None, expected.astype(np.float32)),
            ):
                with self.assertRaisesRegex(ValueError, "Dtype changed"):
                    repair.validate_readback(path, expected, original, target_mask)

    def test_strict_cleanup_verification_rejects_dtype_change(self):
        original = np.array([[1, 0]], dtype=np.int32)
        repaired = np.array([[1, 32766]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.make_config(Path(tmp) / "input", Path(tmp) / "output")
            with mock.patch.object(
                repair,
                "read_image_data",
                side_effect=[(None, original), (None, repaired)],
            ):
                check = repair.verify_original_repaired_pair_with_config(
                    Path(tmp) / "original.cbf",
                    Path(tmp) / "repaired.cbf",
                    cfg,
                )
        self.assertFalse(check["pass"])
        self.assertEqual(check["reason"], "dtype_mismatch")

    def test_repair_write_uses_private_random_temporary_directory(self):
        class RecordingImage:
            def __init__(self):
                self.data = None
                self.write_path = None

            def write(self, path):
                self.write_path = Path(path)
                self.write_path.write_bytes(b"temporary-cbf")

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_dir = tmp / "input"
            output_dir = tmp / "output"
            input_dir.mkdir()
            output_dir.mkdir()
            original_path = input_dir / "source.cbf"
            original_path.write_bytes(b"original-detector-data")
            final_path = output_dir / "source.cbf"
            cfg = self.make_config(input_dir, output_dir)
            original = np.array([[1, 0]], dtype=np.int32)
            repaired = np.array([[1, 32766]], dtype=np.int32)
            target_mask = original == 0
            image = RecordingImage()

            with mock.patch.object(
                repair, "validate_readback", return_value=(0, 0)
            ):
                repair.write_repaired(
                    image,
                    repaired,
                    final_path,
                    cfg,
                    original_path,
                    original,
                    target_mask,
                )

            self.assertIsNotNone(image.write_path)
            self.assertNotEqual(image.write_path.parent, output_dir)
            self.assertEqual(image.write_path.parent.parent, output_dir)
            self.assertTrue(image.write_path.parent.name.startswith(".source.cbf.ringsentry-"))
            self.assertFalse(image.write_path.parent.exists())
            self.assertEqual(final_path.read_bytes(), b"temporary-cbf")
            self.assertEqual(original_path.read_bytes(), b"original-detector-data")

    def test_copy_unmodified_replaces_output_hardlink_without_mutating_external_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_dir = tmp / "input"
            output_dir = tmp / "output"
            input_dir.mkdir()
            output_dir.mkdir()
            source = input_dir / "clean.cbf"
            write_cbf(source, np.array([[1, 2], [3, 4]], dtype=np.int32))
            external = tmp / "external.bin"
            external.write_bytes(b"external-content-must-survive")
            output = output_dir / source.name
            os.link(external, output)

            result = repair.process_file(source, self.make_config(input_dir, output_dir))

            self.assertEqual(result.status, "copied_unmodified")
            self.assertEqual(external.read_bytes(), b"external-content-must-survive")
            self.assertEqual(output.read_bytes(), source.read_bytes())

    def test_copy_from_scan_replaces_output_hardlink_without_mutating_external_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_dir = tmp / "input"
            output_dir = tmp / "output"
            input_dir.mkdir()
            output_dir.mkdir()
            source = input_dir / "clean.cbf"
            write_cbf(source, np.array([[5, 6], [7, 8]], dtype=np.int32))
            cfg = self.make_config(input_dir, output_dir)
            scan_result = repair.scan_file(source, cfg)
            external = tmp / "external.bin"
            external.write_bytes(b"second-external-content-must-survive")
            output = output_dir / source.name
            os.link(external, output)

            result = repair.copy_unmodified_from_scan_result(source, cfg, scan_result)

            self.assertEqual(result.status, "copied_unmodified")
            self.assertEqual(
                external.read_bytes(), b"second-external-content-must-survive"
            )
            self.assertEqual(output.read_bytes(), source.read_bytes())

    def test_recursive_discovery_does_not_enter_reparse_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_dir = tmp / "input"
            output_dir = tmp / "output"
            linked_dir = input_dir / "junction"
            input_dir.mkdir()
            linked_dir.mkdir()
            visible = input_dir / "visible.cbf"
            hidden = linked_dir / "outside.cbf"
            write_cbf(visible, np.array([[1, 2]], dtype=np.int32))
            write_cbf(hidden, np.array([[3, 4]], dtype=np.int32))

            with mock.patch.object(
                repair,
                "is_windows_reparse_point",
                side_effect=lambda path: Path(path) == linked_dir,
            ):
                discovered = repair.iter_cbf_files(
                    input_dir, output_dir, recursive=True
                )

            self.assertEqual(discovered, [visible.resolve()])

    def test_data_dir_discovery_prunes_real_junction_or_reparse_mock(self):
        """A junction to a sibling must never make outside CBFs discoverable."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            root.mkdir()
            visible = root / "visible"
            visible.mkdir()
            write_cbf(visible / "inside.cbf", np.array([[1, 2]], dtype=np.int32))
            second_visible = root / "second-visible"
            second_visible.mkdir()
            write_cbf(
                second_visible / "inside-too.cbf",
                np.array([[7, 8]], dtype=np.int32),
            )

            outside = tmp / "outside"
            outside.mkdir()
            write_cbf(outside / "outside.cbf", np.array([[3, 4]], dtype=np.int32))
            (outside / repair.AUTO_OUTPUT_DIR_NAME).mkdir()
            write_cbf(
                outside / repair.AUTO_OUTPUT_DIR_NAME / "outside_corrected.cbf",
                np.array([[5, 6]], dtype=np.int32),
            )

            junction = root / "junction"
            junction_created = False
            if os.name == "nt":
                completed = subprocess.run(
                    ["cmd.exe", "/c", "mklink", "/J", str(junction), str(outside)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                junction_created = completed.returncode == 0 and junction.is_dir()
            if not junction_created:
                junction.mkdir()

            context = mock.patch.object(
                repair,
                "is_windows_reparse_point",
                side_effect=lambda path: Path(path) == junction,
            ) if not junction_created else mock.patch.object(
                repair, "is_windows_reparse_point", wraps=repair.is_windows_reparse_point
            )
            with context:
                discovered = repair.discover_cbf_data_dirs(root)
                corrected = repair.discover_cbf_data_dirs_with_corrected_parents(root)

            expected = sorted([visible.resolve(), second_visible.resolve()])
            self.assertEqual(discovered, expected)
            self.assertEqual(corrected, expected)

    def test_data_dir_discovery_rejects_reparse_root_before_resolving(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            outside = tmp / "outside"
            outside.mkdir()
            root = tmp / "root"
            root.mkdir()
            with mock.patch.object(
                repair,
                "is_windows_reparse_point",
                side_effect=lambda path: Path(path) == root,
            ):
                with self.assertRaisesRegex(ValueError, "Discovery root"):
                    repair.discover_cbf_data_dirs(root)
                with self.assertRaisesRegex(ValueError, "Discovery root"):
                    repair.discover_cbf_data_dirs_with_corrected_parents(root)

    def test_output_path_rejects_reparse_output_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_dir = tmp / "input"
            output_dir = tmp / "output"
            input_dir.mkdir()
            output_dir.mkdir()
            source = input_dir / "source.cbf"
            write_cbf(source, np.array([[1, 2]], dtype=np.int32))
            cfg = self.make_config(input_dir, output_dir)

            with mock.patch.object(
                repair,
                "is_windows_reparse_point",
                side_effect=lambda path: Path(path).resolve() == output_dir.resolve(),
            ):
                with self.assertRaisesRegex(ValueError, "reparse-point"):
                    repair.output_path_for(source, cfg)

    def test_validation_index_rejects_same_stat_content_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data_dir = tmp / "input"
            output_dir = tmp / "output"
            data_dir.mkdir()
            write_cbf(data_dir / "hot.cbf", np.array([[1, 0], [2, 3]], dtype=np.int32))
            cfg = self.make_config(data_dir, output_dir)
            results, _summary = repair.run_batch(cfg, action="repair")
            repair.write_validation_index_from_results(
                data_dir,
                output_dir,
                cfg,
                results,
            )

            output_path = output_dir / "hot.cbf"
            stat_before = output_path.stat()
            payload = bytearray(output_path.read_bytes())
            payload[-1] ^= 1
            output_path.write_bytes(payload)
            output_path.touch()
            import os
            os.utime(
                output_path,
                ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns),
            )
            self.assertEqual(output_path.stat().st_size, stat_before.st_size)
            self.assertEqual(output_path.stat().st_mtime_ns, stat_before.st_mtime_ns)

            ok, status, _message, _meta = repair.evaluate_validation_index_fast_path(
                data_dir,
                output_dir,
                cfg,
                {"hot.cbf": data_dir / "hot.cbf"},
                {"hot.cbf": output_path},
            )
            self.assertFalse(ok)
            self.assertEqual(status, "output_hash_mismatch")

    def test_validation_index_rejects_unverified_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data_dir = tmp / "input"
            output_dir = tmp / "output"
            data_dir.mkdir()
            write_cbf(data_dir / "hot.cbf", np.array([[1, 0]], dtype=np.int32))
            cfg = self.make_config(data_dir, output_dir)
            results, _summary = repair.run_batch(cfg, action="repair")
            index_path = repair.write_validation_index_from_results(
                data_dir,
                output_dir,
                cfg,
                results,
            )
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["records"][0]["readback_validation_passed"] = False
            index_path.write_text(json.dumps(index), encoding="utf-8")

            ok, status, _message, _meta = repair.evaluate_validation_index_fast_path(
                data_dir,
                output_dir,
                cfg,
                {"hot.cbf": data_dir / "hot.cbf"},
                {"hot.cbf": output_dir / "hot.cbf"},
            )
            self.assertFalse(ok)
            self.assertEqual(status, "record_validation_failed")

    def test_validation_index_rejects_malformed_record_fields_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data_dir = tmp / "input"
            output_dir = tmp / "output"
            data_dir.mkdir()
            write_cbf(data_dir / "hot.cbf", np.array([[1, 0]], dtype=np.int32))
            cfg = self.make_config(data_dir, output_dir)
            results, _summary = repair.run_batch(cfg, action="repair")
            index_path = repair.write_validation_index_from_results(
                data_dir,
                output_dir,
                cfg,
                results,
            )
            base_index = json.loads(index_path.read_text(encoding="utf-8"))
            mutations = {
                "name_is_array": lambda index: index["records"][0].__setitem__(
                    "output_name", []
                ),
                "size_is_null": lambda index: index["records"][0].__setitem__(
                    "output_size_bytes", None
                ),
                "count_is_string": lambda index: index["records"][0].__setitem__(
                    "target_pixels", "one"
                ),
                "record_is_null": lambda index: index.__setitem__("records", [None]),
            }

            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    index = json.loads(json.dumps(base_index))
                    mutate(index)
                    index_path.write_text(json.dumps(index), encoding="utf-8")
                    ok, status, message, _meta = (
                        repair.evaluate_validation_index_fast_path(
                            data_dir,
                            output_dir,
                            cfg,
                            {"hot.cbf": data_dir / "hot.cbf"},
                            {"hot.cbf": output_dir / "hot.cbf"},
                        )
                    )
                    self.assertFalse(ok)
                    self.assertEqual(status, "record_schema_error")
                    self.assertIn("Validation-index", message)

    def test_validation_index_writer_rejects_malformed_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data_dir = tmp / "input"
            output_dir = tmp / "output"
            data_dir.mkdir()
            cfg = self.make_config(data_dir, output_dir)

            with self.assertRaisesRegex(ValueError, "record 1 must be a JSON object"):
                repair.write_validation_index(
                    data_dir,
                    output_dir,
                    cfg,
                    [None],
                    validation_mode="test",
                    trusted_for_cleanup=True,
                )
            self.assertFalse(output_dir.exists())

    def test_cleanup_refuses_file_added_after_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data_dir = tmp / "input"
            output_dir = data_dir / repair.AUTO_OUTPUT_DIR_NAME
            data_dir.mkdir()
            write_cbf(data_dir / "hot.cbf", np.array([[1, 0]], dtype=np.int32))
            cfg = self.make_config(data_dir, output_dir)
            results, _summary = repair.run_batch(cfg, action="repair")
            repair.write_validation_index_from_results(
                data_dir, output_dir, cfg, results
            )
            evaluation = repair.evaluate_corrected_output(data_dir, output_dir, cfg)
            self.assertEqual(evaluation.status, "valid_corrected_output")

            late_path = data_dir / "late.cbf"
            write_cbf(late_path, np.array([[5, 6]], dtype=np.int32))
            deleted_files, deleted_bytes, error = repair.delete_direct_original_cbfs(
                data_dir, evaluation.cleanup_manifest
            )
            self.assertEqual((deleted_files, deleted_bytes), (0, 0))
            self.assertIn("Automatic original CBF removal is disabled", error)
            self.assertTrue((data_dir / "hot.cbf").exists())
            self.assertTrue(late_path.exists())

    def test_cleanup_refuses_content_replaced_after_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data_dir = tmp / "input"
            output_dir = data_dir / repair.AUTO_OUTPUT_DIR_NAME
            data_dir.mkdir()
            original_path = data_dir / "hot.cbf"
            write_cbf(original_path, np.array([[1, 0]], dtype=np.int32))
            cfg = self.make_config(data_dir, output_dir)
            results, _summary = repair.run_batch(cfg, action="repair")
            repair.write_validation_index_from_results(
                data_dir, output_dir, cfg, results
            )
            evaluation = repair.evaluate_corrected_output(data_dir, output_dir, cfg)
            self.assertEqual(evaluation.status, "valid_corrected_output")

            original_path.write_bytes(b"x" * original_path.stat().st_size)
            deleted_files, deleted_bytes, error = repair.delete_direct_original_cbfs(
                data_dir, evaluation.cleanup_manifest
            )
            self.assertEqual((deleted_files, deleted_bytes), (0, 0))
            self.assertIn("Automatic original CBF removal is disabled", error)
            self.assertTrue(original_path.exists())

    def test_automatic_original_cleanup_is_disabled_even_for_valid_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data_dir = tmp / "input"
            output_dir = data_dir / repair.AUTO_OUTPUT_DIR_NAME
            data_dir.mkdir()
            original_path = data_dir / "hot.cbf"
            write_cbf(original_path, np.array([[1, 0]], dtype=np.int32))
            cfg = self.make_config(data_dir, output_dir)
            results, _summary = repair.run_batch(cfg, action="repair")
            repair.write_validation_index_from_results(
                data_dir, output_dir, cfg, results
            )
            evaluation = repair.evaluate_corrected_output(data_dir, output_dir, cfg)
            self.assertEqual(evaluation.status, "valid_corrected_output")

            deleted_files, deleted_bytes, error = repair.delete_direct_original_cbfs(
                data_dir, evaluation.cleanup_manifest
            )
            self.assertEqual((deleted_files, deleted_bytes), (0, 0))
            self.assertIn("Automatic original CBF removal is disabled", error)
            self.assertTrue(original_path.exists())

            cleanup_results, _ = repair.cleanup_corrected_original_cbfs(
                data_dir,
                cfg,
                delete_original=True,
            )
            self.assertEqual(cleanup_results[0].action, "report_only")
            self.assertEqual(cleanup_results[0].status, "cleanup_disabled")
            self.assertEqual(cleanup_results[0].files_deleted, 0)
            self.assertTrue(original_path.exists())

    def test_auto_output_cleaner_rejects_source_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "input"
            data_dir.mkdir()
            original_path = data_dir / "original.cbf"
            write_cbf(original_path, np.array([[1, 0]], dtype=np.int32))

            with self.assertRaisesRegex(ValueError, "not named"):
                repair.clean_auto_output_dir(data_dir, data_dir.parent)

            self.assertTrue(original_path.exists())

    def test_auto_output_cleaner_rejects_windows_reparse_point_before_resolving(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "input"
            output_dir = source_dir / repair.AUTO_OUTPUT_DIR_NAME
            output_dir.mkdir(parents=True)
            generated_cbf = output_dir / "repaired.cbf"
            write_cbf(generated_cbf, np.array([[1, 2]], dtype=np.int32))

            with mock.patch.object(
                repair,
                "is_windows_reparse_point",
                side_effect=lambda path: Path(path) == output_dir,
            ) as reparse_check:
                with self.assertRaisesRegex(ValueError, "reparse-point"):
                    repair.clean_auto_output_dir(output_dir, source_dir)

            reparse_check.assert_any_call(output_dir)
            self.assertTrue(generated_cbf.exists())

    def test_auto_output_cleaner_is_report_only_and_retains_all_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / repair.AUTO_OUTPUT_DIR_NAME
            output_dir.mkdir()
            generated_cbf = output_dir / "repaired.cbf"
            generated_report = output_dir / "cbf_zero2sat_report.csv"
            unrelated = output_dir / "notes.txt"
            write_cbf(generated_cbf, np.array([[1, 2]], dtype=np.int32))
            generated_report.write_text("generated", encoding="utf-8")
            unrelated.write_text("retain", encoding="utf-8")

            repair.clean_auto_output_dir(output_dir, output_dir.parent)

            self.assertTrue(generated_cbf.exists())
            self.assertTrue(generated_report.exists())
            self.assertTrue(unrelated.exists())

    def test_auto_output_cleaner_requires_source_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / repair.AUTO_OUTPUT_DIR_NAME
            output_dir.mkdir()
            generated_cbf = output_dir / "repaired.cbf"
            write_cbf(generated_cbf, np.array([[1, 2]], dtype=np.int32))

            with self.assertRaisesRegex(ValueError, "Source directory is required"):
                repair.clean_auto_output_dir(output_dir)

            self.assertTrue(generated_cbf.exists())

    def test_auto_output_cleaner_rejects_missing_wrongly_named_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp)
            wrong_output = source_dir / "wrong-name"

            with self.assertRaisesRegex(ValueError, "not named"):
                repair.clean_auto_output_dir(wrong_output, source_dir)

            self.assertFalse(wrong_output.exists())

    def test_duplicate_quarantine_api_is_report_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "input"
            data_dir.mkdir()
            original = data_dir / "sample.cbf"
            duplicate = data_dir / "sample (1).cbf"
            write_cbf(original, np.array([[1, 2]], dtype=np.int32))
            duplicate.write_bytes(original.read_bytes())

            scanned = repair.scan_cbf_dir_for_duplicate_downloads(data_dir)
            self.assertEqual(scanned[0].status, "duplicate_confirmed")
            self.assertEqual(scanned[0].action, "report_only")
            reported, _summary = repair.quarantine_duplicate_cbf_downloads(
                data_dir, scan_results=scanned
            )

            self.assertEqual(reported[0].action, "report_only")
            self.assertTrue(original.exists())
            self.assertTrue(duplicate.exists())
            self.assertFalse((data_dir / repair.DUPLICATE_QUARANTINE_DIR_NAME).exists())

    def test_duplicate_report_api_does_not_create_missing_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_root = Path(tmp) / "missing"

            with self.assertRaisesRegex(ValueError, "existing directory"):
                repair.quarantine_duplicate_cbf_downloads(
                    missing_root, scan_results=[]
                )

            self.assertFalse(missing_root.exists())


if __name__ == "__main__":
    unittest.main()
