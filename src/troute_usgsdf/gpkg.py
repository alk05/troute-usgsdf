from __future__ import annotations

import sqlite3
from pathlib import Path


def read_gage_crosswalk(gpkg_path: Path) -> dict[int, str]:
    """Map flowpath waterbody id -> USGS gage id for every flowpath with a gage attached."""
    with sqlite3.connect(str(gpkg_path)) as conn:
        sql = 'SELECT id, gage FROM "flowpath-attributes" WHERE gage NOT NULL'
        rows = conn.execute(sql).fetchall()
    return {int(wb_id.split("-")[1]): gage.split(",")[0] for wb_id, gage in rows}


def read_gage_crosswalk_nwm(gpkg_path: Path, route_link_nc_path: Path) -> dict[int, tuple[str, int | None]]:
    """Map flowpath waterbody id -> (USGS gage id, NWM link id) from RouteLink .nc."""
    wb_to_gage = read_gage_crosswalk(gpkg_path)
    from netCDF4 import Dataset

    with Dataset(str(route_link_nc_path)) as ds:
        if "link" not in ds.variables or "gages" not in ds.variables:
            raise ValueError(
                f"RouteLink file {route_link_nc_path} must contain 'link' and 'gages' variables"
            )
        links = ds.variables["link"][:]
        gages_var = ds.variables["gages"][:]

    gage_to_nwm: dict[str, int] = {}
    for i, row in enumerate(gages_var):
        try:
            gage = "".join(
                ch.decode("utf-8") if isinstance(ch, (bytes, bytearray)) else str(ch)
                for ch in row
            ).strip()
        except Exception:
            gage = str(row).strip()
        if gage:
            gage_to_nwm[gage] = int(links[i])

    return {wb: (gage, gage_to_nwm.get(gage)) for wb, gage in wb_to_gage.items()}
