from __future__ import annotations

from pathlib import Path

import numpy as np


def read_link_mask(mask_path: Path) -> set[int]:
    """Read a t-route mask file: one link id per line, trailing commas and blanks ignored.

    Same format t-route reads for `supernetwork_parameters.mask_file_path`.
    """
    with Path(mask_path).open() as f:
        return {int(line.strip(", \n")) for line in f if line.strip(", \n")}


def read_route_link_gages(
    route_link_nc_path: Path, mask: set[int] | None = None
) -> dict[int, str]:
    """Map NWM link id -> USGS gage id for every RouteLink entry that carries a gage.

    If `mask` is given, only links in it are returned. The mask and the "has a gage"
    filter are applied as vectorized NumPy operations before any per-gage Python work,
    so only the (few thousand) gauged links are ever decoded, even for CONUS.
    """
    from netCDF4 import Dataset

    with Dataset(str(route_link_nc_path)) as ds:
        if "link" not in ds.variables or "gages" not in ds.variables:
            raise ValueError(
                f"RouteLink file {route_link_nc_path} must contain 'link' and 'gages' variables"
            )
        gages_var = ds.variables["gages"]
        # Always get the raw (n_links, n_chars) 'S1' array, regardless of whether the
        # variable has an `_Encoding` attribute that would trigger auto-conversion.
        gages_var.set_auto_maskandscale(False)
        gages_var.set_auto_chartostring(False)
        links_ma = np.ma.asarray(ds.variables["link"][:])
        gages_raw = np.asarray(gages_var[:])

    links = links_ma.filled(0)
    gages = _gage_strings(gages_raw)
    # drop rows without a gage and rows whose link id is missing (masked fill value)
    keep = (gages != b"") & ~np.ma.getmaskarray(links_ma)
    if mask is not None:
        # compare as int64 so mask ids outside the file's (often int32) range just don't match
        mask_ids = np.fromiter(
            (m for m in mask if _INT64_MIN <= m <= _INT64_MAX), dtype=np.int64
        )
        keep &= np.isin(links.astype(np.int64), mask_ids)

    return {
        int(link): gage.decode("utf-8", errors="replace")
        for link, gage in zip(links[keep], gages[keep])
    }


_INT64_MIN, _INT64_MAX = np.iinfo(np.int64).min, np.iinfo(np.int64).max


def _gage_strings(gages_raw: np.ndarray) -> np.ndarray:
    """Return one stripped bytes string per link from the RouteLink `gages` variable.

    Handles the standard fixed-width (n_links, n_chars) 'S1' char array and, for
    non-standard files, a 1-D variable-length string variable. NUL padding is treated
    like whitespace.
    """
    if gages_raw.ndim == 2 and gages_raw.dtype == np.dtype("S1"):
        n_chars = gages_raw.shape[-1]
        # NUL -> space on the raw bytes, then view each fixed-width row as one string
        chars = np.ascontiguousarray(gages_raw).view(np.uint8).copy()
        chars[chars == 0] = ord(" ")
        gages = chars.view(f"S{n_chars}").reshape(-1)
    elif gages_raw.ndim == 1 and gages_raw.dtype.kind in "OSU":
        gages = np.array(
            [
                (g.encode("utf-8") if isinstance(g, str) else bytes(g or b"")).replace(
                    b"\x00", b" "
                )
                for g in gages_raw
            ],
            dtype=bytes,
        )
    else:
        raise ValueError(
            f"Unsupported RouteLink 'gages' layout: shape={gages_raw.shape}, "
            f"dtype={gages_raw.dtype}"
        )
    if gages.size == 0:
        return gages
    return np.char.strip(gages)
