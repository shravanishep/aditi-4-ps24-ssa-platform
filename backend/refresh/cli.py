"""
backend.refresh.cli — Command-line interface for manual and scheduled dataset refresh.

Examples
--------
Show current refresh status:
    python -m backend.refresh.cli --status

Perform a dry-run validation of active satellites without overwriting local files:
    python -m backend.refresh.cli --sources active_satellites_gp --dry-run

Perform a full manual refresh:
    python -m backend.refresh.cli

Download refreshed files to a custom directory:
    python -m backend.refresh.cli --output-dir data/staging
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from backend.refresh.config import RefreshConfig, RefreshSourceConfig
from backend.refresh.metadata import RefreshMetadata
from backend.refresh.scheduler import PeriodicRefreshScheduler
from backend.refresh.service import DataRefreshService

logger = logging.getLogger("backend.refresh.cli")


def print_status(metadata_path: Path) -> None:
    """Print formatted summary of current refresh metadata."""
    meta = RefreshMetadata.load(metadata_path)
    print("=" * 70)
    print("ADITI SSA PLATFORM — CATALOGUE REFRESH STATUS")
    print("=" * 70)
    print(f"Metadata file:            {metadata_path.resolve()}")
    print(f"Status:                   {meta.status.upper()}")
    print(f"Last Attempt:             {meta.last_refresh_attempt or 'Never'}")
    print(f"Last Successful Refresh:  {meta.last_successful_refresh or 'Never'}")
    print("-" * 70)
    print("Configured Sources:")
    if not meta.sources:
        print("  (No sources recorded yet)")
    for name, src in meta.sources.items():
        status_str = "OK" if src.success else f"FAILED: {src.error_message}"
        print(f"  [{name}]")
        print(f"    URL:                 {src.url}")
        print(f"    Destination:         {src.dest_path}")
        print(f"    Retrieved At:        {src.retrieved_at}")
        print(f"    Status:              {status_str}")
        print(f"    Records Valid/Total: {src.valid_records} / {src.total_records}")
        if src.newest_epoch:
            print(f"    Epoch Range:         {src.oldest_epoch} -> {src.newest_epoch}")
            print(f"    Max Epoch Age:       {src.max_epoch_age_days} days")
            print(f"    Stale Records:       {src.stale_records_count}")
        print()
    print("=" * 70)


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m backend.refresh.cli",
        description="ADITI SSA Platform — Orbital Data Refresh CLI",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print current refresh status and metadata, then exit.",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Comma-separated source names to refresh (e.g. 'active_satellites_gp,satcat').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate incoming data without writing or overwriting files.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory where downloaded datasets will be written (default: data/raw).",
    )
    parser.add_argument(
        "--metadata-path",
        type=str,
        default=None,
        help="Path to refresh metadata JSON file (default: data/catalog_refresh_metadata.json).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP request timeout in seconds (default: 15.0).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Maximum HTTP retry attempts (default: 3).",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run periodic scheduler in foreground.",
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=24.0,
        help="Interval in hours for periodic scheduler (default: 24.0).",
    )
    return parser


def main(args: list[str] | None = None) -> int:
    """CLI execution entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = build_parser()
    opts = parser.parse_args(args)

    cfg = RefreshConfig.default()
    if opts.timeout:
        cfg.http_timeout_seconds = opts.timeout
    if opts.retries:
        cfg.max_retries = opts.retries
    if opts.metadata_path:
        cfg.metadata_path = Path(opts.metadata_path)
    if opts.output_dir:
        out_dir = Path(opts.output_dir)
        for s in cfg.sources:
            s.dest_path = out_dir / Path(s.dest_path).name

    meta_path = cfg.get_metadata_path()

    if opts.status:
        print_status(meta_path)
        return 0

    service = DataRefreshService(config=cfg)

    source_filter = [s.strip() for s in opts.sources.split(",")] if opts.sources else None

    if opts.schedule:
        interval_sec = opts.interval_hours * 3600.0
        print(f"Starting Periodic Refresh Scheduler (interval={opts.interval_hours:.1f} hours)...")
        print("Press Ctrl+C to terminate.")
        scheduler = PeriodicRefreshScheduler(
            service=service,
            interval_seconds=interval_sec,
            run_immediately=True,
        )
        scheduler.start()
        try:
            while scheduler.is_running:
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\nShutting down scheduler...")
            scheduler.stop()
        return 0

    print("Executing orbital data refresh...")
    if opts.dry_run:
        print("[DRY-RUN MODE] Files will be validated but NOT written to disk.")

    result = service.refresh_all(source_names=source_filter, dry_run=opts.dry_run)
    print("\nRefresh complete. Status:", result.status.upper())
    for name, s in result.sources.items():
        if s.success:
            print(f"  + {name}: SUCCESS ({s.valid_records} valid records, bytes: {s.bytes_downloaded})")
        else:
            print(f"  - {name}: FAILED ({s.error_message})")

    return 0 if result.status in ("success", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
