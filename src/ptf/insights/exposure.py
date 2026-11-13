"""Which share of a region's imports passes a chokepoint that is disrupted right now?

Three inputs from three domains:
- trade: where the imports come from (`marts.mart_import_sources`, BACI);
- model: which passages the sea route from each region traverses (`sea_distances`);
- shipping: which chokepoints are flagged disrupted today (monitor metrics).

Routes use one representative port per region, so e.g. all Middle East exports are routed
from Jebel Ali through Hormuz, also those of Saudi Arabia that leave from Yanbu on the Red
Sea. The result is an approximation of the exposure, not a shipment-level count.
"""

import pandas as pd

NO_CHOKEPOINT = "Open sea, no chokepoint"


def short_name(chokepoint: str) -> str:
    """'Strait of Hormuz' -> 'Hormuz', 'Suez Canal' -> 'Suez', 'Bab el-Mandeb Strait' -> ..."""
    name = chokepoint.removeprefix("Strait of ")
    for suffix in (" Strait", " Canal", " Passage", " Channel"):
        name = name.removesuffix(suffix)
    return name


def route_chokepoints(
    distances: pd.DataFrame,
    passage_chokepoints: dict[str, str],
    chokepoints: pd.DataFrame,
    focus_region: str,
) -> pd.DataFrame:
    """One row per origin region with the chokepoints its route to `focus_region` passes.

    Columns: origin_region, chokepoint_ids (list, in route order of the config mapping),
    route (readable label, e.g. "Hormuz · Bab el-Mandeb · Suez · Gibraltar").
    """
    names = dict(zip(chokepoints["chokepoint_id"], chokepoints["chokepoint"], strict=True))
    order = list(passage_chokepoints)
    rows = []
    for record in distances[distances["dest_region"] == focus_region].to_dict("records"):
        if record["origin_region"] == focus_region:
            continue
        passages = sorted(
            (p for p in list(record["passages"]) if p in passage_chokepoints), key=order.index
        )
        ids = [passage_chokepoints[p] for p in passages]
        label = " · ".join(short_name(names.get(i, i)) for i in ids) or NO_CHOKEPOINT
        rows.append(
            {"origin_region": record["origin_region"], "chokepoint_ids": ids, "route": label}
        )
    return pd.DataFrame(rows, columns=["origin_region", "chokepoint_ids", "route"])


def latest_year(sources: pd.DataFrame, focus_region: str) -> int:
    return int(sources.loc[sources["importer_region"] == focus_region, "year"].max())


def import_routes(
    sources: pd.DataFrame, routes: pd.DataFrame, focus_region: str, year: int
) -> pd.DataFrame:
    """Extra-regional imports of `focus_region` in `year`, one row per exporter country,
    with the route and chokepoints of the exporter's region."""
    imports = sources[
        (sources["importer_region"] == focus_region)
        & (sources["year"] == year)
        & ~sources["is_intra_regional"]
    ]
    merged = imports.merge(routes, left_on="exporter_region", right_on="origin_region", how="left")
    # Regions without a route (rest of world) count as "no chokepoint known".
    merged["route"] = merged["route"].fillna(NO_CHOKEPOINT)
    merged["chokepoint_ids"] = merged["chokepoint_ids"].apply(
        lambda ids: ids if isinstance(ids, list) else []
    )
    return merged.drop(columns=["origin_region"]).reset_index(drop=True)


def is_exposed(routes: pd.DataFrame, disrupted_ids: set[str]) -> pd.Series:
    """True for rows whose route passes at least one disrupted chokepoint."""
    return routes["chokepoint_ids"].apply(lambda ids: bool(set(ids) & disrupted_ids))


def exposure_share(routes: pd.DataFrame, disrupted_ids: set[str]) -> float:
    """Share of the tonnes in `routes` that pass a disrupted chokepoint, in %."""
    total = routes["qty_t"].sum()
    if total == 0:
        return 0.0
    return float(routes.loc[is_exposed(routes, disrupted_ids), "qty_t"].sum() / total * 100)


def top_share(routes: pd.DataFrame, n: int = 3) -> float:
    """Share of the `n` largest supplier countries in the tonnes, in % (concentration)."""
    total = routes["qty_t"].sum()
    if total == 0:
        return 0.0
    return float(routes["qty_t"].nlargest(n).sum() / total * 100)
