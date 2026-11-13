"""CDM Conjunction Data Message parser.

Supports a simplified CCSDS-compatible key = value text format.
No external dependencies beyond numpy (for PSD validation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CDMObject:
    """Metadata and covariance for one object in a CDM."""
    object_designator: str
    object_name: str
    # 6x6 RTN or TEME covariance, or None if absent.
    # For the simplified format we store a 3x3 position-only covariance.
    covariance_matrix: Optional[list[list[float]]]  # 3x3 position covariance
    covariance_frame: str  # 'RTN' | 'TEME' | 'UNKNOWN'


@dataclass
class CDMRecord:
    """Parsed Conjunction Data Message record."""
    tca: datetime                       # Time of Closest Approach (UTC, aware)
    relative_position_r_km: float       # Radial component (km)
    relative_position_t_km: float       # In-track component (km)
    relative_position_n_km: float       # Cross-track component (km)
    relative_speed_km_s: float          # Relative speed at TCA (km/s)
    object1: CDMObject
    object2: CDMObject
    raw_text: str                       # Unmodified input text


# ---------------------------------------------------------------------------
# Covariance helpers
# ---------------------------------------------------------------------------

def validate_covariance_psd(cov: list[list[float]]) -> bool:
    """Check whether a 3×3 matrix is positive semi-definite.

    Uses numpy's Cholesky decomposition: a matrix is PSD if and only if
    the decomposition succeeds (numpy raises LinAlgError for non-PSD).
    A tiny regularisation ε·I is added to handle the borderline semi-definite
    case (det ≈ 0 but eigenvalues ≥ 0).

    Parameters
    ----------
    cov:
        3×3 matrix as a list of lists of floats.

    Returns
    -------
    bool
        True if the matrix is positive semi-definite, False otherwise.
    """
    arr = np.array(cov, dtype=float)
    if arr.shape != (3, 3):
        return False
    # Symmetrise to suppress floating-point asymmetry
    arr = 0.5 * (arr + arr.T)
    # Small regularisation for the semi-definite boundary
    eps = 1e-12 * np.trace(arr)
    arr_reg = arr + eps * np.eye(3)
    try:
        np.linalg.cholesky(arr_reg)
        return True
    except np.linalg.LinAlgError:
        return False


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_kvp(text: str) -> dict[str, str]:
    """Parse key = value lines from CDM text, ignoring blank and comment lines."""
    kvp: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("COMMENT") or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            kvp[key.strip().upper()] = value.strip()
    return kvp


def _parse_tca(raw: str) -> datetime:
    """Parse an ISO-8601 TCA string to an aware UTC datetime."""
    raw = raw.strip()
    # Normalise trailing Z
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"TCA is not a valid ISO-8601 timestamp: {raw!r}") from exc
    if dt.tzinfo is None:
        # Assume UTC for tz-naive timestamps
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_3x3_cov(kvp: dict[str, str]) -> Optional[list[list[float]]]:
    """Extract the 3×3 RTN position covariance from parsed key-value pairs.

    Required keys: COV_RR, COV_RT, COV_RN, COV_TT, COV_TN, COV_NN.
    Returns None if any required key is absent.
    """
    required = ("COV_RR", "COV_RT", "COV_RN", "COV_TT", "COV_TN", "COV_NN")
    if not all(k in kvp for k in required):
        return None

    rr = float(kvp["COV_RR"])
    rt = float(kvp["COV_RT"])
    rn = float(kvp["COV_RN"])
    tt = float(kvp["COV_TT"])
    tn = float(kvp["COV_TN"])
    nn = float(kvp["COV_NN"])

    # Symmetric 3×3 matrix in RTN order: [R, T, N]
    cov = [
        [rr, rt, rn],
        [rt, tt, tn],
        [rn, tn, nn],
    ]
    return cov


def parse_cdm(text: str) -> CDMRecord:
    """Parse a simplified CDM text into a :class:`CDMRecord`.

    Supported keys
    --------------
    TCA                 ISO-8601 timestamp (required)
    RELATIVE_POSITION_R Radial component in km
    RELATIVE_POSITION_T In-track component in km
    RELATIVE_POSITION_N Cross-track component in km
    RELATIVE_SPEED      Relative speed in km/s
    OBJECT1_DESIGNATOR  Object 1 catalogue ID
    OBJECT1_NAME        Object 1 common name
    OBJECT2_DESIGNATOR  Object 2 catalogue ID
    OBJECT2_NAME        Object 2 common name
    COV_FRAME           Covariance reference frame (default: RTN)
    COV_RR              (R,R) element of position covariance (km²)
    COV_RT, COV_RN      Off-diagonal elements
    COV_TT, COV_TN      T row elements
    COV_NN              (N,N) element

    Raises
    ------
    ValueError
        If TCA is missing or the covariance matrix is not positive semi-definite.
    """
    kvp = _parse_kvp(text)

    # TCA is mandatory
    if "TCA" not in kvp:
        raise ValueError("CDM is missing the required TCA (Time of Closest Approach) field.")

    tca = _parse_tca(kvp["TCA"])

    # Relative geometry — default 0.0 for absent optional fields
    rel_r = float(kvp.get("RELATIVE_POSITION_R", 0.0))
    rel_t = float(kvp.get("RELATIVE_POSITION_T", 0.0))
    rel_n = float(kvp.get("RELATIVE_POSITION_N", 0.0))
    rel_speed = float(kvp.get("RELATIVE_SPEED", 0.0))

    # Covariance
    cov_frame = kvp.get("COV_FRAME", "RTN").upper()
    cov_matrix = _build_3x3_cov(kvp)

    if cov_matrix is not None and not validate_covariance_psd(cov_matrix):
        raise ValueError(
            "The covariance matrix extracted from the CDM is not positive semi-definite. "
            "Check COV_RR/TT/NN diagonal entries and ensure the matrix is physically valid."
        )

    # Objects — shared covariance in this simplified format (single combined block)
    obj1 = CDMObject(
        object_designator=kvp.get("OBJECT1_DESIGNATOR", "UNKNOWN"),
        object_name=kvp.get("OBJECT1_NAME", "OBJECT1"),
        covariance_matrix=cov_matrix,
        covariance_frame=cov_frame if cov_matrix is not None else "UNKNOWN",
    )
    obj2 = CDMObject(
        object_designator=kvp.get("OBJECT2_DESIGNATOR", "UNKNOWN"),
        object_name=kvp.get("OBJECT2_NAME", "OBJECT2"),
        # In simplified CDMs a single combined covariance block is shared;
        # object2 gets None so callers can distinguish combined vs split data.
        covariance_matrix=None,
        covariance_frame="UNKNOWN",
    )

    return CDMRecord(
        tca=tca,
        relative_position_r_km=rel_r,
        relative_position_t_km=rel_t,
        relative_position_n_km=rel_n,
        relative_speed_km_s=rel_speed,
        object1=obj1,
        object2=obj2,
        raw_text=text,
    )
