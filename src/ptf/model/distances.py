"""Sea distances between the representative ports of all model regions.

`searoute` computes the shortest path over a global network of shipping lanes, offline.
Passages can be blocked (e.g. `suez`, `babalmandab`, `panama`), which phase 3 uses for
disruption scenarios. The default blocks only the Northwest Passage, like searoute itself.
"""

from pathlib import Path

import pandas as pd
import searoute

from ptf.core.regions import Port, RegionConfig

DEFAULT_RESTRICTIONS = ["northwest"]


def port_distance_nm(
    origin: Port, destination: Port, restrictions: list[str] | None = None
) -> float:
    """Sea distance between two ports in nautical miles."""
    route = searoute.searoute(
        [origin.lon, origin.lat],
        [destination.lon, destination.lat],
        units="naut",
        restrictions=restrictions if restrictions is not None else DEFAULT_RESTRICTIONS,
    )
    return float(route["properties"]["length"])


def build_distance_table(
    regions: RegionConfig, restrictions: list[str] | None = None
) -> pd.DataFrame:
    """One row per ordered region pair; distance within a region is 0 by definition."""
    rows = []
    for origin_code, origin in regions.regions.items():
        for dest_code, dest in regions.regions.items():
            if origin_code == dest_code:
                distance = 0.0
            else:
                distance = port_distance_nm(origin.port, dest.port, restrictions)
            rows.append(
                {
                    "origin_region": origin_code,
                    "dest_region": dest_code,
                    "origin_port": origin.port.name,
                    "dest_port": dest.port.name,
                    "distance_nm": distance,
                }
            )
    return pd.DataFrame(rows)


def ingest_distances(regions: RegionConfig, raw_dir: Path) -> Path:
    """Compute the base-case distance table and store it in the raw layer."""
    path = raw_dir / "distances" / "sea_distances_base.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    build_distance_table(regions).to_parquet(path, index=False)
    return path
