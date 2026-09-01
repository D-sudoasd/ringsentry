import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

try:
    import tkinter as tk
except Exception:  # pragma: no cover - tkinter may be unavailable in some envs
    tk = None

from gui.tabs.q_calculator_tab import (
    BEAMLINE_PRESETS,
    QCalculatorTab,
    _DetectorPlotPanel,
    _ring_label_indices,
)

_DEFAULT_CALC_PARAMS = {
    "wavelength_A": "1.0",
    "energy_keV": "12.3984",
    "distance_mm": "100.0",
    "pixel_size_mm": "0.1",
    "center_x": "10.0",
    "center_y": "10.0",
    "det_w": "20",
    "det_h": "20",
    "q_start": "0.1",
    "q_end": "10.0",
    "q_step": "9.9",
    "q_unit": "nm^-1",
}


class QCalculatorRegressionTests(unittest.TestCase):
    def _hidden_root(self):
        if tk is None:
            self.skipTest("tkinter is not available")
        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            self.skipTest("Tk display is unavailable: %s" % exc)
        self.addCleanup(root.destroy)
        return root

    def _string_vars(self, root, **overrides):
        values = dict(_DEFAULT_CALC_PARAMS)
        values.update(overrides)
        return {
            key: tk.StringVar(master=root, value=str(value))
            for key, value in values.items()
        }

    def test_dense_ring_plot_throttles_labels_but_keeps_endpoints(self):
        indices = _ring_label_indices(101)

        self.assertLessEqual(len(indices), 6)
        self.assertEqual(indices[0], 0)
        self.assertEqual(indices[-1], 100)
        self.assertEqual(indices, sorted(set(indices)))

    def test_ring_range_is_separate_from_physical_validity(self):
        """A physically valid ring outside the detector must not be drawable."""
        self.assertTrue(
            QCalculatorTab._ring_in_detector(
                r_px=5.0, det_w=20.0, det_h=20.0, center_x=10.0, center_y=10.0
            )
        )
        self.assertFalse(
            QCalculatorTab._ring_in_detector(
                r_px=20.0, det_w=20.0, det_h=20.0, center_x=10.0, center_y=10.0
            )
        )

    def test_plot_labels_use_displayed_q_value_and_unit(self):
        class FakeAxis:
            def __init__(self):
                self.text_calls = []

            def clear(self):
                pass

            def set_xlim(self, *_args):
                pass

            def set_ylim(self, *_args):
                pass

            def add_patch(self, *_args):
                pass

            def plot(self, *_args, **_kwargs):
                pass

            def text(self, *args, **_kwargs):
                self.text_calls.append(args)

            def set_title(self, *_args, **_kwargs):
                pass

            def set_xlabel(self, *_args, **_kwargs):
                pass

            def set_ylabel(self, *_args, **_kwargs):
                pass

            def legend(self, *_args, **_kwargs):
                pass

        class FakeFigure:
            def tight_layout(self):
                pass

        class FakeCanvas:
            def draw(self):
                pass

        panel = _DetectorPlotPanel.__new__(_DetectorPlotPanel)
        panel.ax = FakeAxis()
        panel.figure = FakeFigure()
        panel.canvas = FakeCanvas()
        panel._Rectangle = lambda *args, **kwargs: object()
        panel._Circle = lambda *args, **kwargs: object()
        panel._matplotlib = SimpleNamespace(
            cm=SimpleNamespace(
                viridis=lambda values: np.zeros((len(values), 4))
            )
        )

        with mock.patch("gui.tabs.q_calculator_tab.style_axis"):
            panel.draw_scene(
                {"width": 20, "height": 20, "center_x": 10, "center_y": 10},
                [{"q": 10.0, "q_display": 1.0, "r_px": 5.0, "valid": True}],
                q_unit="A^-1",
            )

        labels = [str(args[2]) for args in panel.ax.text_calls if len(args) >= 3]
        self.assertIn("1 A^-1", labels)

    def test_calculation_keeps_out_of_detector_rows_but_only_plots_visible(self):
        class FakeText:
            def get(self, *_args):
                return ""

        class FakeTree:
            def __init__(self):
                self.rows = []

            def get_children(self):
                return tuple(f"row-{i}" for i in range(1, len(self.rows) + 1))

            def delete(self, *_args):
                self.rows.clear()

            def heading(self, *_args, **_kwargs):
                pass

            def insert(self, _parent, _index, **kwargs):
                self.rows.append(kwargs)
                return f"row-{len(self.rows)}"

        class FakePlot:
            def __init__(self):
                self.calls = []

            def draw_scene(self, *args, **kwargs):
                self.calls.append((args, kwargs))

        class FakeStatus:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

        root = self._hidden_root()
        tab = QCalculatorTab.__new__(QCalculatorTab)
        tab.vars = self._string_vars(root)
        tab.q_text = FakeText()
        tab.tree = FakeTree()
        tab.plot_panel = FakePlot()
        tab.status_var = FakeStatus()
        tab.result_data = []
        tab._plot_rings = []
        tab._selected_q_nm = None

        with mock.patch("gui.tabs.q_calculator_tab.messagebox.showerror") as showerror:
            tab.vars["energy_keV"].set("0")
            self.assertIsNone(tab.get_params())
            showerror.assert_called()
            self.assertIn("energy_keV", showerror.call_args[0][1])

            tab.vars["energy_keV"].set("12.3984")
            tab.vars["q_step"].set("0")
            self.assertIsNone(tab.get_params())
            self.assertIn("q_step", showerror.call_args[0][1])

            tab.result_data = [{"sentinel": True}]
            tab.run_calculation()
            self.assertEqual(tab.result_data, [{"sentinel": True}])

            tab.vars["q_step"].set("9.9")
            parsed = tab.get_params()
            self.assertIsNotNone(parsed)
            self.assertAlmostEqual(parsed["wavelength_A"], 1.0)
            self.assertAlmostEqual(parsed["q_start"], 0.1)
            self.assertAlmostEqual(parsed["q_end"], 10.0)
            self.assertAlmostEqual(parsed["q_step"], 9.9)

            tab.result_data = []
            tab.run_calculation()

        self.assertEqual(len(tab.result_data), 2)
        self.assertAlmostEqual(tab.result_data[0]["q"], 0.1)
        self.assertAlmostEqual(tab.result_data[1]["q"], 10.0)
        self.assertTrue(tab.result_data[0]["physical_valid"])
        self.assertTrue(tab.result_data[0]["in_detector"])
        self.assertTrue(tab.result_data[1]["physical_valid"])
        self.assertFalse(tab.result_data[1]["in_detector"])
        self.assertEqual(len(tab._plot_rings), 1)
        self.assertEqual(len(tab.tree.rows), 2)
        self.assertIn("outside", tab.status_var.value.lower())

    def test_enter_event_invokes_calculation(self):
        tab = QCalculatorTab.__new__(QCalculatorTab)
        tab.run_calculation = mock.Mock()

        result = tab._on_enter(SimpleNamespace())

        tab.run_calculation.assert_called_once_with()
        self.assertEqual(result, "break")

    def test_text_calculation_shortcut_invokes_calculation(self):
        tab = QCalculatorTab.__new__(QCalculatorTab)
        tab.run_calculation = mock.Mock()

        result = tab._on_calculate_shortcut(SimpleNamespace())

        tab.run_calculation.assert_called_once_with()
        self.assertEqual(result, "break")

    def test_csv_default_unit_has_unique_q_columns(self):
        class Var:
            def get(self):
                return "nm^-1"

        class FakeApp:
            def log(self, _message):
                pass

        tab = QCalculatorTab.__new__(QCalculatorTab)
        tab.vars = {"q_unit": Var()}
        tab.result_data = [{
            "q": 1.0, "q_display": 1.0, "two_theta": 1.0,
            "d_A": 6.28, "r_mm": 2.0, "r_px": 20.0,
            "valid": True, "physical_valid": True, "in_detector": True,
        }]
        tab.app = FakeApp()

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "q.csv"
            with mock.patch(
                "gui.tabs.q_calculator_tab.filedialog.asksaveasfilename",
                return_value=str(path),
            ):
                tab._export_csv()

            with path.open(newline="", encoding="utf-8") as handle:
                header = next(csv.reader(handle))

        self.assertEqual(len(header), len(set(header)))
        self.assertEqual(header.count("q_nm^-1"), 1)

    def test_load_config_reads_top_level_custom_presets_across_restart(self):
        class Var:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class FakeCombo:
            def configure(self, **_kwargs):
                pass

        preset = {
            "wavelength_A": 0.5,
            "distance_mm": 1000.0,
            "pixel_size_mm": 0.1,
            "center_x": 50.0,
            "center_y": 50.0,
            "det_w": 100,
            "det_h": 100,
        }

        class FakeApp:
            def _load_config_raw(self):
                return {"q_calc_custom_presets": {"Saved beamline": preset}}

        tab = QCalculatorTab.__new__(QCalculatorTab)
        tab.app = FakeApp()
        tab.cb_preset = FakeCombo()
        tab.vars = {"wavelength_A": Var("1.0")}
        tab._sync_energy_from_wavelength = mock.Mock()
        tab.run_calculation = mock.Mock()

        with mock.patch.dict(BEAMLINE_PRESETS, {}, clear=False):
            tab.load_config({"wavelength_A": "0.5"})

            self.assertEqual(BEAMLINE_PRESETS["Saved beamline"], preset)
            self.assertEqual(tab.vars["wavelength_A"].get(), "0.5")
            tab.run_calculation.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
