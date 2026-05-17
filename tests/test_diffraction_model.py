import math
import unittest

from core.diffraction_model import DiffractionModel


class DiffractionModelTests(unittest.TestCase):
    def test_energy_wavelength_round_trip(self):
        wavelength_a = 1.0
        energy = DiffractionModel.calc_energy_kev(wavelength_a)

        self.assertAlmostEqual(energy, 12.3984, places=6)
        self.assertAlmostEqual(
            DiffractionModel.calc_wavelength_A(energy),
            wavelength_a,
            places=6,
        )

    def test_q_radius_pixel_round_trip(self):
        q_nm = 2.0
        wavelength_a = 1.0
        distance_mm = 1000.0
        pixel_size_mm = 0.1
        center_x = 500.0
        center_y = 600.0

        r_mm, r_px, two_theta_deg, valid = DiffractionModel.q_to_radius(
            q_nm, wavelength_a, distance_mm, pixel_size_mm
        )
        self.assertTrue(valid)
        self.assertGreater(r_mm, 0)
        self.assertGreater(r_px, 0)
        self.assertGreater(two_theta_deg, 0)

        q_back, two_theta_back, r_back = DiffractionModel.pixel_to_q(
            center_x + r_px,
            center_y,
            center_x,
            center_y,
            distance_mm,
            pixel_size_mm,
            wavelength_a,
        )

        self.assertAlmostEqual(q_back, q_nm, places=9)
        self.assertAlmostEqual(two_theta_back, two_theta_deg, places=9)
        self.assertAlmostEqual(r_back, r_mm, places=9)

    def test_q_limits_and_d_spacing(self):
        wavelength_a = 1.0
        qmax = DiffractionModel.qmax_nm_inv(wavelength_a)

        self.assertAlmostEqual(qmax, 40.0 * math.pi, places=9)
        self.assertAlmostEqual(
            DiffractionModel.q_to_d_spacing(2.0, unit="nm"),
            math.pi,
            places=9,
        )
        self.assertAlmostEqual(
            DiffractionModel.q_to_d_spacing(2.0, unit="A"),
            10.0 * math.pi,
            places=9,
        )

    def test_invalid_geometry_returns_invalid_or_zero(self):
        self.assertEqual(DiffractionModel.calc_energy_kev(0), 0.0)
        self.assertEqual(DiffractionModel.calc_wavelength_A(0), 0.0)
        self.assertFalse(
            DiffractionModel.q_to_radius(1.0, 0.0, 1000.0, 0.1)[3]
        )
        self.assertEqual(
            DiffractionModel.pixel_to_q(1, 1, 0, 0, 0.0, 0.1, 1.0),
            (0.0, 0.0, 0.0),
        )
        self.assertEqual(DiffractionModel.q_to_d_spacing(0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
