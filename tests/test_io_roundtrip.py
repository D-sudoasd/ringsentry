import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
import tifffile

from core.edf_io import read_edf, write_edf
from core.loader import load_image_with_info
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
    def test_public_hdf5_loader_rejects_multi_frame_stack(self):
        try:
            import h5py
        except Exception:
            self.skipTest("h5py is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "multi-frame.h5"
            with h5py.File(path, "w") as handle:
                handle.create_dataset(
                    "/entry/data/data",
                    data=np.arange(24, dtype=np.float32).reshape(2, 3, 4),
                )

            with self.assertRaisesRegex(ValueError, "单个 2D"):
                load_image_with_info(path)

    def test_npy_float_export_preserves_nonfinite_values_after_processing_cast(self):
        arr = np.array(
            [[1.5, np.nan], [np.inf, -np.inf]],
            dtype=np.float64,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonfinite.npy"

            success, message, points = save_array(
                arr,
                path,
                "npy",
                preserve_dtype=False,
            )

            self.assertTrue(success, message)
            self.assertEqual(points, arr.size)
            loaded = np.load(path)
            self.assertEqual(loaded.dtype, np.dtype(np.float32))
            self.assertEqual(float(loaded[0, 0]), 1.5)
            self.assertTrue(np.isnan(loaded[0, 1]))
            self.assertTrue(np.isposinf(loaded[1, 0]))
            self.assertTrue(np.isneginf(loaded[1, 1]))

    def test_edf_float_export_preserves_nonfinite_values_for_project_and_fabio_readers(self):
        if fabio is None:
            self.skipTest("fabio is not installed")

        arr = np.array(
            [[2.5, np.nan], [np.inf, -np.inf]],
            dtype=np.float32,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonfinite.edf"

            success, message, points = save_array(
                arr,
                path,
                "edf",
                preserve_dtype=False,
            )

            self.assertTrue(success, message)
            self.assertEqual(points, arr.size)
            for loaded in (read_edf(path), fabio.open(str(path)).data):
                self.assertEqual(loaded.dtype, np.dtype(np.float32))
                self.assertEqual(float(loaded[0, 0]), 2.5)
                self.assertTrue(np.isnan(loaded[0, 1]))
                self.assertTrue(np.isposinf(loaded[1, 0]))
                self.assertTrue(np.isneginf(loaded[1, 1]))

    def test_tiff_float32_export_preserves_nonfinite_values(self):
        arr = np.array(
            [[3.5, np.nan], [np.inf, -np.inf]],
            dtype=np.float64,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonfinite.tif"

            success, message, points = save_array(
                arr,
                path,
                "tif",
                preserve_dtype=False,
            )

            self.assertTrue(success, message)
            self.assertEqual(points, arr.size)
            loaded = tifffile.imread(path)
            self.assertEqual(loaded.dtype, np.dtype(np.float32))
            self.assertEqual(float(loaded[0, 0]), 3.5)
            self.assertTrue(np.isnan(loaded[0, 1]))
            self.assertTrue(np.isposinf(loaded[1, 0]))
            self.assertTrue(np.isneginf(loaded[1, 1]))

    def test_binary_float_exports_preserve_nonfinite_values_when_preserving_dtype(self):
        arr = np.array(
            [[4.5, np.nan], [np.inf, -np.inf]],
            dtype=np.float32,
        )
        readers = {
            "npy": np.load,
            "edf": read_edf,
            "tif": tifffile.imread,
        }
        with tempfile.TemporaryDirectory() as tmp:
            for fmt, reader in readers.items():
                with self.subTest(fmt=fmt):
                    path = Path(tmp) / f"preserved.{fmt}"

                    success, message, points = save_array(
                        arr,
                        path,
                        fmt,
                        preserve_dtype=True,
                    )

                    self.assertTrue(success, message)
                    self.assertEqual(points, arr.size)
                    loaded = reader(path)
                    self.assertEqual(loaded.dtype, np.dtype(np.float32))
                    self.assertEqual(float(loaded[0, 0]), 4.5)
                    self.assertTrue(np.isnan(loaded[0, 1]))
                    self.assertTrue(np.isposinf(loaded[1, 0]))
                    self.assertTrue(np.isneginf(loaded[1, 1]))

    def test_text_matrix_exports_replace_nonfinite_values_and_log_counts(self):
        arr = np.array(
            [[1.25, np.nan], [np.inf, -np.inf]],
            dtype=np.float32,
        )
        expected = np.array([[1.25, 0.0], [0.0, 0.0]], dtype=np.float64)
        with tempfile.TemporaryDirectory() as tmp:
            for fmt, delimiter in (("csv", ","), ("dat", "\t")):
                with self.subTest(fmt=fmt):
                    path = Path(tmp) / f"nonfinite.{fmt}"

                    with self.assertLogs("core.writer", level="WARNING") as captured:
                        success, message, points = save_array(
                            arr,
                            path,
                            fmt,
                            preserve_dtype=False,
                        )

                    self.assertTrue(success, message)
                    self.assertEqual(points, arr.size)
                    np.testing.assert_allclose(
                        np.loadtxt(path, delimiter=delimiter),
                        expected,
                        rtol=0.0,
                        atol=0.0,
                    )
                    np.testing.assert_equal(
                        arr,
                        np.array(
                            [[1.25, np.nan], [np.inf, -np.inf]],
                            dtype=np.float32,
                        ),
                    )
                    log_text = "\n".join(captured.output)
                    self.assertIn(f"{fmt.upper()} compatibility export", log_text)
                    self.assertIn("NaN=1", log_text)
                    self.assertIn("+Inf=1", log_text)
                    self.assertIn("-Inf=1", log_text)
                    self.assertIn(f"{fmt.upper()} compatibility export", message)
                    self.assertIn("NaN=1", message)
                    self.assertIn("+Inf=1", message)
                    self.assertIn("-Inf=1", message)

    def test_text_matrix_exports_log_nan_only_replacements(self):
        arr = np.array([[np.nan, 2.0]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            for fmt in ("csv", "dat"):
                with self.subTest(fmt=fmt):
                    path = Path(tmp) / f"nan-only.{fmt}"

                    with self.assertLogs("core.writer", level="WARNING") as captured:
                        success, message, _ = save_array(arr, path, fmt)

                    self.assertTrue(success, message)
                    log_text = "\n".join(captured.output)
                    self.assertIn(f"{fmt.upper()} compatibility export", log_text)
                    self.assertIn("NaN=1", log_text)
                    self.assertIn("+Inf=0", log_text)
                    self.assertIn("-Inf=0", log_text)

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

    def test_edf_writer_protects_control_fields_from_header_extras(self):
        arr = np.arange(4, dtype=np.uint16).reshape(2, 2)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reserved-extras.edf"
            write_edf(
                arr,
                path,
                header_extra={
                    "Compression": "RunLengthEncoded",
                    "HeaderSize": "1024",
                },
            )

            raw = path.read_bytes()[:512]
            self.assertIn(b"User_Compression = RunLengthEncoded", raw)
            self.assertIn(b"User_HeaderSize = 1024", raw)
            self.assertTrue(np.array_equal(read_edf(path), arr))

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

    def test_edf_reader_handles_declared_1024_byte_uncompressed_header(self):
        arr = np.arange(6, dtype="<u2").reshape(2, 3)
        header = "\n".join(
            [
                "{",
                "HeaderSize = 1024 ;",
                "Compression = uncompressed ;",
                "ByteOrder = LowByteFirst ;",
                "DataType = UnsignedShort ;",
                "Dim_1 = 3 ;",
                "Dim_2 = 2 ;",
                f"Size = {arr.nbytes} ;",
                "}",
                "",
            ]
        ).encode("ascii")
        header += b" " * (1024 - len(header))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "declared-1024.edf"
            path.write_bytes(header + arr.tobytes())

            loaded = read_edf(path)
            self.assertEqual(loaded.dtype, np.dtype(np.uint16))
            self.assertTrue(np.array_equal(loaded, arr))

    def test_edf_reader_rejects_header_without_opening_brace(self):
        arr = np.arange(4, dtype="<i2").reshape(2, 2)
        header = "\n".join(
            [
                "ByteOrder = LowByteFirst ;",
                "DataType = SignedShort ;",
                "Dim_1 = 2 ;",
                "Dim_2 = 2 ;",
                f"Size = {arr.nbytes} ;",
                "}",
                "",
            ]
        ).encode("ascii")
        header += b" " * (512 - len(header))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing-opening-brace.edf"
            path.write_bytes(header + arr.tobytes())
            with self.assertRaisesRegex(ValueError, "opening brace"):
                read_edf(path)

    def test_edf_reader_rejects_compressed_payload_marker(self):
        arr = np.arange(4, dtype="<i2").reshape(2, 2)
        header = "\n".join(
            [
                "{",
                "Compression = RunLengthEncoded ;",
                "ByteOrder = LowByteFirst ;",
                "DataType = SignedShort ;",
                "Dim_1 = 2 ;",
                "Dim_2 = 2 ;",
                f"Size = {arr.nbytes} ;",
                "}",
                "",
            ]
        ).encode("ascii")
        header += b" " * (512 - len(header))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "compressed.edf"
            path.write_bytes(header + arr.tobytes())
            with self.assertRaisesRegex(ValueError, "Compression"):
                read_edf(path)

    def test_edf_reader_rejects_incorrect_declared_header_offset(self):
        arr = np.array(
            [[1024, 1025], [1026, 1027]],
            dtype="<i2",
        )
        header = "\n".join(
            [
                "{",
                "EDF_HeaderSize = 512 ;",
                "ByteOrder = LowByteFirst ;",
                "DataType = SignedShort ;",
                "Dim_1 = 2 ;",
                "Dim_2 = 2 ;",
                f"Size = {arr.nbytes} ;",
                "}",
                "",
            ]
        ).encode("ascii")
        header += b" " * (1024 - len(header))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incorrect-header-offset.edf"
            path.write_bytes(header + arr.tobytes())
            with self.assertRaisesRegex(ValueError, "EDF_HeaderSize"):
                read_edf(path)

    def test_edf_reader_rejects_unknown_byte_order(self):
        arr = np.arange(4, dtype="<i2").reshape(2, 2)
        header = "\n".join(
            [
                "{",
                "ByteOrder = SidewaysBytes ;",
                "DataType = SignedShort ;",
                "Dim_1 = 2 ;",
                "Dim_2 = 2 ;",
                f"Size = {arr.nbytes} ;",
                "}",
                "",
            ]
        ).encode("ascii")
        header += b" " * (512 - len(header))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-byte-order.edf"
            path.write_bytes(header + arr.tobytes())
            with self.assertRaisesRegex(ValueError, "ByteOrder"):
                read_edf(path)

    def test_edf_reader_rejects_declared_size_mismatch(self):
        arr = np.arange(4, dtype="<i2").reshape(2, 2)
        header = "\n".join(
            [
                "{",
                "ByteOrder = LowByteFirst ;",
                "DataType = SignedShort ;",
                "Dim_1 = 2 ;",
                "Dim_2 = 2 ;",
                f"Size = {arr.nbytes + 4} ;",
                "}",
                "",
            ]
        ).encode("ascii")
        header += b" " * (512 - len(header))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-size.edf"
            path.write_bytes(header + arr.tobytes())
            with self.assertRaisesRegex(ValueError, "does not match"):
                read_edf(path)

    def test_edf_reader_rejects_conflicting_binary_size_fields(self):
        arr = np.arange(4, dtype="<i2").reshape(2, 2)
        header = "\n".join(
            [
                "{",
                "ByteOrder = LowByteFirst ;",
                "DataType = SignedShort ;",
                "Dim_1 = 2 ;",
                "Dim_2 = 2 ;",
                f"EDF_BinarySize = {arr.nbytes} ;",
                f"Size = {arr.nbytes + 2} ;",
                "}",
                "",
            ]
        ).encode("ascii")
        header += b" " * (512 - len(header))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conflicting-sizes.edf"
            path.write_bytes(header + arr.tobytes())
            with self.assertRaisesRegex(ValueError, "conflicting"):
                read_edf(path)

    def test_edf_reader_rejects_trailing_bytes(self):
        arr = np.arange(4, dtype="<i2").reshape(2, 2)
        header = "\n".join(
            [
                "{",
                "ByteOrder = LowByteFirst ;",
                "DataType = SignedShort ;",
                "Dim_1 = 2 ;",
                "Dim_2 = 2 ;",
                f"Size = {arr.nbytes} ;",
                "}",
                "",
            ]
        ).encode("ascii")
        header += b" " * (512 - len(header))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trailing.edf"
            path.write_bytes(header + arr.tobytes() + b"extra")
            with self.assertRaisesRegex(ValueError, "trailing bytes"):
                read_edf(path)

    def test_worker_text_export_records_nonfinite_replacement_in_logs(self):
        arr = np.array([[1.0, np.nan], [np.inf, -np.inf]], dtype=np.float32)
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
                "roi": None,
                "bin_factor": 1,
                "lossless_matrix": True,
            }
            logs = process_one_file(
                (
                    source,
                    Path("input.tif"),
                    tmp,
                    output_dir,
                    ["csv"],
                    xy_opts,
                    "/entry/data/data",
                    proc_opts,
                    threading.Event(),
                    True,
                )
            )
            success_log = next(line for line in logs if line.startswith("SUCCESS:"))
            self.assertIn("CSV compatibility export", success_log)
            self.assertIn("NaN=1", success_log)
            self.assertIn("+Inf=1", success_log)
            self.assertIn("-Inf=1", success_log)

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

    def test_cbf_tiff_export_accepts_loader_metadata_keys(self):
        arr = np.array([[0, 70000], [10, 20]], dtype=np.int32)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "loader-metadata.tif"
            success, message, _ = save_array(
                arr,
                path,
                "tif",
                preserve_dtype=True,
                metadata={"source_kind": "cbf", "dtype": "int32"},
            )
            self.assertTrue(success, message)
            self.assertIn("compatibility cast", message)
            with tifffile.TiffFile(path) as tif:
                self.assertEqual(tif.pages[0].dtype, np.dtype(np.float32))

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
