from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TrouteWindow:
    start: datetime
    end: datetime
    dt: int  # forcing/routing timestep, in seconds


def read_troute_window(troute_config_path: Path) -> TrouteWindow:
    """Read the simulation start/end/timestep out of a troute.yaml.

    start_datetime is UTC (naive). end is start + forcing_parameters.dt * nts.
    """
    config = yaml.safe_load(Path(troute_config_path).read_text())
    compute = config["compute_parameters"]

    start = compute["restart_parameters"]["start_datetime"]
    if isinstance(start, str):
        start = datetime.fromisoformat(start)

    forcing = compute["forcing_parameters"]
    dt = int(forcing["dt"])
    nts = int(forcing["nts"])
    end = start + timedelta(seconds=dt * nts)

    return TrouteWindow(start=start, end=end, dt=dt)
