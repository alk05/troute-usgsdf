from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .config import make_troute_window, read_troute_window
from .core import build_usgs_da_dataframe, resolve_ngiab_paths

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    ngiab_data_dir: Optional[Path] = typer.Option(
        None,
        "--ngiab-data-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help=(
            "Path to an NGIAB data directory. Derives --gpkg (<dir>/config/*.gpkg), "
            "--troute-config (<dir>/config/troute.yaml) and --output "
            "(<dir>/config/troute_da.feather). Cannot be combined with those options."
        ),
    ),
    gpkg: Optional[Path] = typer.Option(
        None,
        "--gpkg",
        exists=True,
        dir_okay=False,
        help="Path to the hydrofabric geopackage (optional if --route-link is given).",
    ),
    route_link: Optional[Path] = typer.Option(
        None,
        "--route-link",
        exists=True,
        dir_okay=False,
        help="RouteLink .nc file containing NWM link ids and USGS gages.",
    ),
    mask: Optional[Path] = typer.Option(
        None,
        "--mask",
        exists=True,
        dir_okay=False,
        help="Optional text file containing link IDs to filter the domain.",
    ),
    troute_config: Optional[Path] = typer.Option(
        None,
        "--troute-config",
        exists=True,
        dir_okay=False,
        help="Path to the t-route troute.yaml config.",
    ),
    start: Optional[str] = typer.Option(
        None,
        "--start",
        help="Simulation start time (e.g. '2026-06-19 04:00' or ISO format). Alternative to --troute-config.",
    ),
    end: Optional[str] = typer.Option(
        None,
        "--end",
        help="Simulation end time. Used with --start as alternative to --nts.",
    ),
    nts: Optional[int] = typer.Option(
        None,
        "--nts",
        help="Number of timesteps. Used with --start and --dt.",
    ),
    dt: int = typer.Option(
        300,
        "--dt",
        help="Forcing/routing timestep in seconds (default: 300s).",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        dir_okay=False,
        help="Path to write the output feather file.",
    ),
    observed_steps: int = typer.Option(
        2,
        "--observed-steps",
        help=(
            "Number of time steps to keep populated with observations before NaN truncation"
            "(default: 2, which corresponds to five minutes)."
            "Pass 0 to keep the full window."
        ),
    ),
) -> None:
    """Build a USGS streamflow data-assimilation dataframe for t-route."""
    if ngiab_data_dir is not None:
        explicit_passed = [
            name
            for name, val in (
                ("--gpkg", gpkg),
                ("--route-link", route_link),
                ("--mask", mask),
                ("--troute-config", troute_config),
                ("--start", start),
                ("--end", end),
                ("--nts", nts),
                ("--output", output),
            )
            if val is not None
        ]
        if explicit_passed:
            raise typer.BadParameter(
                f"--ngiab-data-dir cannot be combined with: {', '.join(explicit_passed)}"
            )
        gpkg, troute_config, output = resolve_ngiab_paths(ngiab_data_dir)
        window = read_troute_window(troute_config)
    else:
        # Require output
        if output is None:
            raise typer.BadParameter("Missing --output (or pass --ngiab-data-dir instead)")

        # Require at least one domain source: --gpkg or --route-link
        if gpkg is None and route_link is None:
            raise typer.BadParameter("Must provide at least one of --gpkg or --route-link")

        # Require at least one time window source: --troute-config or --start
        if troute_config is None and start is None:
            raise typer.BadParameter("Must provide either --troute-config or --start")
        if troute_config is not None and start is not None:
            raise typer.BadParameter("--troute-config and --start cannot be combined")

        # Resolve window
        if troute_config is not None:
            window = read_troute_window(troute_config)
        else:
            try:
                window = make_troute_window(start=start, end=end, nts=nts, dt=dt)
            except ValueError as e:
                raise typer.BadParameter(str(e))

    if gpkg:
        typer.echo(f"gpkg: {gpkg}")
    if route_link:
        typer.echo(f"route link: {route_link}")
    if mask:
        typer.echo(f"mask: {mask}")
    typer.echo(f"window: {window.start} to {window.end} (dt={window.dt}s)")
    typer.echo(f"output: {output}")
    typer.echo(f"observed steps: {observed_steps}")            

    df = build_usgs_da_dataframe(
        output_path=output,
        gpkg_path=gpkg,
        route_link_nc_path=route_link,
        mask_path=mask,
        window=window,
        observed_steps=observed_steps,
    )
    typer.echo(df)


def run() -> None:
    app()


if __name__ == "__main__":
    run()
