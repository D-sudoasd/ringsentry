import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

from core.edf_io import write_edf
from core.loader import (
    _normalize_loaded_array,
    build_filelist_from_selected_paths,
    find_files_recursive,
    is_supported_input_file,
    load_image_with_info,
    sniff_file_kind,
)

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


class LoaderDiscoveryTests(unittest.TestCase):
    @staticmethod
    def _write_tif(path, value=1):
        path.parent.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(path, np.full((2, 2), value, dtype=np.uint16))

    @staticmethod
    def _found_names(entries):
        return sorted(str(rel_path).replace("\\", "/") for _path, rel_path in entries)

    @staticmethod
    def _try_file_symlink(link, target):
        try:
            link.symlink_to(target)
            return True
        except (OSError, NotImplementedError):
            return False

    @staticmethod
    def _try_dir_reparse(link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
            return True
        except (OSError, NotImplementedError):
            pass
        if os.name == "nt":
            completed = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True,
                text=True,
            )
            return completed.returncode == 0 and link.exists()
        return False

    def test_sniff_and_supported_flags_for_tif_and_npy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tif_path = tmp / "detector.tif"
            npy_path = tmp / "matrix.npy"
            missing = tmp / "missing.tif"
            self._write_tif(tif_path, 7)
            np.save(npy_path, np.arange(4, dtype=np.float32).reshape(2, 2))

            self.assertEqual(sniff_file_kind(tif_path), "tiff")
            self.assertTrue(is_supported_input_file(tif_path))
            self.assertFalse(is_supported_input_file(npy_path))
            self.assertFalse(is_supported_input_file(missing))
            with self.assertRaises(ValueError):
                sniff_file_kind(npy_path)

    def test_find_files_recursive_skips_converted_and_honors_exclude_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            keep = tmp / "keep.tif"
            nested = tmp / "nested" / "frame.tif"
            converted = tmp / "_converted" / "child.tif"
            excluded_dir = tmp / "skip_me"
            excluded = excluded_dir / "hidden.tif"
            ignored_npy = tmp / "not-an-input.npy"
            self._write_tif(keep, 1)
            self._write_tif(nested, 2)
            self._write_tif(converted, 3)
            self._write_tif(excluded, 4)
            np.save(ignored_npy, np.ones((2, 2), dtype=np.float32))

            positional = find_files_recursive(tmp, (excluded_dir,))
            keyword = find_files_recursive(tmp, exclude_dirs=(excluded_dir,))
            self.assertEqual(self._found_names(positional), self._found_names(keyword))
            self.assertEqual(
                self._found_names(positional),
                ["keep.tif", "nested/frame.tif"],
            )

    def test_find_files_recursive_skips_reparse_files_dirs_and_escaped_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            outside = tmp / "outside"
            root.mkdir()
            outside.mkdir()
            inside = root / "inside.tif"
            escaped_target = outside / "escaped.tif"
            outside_nested = outside / "more" / "linked.tif"
            self._write_tif(inside, 1)
            self._write_tif(escaped_target, 2)
            self._write_tif(outside_nested, 3)

            file_link = root / "alias.tif"
            dir_link = root / "linked_dir"
            made_file_link = self._try_file_symlink(file_link, escaped_target)
            made_dir_link = self._try_dir_reparse(dir_link, outside / "more")
            if not made_file_link and not made_dir_link:
                self.skipTest("symlink/junction creation unavailable")

            found = self._found_names(find_files_recursive(root))
            self.assertEqual(found, ["inside.tif"])
            if made_file_link:
                self.assertTrue(file_link.exists())
            if made_dir_link:
                self.assertTrue((dir_link / "linked.tif").exists())

    def test_build_filelist_skips_missing_and_unsupported_selected_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tif_path = tmp / "keep.tif"
            npy_path = tmp / "matrix.npy"
            missing = tmp / "gone.tif"
            not_a_file = tmp / "subdir"
            not_a_file.mkdir()
            self._write_tif(tif_path, 1)
            np.save(npy_path, np.ones((2, 2), dtype=np.float32))

            filelist, common_root, skipped = build_filelist_from_selected_paths(
                [str(tif_path), str(npy_path), str(missing), str(not_a_file)]
            )

            self.assertEqual(len(filelist), 1)
            self.assertEqual(filelist[0][0], tif_path.resolve())
            self.assertEqual(common_root, tif_path.resolve().parent)
            reasons = {Path(path).name: reason for path, reason in skipped}
            self.assertEqual(reasons.get("matrix.npy"), "unsupported")
            self.assertEqual(reasons.get("gone.tif"), "missing")
            self.assertEqual(reasons.get("subdir"), "not a file")


if __name__ == "__main__":
    unittest.main()
