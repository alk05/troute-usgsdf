from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml


@dataclass(frozen=True)
class TrouteWindow:
    start: datetime
    end: datetime
    dt: int  # forcing/routing timestep, in seconds

def make_troute_window(
    start: datetime | str,
    *,
    dt: int = 300,
    end: datetime | str | None = None,
    nts: int | None = None,
) -> TrouteWindow:
    """Build a TrouteWindow without a yaml.
    Requires `start` and either `end` or `nts`.
    `dt` defaults to 300 seconds.
    """
    if dt <= 0:
        raise ValueError(f"dt must be positive, got {dt}")
    if (end is None) == (nts is None):
        raise ValueError("Must provide exactly one of 'end' or 'nts' along with 'start'")

    start = _parse_naive_utc(start, "start")
    if nts is not None:
        if nts <= 0:
            raise ValueError(f"nts must be positive, got {nts}")
        try:
            end = start + timedelta(seconds=dt * nts)
        except OverflowError:
            raise ValueError(f"nts={nts} x dt={dt}s runs past the maximum representable date")
    else:
        end = _parse_naive_utc(end, "end")
        span = (end - start).total_seconds()
        if span <= 0:
            raise ValueError(f"end ({end}) must be after start ({start})")
        if span % dt:
            raise ValueError(
                f"end ({end}) is not a whole number of dt={dt}s steps after start ({start})"
            )

    # the time grid is a pandas DatetimeIndex (ns precision), which has a narrower range
    for name, value in (("start", start), ("end", end)):
        if not (pd.Timestamp.min <= pd.Timestamp(value) <= pd.Timestamp.max):
            raise ValueError(
                f"{name} ({value}) is outside the supported range "
                f"{pd.Timestamp.min:%Y-%m-%d} to {pd.Timestamp.max:%Y-%m-%d}"
            )

    return TrouteWindow(start=start, end=end, dt=dt)


def _parse_naive_utc(value: datetime | date | str, name: str) -> datetime:
    """Parse to a naive datetime, converting tz-aware input to naive UTC (t-route's convention)."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(f"Invalid {name} time {value!r}; expected e.g. '2026-06-19 04:00'")
    elif isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time())
    elif not isinstance(value, datetime):
        raise ValueError(f"Invalid {name} time {value!r}; expected e.g. '2026-06-19 04:00'")
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value



def read_troute_window(troute_config_path: Path) -> TrouteWindow:
    """Read the simulation start/end/timestep out of a troute.yaml.

    start_datetime is UTC (naive). end is start + forcing_parameters.dt * nts.
    Raises ValueError (or OSError if unreadable) with a readable message if malformed.
    """
    try:
        config = yaml.safe_load(Path(troute_config_path).read_text())
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML: {e}") from e
    try:
        compute = config["compute_parameters"]
        start = compute["restart_parameters"]["start_datetime"]
        forcing = compute["forcing_parameters"]
        dt = _as_int(forcing["dt"], "dt")
        nts = _as_int(forcing["nts"], "nts")
    except (KeyError, TypeError, ValueError, OverflowError) as e:
        raise ValueError(
            "expected compute_parameters.restart_parameters.start_datetime and "
            f"compute_parameters.forcing_parameters.dt/nts (integers); got error {e!r}"
        ) from e
    return make_troute_window(start, dt=dt, nts=nts)


def _as_int(value: object, name: str) -> int:
    """Convert a YAML number to int, rejecting non-integral values instead of truncating."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{name} must be an integer, got {value!r}")
    return int(value)
