"""Diffraction physics model for the Q calculator.

Formula conventions:
- Energy-wavelength: E[keV] = 12.3984 / wavelength[Angstrom]
- Scattering vector: Q = 4*pi*sin(theta) / wavelength
- Geometry: tan(2theta) = r / D
- Plane spacing: d = 2*pi / Q
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

import numpy as np


BEAMLINE_PRESETS: Dict[str, dict] = {
    "BL19B2 (SAXS)": dict(
        wavelength_A=0.413, distance_mm=3055.18, pixel_size_mm=0.172,
        center_x=688.19, center_y=783.68, det_w=1475, det_h=1679,
    ),
    "DESY (P03)": dict(
        wavelength_A=0.149, distance_mm=3139.47, pixel_size_mm=0.150,
        center_x=3390.83, center_y=177.08, det_w=4000, det_h=4000,
    ),
    "Standard Lab (Cu K-alpha)": dict(
        wavelength_A=1.5418, distance_mm=200.0, pixel_size_mm=0.172,
        center_x=500.0, center_y=500.0, det_w=1000, det_h=1000,
    ),
    "APS 12ID-B (SAXS)": dict(
        wavelength_A=1.033, distance_mm=2002.0, pixel_size_mm=0.172,
        center_x=1030.0, center_y=1030.0, det_w=2070, det_h=2068,
    ),
    "ESRF ID02 (SAXS)": dict(
        wavelength_A=0.996, distance_mm=1000.0, pixel_size_mm=0.075,
        center_x=1565.0, center_y=1565.0, det_w=3110, det_h=3269,
    ),
    "Diamond I22 (SAXS)": dict(
        wavelength_A=1.000, distance_mm=2500.0, pixel_size_mm=0.172,
        center_x=1000.0, center_y=1000.0, det_w=2000, det_h=2000,
    ),
    "SPring-8 BL40XU": dict(
        wavelength_A=1.000, distance_mm=1500.0, pixel_size_mm=0.172,
        center_x=690.0, center_y=785.0, det_w=1475, det_h=1679,
    ),
}


class DiffractionModel:
    """GUI-independent physical calculations for Q, angle, radius, and d-spacing."""

    @staticmethod
    def calc_energy_kev(wavelength_A: float) -> float:
        """Convert wavelength in Angstrom to photon energy in keV."""
        if wavelength_A <= 0:
            return 0.0
        return 12.3984 / wavelength_A

    @staticmethod
    def calc_wavelength_A(energy_kev: float) -> float:
        """Convert photon energy in keV to wavelength in Angstrom."""
        if energy_kev <= 0:
            return 0.0
        return 12.3984 / energy_kev

    @staticmethod
    def qmax_nm_inv(wavelength_A: float) -> float:
        """Geometric upper bound from sin(theta) <= 1: Qmax = 4*pi/lambda."""
        if wavelength_A <= 0:
            return 0.0
        lam_nm = wavelength_A * 0.1
        return (4.0 * math.pi) / lam_nm

    @staticmethod
    def q_to_radius(
        q_nm: float,
        wavelength_A: float,
        distance_mm: float,
        pixel_size_mm: float,
        eps: float = 1e-12,
    ) -> Tuple[float, float, float, bool]:
        """Compute detector radius for a target Q.

        Returns ``(r_mm, r_px, two_theta_deg, valid)``.
        """
        if wavelength_A <= 0 or distance_mm <= 0 or pixel_size_mm <= 0 or q_nm < 0:
            return 0.0, 0.0, 0.0, False

        lam_nm = wavelength_A * 0.1
        ratio = (q_nm * lam_nm) / (4.0 * math.pi)  # sin(theta)

        if ratio < -eps or ratio > 1.0 + eps:
            return 0.0, 0.0, 0.0, False
        ratio = float(np.clip(ratio, 0.0, 1.0))

        theta = math.asin(ratio)
        two_theta = 2.0 * theta

        if abs((math.pi / 2.0) - two_theta) < 1e-6:
            return 0.0, 0.0, 0.0, False

        r_mm = distance_mm * math.tan(two_theta)
        r_px = r_mm / pixel_size_mm
        return float(r_mm), float(r_px), float(math.degrees(two_theta)), True

    @staticmethod
    def pixel_to_q(
        x_px: float,
        y_px: float,
        center_x: float,
        center_y: float,
        distance_mm: float,
        pixel_size_mm: float,
        wavelength_A: float,
    ) -> Tuple[float, float, float]:
        """Invert detector pixel coordinate to Q.

        Returns ``(q_nm, two_theta_deg, r_mm)``.
        """
        if wavelength_A <= 0 or distance_mm <= 0 or pixel_size_mm <= 0:
            return 0.0, 0.0, 0.0

        dx = (x_px - center_x) * pixel_size_mm
        dy = (y_px - center_y) * pixel_size_mm
        r_mm = math.hypot(dx, dy)

        two_theta = math.atan2(r_mm, distance_mm)
        theta = two_theta / 2.0

        lam_nm = wavelength_A * 0.1
        q_nm = (4.0 * math.pi * math.sin(theta)) / lam_nm
        return float(q_nm), float(math.degrees(two_theta)), float(r_mm)

    @staticmethod
    def q_to_d_spacing(q_nm: float, unit: str = "A") -> float:
        """Convert Q in nm^-1 to crystal plane spacing d."""
        if q_nm <= 0:
            return 0.0
        d_nm = (2.0 * math.pi) / q_nm
        if unit == "A":
            return d_nm * 10.0
        return d_nm

    @staticmethod
    def max_radius_px(det_w: float, det_h: float, cx: float, cy: float) -> float:
        """Maximum pixel radius from beam center to any detector corner."""
        corners = [(0, 0), (det_w, 0), (0, det_h), (det_w, det_h)]
        return max(math.hypot(x - cx, y - cy) for x, y in corners)

    @staticmethod
    def detector_qmax_nm(
        det_w: float, det_h: float,
        cx: float, cy: float,
        distance_mm: float, pixel_size_mm: float,
        wavelength_A: float,
    ) -> float:
        """Maximum Q reachable on the detector in nm^-1."""
        rmax = DiffractionModel.max_radius_px(det_w, det_h, cx, cy) * pixel_size_mm
        two_theta = math.atan2(rmax, distance_mm) if distance_mm > 0 else 0.0
        theta = two_theta / 2.0
        lam_nm = wavelength_A * 0.1
        if lam_nm <= 0:
            return 0.0
        return (4.0 * math.pi * math.sin(theta)) / lam_nm
