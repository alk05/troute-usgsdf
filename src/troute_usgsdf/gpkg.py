from __future__ import annotations

import sqlite3
from pathlib import Path

from .routelink import read_route_link_gages


def read_gage_crosswalk(gpkg_path: Path) -> dict[int, str]:
    """Map flowpath waterbody id -> USGS gage id for every flowpath with a gage attached."""
    with sqlite3.connect(str(gpkg_path)) as conn:
        sql = 'SELECT id, gage FROM "flowpath-attributes" WHERE gage NOT NULL'
        rows = conn.execute(sql).fetchall()
    return {int(wb_id.split("-")[1]): gage.split(",")[0] for wb_id, gage in rows}


def read_gage_crosswalk_nwm(
    gpkg_path: Path, route_link_nc_path: Path
) -> dict[int, tuple[str, int | None]]:
    """Map flowpath waterbody id -> (USGS gage id, NWM link id) using RouteLink .nc."""
    wb_to_gage = read_gage_crosswalk(gpkg_path)
    link_to_gage = read_route_link_gages(route_link_nc_path)
    gage_to_nwm = {gage: link for link, gage in link_to_gage.items()}
    return {wb: (gage, gage_to_nwm.get(gage)) for wb, gage in wb_to_gage.items()}