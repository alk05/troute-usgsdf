from __future__ import annotations

import sqlite3
from pathlib import Path


def read_gage_crosswalk(gpkg_path: Path) -> dict[int, str]:
    """Map flowpath waterbody id -> USGS gage id for every flowpath with a gage attached."""
    with sqlite3.connect(str(gpkg_path)) as conn:
        sql = 'SELECT id, gage FROM "flowpath-attributes" WHERE gage NOT NULL'
        rows = conn.execute(sql).fetchall()
    return {int(wb_id.split("-")[1]): gage.split(",")[0] for wb_id, gage in rows}
