# troute-usgsdf

Builds a USGS streamflow dataframe shaped to fill
[t-route](https://github.com/NOAA-OWP/t-route)'s
`data_assimilation.usgs_df` directly, instead of writing individual USGS
timeslice NetCDF files for t-route to read back in.

The output is a feather file: one row per waterbody id (crosswalked from the
hydrofabric geopackage's gage attributes), one column per timestep on the
simulation's time grid, values in m3/s.

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

The simulation start/end/timestep are read from `troute.yaml`
(`compute_parameters.restart_parameters.start_datetime`, and
`compute_parameters.forcing_parameters.dt`/`nts`).

If `--output` already exists and already contains every required waterbody id
and timestamp, it's reused as-is and no USGS data is re-fetched. Otherwise
the full dataframe is (re)fetched from USGS and the file is overwritten.
