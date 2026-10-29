# troute-usgsdf

Builds a USGS streamflow dataframe shaped to fill
[t-route](https://github.com/NOAA-OWP/t-route)'s
`data_assimilation.usgs_df` directly, instead of writing individual USGS
timeslice NetCDF files for t-route to read back in.

The output is a feather file: one row per identifier (flowpath waterbody ID
from a hydrofabric geopackage, or NWM link ID from a RouteLink file), one column
per timestep on the simulation's time grid, values in m3/s (`float32`).

> **Status:** this repo only builds the dataframe. 
> To use it, add the path to the USGS dataframe to `troute.yaml` under `compute_parameters.data_assimilation_parameters.streamflow_da.da_from_feather: ./path/to/usgs_df.feather`.

This tool is intended to be used as a standalone CLI tool either via `uvx` or `uv tool install troute-usgsdf`.

```bash
uvx troute-usgsdf --ngiab-data-dir /path/to/ngiab/output
# or
uv tool install troute-usgsdf
makedf --ngiab-data-dir /path/to/ngiab/output
```

## Usage

Point it at an NGIAB run's data directory, and the geopackage, troute config,
and output path are all derived automatically
(`<dir>/config/*.gpkg`, `<dir>/config/troute.yaml`, `<dir>/config/troute_da.feather`):

```bash
uvx troute-usgsdf --ngiab-data-dir /path/to/ngiab/output
```

Or point at the three paths explicitly:

```bash
uvx troute-usgsdf \
  --gpkg /path/to/domain.gpkg \
  --troute-config /path/to/troute.yaml \
  --output /path/to/troute_da.feather
```

Or use a RouteLink `.nc` file (e.g. for NHD domains where no geopackage exists), with an optional link mask file:

```bash
uvx troute-usgsdf \
  --route-link /path/to/RouteLink.nc \
  --mask /path/to/link_mask.txt \
  --troute-config /path/to/troute.yaml \
  --output /path/to/troute_da.feather
```

### Specifying Time Windows

The simulation start/end/timestep can be read from `troute.yaml`
(`compute_parameters.restart_parameters.start_datetime`, and
`compute_parameters.forcing_parameters.dt`/`nts`), or specified directly without a YAML config:

```bash
uvx troute-usgsdf \
  --route-link /path/to/RouteLink.nc \
  --start "2026-06-19 04:00" \
  --nts 216 \
  --dt 300 \
  --output /path/to/troute_da.feather
```

`--start` and `--end` accept ISO-8601 or `"YYYY-MM-DD HH:MM"` strings. `--nts` specifies the number of timesteps, and `--dt` defaults to 300 seconds.

### Observation Truncation (`--observed-steps`)

In hindcast and forecast mode, future observations are not known at the time of forecast initialization. By default, `--observed-steps 2` keeps observations for the first two timesteps (five minutes under `dt=300`) and masks subsequent steps with `NaN`.

Pass `--observed-steps 0` to preserve observations across the full simulation window without truncation.

### CLI Reference

| Option | Description |
|---|---|
| `--ngiab-data-dir PATH` | Path to NGIAB run data directory (automatically derives gpkg, troute config, and output feather). |
| `--gpkg PATH` | Path to hydrofabric geopackage (optional if `--route-link` is given). |
| `--route-link PATH` | RouteLink `.nc` file containing NWM link IDs and USGS gages. |
| `--mask PATH` | Optional text file containing link IDs to filter the domain. |
| `--troute-config PATH` | Path to t-route `troute.yaml` config (alternative to `--start`). |
| `--start TEXT` | Simulation start time (`YYYY-MM-DD HH:MM` or ISO format). |
| `--end TEXT` | Simulation end time (paired with `--start`). |
| `--nts INTEGER` | Number of timesteps (paired with `--start` and `--dt`). |
| `--dt INTEGER` | Routing/forcing timestep in seconds (default: `300`). |
| `--output PATH` | Path to write the output `.feather` file. |
| `--observed-steps INTEGER` | Number of timesteps to keep populated before NaN truncation (default: `2`; `0` keeps full window). |

## Output Caching

If `--output` already exists and already contains every required identifier
and timestamp (and is not all-NaN), it's reused as-is and no USGS data is re-fetched. Otherwise
the full dataframe is (re)fetched from USGS and the file is overwritten.
