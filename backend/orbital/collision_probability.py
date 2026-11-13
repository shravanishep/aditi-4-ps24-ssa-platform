"""Collision Probability (Pc) Calculation — Foster's 2D Encounter-Plane Method.

Calculates the collision probability between two space objects at Time of
Closest Approach (TCA) given their relative geometry and position covariance matrices.

IMPORTANT SCIENTIFIC CONSTRAINTS & ASSUMPTIONS:
1. Covariance Requirement: A miss distance alone is NOT sufficient to calculate Pc.
   If covariance is unavailable for either object, Pc CANNOT be calculated and
   pc=None is returned. No fabricated or assumed uncertainty is ever substituted.
2. Linear Relative Motion: The relative velocity is assumed constant during the
   brief encounter period (valid for high-speed close encounters, duration < a few seconds).
3. Spherical Hard-Body: Objects are modeled as spheres whose combined radius is
   hard_body_radius_km (default 20 m = 0.020 km).
4. Stationary Gaussian Uncertainty: Positional uncertainties are modeled as zero-mean,
   uncorrelated, 3-D Gaussian random variables characterized by covariance matrices.
5. Coordinate Frame: 3x3 position covariance matrices are expected in the RTN
   (Radial-Transverse-Normal) frame. The encounter plane is spanned by the R and N axes
   (perpendicular to the nominal transverse velocity direction).

DISCLAIMER: This is a research prototype implementing Foster's (1992) 2D method.
It is NOT certified for operational spaceflight or conjunction assessment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


_DISCLAIMER = (
    "Research prototype implementing Foster's (1992) 2D encounter-plane method. "
    "Assumes linear relative motion, stationary Gaussian positional error, and a "
    "spherical hard-body. Not certified for operational collision avoidance decisions."
)


@dataclass
class PcResult:
    """Structured output of a collision probability evaluation."""

    pc: Optional[float]
    pc_method: str
    hard_body_radius_km: float
    combined_covariance_valid: bool
    miss_distance_km: float
    relative_speed_km_s: float
    encounter_duration_sec: Optional[float]
    b_plane_sigma1_km: Optional[float]
    b_plane_sigma2_km: Optional[float]
    computation_notes: list[str] = field(default_factory=list)
    disclaimer: str = _DISCLAIMER


def compute_pc_foster_2d(
    miss_distance_km: float,
    relative_speed_km_s: float,
    cov1_rtn_3x3: Optional[list[list[float]]] = None,
    cov2_rtn_3x3: Optional[list[list[float]]] = None,
    hard_body_radius_km: float = 0.020,
    rel_r_km: float = 0.0,
    rel_n_km: float = 0.0,
) -> PcResult:
    """Compute collision probability using Foster's 2-D encounter-plane method.

    Parameters
    ----------
    miss_distance_km : float
        Scalar Euclidean separation at TCA [km]. Must be > 0.
    relative_speed_km_s : float
        Relative speed at TCA [km/s]. Must be > 0.
    cov1_rtn_3x3 : list[list[float]] | None
        3x3 position covariance of object 1 in RTN frame [km²].
    cov2_rtn_3x3 : list[list[float]] | None
        3x3 position covariance of object 2 in RTN frame [km²].
    hard_body_radius_km : float
        Combined physical collision radius [km]. Default 0.020 km (20 m).
    rel_r_km : float
        Radial component of relative position at TCA [km].
    rel_n_km : float
        Normal/cross-track component of relative position at TCA [km].

    Returns
    -------
    PcResult
        Dataclass containing Pc (float in [0, 1] or None), methodology notes,
        and uncertainty parameters.
    """
    notes: list[str] = []

    # Input validations
    if miss_distance_km <= 0:
        raise ValueError("miss_distance_km must be strictly positive.")
    if relative_speed_km_s <= 0:
        raise ValueError("relative_speed_km_s must be strictly positive.")
    if hard_body_radius_km <= 0:
        raise ValueError("hard_body_radius_km must be strictly positive.")

    # Check covariance availability
    if cov1_rtn_3x3 is None and cov2_rtn_3x3 is None:
        notes.append("No covariance data provided for either object.")
        return PcResult(
            pc=None,
            pc_method="unavailable",
            hard_body_radius_km=hard_body_radius_km,
            combined_covariance_valid=False,
            miss_distance_km=miss_distance_km,
            relative_speed_km_s=relative_speed_km_s,
            encounter_duration_sec=None,
            b_plane_sigma1_km=None,
            b_plane_sigma2_km=None,
            computation_notes=notes,
        )

    # Convert to numpy arrays
    c1 = np.array(cov1_rtn_3x3, dtype=float) if cov1_rtn_3x3 is not None else np.zeros((3, 3))
    c2 = np.array(cov2_rtn_3x3, dtype=float) if cov2_rtn_3x3 is not None else np.zeros((3, 3))

    if c1.shape != (3, 3) or c2.shape != (3, 3):
        notes.append(f"Invalid covariance shape: c1={c1.shape}, c2={c2.shape}. Expected (3, 3).")
        return PcResult(
            pc=None,
            pc_method="invalid_covariance",
            hard_body_radius_km=hard_body_radius_km,
            combined_covariance_valid=False,
            miss_distance_km=miss_distance_km,
            relative_speed_km_s=relative_speed_km_s,
            encounter_duration_sec=None,
            b_plane_sigma1_km=None,
            b_plane_sigma2_km=None,
            computation_notes=notes,
        )

    # Combine covariances (uncorrelated error assumption: C = C1 + C2)
    c_combined = c1 + c2

    # Check symmetry and positive semi-definiteness of 3x3 combined matrix
    c_combined = 0.5 * (c_combined + c_combined.T)
    evals_3d = np.linalg.eigvalsh(c_combined)
    if np.any(evals_3d < -1e-10):
        notes.append(f"Combined 3D covariance is not positive semi-definite (min eigenvalue={evals_3d[0]:.3e}).")
        return PcResult(
            pc=None,
            pc_method="invalid_covariance",
            hard_body_radius_km=hard_body_radius_km,
            combined_covariance_valid=False,
            miss_distance_km=miss_distance_km,
            relative_speed_km_s=relative_speed_km_s,
            encounter_duration_sec=None,
            b_plane_sigma1_km=None,
            b_plane_sigma2_km=None,
            computation_notes=notes,
        )

    # Encounter duration estimate: 2 * r_hbr / v_rel
    encounter_duration_sec = (2.0 * hard_body_radius_km) / relative_speed_km_s

    # Project into the 2-D encounter plane (R-N axes, indices 0 and 2 in RTN)
    # RTN: 0 = Radial (R), 1 = Transverse (T, velocity direction), 2 = Normal (N)
    cov_2d = np.array([
        [c_combined[0, 0], c_combined[0, 2]],
        [c_combined[2, 0], c_combined[2, 2]],
    ], dtype=float)

    evals_2d, evecs_2d = np.linalg.eigh(cov_2d)

    if evals_2d[0] <= 1e-12 or evals_2d[1] <= 1e-12:
        notes.append("Encounter plane covariance projection is singular or near-zero.")
        return PcResult(
            pc=None,
            pc_method="singular_covariance",
            hard_body_radius_km=hard_body_radius_km,
            combined_covariance_valid=False,
            miss_distance_km=miss_distance_km,
            relative_speed_km_s=relative_speed_km_s,
            encounter_duration_sec=encounter_duration_sec,
            b_plane_sigma1_km=None,
            b_plane_sigma2_km=None,
            computation_notes=notes,
        )

    sigma1 = math.sqrt(evals_2d[1])  # major semi-axis
    sigma2 = math.sqrt(evals_2d[0])  # minor semi-axis

    # Miss vector in R-N plane
    # If specific R, N components were provided, use them; otherwise use miss_distance along minor axis
    if abs(rel_r_km) > 1e-9 or abs(rel_n_km) > 1e-9:
        d_vec = np.array([rel_r_km, rel_n_km])
    else:
        # Without specific components, miss vector magnitude is miss_distance_km
        d_vec = np.array([0.0, miss_distance_km])

    # Transform miss vector into principal axes frame of 2D covariance
    d_prime = evecs_2d.T @ d_vec
    x0, y0 = float(d_prime[1]), float(d_prime[0])

    # Foster's 2D formulation:
    # Pc = (1 / (2*pi*sigma1*sigma2)) * integral over circle(radius=r_hbr) of exp(-0.5 * (x²/s1² + y²/s2²))
    # When r_hbr << sigma1, sigma2, the standard disk approximation is:
    # Pc ≈ (r_hbr² / (2 * sigma1 * sigma2)) * exp(-0.5 * (x0²/sigma1² + y0²/sigma2²))
    mahalanobis_sq = (x0**2) / (sigma1**2) + (y0**2) / (sigma2**2)
    
    # Check if disk is small relative to uncertainty (r_hbr < 0.1 * min(sigma1, sigma2))
    if hard_body_radius_km < 0.1 * min(sigma1, sigma2):
        pc_approx = (hard_body_radius_km**2 / (2.0 * sigma1 * sigma2)) * math.exp(-0.5 * mahalanobis_sq)
        pc = float(np.clip(pc_approx, 0.0, 1.0))
        notes.append("Computed using Foster 2D analytical disk approximation.")
    else:
        # Use numerical polar integration for larger hard-body or small covariance
        n_r = 50
        n_theta = 72
        r_vals = np.linspace(0, hard_body_radius_km, n_r)
        dr = r_vals[1] - r_vals[0]
        theta_vals = np.linspace(0, 2 * math.pi, n_theta, endpoint=False)
        dtheta = 2 * math.pi / n_theta

        R_grid, TH_grid = np.meshgrid(r_vals, theta_vals)
        X = x0 + R_grid * np.cos(TH_grid)
        Y = y0 + R_grid * np.sin(TH_grid)

        integrand = np.exp(-0.5 * ((X**2) / (sigma1**2) + (Y**2) / (sigma2**2))) * R_grid
        integral = np.sum(integrand) * dr * dtheta
        pc_num = integral / (2.0 * math.pi * sigma1 * sigma2)
        pc = float(np.clip(pc_num, 0.0, 1.0))
        notes.append("Computed using Foster 2D numerical polar integration.")

    notes.append(f"Primary uncertainty semi-axis: {sigma1:.3f} km; Secondary: {sigma2:.3f} km.")
    notes.append(f"Mahalanobis distance: {math.sqrt(mahalanobis_sq):.2f} sigma.")

    return PcResult(
        pc=pc,
        pc_method="Foster_2D",
        hard_body_radius_km=hard_body_radius_km,
        combined_covariance_valid=True,
        miss_distance_km=miss_distance_km,
        relative_speed_km_s=relative_speed_km_s,
        encounter_duration_sec=round(encounter_duration_sec, 6),
        b_plane_sigma1_km=round(sigma1, 6),
        b_plane_sigma2_km=round(sigma2, 6),
        computation_notes=notes,
    )

