"""Which share of a region's imports passes a chokepoint that is closed or disrupted?

Three inputs from three domains:
- trade: where the imports come from (`marts.mart_import_sources`, BACI);
- model: which passages the sea route from each origin traverses (`sea_distances`);
- shipping: which chokepoints are closed or disrupted (monitor metrics, insights.scenario).

Routes start at one representative port per region, unless a country has its own export
ports (spec 014, `country_routes` in config/model.yaml, origin key 'ISO3:Port'). A country
with several ports and no sourced shares appears once per port with its full tonnes; sums
over countries then give a range ("between all from the least and all from the most
exposed port"), never a split.
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
    """One row per origin (region or 'ISO3:Port') with the chokepoints its route to
    `focus_region` passes.

    Columns: origin_region, chokepoint_ids (list, in route order of the config mapping),
    route (readable label, e.g. "Hormuz · Bab el-Mandeb · Suez · Gibraltar"), distance_nm.
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
        distance = float(record.get("distance_nm", float("nan")))
        if pd.isna(distance) and "distance_nm" in record:
            label = "no sea route"
        rows.append(
            {
                "origin_region": record["origin_region"],
                "chokepoint_ids": ids,
                "route": label,
                "distance_nm": distance,
            }
        )
    return pd.DataFrame(rows, columns=["origin_region", "chokepoint_ids", "route", "distance_nm"])


def latest_year(sources: pd.DataFrame, focus_region: str) -> int:
    return int(sources.loc[sources["importer_region"] == focus_region, "year"].max())


def with_route_keys(rows: pd.DataFrame, country_keys: dict[str, list[str]]) -> pd.DataFrame:
    """One row per exporter country and export port: route_key ('ISO3:Port' for countries
    with own ports, else the exporter region), port ('' for the region's port) and n_ports."""
    parts = []
    for row in rows.to_dict("records"):
        keys = country_keys.get(row["exporter_iso3"])
        if not keys:
            parts.append({**row, "route_key": row["exporter_region"], "port": "", "n_ports": 1})
            continue
        for key in keys:
            port = key.split(":", 1)[1]
            parts.append({**row, "route_key": key, "port": port, "n_ports": len(keys)})
    columns = [*rows.columns, "route_key", "port", "n_ports"]
    return pd.DataFrame(parts, columns=columns)


def import_routes(
    sources: pd.DataFrame,
    routes: pd.DataFrame,
    focus_region: str,
    year: int,
    country_keys: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """Extra-regional imports of `focus_region` in `year`, one row per exporter country and
    export port, with the route and chokepoints of that port."""
    imports = sources[
        (sources["importer_region"] == focus_region)
        & (sources["year"] == year)
        & ~sources["is_intra_regional"]
    ]
    keyed = with_route_keys(imports.reset_index(drop=True), country_keys or {})
    merged = keyed.merge(routes, left_on="route_key", right_on="origin_region", how="left")
    # Origins without a route (rest of world) count as "no chokepoint known".
    merged["route"] = merged["route"].fillna(NO_CHOKEPOINT)
    merged["chokepoint_ids"] = merged["chokepoint_ids"].apply(
        lambda ids: ids if isinstance(ids, list) else []
    )
    return merged.drop(columns=["origin_region"]).reset_index(drop=True)


def country_tonnes(routes: pd.DataFrame) -> pd.Series:
    """Tonnes per exporter country, counted once even with several ports."""
    return routes.groupby("exporter_iso3")["qty_t"].first()


def tonnes_range(routes: pd.DataFrame, mask: pd.Series) -> tuple[float, float]:
    """Tonnes for which `mask` holds: (low, high). Low counts a country only if all its ports
    match, high if any port matches; without several ports both are equal."""
    flags = routes.assign(match=mask.to_numpy()).groupby("exporter_iso3")["match"]
    tonnes = country_tonnes(routes)
    low = float(tonnes[flags.all()].sum())
    high = float(tonnes[flags.any()].sum())
    return low, high


def share_range(routes: pd.DataFrame, mask: pd.Series) -> tuple[float, float]:
    """`tonnes_range` as % of the countries' tonnes."""
    total = float(country_tonnes(routes).sum()) if not routes.empty else 0.0
    if total == 0:
        return 0.0, 0.0
    low, high = tonnes_range(routes, mask)
    return low / total * 100, high / total * 100


def is_exposed(routes: pd.DataFrame, disrupted_ids: set[str]) -> pd.Series:
    """True for rows whose route passes at least one disrupted chokepoint."""
    return routes["chokepoint_ids"].apply(lambda ids: bool(set(ids) & disrupted_ids))


def exposure_share(routes: pd.DataFrame, disrupted_ids: set[str]) -> float:
    """Share of the tonnes that pass a disrupted chokepoint, in % (upper bound of the range)."""
    return share_range(routes, is_exposed(routes, disrupted_ids))[1]


def top_share(routes: pd.DataFrame, n: int = 3) -> float:
    """Share of the `n` largest supplier countries in the tonnes, in % (concentration)."""
    tonnes = country_tonnes(routes) if not routes.empty else pd.Series(dtype=float)
    total = tonnes.sum()
    if total == 0:
        return 0.0
    return float(tonnes.nlargest(n).sum() / total * 100)


def by_country(routes: pd.DataFrame, flag: str) -> pd.DataFrame:
    """One row per exporter country for charts: tonnes once, the route labels of its ports
    joined with " or ", and `flag` true if any port has it (with `flag`_all if all do)."""
    rows = []
    for _iso3, group in routes.groupby("exporter_iso3", sort=False):
        first = group.iloc[0]
        labels = list(dict.fromkeys(group["route"]))
        route = " or ".join(labels)
        if len(group) > 1:
            route += " (port shares unknown)"
        rows.append(
            {
                "exporter_iso3": first["exporter_iso3"],
                "exporter_name": first["exporter_name"],
                "exporter_region": first["exporter_region"],
                "qty_t": float(first["qty_t"]),
                "route": route,
                flag: bool(group[flag].any()),
                f"{flag}_all": bool(group[flag].all()),
            }
        )
    columns = [
        "exporter_iso3",
        "exporter_name",
        "exporter_region",
        "qty_t",
        "route",
        flag,
        f"{flag}_all",
    ]
    return pd.DataFrame(rows, columns=columns)


OTHER_DESTINATION = "Other Europe"


def destination_tonnes(
    bilateral: pd.DataFrame, focus_region: str, year: int, groups: dict[str, list[str]]
) -> pd.DataFrame:
    """Extra-regional imports of the focus region per exporter country and destination group
    (importer countries grouped by a setting; unlisted countries -> "Other Europe").

    Columns: exporter_iso3, destination, qty_t.
    """
    rows = bilateral[
        (bilateral["importer_region"] == focus_region)
        & (bilateral["exporter_region"] != focus_region)
        & (bilateral["year"] == year)
    ]
    group_of = {iso3: name for name, members in groups.items() for iso3 in members}
    rows = rows.assign(destination=rows["importer_iso3"].map(group_of).fillna(OTHER_DESTINATION))
    grouped = rows.groupby(["exporter_iso3", "destination"], as_index=False).agg(
        qty_t=("qty_t", "sum")
    )
    return grouped


def top_with_other(table: pd.DataFrame, n: int, column: str = "qty_t") -> pd.DataFrame:
    """The `n` largest rows by `column`, the rest summed into one row named "Other"."""
    ranked = table.sort_values(column, ascending=False)
    top, rest = ranked.head(n), ranked.iloc[n:]
    if rest.empty:
        return top.reset_index(drop=True)
    other = {c: None for c in table.columns} | {
        "exporter_iso3": "OTHER",
        "exporter_name": f"Other ({len(rest)} countries)",
        column: float(rest[column].sum()),
    }
    return pd.concat([top, pd.DataFrame([other])], ignore_index=True)
