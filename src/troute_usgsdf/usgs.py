from __future__ import annotations

import pandas as pd
from hydrotools.waterdata_client import ContinuousClient
from hydrotools.waterdata_client.transformers import to_dataframe

# The API caps each request at 50,000 rows, so request the gages in batches
# small enough that a batch can't be silently truncated.
LIMIT = 50_000
BATCH_SIZE = 40

# cubic feet per second -> cubic meters per second
CFS_TO_CMS = 0.0283168


def fetch_usgs_streamflow(sites: list[str], start_time, end_time) -> pd.DataFrame:
    """Fetch 00060 streamflow for many sites at once, batched under the row cap."""
    client = ContinuousClient(transformer=to_dataframe)
    frames = []
    for i in range(0, len(sites), BATCH_SIZE):
        batch = sites[i : i + BATCH_SIZE]
        print(f"Downloading USGS data for {len(batch)} sites ({i + 1}-{i + len(batch)})")
        try:
            observations = client.get(
                monitoring_location_id=batch,
                limit=LIMIT,
                parameter_code="00060",  # Volumetric streamflow in ft^3/s
                datetime=[pd.Timestamp(start_time), pd.Timestamp(end_time)],
            )
        except Exception:  # throws a custom error that I'm not importing
            print(f"No data found for batch {batch}")
            continue
        if len(observations) >= LIMIT:
            print(
                f"WARNING: batch starting at {i} hit the {LIMIT} row cap; "
                "reduce BATCH_SIZE to avoid truncation"
            )
        frames.append(observations)
    if not frames:
        return pd.DataFrame(columns=["usgs_site_code", "value_time", "value"])
    observations = pd.concat(frames, ignore_index=True)
    # cast value_time to datetime, they are strings in UTC -> tz-naive UTC
    observations["value_time"] = pd.to_datetime(
        observations["value_time"], utc=True
    ).dt.tz_localize(None)
    return observations[["usgs_site_code", "value_time", "value"]]


def interpolate_to_grid(observations: pd.DataFrame, target_index: pd.DatetimeIndex) -> pd.Series:
    """Interpolate irregular observations onto the target time grid."""
    if observations.empty:
        return pd.Series(index=target_index, dtype="float64")
    series = (
        observations.assign(value=pd.to_numeric(observations["value"], errors="coerce"))
        .set_index("value_time")["value"]
        .sort_index()
    )
    # collapse any duplicate timestamps
    series = series[~series.index.duplicated(keep="first")]
    # linear time interpolation onto the union of observed + target times,
    # then keep only the target grid (no extrapolation beyond observed range)
    union_index = series.index.union(target_index)
    series = series.reindex(union_index).interpolate(method="time")
    return series.reindex(target_index) * CFS_TO_CMS
