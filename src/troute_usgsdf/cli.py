from __future__ import annotations

from pathlib import Path
from typing import NoReturn, Optional

import typer

from .config import make_troute_window, read_troute_window
from .core import EmptyDomainError, build_usgs_da_dataframe, resolve_ngiab_paths

app = typer.Typer(add_completion=False, no_args_is_help=True)

DEFAULT_DT = 300

PRESET = "Preset (replaces Domain, Time window and --output)"
DOMAIN = "Domain (--gpkg and/or --route-link)"
TIME = "Time window (--troute-config OR --start with --end/--nts)"
OUTPUT = "Output"


def _fail(message: str) -> NoReturn:
    """Report a usage error (like click's UsageError: message on stderr, exit code 2)."""
    typer.echo(f"Error: {message}\nTry '--help' for help.", err=True)
    raise typer.Exit(2)


def _passed(**opts: object) -> list[str]:
    """Return the flag names of the options that were actually given."""
    return [f"--{name.replace('_', '-')}" for name, val in opts.items() if val is not None]


def _reject(context: str, flags: list[str]) -> None:
    if flags:
        _fail(f"{context} cannot be combined with: {', '.join(flags)}")


@app.command(no_args_is_help=True)
def main(
    ngiab_data_dir: Optional[Path] = typer.Option(
        None,
        "--ngiab-data-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        rich_help_panel=PRESET,
        help=(
            "Path to an NGIAB data directory. Derives --gpkg (<dir>/config/*.gpkg), "
            "--troute-config (<dir>/config/troute.yaml) and --output "
            "(<dir>/config/troute_da.feather). Cannot be combined with any Domain, "
            "Time window or --output option."
        ),
    ),
    gpkg: Optional[Path] = typer.Option(
        None,
        "--gpkg",
        exists=True,
        dir_okay=False,
        rich_help_panel=DOMAIN,
        help=(
            "Hydrofabric geopackage. Alone: rows are flowpath ids. "
            "With --route-link: rows are NWM link ids."
        ),
    ),
    route_link: Optional[Path] = typer.Option(
        None,
        "--route-link",
        exists=True,
        dir_okay=False,
        rich_help_panel=DOMAIN,
        help="RouteLink .nc file containing NWM link ids and USGS gages. Rows are NWM link ids.",
    ),
    mask: Optional[Path] = typer.Option(
        None,
        "--mask",
        exists=True,
        dir_okay=False,
        rich_help_panel=DOMAIN,
        help="Text file of NWM link ids to keep (t-route mask format). Requires --route-link.",
    ),
    troute_config: Optional[Path] = typer.Option(
        None,
        "--troute-config",
        exists=True,
        dir_okay=False,
        rich_help_panel=TIME,
        help="t-route troute.yaml; start, dt and nts are read from it. Excludes --start/--end/--nts/--dt.",
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        rich_help_panel=TIME,
        help="Simulation start time (e.g. '2026-06-19 04:00'). Requires exactly one of --end or --nts.",
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        rich_help_panel=TIME,
        help="Simulation end time. Requires --start; excludes --nts.",
    ),
    nts: Optional[int] = typer.Option(
        None,
        "--nts",
        min=1,
        rich_help_panel=TIME,
        help="Number of timesteps. Requires --start; excludes --end.",
    ),
    dt: Optional[int] = typer.Option(
        None,
        "--dt",
        min=1,
        rich_help_panel=TIME,
        help=f"Timestep in seconds. Requires --start (default: {DEFAULT_DT}).",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        dir_okay=False,
        rich_help_panel=OUTPUT,
        help="Path to write the output feather file. Required unless --ngiab-data-dir is given.",
    ),
    observed_steps: Optional[int] = typer.Option(
        None,
        "--observed-steps",
        min=1,
        rich_help_panel=OUTPUT,
        help=(
            "Keep observations only for the first N timesteps and set the rest to NaN "
            "(forecast mode). Omit to keep the full window."
        ),
    ),
) -> None:
    """Build a USGS streamflow data-assimilation dataframe for t-route."""
    if ngiab_data_dir is not None:
        _reject(
            "--ngiab-data-dir",
            _passed(
                gpkg=gpkg,
                route_link=route_link,
                mask=mask,
                troute_config=troute_config,
                start=start,
                end=end,
                nts=nts,
                dt=dt,
                output=output,
            ),
        )
        try:
            gpkg, troute_config, output = resolve_ngiab_paths(ngiab_data_dir)
            window = read_troute_window(troute_config)
        except (OSError, ValueError) as e:
            _fail(f"--ngiab-data-dir {ngiab_data_dir}: {e}")
    else:
        if output is None:
            _fail("Missing --output (or pass --ngiab-data-dir instead)")

        # Domain
        if gpkg is None and route_link is None:
            _fail("Must provide at least one of --gpkg or --route-link")
        if mask is not None and route_link is None:
            _fail(
                "--mask filters NWM link ids and requires --route-link "
                "(a --gpkg-only run is keyed by flowpath id)"
            )

        # Time window
        if troute_config is not None:
            _reject(
                "--troute-config",
                _passed(start=start, end=end, nts=nts, dt=dt),
            )
            try:
                window = read_troute_window(troute_config)
            except (OSError, ValueError) as e:
                _fail(f"--troute-config {troute_config}: {e}")
        elif start is not None:
            if (end is None) == (nts is None):
                _fail("--start requires exactly one of --end or --nts")
            try:
                window = make_troute_window(
                    start=start, end=end, nts=nts, dt=dt if dt is not None else DEFAULT_DT
                )
            except ValueError as e:
                _fail(str(e))
        else:
            orphans = _passed(end=end, nts=nts, dt=dt)
            if orphans:
                _fail(f"{', '.join(orphans)}: only valid with --start")
            _fail("Must provide either --troute-config or --start")

    if gpkg:
        typer.echo(f"gpkg: {gpkg}")
    if route_link:
        typer.echo(f"route link: {route_link}")
    if mask:
        typer.echo(f"mask: {mask}")
    typer.echo(f"window: {window.start} to {window.end} (dt={window.dt}s)")
    typer.echo(f"output: {output}")
    typer.echo(
        f"observed steps: {observed_steps if observed_steps is not None else 'all (full window)'}"
    )

    try:
        df = build_usgs_da_dataframe(
            output_path=output,
            gpkg_path=gpkg,
            route_link_nc_path=route_link,
            mask_path=mask,
            window=window,
            observed_steps=observed_steps,
        )
    except EmptyDomainError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(df)


def run() -> None:
    app()


if __name__ == "__main__":
    run()
