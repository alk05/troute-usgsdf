from __future__ import annotations

from pathlib import Path


def _decode_gage(row) -> str:
    """RouteLink stores gage ids as fixed-width character arrays; join and strip."""
    try:
        return "".join(
            ch.decode("utf-8") if isinstance(ch, (bytes, bytearray)) else str(ch)
            for ch in row
        ).strip()
    except Exception:
        return str(row).strip()


def read_route_link_gages(route_link_nc_path: Path) -> dict[int, str]:
    """Map NWM link id -> USGS gage id for every RouteLink entry that carries a gage."""
    from netCDF4 import Dataset

    with Dataset(str(route_link_nc_path)) as ds:
        if "link" not in ds.variables or "gages" not in ds.variables:
            raise ValueError(
                f"RouteLink file {route_link_nc_path} must contain 'link' and 'gages' variables"
            )
        links = ds.variables["link"][:]
        gages_var = ds.variables["gages"][:]

    link_to_gage: dict[int, str] = {}
    for i, row in enumerate(gages_var):
        gage = _decode_gage(row)
        if gage:
            link_to_gage[int(links[i])] = gage
    return link_to_gage


def read_link_mask(mask_path: Path) -> set[int]:
    """Read a t-route mask file: one link id per line, trailing commas and blanks ignored.

    Same format t-route reads for `supernetwork_parameters.mask_file_path`.
    """
    with Path(mask_path).open() as f:
        return {int(line.strip(", \n")) for line in f if line.strip(", \n")}


def read_gage_crosswalk_route_link(
    route_link_nc_path: Path, mask_path: Path | None = None
) -> dict[int, str]:
    """Map NWM link id -> USGS gage id from the RouteLink alone, with no geopackage.

    The RouteLink already carries both halves of the crosswalk, so a hydrofabric
    geopackage is only needed when the output should be keyed by flowpath id instead.
    """
    link_to_gage = read_route_link_gages(route_link_nc_path)
    if mask_path is not None:
        mask = read_link_mask(mask_path)
        link_to_gage = {
            link: gage for link, gage in link_to_gage.items() if link in mask
        }
    return link_to_gage 