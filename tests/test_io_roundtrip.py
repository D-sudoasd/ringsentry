import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
import tifffile

from core.edf_io import read_edf, write_edf
from core.worker import process_one_file
from core.writer import save_array

try:
    import fabio
    from fabio.cbfimage import cbfimage
    from fabio.edfimage import edfimage
except Exception:
    fabio = None
    cbfimage = None
    edfimage = None


class DetectorIORoundTripTests(unittest.TestCase):
    def test_edf_writer_is_readable_by_fabio(self):
        if fabio is None:
            self.skipTest("fabio is not installed")

        arr = (np.arange(12, dtype=np.int32).reshape(3, 4) - 5) * 100
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.edf"
            write_edf(arr, path, header_extra={"OriginalKind": "cbf"})

            raw = path.read_bytes()
            self.assertIn(b"EDF_HeaderSize", raw[:512])
            self.assertIn(b"EDF_BinarySize", raw[:512])

            own = read_edf(path)
            self.assertTrue(np.array_equal(own, arr))

            ext = fabio.open(str(path)).data
            self.assertEqual(ext.dtype, np.dtype(np.int32))
            self.assertTrue(np.array_equal(ext, arr))

    def test_edf_reader_handles_fabio_512_byte_header(self):
        if edfimage is None:
            self.skipTest("fabio is not installed")

        arr = np.arange(20, dtype=np.uint16).reshape(4, 5)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fabio.edf"
            edfimage(data=arr).write(str(path))

            loaded = read_edf(path)
            self.assertEqual(loaded.dtype, np.dtype(np.uint16))
            self.assertTrue(np.array_equal(loaded, arr))

    def test_edf_reader_handles_legacy_1024_byte_header_without_size_field(self):
        arr = (np.arange(12, dtype="<i4").reshape(3, 4) - 6) * 10
        header = "\n".join(
            [
                "{",
                "HeaderID = EH:000001:000000:000000 ;",
                "Image = 1 ;",
                "ByteOrder = LowByteFirst ;",
                "DataType = SignedInteger ;",
                "Dim_1 = 4 ;",
                "Dim_2 = 3 ;",
                f"Size = {arr.nbytes} ;",
                "}",
                "",
            ]
        ).encode("ascii")
        header = header + (b" " * (1024 - len(header)))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.edf"
            path.write_bytes(header + arr.tobytes(order="C"))

            loaded = read_edf(path)
            self.assertEqual(loaded.dtype, np.dtype(np.int32))
            self.assertTrue(np.array_equal(loaded, arr))

    def test_cbf_int32_tiff_export_uses_compatible_dtype(self):
        arr = np.array(
            [[0, 70000, 1234567], [10, 20, 30]],
            dtype=np.int32,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.tif"
            success, message, points = save_array(
                arr,
                path,
                "tif",
                preserve_dtype=True,
                metadata={"OriginalKind": "cbf", "OriginalDType": "int32"},
            )

            self.assertTrue(success, message)
            self.assertEqual(points, arr.size)
            self.assertIn("int32 -> float32", message)
            loaded = tifffile.imread(path)
            self.assertEqual(loaded.dtype, np.dtype(np.float32))
            self.assertTrue(np.array_equal(loaded, arr.astype(np.float32)))

    def test_cbf_int32_tiff_export_reports_precision_risk(self):
        arr = np.array([[0, 16777217]], dtype=np.int32)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.tif"
            with self.assertLogs("core.writer", level="WARNING"):
                success, message, _ = save_array(
                    arr,
                    path,
                    "tif",
                    preserve_dtype=True,
                    metadata={"OriginalKind": "cbf", "OriginalDType": "int32"},
                )

            self.assertTrue(success, message)
            self.assertIn("exact integer range", message)
            loaded = tifffile.imread(path)
            self.assertEqual(loaded.dtype, np.dtype(np.float32))

    def test_worker_cbf_to_edf_tiff_npy_outputs_round_trip(self):
        if fabio is None or cbfimage is None:
            self.skipTest("fabio is not installed")

        arr = np.array(
            [[0, 1, 2, 70000], [10, 20, 30, 1234567]],
            dtype=np.int32,
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_dir = tmp / "input"
            output_dir = tmp / "out"
            input_dir.mkdir()
            source = input_dir / "sample.cbf"
            cbfimage(data=arr).write(str(source))

            xy_opts = {
                "header": True,
                "one_based": False,
                "skip_zeros": False,
                "zero_tol": 0.0,
                "y_axis_origin": "top-left",
            }
            proc_opts = {
                "dark_frame": None,
                "flat_frame": None,
                "flat_is_dark_subtracted": True,
                "roi": None,
                "mask_frame": None,
                "mask_nonzero_is_invalid": True,
                "clip_negative": False,
                "bg_offset": 0.0,
                "min_intensity": None,
                "max_intensity": None,
                "rotate_deg": "0",
                "flip_x": False,
                "flip_y": False,
                "bin_factor": 1,
                "pclip_low": None,
                "pclip_high": None,
                "intensity_transform": "none",
                "gamma": 1.0,
                "norm_mode": "none",
                "hot_pixel_enable": False,
                "hot_pixel_window": 3,
                "hot_pixel_sigma": 8.0,
                "lossless_matrix": True,
            }

            logs = process_one_file(
                (
                    source,
                    Path("sample.cbf"),
                    input_dir,
                    output_dir,
                    ["edf", "tif", "npy", "xycsv"],
                    xy_opts,
                    "/entry/data/data",
                    proc_opts,
                    threading.Event(),
                    True,
                )
            )

            self.assertFalse(
                [line for line in logs if line.startswith(("ERROR", "FAILED"))]
            )
            self.assertTrue(
                any("TIFF CBF compatibility cast" in line for line in logs)
            )

            edf_back = fabio.open(str(output_dir / "edf" / "sample.edf")).data
            tif_back = tifffile.imread(output_dir / "tif" / "sample.tif")
            npy_back = np.load(output_dir / "npy" / "sample.npy")

            self.assertTrue(np.array_equal(edf_back, arr))
            self.assertTrue(np.array_equal(tif_back, arr.astype(np.float32)))
            self.assertTrue(np.array_equal(npy_back, arr))

    def test_worker_reports_binning_edge_crop(self):
        arr = np.arange(15, dtype=np.uint16).reshape(3, 5)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "input.tif"
            output_dir = tmp / "out"
            tifffile.imwrite(source, arr)

            xy_opts = {
                "header": True,
                "one_based": False,
                "skip_zeros": False,
                "zero_tol": 0.0,
                "y_axis_origin": "top-left",
            }
            proc_opts = {
                "dark_frame": None,
                "flat_frame": None,
                "flat_is_dark_subtracted": True,
                "roi": None,
                "mask_frame": None,
                "mask_nonzero_is_invalid": True,
                "clip_negative": False,
                "bg_offset": 0.0,
                "min_intensity": None,
                "max_intensity": None,
                "rotate_deg": "0",
                "flip_x": False,
                "flip_y": False,
                "bin_factor": 2,
                "pclip_low": None,
                "pclip_high": None,
                "intensity_transform": "none",
                "gamma": 1.0,
                "norm_mode": "none",
                "hot_pixel_enable": False,
                "hot_pixel_window": 3,
                "hot_pixel_sigma": 8.0,
                "lossless_matrix": True,
            }

            logs = process_one_file(
                (
                    source,
                    Path("input.tif"),
                    tmp,
                    output_dir,
                    ["npy"],
                    xy_opts,
                    "/entry/data/data",
                    proc_opts,
                    threading.Event(),
                    True,
                )
            )

            self.assertTrue(any("will crop 1 rows and 1 cols" in line for line in logs))
            loaded = np.load(output_dir / "npy" / "input.npy")
            expected = np.array([[3.0, 5.0]], dtype=np.float32)
            self.assertTrue(np.array_equal(loaded, expected))

    def test_worker_png_export_uses_processed_array_size_and_proc_mode(self):
        arr = np.arange(16, dtype=np.uint16).reshape(4, 4)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "sample.tif"
            output_dir = tmp / "out"
            tifffile.imwrite(source, arr)

            xy_opts = {
                "header": True,
                "one_based": False,
                "skip_zeros": False,
                "zero_tol": 0.0,
                "y_axis_origin": "top-left",
            }
            png_opts = {
                "scale": "linear",
                "vmin": "0",
                "vmax": "15",
                "colormap": "viridis",
            }
            proc_opts = {
                "dark_frame": None,
                "flat_frame": None,
                "flat_is_dark_subtracted": True,
                "roi": None,
                "mask_frame": None,
                "mask_nonzero_is_invalid": True,
                "clip_negative": False,
                "bg_offset": 0.0,
                "min_intensity": None,
                "max_intensity": None,
                "rotate_deg": "0",
                "flip_x": False,
                "flip_y": False,
                "bin_factor": 2,
                "pclip_low": None,
                "pclip_high": None,
                "intensity_transform": "none",
                "gamma": 1.0,
                "norm_mode": "none",
                "hot_pixel_enable": False,
                "hot_pixel_window": 3,
                "hot_pixel_sigma": 8.0,
                "lossless_matrix": True,
            }

            logs = process_one_file(
                (
                    source,
                    Path("sample.tif"),
                    tmp,
                    output_dir,
                    ["png"],
                    xy_opts,
                    png_opts,
                    "/entry/data/data",
                    proc_opts,
                    threading.Event(),
                    True,
                )
            )

            self.assertFalse(
                [line for line in logs if line.startswith(("ERROR", "FAILED"))]
            )
            self.assertTrue(any("[png/PROC]" in line for line in logs), logs)
            with Image.open(output_dir / "png" / "sample.png") as img:
                self.assertEqual(img.mode, "RGB")
                self.assertEqual(img.size, (2, 2))


if __name__ == "__main__":
    unittest.main()
