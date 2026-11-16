"""
ml.pipeline.regime_sampler — Stratified regime-diverse satellite selection.

This module selects a balanced, diverse sample of satellites across orbital
regimes (LEO, MEO, GEO, HEO) for ML dataset expansion (v2+).

Design goals
------------
- Deterministic: given same GP CSV and config, produces identical selection.
- Regime-aware: explicitly controls per-regime satellite quotas.
- Honest: reports actual counts achieved, never inflates.
- Safe: does not modify the GP dataframe; returns a filtered copy.

Regime classification boundaries
---------------------------------
LEO : MEAN_MOTION >= 11.25 rev/day        (altitude roughly < 2,000 km)
MEO : 2.0 <= MEAN_MOTION < 11.25          (altitude 2,000 – 35,000 km)
GEO : 0.99 <= MEAN_MOTION < 2.0 (narrow) (altitude ~35,786 km)
HEO : MEAN_MOTION < 0.99                  (highly elliptical / deep space)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import pandas as pd


# ---------------------------------------------------------------------------
# Regime classification helpers
# ---------------------------------------------------------------------------

_LEO_MM_MIN: float = 11.25    # rev/day lower boundary for LEO
_MEO_MM_MIN: float = 2.0      # rev/day lower boundary for MEO
_GEO_MM_LOW: float = 0.99     # rev/day approximate GEO lower boundary
_GEO_MM_HIGH: float = 2.0     # rev/day approximate GEO upper boundary


def classify_regime(mean_motion_rev_day: float) -> str:
    """Return orbital regime label for a given mean motion (rev/day)."""
    if mean_motion_rev_day >= _LEO_MM_MIN:
        return "LEO"
    elif mean_motion_rev_day >= _MEO_MM_MIN:
        return "MEO"
    elif mean_motion_rev_day >= _GEO_MM_LOW:
        return "GEO"
    else:
        return "HEO"


def add_regime_column(gp_df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'regime' string column to the GP DataFrame. Non-destructive."""
    out = gp_df.copy()
    out["regime"] = out["MEAN_MOTION"].apply(classify_regime)
    return out


# ---------------------------------------------------------------------------
# Stratified sampler configuration
# ---------------------------------------------------------------------------

@dataclass
class RegimeSamplerConfig:
    """Per-regime satellite quotas for stratified dataset construction.

    Parameters
    ----------
    leo_count : int
        Maximum LEO satellites to include. LEO is by far the largest regime.
    meo_count : int
        Maximum MEO satellites (GPS/GLONASS bands). Often only ~100-200 available.
    geo_count : int
        Maximum GEO satellites. Limited to ~500 in active catalogue.
    heo_count : int
        Maximum HEO/deep-space satellites. Usually < 150 valid records.
    sort_by : str
        GP column to sort within each regime before taking the head.
        Default "NORAD_CAT_ID" gives deterministic reproducible selection.
    """
    leo_count: int = 150
    meo_count: int = 20
    geo_count: int = 20
    heo_count: int = 10
    sort_by: str = "NORAD_CAT_ID"

    @property
    def total_target(self) -> int:
        return self.leo_count + self.meo_count + self.geo_count + self.heo_count


# ---------------------------------------------------------------------------
# Main selection function
# ---------------------------------------------------------------------------

def select_regime_diverse_satellites(
    gp_df: pd.DataFrame,
    config: RegimeSamplerConfig | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Return a stratified regime-diverse subset of the GP DataFrame.

    Parameters
    ----------
    gp_df : pd.DataFrame
        Full GP orbital element DataFrame (from load_gp_data()).
    config : RegimeSamplerConfig | None
        Per-regime quotas. Defaults to RegimeSamplerConfig().
    verbose : bool
        Print per-regime selection counts.

    Returns
    -------
    pd.DataFrame
        Filtered GP DataFrame (subset of input rows, deterministic order).
        A 'regime' column is added for downstream audit.

    Notes
    -----
    - Selection is deterministic: sorted by config.sort_by within each regime,
      then head(quota) taken.
    - If a regime has fewer available satellites than its quota, all available
      are taken and the shortfall is reported.
    - The returned DataFrame is a copy; original gp_df is not modified.
    """
    cfg = config or RegimeSamplerConfig()

    tagged = add_regime_column(gp_df)

    quotas: dict[str, int] = {
        "LEO": cfg.leo_count,
        "MEO": cfg.meo_count,
        "GEO": cfg.geo_count,
        "HEO": cfg.heo_count,
    }

    selected_parts: list[pd.DataFrame] = []
    regime_report: dict[str, dict] = {}

    for regime, quota in quotas.items():
        regime_df = tagged[tagged["regime"] == regime].copy()
        available = len(regime_df)
        actual = min(available, quota)

        # Sort for determinism, then take head
        regime_df = regime_df.sort_values(cfg.sort_by).head(actual)
        selected_parts.append(regime_df)

        regime_report[regime] = {
            "available": available,
            "quota": quota,
            "selected": actual,
            "shortfall": max(0, quota - available),
        }

        if verbose:
            shortfall_note = (
                f" (quota {quota}, only {available} available)"
                if actual < quota else ""
            )
            print(
                f"  [Regime Sampler] {regime}: selected {actual}{shortfall_note}",
                file=sys.stderr,
                flush=True,
            )

    combined = pd.concat(selected_parts, ignore_index=True)
    total_selected = len(combined)

    if verbose:
        print(
            f"  [Regime Sampler] Total selected: {total_selected} satellites "
            f"(target: {cfg.total_target})",
            file=sys.stderr,
            flush=True,
        )

    return combined, regime_report
