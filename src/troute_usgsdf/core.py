from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import read_troute_window
from .gpkg import read_gage_crosswalk
from .usgs import fetch_usgs_streamflow, interpolate_to_grid

# fetch a day of padding on each side of the simulation window so the
# grid edges can be interpolated rather than extrapolated
PAD = pd.Timedelta(days=1)


def _incompleteness_reason(
    cached: pd.DataFrame, required_wb_ids: set[int], target_index: pd.DatetimeIndex
) -> str | None:
    """Return None if `cached` already has every required row and timestamp, else why not."""
    missing_rows = required_wb_ids - set(cached.index)
    if missing_rows:
        return f"missing {len(missing_rows)} waterbody id(s): {sorted(missing_rows)}"
    missing_dates = target_index.difference(cached.columns)
    if not missing_dates.empty:
        return (
            f"missing {len(missing_dates)} timestamp(s) "
            f"({missing_dates.min()} to {missing_dates.max()})"
        )
    return None


def resolve_ngiab_paths(ngiab_data_dir: Path) -> tuple[Path, Path, Path]:
    """Derive gpkg/troute-config/output paths from an NGIAB data directory."""
    config_dir = Path(ngiab_data_dir) / "config"
    matches = sorted(config_dir.glob("*.gpkg"))
    if not matches:
        raise FileNotFoundError(f"No .gpkg file found in {config_dir}")
    if len(matches) > 1:
        raise FileNotFoundError(f"Multiple .gpkg files found in {config_dir}: {matches}")

    gpkg_path = matches[0]
    troute_config_path = config_dir / "troute.yaml"
    output_path = config_dir / "troute_da.feather"
    return gpkg_path, troute_config_path, output_path


def build_usgs_da_dataframe(
    gpkg_path: Path,
    troute_config_path: Path,
    output_path: Path,
) -> pd.DataFrame:
    """Build a waterbody-id x time dataframe of USGS streamflow (m3/s) and write it to `output_path`.

    The time grid and window are taken from `troute_config_path` (start_datetime,
    forcing dt/nts); gage locations are crosswalked from `gpkg_path`.
    """
    window = read_troute_window(troute_config_path)
    target_index = pd.date_range(
        window.start, window.end, freq=pd.Timedelta(seconds=window.dt)
    )

    wb_to_gage = read_gage_crosswalk(gpkg_path)
    output_path = Path(output_path)

    if output_path.exists():
        try:
            cached = pd.read_feather(output_path)
        except Exception as e:
            print(f"Could not read existing {output_path} ({e}); refetching")
            cached = None
        if cached is not None:
            reason = _incompleteness_reason(cached, set(wb_to_gage), target_index)
            if reason is None:
                print(
                    f"{output_path} already covers {window.start} to {window.end} "
                    "for all required waterbody ids; skipping USGS fetch"
                )
                return cached
            print(f"{output_path} exists but is incomplete ({reason}); fetching from USGS")

    sites = sorted({f"USGS-{gage}" for gage in wb_to_gage.values()})

    observations = fetch_usgs_streamflow(sites, window.start - PAD, window.end + PAD)

    by_gage = {
        site.removeprefix("USGS-"): interpolate_to_grid(group, target_index)
        for site, group in observations.groupby("usgs_site_code")
    }
    empty = pd.Series(index=target_index, dtype="float64")
    rows = {wb: by_gage.get(gage, empty) for wb, gage in wb_to_gage.items()}

    usgs_df = pd.DataFrame(rows).T.astype("float32")
    usgs_df.columns = target_index

    output_path.parent.mkdir(parents=True, exist_ok=True)
    usgs_df.to_feather(output_path)

    return usgs_df
