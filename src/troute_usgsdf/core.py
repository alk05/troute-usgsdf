from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from .config import TrouteWindow, read_troute_window
from .gpkg import read_gage_crosswalk, read_gage_crosswalk_nwm
from .routelink import read_link_mask, read_route_link_gages
from .usgs import fetch_usgs_streamflow, interpolate_to_grid

# fetch a day of padding on each side of the simulation window so the
# grid edges can be interpolated rather than extrapolated
PAD = pd.Timedelta(days=1)


class EmptyDomainError(ValueError):
    """The domain (after any mask) contains no gauged ids, so there is nothing to fetch."""


# Key in the feather's Arrow schema metadata recording how the file was built, so a
# cached file is only reused when it was built with the same options.
_META_KEY = b"troute_usgsdf"


def _write_feather(df: pd.DataFrame, path: Path, build_options: dict) -> None:
    import pyarrow as pa
    from pyarrow import feather

    table = pa.Table.from_pandas(df)
    metadata = {**(table.schema.metadata or {}), _META_KEY: json.dumps(build_options).encode()}
    feather.write_feather(table.replace_schema_metadata(metadata), str(path))


def _read_feather(path: Path) -> tuple[pd.DataFrame, dict | None]:
    from pyarrow import feather

    table = feather.read_table(str(path))
    raw = (table.schema.metadata or {}).get(_META_KEY)
    return table.to_pandas(), (json.loads(raw) if raw is not None else None)


def _stale_reason(
    cached: pd.DataFrame,
    cached_options: dict | None,
    build_options: dict,
    required_ids: set[int],
    target_index: pd.DatetimeIndex,
) -> str | None:
    """Return None if `cached` is exactly what this run would build, else why not."""
    if cached_options is None:
        return "it has no build metadata (written by an older version)"
    if cached_options != build_options:
        return f"it was built with {cached_options}, this run uses {build_options}"
    cached_ids = set(cached.index)
    missing_rows = required_ids - cached_ids
    if missing_rows:
        return f"missing {len(missing_rows)} id(s): {sorted(missing_rows)}"
    extra_rows = cached_ids - required_ids
    if extra_rows:
        return f"has {len(extra_rows)} id(s) outside the requested domain/mask"
    if not pd.DatetimeIndex(cached.columns).equals(target_index):
        return (
            f"its time grid ({cached.columns.min()} to {cached.columns.max()}, "
            f"{len(cached.columns)} steps) differs from this run's "
            f"({target_index.min()} to {target_index.max()}, {len(target_index)} steps)"
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


def resolve_crosswalk(
    gpkg_path: Path | None = None,
    route_link_nc_path: Path | None = None,
    mask_path: Path | None = None,
) -> dict[int, str]:
    """Resolve mapping from output IDs (waterbody or NWM link) to USGS gage IDs.

    Returns:
        A dict of {output_id: gage_id}.
        - gpkg only: flowpath ID -> gage ID
        - gpkg + route-link: NWM link ID -> gage ID
        - route-link only: NWM link ID -> gage ID

    `mask_path` filters NWM link IDs, so it requires `route_link_nc_path`.
    """
    if route_link_nc_path is None:
        if gpkg_path is None:
            raise ValueError("Must provide at least one of gpkg_path or route_link_nc_path")
        if mask_path is not None:
            raise ValueError(
                "mask_path filters NWM link ids and requires route_link_nc_path; "
                "a gpkg-only crosswalk is keyed by flowpath id"
            )
        return read_gage_crosswalk(gpkg_path)

    mask = read_link_mask(mask_path) if mask_path is not None else None
    if gpkg_path is None:
        return read_route_link_gages(route_link_nc_path, mask=mask)

    wb_to_gage = read_gage_crosswalk_nwm(gpkg_path, route_link_nc_path, mask=mask)
    return {nwm: gage for gage, nwm in wb_to_gage.values() if nwm is not None}


def build_usgs_da_dataframe(
    output_path: Path,
    *,
    gpkg_path: Path | None = None,
    route_link_nc_path: Path | None = None,
    mask_path: Path | None = None,
    troute_config_path: Path | None = None,
    window: TrouteWindow | None = None,
    observed_steps: int | None = None,
) -> pd.DataFrame:
    """Build a waterbody-id x time dataframe of USGS streamflow (m3/s) and write it to `output_path`.

    The time grid and window are taken from `window`, or from `troute_config_path`
    (start_datetime, forcing dt/nts); gage locations come from `resolve_crosswalk`.

    If `observed_steps` is given, only the first `observed_steps` timesteps keep
    observations and the rest are set to NaN (forecast mode). If None, the full
    window is kept.
    """
    if observed_steps is not None and observed_steps < 1:
        raise ValueError(f"observed_steps must be >= 1 or None, got {observed_steps}")
    if window is None:
        if troute_config_path is None:
            raise ValueError("Must provide either troute_config_path or window")
        window = read_troute_window(troute_config_path)

    target_index = pd.date_range(
        window.start, window.end, freq=pd.Timedelta(seconds=window.dt)
    )

    id_to_gage = resolve_crosswalk(
        gpkg_path=gpkg_path,
        route_link_nc_path=route_link_nc_path,
        mask_path=mask_path,
    )
    if not id_to_gage:
        raise EmptyDomainError(
            "No gauged ids in the domain"
            + (f" after applying mask {mask_path}" if mask_path is not None else "")
        )
    required_ids = set(id_to_gage)
    output_path = Path(output_path)
    build_options = {
        "observed_steps": int(observed_steps) if observed_steps is not None else None,
        # the same ids can map to different gages if the gpkg/RouteLink changes
        "crosswalk_sha256": hashlib.sha256(
            json.dumps(sorted((int(k), str(v)) for k, v in id_to_gage.items())).encode()
        ).hexdigest(),
    }

    if output_path.exists():
        try:
            cached, cached_options = _read_feather(output_path)
        except Exception as e:
            print(f"Could not read existing {output_path} ({e}); refetching")
            cached = None
        if cached is not None:
            if cached.isna().all(axis=None):
                print(f"{output_path} contains only NaNs; refetching USGS data")
            else:
                reason = _stale_reason(
                    cached, cached_options, build_options, required_ids, target_index
                )
                if reason is None:
                    print(
                        f"{output_path} already covers {window.start} to {window.end} "
                        "for exactly the required ids; skipping USGS fetch"
                    )
                    return cached
                print(f"{output_path} exists but is stale ({reason}); fetching from USGS")

    sites = sorted({f"USGS-{gage}" for gage in id_to_gage.values() if gage})

    observations = fetch_usgs_streamflow(sites, window.start - PAD, window.end + PAD)

    by_gage = {
        site.removeprefix("USGS-"): interpolate_to_grid(group, target_index)
        for site, group in observations.groupby("usgs_site_code")
    }
    empty = pd.Series(index=target_index, dtype="float64")
    rows = {out_id: by_gage.get(gage, empty) for out_id, gage in id_to_gage.items()}

    usgs_df = pd.DataFrame(rows).T.astype("float32")
    usgs_df.columns = target_index
    usgs_df = usgs_df.sort_index()

    if observed_steps is not None and usgs_df.shape[1] > observed_steps:
        usgs_df.iloc[:, observed_steps:] = float("nan")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_feather(usgs_df, output_path, build_options)

    return usgs_df
