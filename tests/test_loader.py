import tempfile
import unittest
from pathlib import Path

import numpy as np

from core.edf_io import write_edf
from core.loader import _normalize_loaded_array, load_image_with_info

try:
    from fabio.cbfimage import cbfimage
except Exception:
    cbfimage = None


class LoaderShapeSafetyTests(unittest.TestCase):
    def test_public_hdf5_loader_accepts_singleton_frame_dataset(self):
        try:
            import h5py
        except Exception:
            self.skipTest("h5py is not installed")

        source = np.arange(12, dtype=np.float32).reshape(1, 3, 4)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "single-frame.h5"
            with h5py.File(path, "w") as handle:
                handle.create_dataset("/entry/data/data", data=source)

            loaded = load_image_with_info(path)

        self.assertTrue(np.array_equal(loaded["data"], source[0]))
        self.assertEqual(loaded["metadata"]["source_kind"], "hdf5")
        self.assertEqual(loaded["metadata"]["shape"], (3, 4))
        self.assertEqual(loaded["metadata"]["dtype"], "float32")

    def test_public_edf_loader_round_trip(self):
        source = np.array(
            [[0, 1, 65535], [10, 20, 30]],
            dtype=np.uint16,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detector.edf"
            write_edf(source, path)

            loaded = load_image_with_info(path)

        self.assertTrue(np.array_equal(loaded["data"], source))
        self.assertEqual(loaded["data"].dtype, source.dtype)
        self.assertEqual(loaded["metadata"]["source_kind"], "edf")
        self.assertEqual(loaded["metadata"]["shape"], source.shape)

    def test_public_edf_loader_rejects_invalid_byte_order(self):
        source = np.arange(4, dtype="<i2").reshape(2, 2)
        header = "\n".join(
            [
                "{",
                "HeaderID = EH:000001:000000:000000 ;",
                "Image = 1 ;",
                "ByteOrder = SidewaysBytes ;",
                "DataType = SignedShort ;",
                "Dim_1 = 2 ;",
                "Dim_2 = 2 ;",
                f"Size = {source.nbytes} ;",
                "}",
                "",
            ]
        ).encode("ascii")
        header += b" " * (512 - len(header))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid-byte-order.edf"
            path.write_bytes(header + source.tobytes())
            with self.assertRaisesRegex(ValueError, "ByteOrder"):
                load_image_with_info(path)

    def test_public_cbf_loader_reads_fabio_fixture(self):
        if cbfimage is None:
            self.skipTest("fabio CBF support is not installed")

        source = np.array(
            [[0, 1, 2], [10, 20, 1234567]],
            dtype=np.int32,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "detector.cbf"
            cbfimage(data=source).write(str(path))

            loaded = load_image_with_info(path)

        self.assertTrue(np.array_equal(loaded["data"], source))
        self.assertEqual(loaded["data"].dtype, source.dtype)
        self.assertEqual(loaded["metadata"]["source_kind"], "cbf")
        self.assertEqual(loaded["metadata"]["shape"], source.shape)

    def test_singleton_frame_axis_is_squeezed(self):
        arr = np.arange(12).reshape(1, 3, 4)
        loaded = _normalize_loaded_array(arr, Path("single-frame.h5"))
        self.assertTrue(np.array_equal(loaded, arr[0]))

    def test_singleton_channel_axis_is_squeezed(self):
        arr = np.arange(12).reshape(3, 4, 1)
        loaded = _normalize_loaded_array(arr, Path("single-channel.h5"))
        self.assertTrue(np.array_equal(loaded, arr[..., 0]))

    def test_multi_frame_stack_is_rejected_instead_of_selecting_first_frame(self):
        arr = np.arange(24).reshape(2, 3, 4)
        with self.assertRaisesRegex(ValueError, "单个 2D"):
            _normalize_loaded_array(arr, Path("multi-frame.h5"))

    def test_multi_channel_stack_is_rejected_instead_of_selecting_first_channel(self):
        arr = np.arange(24).reshape(3, 4, 2)
        with self.assertRaisesRegex(ValueError, "单个 2D"):
            _normalize_loaded_array(arr, Path("multi-channel.h5"))


if __name__ == "__main__":
    unittest.main()
