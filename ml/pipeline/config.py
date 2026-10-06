"""
ml.pipeline.config — Build configuration for the Layer 7 dataset pipeline.

All pipeline parameters live here so that build behaviour is fully
explicit and auditable.  The configuration is also embedded verbatim
into the output metadata JSON so that any dataset artefact can be
traced back to the exact settings that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    """Configuration for the orbital feature dataset builder.

    Parameters
    ----------
    gp_csv_path:
        Path to the CelesTrak GP CSV file (source of orbital elements).
    output_parquet_path:
        Destination path for the ML-ready Parquet dataset.
    output_metadata_path:
        Destination path for the JSON metadata sidecar.
    window_hours:
        Total propagation window length in hours, centred on each
        satellite's GP epoch.  Default is 24 hours (+/-12 h from epoch).
    step_minutes:
        Sampling interval in minutes.  Default 15 minutes yields
        97 observations per satellite over a 24-hour window.
    max_satellites:
        Maximum number of satellites to include, selected by ascending
        NORAD_CAT_ID (deterministic).  Set to None to process the full
        GP dataset.
    max_sgp4_error_pct:
        Fraction (%) of rows allowed to have sgp4_error != 0 before a
        warning is emitted.  This is a warning threshold, not a hard
        failure.
    train_frac:
        Fraction of each satellite's observations assigned to "train".
        Split is chronological (by t_offset_minutes).
    val_frac:
        Fraction assigned to "val".  The remaining fraction is "test".
    """

    gp_csv_path: str = "data/raw/active_satellites_gp.csv"
    output_parquet_path: str = "data/processed/orbital_features.parquet"
    output_metadata_path: str = "data/processed/orbital_features_metadata.json"

    # Propagation window and sampling
    window_hours: float = 24.0
    step_minutes: float = 15.0

    # Satellite selection (deterministic by NORAD_CAT_ID sort)
    max_satellites: int | None = 200

    # Quality thresholds
    max_sgp4_error_pct: float = 5.0

    # Per-satellite chronological split fractions
    train_frac: float = 0.60
    val_frac: float = 0.20
    # test_frac = 1.0 - train_frac - val_frac

    def n_steps(self) -> int:
        """Number of observations per satellite for this configuration."""
        return int(self.window_hours * 60.0 / self.step_minutes) + 1

    def to_dict(self) -> dict:
        """Return configuration as a plain dict for metadata serialisation."""
        return {
            "gp_csv_path": self.gp_csv_path,
            "output_parquet_path": self.output_parquet_path,
            "output_metadata_path": self.output_metadata_path,
            "window_hours": self.window_hours,
            "step_minutes": self.step_minutes,
            "n_steps_per_satellite": self.n_steps(),
            "max_satellites": self.max_satellites,
            "max_sgp4_error_pct": self.max_sgp4_error_pct,
            "train_frac": self.train_frac,
            "val_frac": self.val_frac,
            "test_frac": round(1.0 - self.train_frac - self.val_frac, 6),
        }
