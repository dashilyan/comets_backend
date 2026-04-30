"""
Orbital mechanics service.

Pipeline:
    pixel (x, y)  ──pixel_to_radec──►  sky (RA, Dec)
    sky positions ──compute_orbital_elements──►  Keplerian elements

Coordinate frame: ICRS / second equatorial system (J2000).
Orbital elements are defined relative to the equatorial plane of J2000.

Dependencies: astropy, skyfield, scipy, numpy.
"""

import logging

import numpy as np
from astropy.coordinates import get_body_barycentric
from astropy.time import Time
import astropy.units as u
from scipy.optimize import minimize
from skyfield.api import load as skyfield_load

logger = logging.getLogger(__name__)

# GM_sun in AU³ day⁻²  (= 4π² / 365.25²)
_MU = 4.0 * np.pi**2 / (365.25**2)

# Skyfield timescale — built once at import time (no network call needed)
_TS = skyfield_load.timescale()


# ---------------------------------------------------------------------------
# Pixel → RA/Dec
# ---------------------------------------------------------------------------

def pixel_to_radec(
    x_px: float,
    y_px: float,
    img_width: int,
    img_height: int,
    center_ra_deg: float,
    center_dec_deg: float,
    focal_length_mm: float,
    pixel_size_um: float = 4.65,
) -> tuple[float, float]:
    """
    Convert pixel coordinates to equatorial sky coordinates (ICRS).

    Uses a flat-sky (gnomonic) approximation valid for small fields of view.

    Args:
        x_px, y_px        — comet position in pixels (origin = top-left)
        img_width/height  — image dimensions in pixels
        center_ra_deg     — right ascension of image centre [deg]
        center_dec_deg    — declination of image centre [deg]
        focal_length_mm   — telescope focal length [mm]
        pixel_size_um     — sensor pixel pitch [µm], default 4.65 µm (typical CCD)

    Returns:
        (ra_deg, dec_deg) in ICRS.
    """
    # Plate scale: arcsec per pixel  →  deg per pixel
    plate_scale_deg = np.degrees(np.arctan2(pixel_size_um * 1e-3, focal_length_mm))

    # Pixel offsets from image centre (flip y: image y increases downward)
    dx = x_px - img_width / 2.0
    dy = img_height / 2.0 - y_px

    cos_dec = np.cos(np.radians(center_dec_deg))
    if abs(cos_dec) < 1e-6:
        cos_dec = 1e-6

    ra = (center_ra_deg + dx * plate_scale_deg / cos_dec) % 360.0
    dec = float(np.clip(center_dec_deg + dy * plate_scale_deg, -90.0, 90.0))
    return ra, dec


# ---------------------------------------------------------------------------
# Orbital mechanics helpers
# ---------------------------------------------------------------------------

def _earth_pos_au(t_jd: float) -> np.ndarray:
    """Heliocentric position of Earth in AU at Julian date t_jd (ICRS)."""
    t = Time(t_jd, format="jd", scale="tdb")
    pos = get_body_barycentric("earth", t)
    return np.array([
        pos.x.to(u.au).value,
        pos.y.to(u.au).value,
        pos.z.to(u.au).value,
    ])


def _solve_kepler(M: float, e: float, tol: float = 1e-10) -> float:
    """Solve Kepler's equation  M = E − e·sin(E)  by Newton–Raphson iteration."""
    E = float(M)
    for _ in range(60):
        dE = (M - E + e * np.sin(E)) / (1.0 - e * np.cos(E))
        E += dE
        if abs(dE) < tol:
            break
    return E


def _rotation_matrix(node_deg: float, i_deg: float, peri_deg: float) -> np.ndarray:
    """
    Rotation matrix from perifocal frame to ICRS equatorial frame.
    Standard Euler sequence: Rz(Ω) · Rx(i) · Rz(ω).
    """
    O = np.radians(node_deg)
    inc = np.radians(i_deg)
    w = np.radians(peri_deg)

    cos_O, sin_O = np.cos(O), np.sin(O)
    cos_i, sin_i = np.cos(inc), np.sin(inc)
    cos_w, sin_w = np.cos(w), np.sin(w)

    return np.array([
        [cos_O * cos_w - sin_O * sin_w * cos_i,
         -cos_O * sin_w - sin_O * cos_w * cos_i,
         sin_O * sin_i],
        [sin_O * cos_w + cos_O * sin_w * cos_i,
         -sin_O * sin_w + cos_O * cos_w * cos_i,
         -cos_O * sin_i],
        [sin_w * sin_i,
         cos_w * sin_i,
         cos_i],
    ])


def _keplerian_to_helio(
    a: float, e: float,
    i_deg: float, node_deg: float, peri_deg: float,
    M_deg: float,
) -> np.ndarray:
    """
    Convert Keplerian elements to heliocentric Cartesian position [AU] in ICRS.

    Returns shape-(3,) ndarray.
    """
    M = np.radians(M_deg)
    E = _solve_kepler(M, e)
    nu = 2.0 * np.arctan2(
        np.sqrt(1.0 + e) * np.sin(E / 2.0),
        np.sqrt(1.0 - e) * np.cos(E / 2.0),
    )
    r = a * (1.0 - e * np.cos(E))

    # Position in perifocal frame
    r_peri = np.array([r * np.cos(nu), r * np.sin(nu), 0.0])

    Q = _rotation_matrix(node_deg, i_deg, peri_deg)
    return Q @ r_peri


def _predicted_radec(
    a: float, e: float, i: float, node: float, peri: float,
    M0: float, t0_jd: float,
    t_jd: float,
    earth_pos: np.ndarray,
) -> tuple[float, float] | tuple[None, None]:
    """
    Predict (RA, Dec) [deg] of object with given elements at time t_jd.
    M0 is mean anomaly [deg] at epoch t0_jd.
    """
    if e < 0.0 or e >= 1.0 or a <= 0.0:
        return None, None

    n_deg_per_day = np.degrees(np.sqrt(_MU / max(a, 1e-9) ** 3))
    M = (M0 + n_deg_per_day * (t_jd - t0_jd)) % 360.0

    r_helio = _keplerian_to_helio(a, e, i, node, peri, M)
    rho = r_helio - earth_pos  # geocentric vector

    ra = np.degrees(np.arctan2(rho[1], rho[0])) % 360.0
    dec = np.degrees(np.arctan2(rho[2], np.hypot(rho[0], rho[1])))
    return float(ra), float(dec)


def _angular_sep(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Angular separation [deg] between two ICRS positions."""
    r1, d1, r2, d2 = map(np.radians, [ra1, dec1, ra2, dec2])
    cos_sep = (
        np.sin(d1) * np.sin(d2)
        + np.cos(d1) * np.cos(d2) * np.cos(r1 - r2)
    )
    return float(np.degrees(np.arccos(np.clip(cos_sep, -1.0, 1.0))))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_orbital_elements(
    ra_dec_list: list[tuple[float, float]],
    times_jd: list[float],
) -> dict | None:
    """
    Fit Keplerian orbital elements to a sequence of observed (RA, Dec) positions.

    Uses scipy Nelder-Mead to minimise the sum of squared angular residuals
    between observed and modelled sky positions.

    Args:
        ra_dec_list — list of (ra_deg, dec_deg) for each detection
        times_jd    — Julian dates corresponding to each detection

    Returns:
        dict with keys: a [AU], e, i [deg], node [deg], peri [deg], period [yr]
        or None if fewer than 3 observations or optimisation fails.

    Note:
        Orbit determination from observations taken within a single session
        (minutes apart) is geometrically ill-conditioned. More observations
        spread over days improve accuracy significantly.
    """
    if len(ra_dec_list) < 3:
        logger.warning("Need ≥3 positions for orbit determination, got %d", len(ra_dec_list))
        return None

    # Precompute Earth positions once (Astropy ERFA ephemeris, no network)
    earth_positions = [_earth_pos_au(t) for t in times_jd]
    # Use Skyfield timescale to validate Julian dates
    for t_jd in times_jd:
        _TS.tt_jd(t_jd)  # raises if JD is nonsensical

    t0 = times_jd[len(times_jd) // 2]

    def total_residual(params: list) -> float:
        a, e, i, node, peri, M0 = params
        if not (0.1 < a < 200 and 0.0 <= e < 1.0):
            return 1e12
        total = 0.0
        for (ra_obs, dec_obs), t, R in zip(ra_dec_list, times_jd, earth_positions):
            ra_p, dec_p = _predicted_radec(a, e, i, node, peri, M0, t0, t, R)
            if ra_p is None:
                return 1e12
            total += _angular_sep(ra_obs, dec_obs, ra_p, dec_p) ** 2
        return total

    # Try several starting points to avoid local minima
    initial_guesses = [
        [2.5, 0.50, 15.0,  60.0, 120.0,   0.0],
        [5.0, 0.70, 30.0, 160.0, 250.0,  90.0],
        [1.5, 0.30, 10.0, 270.0,  45.0, 180.0],
        [3.0, 0.85, 50.0, 340.0, 200.0, 270.0],
    ]

    best = None
    for x0 in initial_guesses:
        try:
            res = minimize(
                total_residual,
                x0,
                method="Nelder-Mead",
                options={"maxiter": 20000, "xatol": 1e-5, "fatol": 1e-7},
            )
            if best is None or res.fun < best.fun:
                best = res
        except Exception as exc:
            logger.debug("Optimisation attempt failed: %s", exc)

    if best is None or best.fun > 5.0:
        logger.warning(
            "Orbit determination poor fit (residual=%.4f deg²)",
            best.fun if best else -1,
        )
        return None

    a, e, i, node, peri, M0 = best.x
    e = abs(e)

    period = (
        float(2.0 * np.pi * np.sqrt(max(a, 0) ** 3 / _MU) / 365.25)
        if 0.0 <= e < 1.0 and a > 0
        else None
    )

    return {
        "a": float(a),
        "e": float(e),
        "i": float(i % 180.0),
        "node": float(node % 360.0),
        "peri": float(peri % 360.0),
        "period": period,
    }
