"""Sea distances between the representative ports of all model regions.

`searoute` computes the shortest path over a global network of shipping lanes, offline.
Passages can be blocked (e.g. `suez`, `babalmandab`, `panama`), which phase 3 uses for
disruption scenarios, and each route reports the passages it traverses (spec 006).
The default blocks only the Northwest Passage, like searoute itself.
"""

from pathlib import Path

import pandas as pd
import searoute

from ptf.core.regions import Port, RegionConfig

DEFAULT_RESTRICTIONS = ["northwest"]


def sea_route(
    origin: Port, destination: Port, restrictions: list[str] | None = None
) -> tuple[float, list[str]]:
    """Sea distance in nautical miles and the passages the route traverses (sorted).

    Passages are searoute's names, e.g. "suez", "babalmandab", "ormuz"; `config/sourcing.yaml`
    maps them to PortWatch chokepoints.
    """
    route = searoute.searoute(
        [origin.lon, origin.lat],
        [destination.lon, destination.lat],
        units="naut",
        restrictions=restrictions if restrictions is not None else DEFAULT_RESTRICTIONS,
        return_passages=True,
    )
    properties = route["properties"]
    return float(properties["length"]), sorted(properties.get("traversed_passages", []))


def port_distance_nm(
    origin: Port, destination: Port, restrictions: list[str] | None = None
) -> float:
    """Sea distance between two ports in nautical miles."""
    return sea_route(origin, destination, restrictions)[0]


def build_distance_table(
    regions: RegionConfig, restrictions: list[str] | None = None
) -> pd.DataFrame:
    """One row per ordered region pair with distance and traversed passages.

    Within a region the distance is 0 and the list of passages is empty by definition.
    """
    rows = []
    passages: list[str]
    for origin_code, origin in regions.regions.items():
        for dest_code, dest in regions.regions.items():
            if origin_code == dest_code:
                distance, passages = 0.0, []
            else:
                distance, passages = sea_route(origin.port, dest.port, restrictions)
            rows.append(
                {
                    "origin_region": origin_code,
                    "dest_region": dest_code,
                    "origin_port": origin.port.name,
                    "dest_port": dest.port.name,
                    "distance_nm": distance,
                    "passages": passages,
                }
            )
    return pd.DataFrame(rows)


def distance_path(raw_dir: Path, variant: str = "base") -> Path:
    return raw_dir / "distances" / f"sea_distances_{variant}.parquet"


def read_distance_table(raw_dir: Path, variant: str = "base") -> pd.DataFrame | None:
    """A stored distance table, or None if it is missing or predates the `passages` column
    (then `ptf ingest` has to run again)."""
    path = distance_path(raw_dir, variant)
    if not path.exists():
        return None
    table = pd.read_parquet(path)
    return table if "passages" in table.columns else None


def ingest_distances(regions: RegionConfig, raw_dir: Path) -> Path:
    """Compute the base-case distance table and store it in the raw layer."""
    path = distance_path(raw_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_distance_table(regions).to_parquet(path, index=False)
    return path


def ingest_route_variants(
    regions: RegionConfig, raw_dir: Path, variants: dict[str, list[str]]
) -> list[Path]:
    """One distance table per variant (name -> blocked passages), e.g. "red_sea_closed"."""
    paths = []
    for name, restrictions in variants.items():
        path = distance_path(raw_dir, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        build_distance_table(regions, restrictions).to_parquet(path, index=False)
        paths.append(path)
    return paths
