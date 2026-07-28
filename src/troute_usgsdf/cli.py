from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

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
        help="Path to the hydrofabric geopackage.",
    ),
    troute_config: Optional[Path] = typer.Option(
        None,
        "--troute-config",
        exists=True,
        dir_okay=False,
        help="Path to the t-route troute.yaml config.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        dir_okay=False,
        help="Path to write the output feather file.",
    ),
) -> None:
    """Build a USGS streamflow data-assimilation dataframe for t-route."""
    if ngiab_data_dir is not None:
        if gpkg is not None or troute_config is not None or output is not None:
            raise typer.BadParameter(
                "--gpkg/--troute-config/--output cannot be combined with --ngiab-data-dir"
            )
        gpkg, troute_config, output = resolve_ngiab_paths(ngiab_data_dir)
    else:
        missing = [
            name
            for name, value in (
                ("--gpkg", gpkg),
                ("--troute-config", troute_config),
                ("--output", output),
            )
            if value is None
        ]
        if missing:
            raise typer.BadParameter(
                f"Missing {', '.join(missing)} (or pass --ngiab-data-dir instead)"
            )

    typer.echo(f"gpkg: {gpkg}")
    typer.echo(f"troute config: {troute_config}")
    typer.echo(f"output: {output}")

    df = build_usgs_da_dataframe(gpkg, troute_config, output)
    typer.echo(df)


def run() -> None:
    app()


if __name__ == "__main__":
    run()
