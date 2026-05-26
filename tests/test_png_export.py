import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from core.png_export import array_to_png_rgb, normalize_png_array
from core.writer import save_array


class PngExportTests(unittest.TestCase):
    def test_linear_scale_clips_to_fixed_display_range(self):
        arr = np.array([[-5.0, 0.0, 5.0, 10.0, 15.0, np.nan, np.inf]])

        norm = normalize_png_array(arr, vmin=0.0, vmax=10.0, scale="linear")

        expected = np.array([[0.0, 0.0, 0.5, 1.0, 1.0, 0.0, 0.0]], dtype=np.float32)
        self.assertTrue(np.allclose(norm, expected, equal_nan=False))

    def test_log_scale_accepts_negative_vmin_and_stays_monotonic(self):
        arr = np.array([[-5.0, -4.0, 0.0, 5.0]], dtype=np.float32)

        norm = normalize_png_array(arr, vmin=-5.0, vmax=5.0, scale="log")

        self.assertEqual(float(norm[0, 0]), 0.0)
        self.assertEqual(float(norm[0, -1]), 1.0)
        self.assertTrue(np.all(np.diff(norm[0]) >= 0))
        self.assertTrue(np.all(np.isfinite(norm)))

    def test_nonfinite_pixels_are_black_in_rgb_png_payload(self):
        arr = np.array([[0.0, np.nan, np.inf]], dtype=np.float32)

        rgb = array_to_png_rgb(arr, vmin=0.0, vmax=1.0, scale="linear")

        self.assertEqual(rgb.shape, (1, 3, 3))
        self.assertFalse(np.array_equal(rgb[0, 0], np.array([0, 0, 0], dtype=np.uint8)))
        self.assertTrue(np.array_equal(rgb[0, 1], np.array([0, 0, 0], dtype=np.uint8)))
        self.assertTrue(np.array_equal(rgb[0, 2], np.array([0, 0, 0], dtype=np.uint8)))

    def test_invalid_png_display_options_raise_clear_errors(self):
        arr = np.array([[1.0]], dtype=np.float32)

        with self.assertRaisesRegex(ValueError, "PNG I Max"):
            normalize_png_array(arr, vmin=1.0, vmax=1.0, scale="linear")
        with self.assertRaisesRegex(ValueError, "PNG Scale"):
            normalize_png_array(arr, vmin=0.0, vmax=1.0, scale="sqrt")

    def test_save_array_writes_rgb_png_with_input_pixel_size(self):
        arr = np.arange(6, dtype=np.float32).reshape(2, 3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.png"

            success, message, points = save_array(
                arr,
                path,
                "png",
                png_options={
                    "scale": "linear",
                    "vmin": "0",
                    "vmax": "5",
                    "colormap": "viridis",
                },
            )

            self.assertTrue(success, message)
            self.assertEqual(points, arr.size)
            with Image.open(path) as img:
                self.assertEqual(img.mode, "RGB")
                self.assertEqual(img.size, (3, 2))


if __name__ == "__main__":
    unittest.main()
