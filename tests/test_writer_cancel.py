import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from core.writer import save_array


class _CancelAfterChecks(threading.Event):
    """Set the event after ``n`` ``is_set`` polls so the pre-write check passes."""

    def __init__(self, n):
        super().__init__()
        self._n = 0
        self._target = int(n)

    def is_set(self):
        self._n += 1
        if self._n >= self._target:
            threading.Event.set(self)
        return threading.Event.is_set(self)


class WriterCancelTests(unittest.TestCase):
    def test_xy_cancel_before_write_is_cancelled(self):
        arr = np.zeros((3, 2), dtype=np.float32)
        event = threading.Event()
        event.set()
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for fmt, name in (("xycsv", "before.csv"), ("xydat", "before.dat")):
                success, message, points = save_array(
                    arr,
                    tmp / name,
                    fmt,
                    xy_skip_zeros=True,
                    xy_zero_tol=0.0,
                    cancellation_event=event,
                )
                self.assertFalse(success)
                self.assertTrue(str(message).upper().startswith("CANCELLED"))
                self.assertEqual(points, 0)
                self.assertFalse((tmp / name).exists())

    def test_xy_cancel_during_write_with_empty_rows_is_cancelled_not_empty(self):
        arr = np.zeros((4, 3), dtype=np.float32)
        arr[-1, -1] = 5.0
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for fmt, name in (("xycsv", "during.csv"), ("xydat", "during.dat")):
                # 1: save_array pre-check; 2: first XY row (all zeros / skip).
                event = _CancelAfterChecks(2)
                success, message, points = save_array(
                    arr,
                    tmp / name,
                    fmt,
                    xy_skip_zeros=True,
                    xy_zero_tol=0.0,
                    cancellation_event=event,
                )
                self.assertFalse(success, message)
                self.assertEqual(message, "CANCELLED during write")
                self.assertEqual(points, 0)
                self.assertNotIn("阈值", message)
                self.assertFalse((tmp / name).exists())

    def test_xy_empty_without_cancel_still_reports_threshold_message(self):
        arr = np.zeros((2, 2), dtype=np.float32)
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            success, message, points = save_array(
                arr,
                tmp / "empty.csv",
                "xycsv",
                xy_skip_zeros=True,
                xy_zero_tol=0.0,
            )
            self.assertFalse(success)
            self.assertEqual(points, 0)
            self.assertIn("阈值", message)
            self.assertFalse(str(message).upper().startswith("CANCELLED"))


if __name__ == "__main__":
    unittest.main()
