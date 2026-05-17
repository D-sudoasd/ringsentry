import unittest

import numpy as np

from core.quality import analyze_image_quality, assess_processing_plan


class QualityControlTests(unittest.TestCase):
    def test_quality_statistics_detect_common_risks(self):
        arr = np.ones((100, 100), dtype=np.float32)
        arr[:60, :] = 0.0
        arr[60:62, :100] = -5.0
        arr[70:71, :30] = 1000.0
        arr[0, 0] = np.nan
        arr[0, 1] = np.inf

        report = analyze_image_quality(arr, source_name="sample.tif")

        categories = {finding.category for finding in report.findings}
        self.assertIn("invalid_values", categories)
        self.assertIn("zeros", categories)
        self.assertIn("negative", categories)
        self.assertIn("hot_pixels", categories)
        self.assertTrue(report.review_required)
        self.assertEqual(report.stats["nan_count"], 1)
        self.assertEqual(report.stats["inf_count"], 1)
        self.assertGreater(report.stats["zero_ratio"], 0.5)
        self.assertGreater(report.stats["negative_ratio"], 0.01)

    def test_saturation_is_reported_for_integer_dtype(self):
        arr = np.array([[0, np.iinfo(np.uint16).max]], dtype=np.uint16)

        report = analyze_image_quality(arr)

        self.assertEqual(report.stats["saturated_high_count"], 1)
        self.assertIn(
            "saturation",
            {finding.category for finding in report.findings},
        )

    def test_suggestions_are_explainable_and_non_mutating(self):
        arr = np.ones((100, 100), dtype=np.int32)
        arr.flat[:200] = 1000
        before = arr.copy()

        report = analyze_image_quality(
            arr,
            metadata={"source_kind": "cbf", "dtype": "int32"},
        )

        self.assertTrue(np.array_equal(arr, before))
        actions = [suggestion.action for suggestion in report.suggestions]
        self.assertTrue(any("hot pixel" in action for action in actions))
        self.assertTrue(any("EDF" in action and "NPY" in action for action in actions))

    def test_processing_plan_reports_roi_binning_and_tiff_dtype_risks(self):
        report = analyze_image_quality(
            np.ones((5, 7), dtype=np.int32),
            metadata={"source_kind": "cbf", "dtype": "int32"},
        )

        findings = assess_processing_plan(
            report,
            formats=["tif"],
            roi=(1, 1, 4, 3),
            bin_factor=2,
        )
        categories = {finding.category for finding in findings}
        self.assertIn("binning", categories)
        self.assertIn("tiff_dtype", categories)

        roi_errors = assess_processing_plan(report, roi=(6, 0, 2, 2))
        self.assertIn("roi", {finding.category for finding in roi_errors})
        self.assertIn("ERROR", {finding.level for finding in roi_errors})

        bin_errors = assess_processing_plan(report, bin_factor=8)
        self.assertIn("binning", {finding.category for finding in bin_errors})
        self.assertIn("ERROR", {finding.level for finding in bin_errors})

        zero_bin = assess_processing_plan(report, bin_factor=0)
        self.assertIn("binning", {finding.category for finding in zero_bin})
        self.assertIn("ERROR", {finding.level for finding in zero_bin})


if __name__ == "__main__":
    unittest.main()
