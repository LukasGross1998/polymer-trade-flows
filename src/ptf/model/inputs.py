"""Build the inputs of the transport LP from the clean layer and the assumptions (model layer).

- observed region-to-region flows: `bilateral_flows` summed by region pair
- regional balance: production (assumption) + imports - exports = demand ("apparent
  consumption"); only trade *between* regions counts, trade within a region cancels out
- unit cost per route: production cost of the origin + sea freight (+ tariff, 0 in the base case)

The rest-of-world region is not part of the LP (it has no port and, after mapping all
countries to regions, holds well below 1 % of inter-regional trade). Its trade with the model
regions still counts in their imports and exports.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ptf.model.config import ModelConfig


@dataclass
class ModelInputs:
    """Everything the LP needs, as plain Python dicts keyed by region codes."""

    regions: list[str]
    capacity_t: dict[str, float]
    demand_t: dict[str, float]
    prod_cost_usd_t: dict[str, float]
    freight_usd_t: dict[tuple[str, str], float]
    tariff_usd_t: dict[tuple[str, str], float]
    penalty_usd_t: float

    def unit_cost_usd_t(self, origin: str, dest: str) -> float:
        """Delivered cost of one tonne from `origin` to `dest`."""
        route = (origin, dest)
        return self.prod_cost_usd_t[origin] + self.freight_usd_t[route] + self.tariff_usd_t[route]


def observed_region_flows(flows: pd.DataFrame, year: int) -> pd.DataFrame:
    """Observed trade per region pair in one year, including trade within a region."""
    return (
        flows[flows["year"] == year]
        .groupby(["exporter_region", "importer_region"])["qty_t"]
        .sum()
        .reset_index()
    )


def region_balance(observed: pd.DataFrame, config: ModelConfig) -> pd.DataFrame:
    """Capacity, production, inter-regional imports/exports and demand per model region."""
    between = observed[observed["exporter_region"] != observed["importer_region"]]
    imports = between.groupby("importer_region")["qty_t"].sum()
    exports = between.groupby("exporter_region")["qty_t"].sum()

    rows = []
    for region, assumption in config.regions.items():
        production = assumption.production_t
        imported = float(imports.get(region, 0.0))
        exported = float(exports.get(region, 0.0))
        demand = production + imported - exported
        if demand < 0:
            raise ValueError(
                f"{region}: observed exports ({exported:,.0f} t) exceed assumed production plus "
                f"imports ({production + imported:,.0f} t); check capacity/utilisation"
            )
        rows.append(
            {
                "region": region,
                "capacity_t": assumption.capacity_t,
                "production_t": production,
                "imports_t": imported,
                "exports_t": exported,
                "net_imports_t": imported - exported,
                "demand_t": demand,
            }
        )
    return pd.DataFrame(rows)


def route_costs(distances: pd.DataFrame, config: ModelConfig) -> pd.DataFrame:
    """Unit cost per route = production cost of origin + freight + tariff (base case: 0)."""
    routes = distances[
        distances["origin_region"].isin(config.regions)
        & distances["dest_region"].isin(config.regions)
    ].drop(columns=["passages"], errors="ignore")  # route passages are for the buyer view
    routes["prod_cost_usd_t"] = routes["origin_region"].map(
        {code: r.prod_cost_usd_t for code, r in config.regions.items()}
    )
    routes["freight_usd_t"] = routes["distance_nm"].map(config.freight.cost_usd_t)
    routes["tariff_usd_t"] = 0.0
    routes["unit_cost_usd_t"] = (
        routes["prod_cost_usd_t"] + routes["freight_usd_t"] + routes["tariff_usd_t"]
    )
    return routes.reset_index(drop=True)


def build_inputs(balance: pd.DataFrame, costs: pd.DataFrame, config: ModelConfig) -> ModelInputs:
    """Convert the model-layer tables into the dict structure the LP builder expects."""
    route = list(zip(costs["origin_region"], costs["dest_region"], strict=True))
    return ModelInputs(
        regions=list(balance["region"]),
        capacity_t=dict(zip(balance["region"], balance["capacity_t"], strict=True)),
        demand_t=dict(zip(balance["region"], balance["demand_t"], strict=True)),
        prod_cost_usd_t={code: r.prod_cost_usd_t for code, r in config.regions.items()},
        freight_usd_t=dict(zip(route, costs["freight_usd_t"], strict=True)),
        tariff_usd_t=dict(zip(route, costs["tariff_usd_t"], strict=True)),
        penalty_usd_t=config.penalty_usd_t,
    )


def write_model_layer(
    model_dir: Path, year: int, observed: pd.DataFrame, balance: pd.DataFrame, costs: pd.DataFrame
) -> Path:
    """Store the model inputs as Parquet: data/model/{year}/..."""
    folder = model_dir / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    observed.to_parquet(folder / "observed_region_flows.parquet", index=False)
    balance.to_parquet(folder / "region_balance.parquet", index=False)
    costs.to_parquet(folder / "route_costs.parquet", index=False)
    return folder
