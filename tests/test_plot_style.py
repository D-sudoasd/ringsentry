import tempfile
import unittest
from pathlib import Path

from core.plot_style import (
    PLOT_PRESET_LABELS,
    get_plot_preset,
    save_figure,
)


class PlotStyleTests(unittest.TestCase):
    def test_required_export_presets_are_available(self):
        labels = set(PLOT_PRESET_LABELS)

        self.assertIn("Single-column figure", labels)
        self.assertIn("Double-column figure", labels)
        self.assertIn("Presentation", labels)
        self.assertIn("Raw inspection", labels)
        self.assertIn("Publication", labels)

        publication = get_plot_preset("Publication")
        self.assertGreaterEqual(publication["dpi"], 600)
        self.assertEqual(publication["colormap"], "viridis")

    def test_save_figure_supports_raster_and_vector_outputs(self):
        import matplotlib

        matplotlib.use("Agg", force=True)
        from matplotlib.figure import Figure

        fig = Figure()
        ax = fig.add_subplot(111)
        ax.plot([0, 1, 2], [1, 3, 2], label="experimental data")
        ax.set_xlabel("Q (nm^-1)")
        ax.set_ylabel("Intensity (a.u.)")
        ax.legend()

        with tempfile.TemporaryDirectory() as tmp:
            png_path = Path(tmp) / "figure.png"
            pdf_path = Path(tmp) / "figure.pdf"

            save_figure(fig, png_path, preset="Publication")
            save_figure(fig, pdf_path, preset="Single-column figure")

            self.assertGreater(png_path.stat().st_size, 0)
            self.assertGreater(pdf_path.stat().st_size, 0)

    def test_save_figure_restores_live_figure_size(self):
        import matplotlib

        matplotlib.use("Agg", force=True)
        from matplotlib.figure import Figure

        fig = Figure(figsize=(5.6, 4.4), dpi=100)
        ax = fig.add_subplot(111)
        ax.plot([0, 1], [0, 1])
        original_size = tuple(fig.get_size_inches())

        with tempfile.TemporaryDirectory() as tmp:
            save_figure(fig, Path(tmp) / "figure.png", preset="Single-column figure")

        self.assertEqual(tuple(fig.get_size_inches()), original_size)


if __name__ == "__main__":
    unittest.main()
