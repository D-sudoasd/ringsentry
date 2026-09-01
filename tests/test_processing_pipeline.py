import unittest
from unittest.mock import patch

import numpy as np

from core.processing import apply_processing, processing_is_identity


class ProcessingPipelineTests(unittest.TestCase):
    def test_dark_frame_is_subtracted(self):
        raw = np.array([[10, 20], [30, 40]], dtype=np.float32)
        dark = np.array([[1, 2], [3, 4]], dtype=np.float32)

        out = apply_processing(raw, dark_frame=dark)

        self.assertTrue(np.array_equal(out, raw - dark))

    def test_flat_not_dark_subtracted_uses_flat_minus_dark(self):
        raw = np.array([[10, 20]], dtype=np.float32)
        dark = np.array([[1, 2]], dtype=np.float32)
        flat = np.array([[3, 6]], dtype=np.float32)

        out = apply_processing(
            raw,
            dark_frame=dark,
            flat_frame=flat,
            flat_is_dark_subtracted=False,
        )

        expected = (raw - dark) / (flat - dark)
        self.assertTrue(np.allclose(out, expected))

    def test_raw_flat_without_matching_dark_is_rejected(self):
        raw = np.array([[10, 20]], dtype=np.float32)
        flat = np.array([[2, 4]], dtype=np.float32)

        with self.assertRaisesRegex(ValueError, "必须同时提供匹配的暗场"):
            apply_processing(
                raw,
                flat_frame=flat,
                flat_is_dark_subtracted=False,
            )

    def test_flat_near_zero_denominator_becomes_nan(self):
        raw = np.array([[10, 20]], dtype=np.float32)
        flat = np.array([[0, 5]], dtype=np.float32)

        with self.assertLogs("core.processing", level="WARNING"):
            out = apply_processing(raw, flat_frame=flat)

        self.assertTrue(np.isnan(out[0, 0]))
        self.assertEqual(float(out[0, 1]), 4.0)

    def test_roi_mask_and_intensity_clipping(self):
        raw = np.arange(16, dtype=np.float32).reshape(4, 4)
        mask = np.zeros((4, 4), dtype=np.uint8)
        mask[1, 2] = 1

        out = apply_processing(
            raw,
            roi=(1, 1, 2, 2),
            mask_frame=mask,
            min_intensity=5,
            max_intensity=10,
        )

        expected = np.array([[5, np.nan], [9, 10]], dtype=np.float32)
        self.assertTrue(np.allclose(out, expected, equal_nan=True))

    def test_mask_zero_can_mean_invalid(self):
        raw = np.array([[1, 2], [3, 4]], dtype=np.float32)
        mask = np.array([[1, 0], [1, 1]], dtype=np.uint8)

        out = apply_processing(
            raw,
            mask_frame=mask,
            mask_nonzero_is_invalid=False,
        )

        expected = np.array([[1, np.nan], [3, 4]], dtype=np.float32)
        self.assertTrue(np.allclose(out, expected, equal_nan=True))

    def test_percentile_negative_transform_gamma_and_minmax(self):
        raw = np.array([[-1, 0, 1, 3]], dtype=np.float32)

        out = apply_processing(
            raw,
            pclip_low=25,
            pclip_high=100,
            intensity_transform="sqrt",
            gamma=2.0,
            norm_mode="minmax",
        )

        expected = np.array([[np.nan, 0.0, 1.0 / 3.0, 1.0]], dtype=np.float32)
        self.assertTrue(np.allclose(out, expected, atol=1e-6, equal_nan=True))

    def test_hot_pixel_suppression_replaces_isolated_spike(self):
        raw = np.ones((5, 5), dtype=np.float32)
        raw[2, 2] = 100.0

        out = apply_processing(
            raw,
            hot_pixel_enable=True,
            hot_pixel_window=3,
            hot_pixel_sigma=8.0,
        )

        self.assertEqual(float(out[2, 2]), 1.0)

    def test_rotation_flip_and_binning(self):
        raw = np.arange(16, dtype=np.float32).reshape(4, 4)

        out = apply_processing(
            raw,
            rotate_deg="90",
            flip_x=True,
            bin_factor=2,
        )

        expected = np.array([[12.5, 4.5], [10.5, 2.5]], dtype=np.float32)
        self.assertTrue(np.array_equal(out, expected))

    def test_invalid_shapes_and_parameters_raise(self):
        raw = np.ones((2, 2), dtype=np.float32)

        with self.assertRaises(ValueError):
            apply_processing(raw, dark_frame=np.ones((3, 3), dtype=np.float32))
        with self.assertRaises(ValueError):
            apply_processing(raw, roi=(0, 0, 3, 1))
        with self.assertRaises(ValueError):
            apply_processing(raw, bin_factor=0)
        with self.assertRaises(ValueError):
            apply_processing(raw, gamma=0)
        with self.assertRaises(ValueError):
            apply_processing(raw, rotate_deg="45")

    def test_processing_is_identity_empty_and_mutating_keys(self):
        self.assertTrue(processing_is_identity({}))

        mutating = (
            ("dark_frame", object()),
            ("flat_frame", object()),
            ("roi", (0, 0, 1, 1)),
            ("mask_frame", object()),
            ("clip_negative", True),
            ("bg_offset", 1.0),
            ("min_intensity", 0.0),
            ("max_intensity", 1.0),
            ("rotate_deg", "90"),
            ("flip_x", True),
            ("flip_y", True),
            ("bin_factor", 2),
            ("pclip_low", 0.0),
            ("pclip_high", 100.0),
            ("intensity_transform", "sqrt"),
            ("gamma", 2.0),
            ("norm_mode", "minmax"),
            ("hot_pixel_enable", True),
        )
        for key, value in mutating:
            with self.subTest(key=key):
                self.assertFalse(processing_is_identity({key: value}))

    def test_hot_pixel_memory_error_is_raised(self):
        raw = np.ones((5, 5), dtype=np.float32)
        raw[2, 2] = 100.0

        with patch.object(
            np.lib.stride_tricks,
            "sliding_window_view",
            side_effect=MemoryError,
        ):
            with self.assertRaises(MemoryError):
                apply_processing(raw, hot_pixel_enable=True)


if __name__ == "__main__":
    unittest.main()
