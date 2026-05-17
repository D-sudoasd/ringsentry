import tempfile
import unittest
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

            results, summary = repair.run_batch(
                self.make_config(data_dir, repair_out),
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

            repaired_hot = read_cbf(repair_out / "hot.cbf")
            self.assertEqual(int(repaired_hot[0, 1]), 32766)
            self.assertEqual(int(repaired_hot[0, 0]), 5)
            self.assertEqual(int(repaired_hot[1, 2]), 10)
            self.assertTrue(np.array_equal(read_cbf(repair_out / "clean.cbf"), companion))

            by_name = {Path(r.input_file).name: r for r in results}
            self.assertEqual(by_name["hot.cbf"].status, "repaired_verified")
            self.assertEqual(by_name["clean.cbf"].status, "copied_unmodified")

    def test_gui_tab_module_imports(self):
        import gui.tabs.overexposure_tab as tab

        self.assertEqual(tab.IMPORT_ERROR, None)
        self.assertTrue(hasattr(tab, "OverexposureRepairTab"))


if __name__ == "__main__":
    unittest.main()
