# troute-usgsdf

Builds a USGS streamflow dataframe shaped to fill
[t-route](https://github.com/NOAA-OWP/t-route)'s
`data_assimilation.usgs_df` directly, instead of writing individual USGS
timeslice NetCDF files for t-route to read back in.

The output is a feather file: one row per identifier (flowpath waterbody ID
from a hydrofabric geopackage, or NWM link ID from a RouteLink file), one column
per timestep on the simulation's time grid, values in m3/s.

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

Or use a RouteLink `.nc` file, with an optional mask file (`--mask` filters NWM link IDs,
so it requires `--route-link`; it cannot be used with `--gpkg` alone):

```bash
uvx troute-usgsdf \
  --route-link /path/to/RouteLink.nc \
  --mask /path/to/mask.txt \
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

`--start` and `--end` accept `"YYYY-MM-DD HH:MM"` strings (UTC; timezone-aware ISO strings are converted to UTC). `--end` must be after `--start` by a whole number of `--dt` steps. `--start` needs exactly one of
`--end` or `--nts` (number of timesteps), and `--dt` defaults to 300 seconds.
`--troute-config` and `--start` are mutually exclusive: when using `--troute-config`,
passing any of `--start`, `--end`, `--nts` or `--dt` is an error rather than being ignored.

### Observation Truncation (`--observed-steps`)

By default, observations are kept across the full simulation window.

In forecast mode, future observations are not known at the time of forecast initialization.
Pass `--observed-steps N` to keep observations only for the first `N` timesteps and set the
remaining steps to `NaN` (e.g. `--observed-steps 2` keeps the first two timesteps, five
minutes under `dt=300`).

### CLI Reference

Options are grouped in `--help`. Within each group:

- **Preset:** `--ngiab-data-dir` replaces every Domain, Time window and `--output` option; combining them is an error.
- **Domain:** at least one of `--gpkg` / `--route-link`. `--mask` requires `--route-link`.
- **Time window:** either `--troute-config`, or `--start` plus exactly one of `--end` / `--nts` (optionally `--dt`).
- **Output:** `--output` is required unless using the preset; `--observed-steps` is optional.

| Group | Option | Description |
|---|---|---|
| Preset | `--ngiab-data-dir PATH` | NGIAB run data directory (derives gpkg, troute config, and output feather). |
| Domain | `--gpkg PATH` | Hydrofabric geopackage. Alone: rows are flowpath IDs. With `--route-link`: rows are NWM link IDs. |
| Domain | `--route-link PATH` | RouteLink `.nc` file containing NWM link IDs and USGS gages. |
| Domain | `--mask PATH` | Text file of NWM link IDs to keep. Requires `--route-link`. |
| Time window | `--troute-config PATH` | t-route `troute.yaml` (excludes `--start`/`--end`/`--nts`/`--dt`). |
| Time window | `--start TEXT` | Simulation start time (`YYYY-MM-DD HH:MM`). Requires `--end` or `--nts`. |
| Time window | `--end TEXT` | Simulation end time. Requires `--start`; excludes `--nts`. |
| Time window | `--nts INTEGER` | Number of timesteps. Requires `--start`; excludes `--end`. |
| Time window | `--dt INTEGER` | Timestep in seconds (default: `300`). Requires `--start`. |
| Output | `--output PATH` | Path to write the output `.feather` file. |
| Output | `--observed-steps INTEGER` | Keep only the first N timesteps of observations (default: full window). |

## Output Caching

If `--output` already exists, it is reused as-is (no USGS fetch) only when it was built
for exactly this run: the same ids (after `--mask`), the same time grid, and the same
`--observed-steps`. These options are stored in the feather's metadata. Otherwise (including
files written by older versions without that metadata, or all-NaN files) the dataframe is
refetched from USGS and the file is overwritten.
